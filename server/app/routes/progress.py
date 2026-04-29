from fastapi import APIRouter, Depends, HTTPException
from app.models import ProgressCreate, LessonCompletion
from app.middleware.auth import get_current_user, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/progress", tags=["progress"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LessonCompleteBody(BaseModel):
    course_id: str
    lesson_id: str
    score: Optional[float] = None  # None for video/doc, float for quiz


# ─────────────────────────────────────────────────────────────
# POST /api/progress/complete  — Student marks lesson complete
# ─────────────────────────────────────────────────────────────
@router.post("/complete")
async def mark_lesson_complete(
    body: LessonCompleteBody,
    token_data: TokenData = Depends(get_current_user),
):
    """
    Mark a lesson as complete. 
    Students can call this.
    Instructor can as well call this for testing.
    """
    if token_data.role not in ["student", "instructor"]:
        raise HTTPException(status_code=403, detail="Access required (403 Forbidden)")
    
    db = get_db()
    student_id = token_data.user_id

    # Guard: validate course exists
    try:
        course = await db.courses.find_one({"_id": ObjectId(body.course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    # Guard: validate lesson exists inside course
    lesson_found = False
    for ch in course.get("chapters", []):
        for ls in ch.get("lessons", []):
            if ls.get("lesson_id") == body.lesson_id:
                lesson_found = True
                break
        if lesson_found:
            break
    if not lesson_found:
        raise HTTPException(status_code=404, detail="Lesson not found in this course (404 Not Found)")

    # Find or create progress document for this student+course
    progress_doc = await db.student_progress.find_one({
        "student_id": student_id,
        "course_id": body.course_id,
    })

    if progress_doc:
        # Check if already completed
        already = any(
            lc["lesson_id"] == body.lesson_id
            for lc in progress_doc.get("lesson_completions", [])
        )
        if already:
            # If score is being updated (re-submit quiz), allow update
            if body.score is not None:
                await db.student_progress.update_one(
                    {
                        "_id": progress_doc["_id"],
                        "lesson_completions.lesson_id": body.lesson_id,
                    },
                    {
                        "$set": {
                            "lesson_completions.$.score": body.score,
                            "lesson_completions.$.completed_at": utc_now(),
                            "last_updated": utc_now(),
                        }
                    },
                )
                return {"message": "Score updated", "already_done": True}
            return {"message": "Lesson already completed", "already_done": True}

        # Push new completion
        completion = {
            "lesson_id": body.lesson_id,
            "completed_at": utc_now(),
            "score": body.score,
        }
        await db.student_progress.update_one(
            {"_id": progress_doc["_id"]},
            {
                "$push": {"lesson_completions": completion},
                "$set":  {"last_updated": utc_now()},
            },
        )
    else:
        # Create new progress document
        completion = {
            "lesson_id": body.lesson_id,
            "completed_at": utc_now(),
            "score": body.score,
        }
        new_doc = {
            "student_id": student_id,
            "course_id":  body.course_id,
            "lesson_completions": [completion],
            "overall_progress_pct": 0.0,
            "last_updated": utc_now(),
        }
        await db.student_progress.insert_one(new_doc)

    # Recalculate overall_progress_pct
    await _recalculate_progress(db, student_id, body.course_id, course)

    return {"message": "Lesson marked as complete!", "already_done": False}


# ─────────────────────────────────────────────────────────────
# GET /api/progress/{course_id}  — Student's own progress
# ─────────────────────────────────────────────────────────────
@router.get("/my/{course_id}")
async def get_my_progress(
    course_id: str,
    token_data: TokenData = Depends(get_current_user),
):
    """Get current user's own progress in a course."""
    db = get_db()
    student_id = token_data.user_id
    return await _build_progress_response(db, student_id, course_id)


# ─────────────────────────────────────────────────────────────
# GET /api/progress/student/{course_id}
# Authenticated student checks their own progress (used by lesson_view.html)
# ─────────────────────────────────────────────────────────────
@router.get("/{course_id}")
async def get_progress(
    course_id: str,
    token_data: TokenData = Depends(get_current_user),
):
    """
    Get authenticated user's progress in a course.
    Used by lesson_view.html progress bar.
    """
    db = get_db()
    return await _build_progress_response(db, token_data.user_id, course_id)


# ─────────────────────────────────────────────────────────────
# GET /api/progress/instructor/{student_id}/{course_id}
# Instructor checks a specific student's progress
# ─────────────────────────────────────────────────────────────
@router.get("/instructor/{student_id}/{course_id}")
async def get_student_progress_by_id(
    student_id: str,
    course_id: str,
    token_data: TokenData = Depends(get_current_user),
):
    """
    Instructor views a student's progress by student_id.
    Only instructors can call this.
    """
    if token_data.role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor access required (403 Forbidden)")
    db = get_db()
    return await _build_progress_response(db, student_id, course_id)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
async def _build_progress_response(db, student_id: str, course_id: str) -> dict:
    # Count total lessons
    try:
        course = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    total = 0
    for ch in course.get("chapters", []):
        if not ch.get("is_deleted"):
            total += len([ls for ls in ch.get("lessons", []) if not ls.get("is_deleted")])

    # Aggregation pipeline — filter out noise values like "V", "", None
    pipeline = [
        {"$match": {"student_id": student_id, "course_id": course_id}},
        {"$unwind": "$lesson_completions"},
        {
            "$match": {
                "lesson_completions.lesson_id": {
                    "$nin": ["V", "v", "", None],
                    "$exists": True,
                }
            }
        },
        {
            "$group": {
                "_id": "$course_id",
                "completed_count": {"$sum": 1},
                "completed_lesson_ids": {"$push": "$lesson_completions.lesson_id"},
                "quiz_scores": {
                    "$push": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$ne": ["$lesson_completions.score", None]},
                                    {"$isNumber": "$lesson_completions.score"},
                                ]
                            },
                            "$lesson_completions.score",
                            "$$REMOVE",
                        ]
                    }
                },
            }
        },
    ]

    cursor = db.student_progress.aggregate(pipeline)
    result_list = await cursor.to_list(length=1)

    if result_list:
        completed_count = result_list[0]["completed_count"]
        completed_ids   = result_list[0]["completed_lesson_ids"]
        quiz_scores     = [s for s in result_list[0].get("quiz_scores", []) if isinstance(s, (int, float))]
    else:
        completed_count = 0
        completed_ids   = []
        quiz_scores     = []

    pct = round((completed_count / total) * 100, 2) if total > 0 else 0
    avg_score = round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else None

    return {
        "student_id": student_id,
        "course_id": course_id,
        "total_lessons_in_course": total,
        "completed_lessons_count": completed_count,
        "completion_percentage": pct,
        "completed_lesson_ids": completed_ids,
        "avg_quiz_score": avg_score,
    }


async def _recalculate_progress(db, student_id: str, course_id: str, course: dict):
    total = 0
    for ch in course.get("chapters", []):
        if not ch.get("is_deleted"):
            total += len([ls for ls in ch.get("lessons", []) if not ls.get("is_deleted")])
    progress_doc = await db.student_progress.find_one({
        "student_id": student_id, "course_id": course_id
    })
    if not progress_doc or total == 0:
        return
    completed = len(progress_doc.get("lesson_completions", []))
    pct = round((completed / total) * 100, 2)
    await db.student_progress.update_one(
        {"_id": progress_doc["_id"]},
        {"$set": {"overall_progress_pct": pct}},
    )
