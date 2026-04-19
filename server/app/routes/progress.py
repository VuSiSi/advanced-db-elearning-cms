from fastapi import APIRouter, Depends, HTTPException
from app.models import ProgressCreate, LessonCompletion
from app.middleware.auth import get_current_user, require_student, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/api/progress", tags=["progress"])


# ─────────────────────────────────────────────────────────────
# POST /api/progress/complete  — Student marks lesson complete
# ─────────────────────────────────────────────────────────────
class LessonCompleteRequest:
    def __init__(self, course_id: str, lesson_id: str):
        self.course_id = course_id
        self.lesson_id = lesson_id


from pydantic import BaseModel


class LessonCompleteBody(BaseModel):
    course_id: str
    lesson_id: str


@router.post("/complete")
async def mark_lesson_complete(
    body: LessonCompleteBody,
    token_data: TokenData = Depends(get_current_user),
):
    """Mark a lesson as complete for the current student."""
    db = get_db()
    student_id = token_data.user_id

    # Guard: validate course exists
    try:
        course = await db.courses.find_one({"_id": ObjectId(body.course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

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
        raise HTTPException(status_code=404, detail="Lesson not found in this course")

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
            return {"message": "Lesson already completed", "already_done": True}

        # Push new completion
        completion = LessonCompletion(lesson_id=body.lesson_id)
        await db.student_progress.update_one(
            {"_id": progress_doc["_id"]},
            {
                "$push": {"lesson_completions": completion.model_dump()},
                "$set":  {"last_updated": datetime.utcnow()},
            },
        )
    else:
        # Create new progress document
        completion = LessonCompletion(lesson_id=body.lesson_id)
        new_doc = {
            "student_id": student_id,
            "course_id":  body.course_id,
            "lesson_completions": [completion.model_dump()],
            "overall_progress_pct": 0.0,
            "last_updated": datetime.utcnow(),
        }
        await db.student_progress.insert_one(new_doc)

    # Recalculate overall_progress_pct
    await _recalculate_progress(db, student_id, body.course_id, course)

    return {"message": "Lesson marked as complete!", "already_done": False}


# ─────────────────────────────────────────────────────────────
# GET /api/progress/{course_id}  — Student's own progress
# ─────────────────────────────────────────────────────────────
@router.get("/{course_id}")
async def get_my_progress(
    course_id: str,
    token_data: TokenData = Depends(get_current_user),
):
    """Get current student's progress in a course."""
    db = get_db()
    student_id = token_data.user_id
    return await _build_progress_response(db, student_id, course_id)


# ─────────────────────────────────────────────────────────────
# GET /api/progress/{student_email}/{course_id}
# Instructor-facing: lookup by student email
# ─────────────────────────────────────────────────────────────
@router.get("/{student_email}/{course_id}")
async def get_student_progress(student_email: str, course_id: str):
    """
    Get a student's progress by email (no auth guard — used by lesson_view.html
    which checks auth on the client).  Returns progress data for the progress bar.
    """
    db = get_db()

    # resolve student_id from email
    user = await db.users.find_one({"email": student_email})
    if not user:
        return {
            "student": student_email,
            "course_id": course_id,
            "total_lessons_in_course": 0,
            "completed_lessons_count": 0,
            "completion_percentage": "0%",
            "completed_lesson_ids": [],
        }

    return await _build_progress_response(db, str(user["_id"]), course_id)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
async def _build_progress_response(db, student_id: str, course_id: str) -> dict:
    # Count total lessons
    try:
        course = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    total = sum(
        len(ch.get("lessons", []))
        for ch in course.get("chapters", [])
    )

    # Aggregation pipeline — same pattern as main.py but using student_id
    pipeline = [
        {"$match": {"student_id": student_id, "course_id": course_id}},
        {"$unwind": "$lesson_completions"},
        {
            "$match": {
                "lesson_completions.lesson_id": {"$nin": ["V", "v", "", None]}
            }
        },
        {
            "$group": {
                "_id": "$course_id",
                "completed_count": {"$sum": 1},
                "completed_lesson_ids": {"$push": "$lesson_completions.lesson_id"},
            }
        },
    ]

    cursor = db.student_progress.aggregate(pipeline)
    result_list = await cursor.to_list(length=1)

    if result_list:
        completed_count = result_list[0]["completed_count"]
        completed_ids   = result_list[0]["completed_lesson_ids"]
    else:
        completed_count = 0
        completed_ids   = []

    pct = round((completed_count / total) * 100, 2) if total > 0 else 0

    return {
        "student_id": student_id,
        "course_id": course_id,
        "total_lessons_in_course": total,
        "completed_lessons_count": completed_count,
        "completion_percentage": f"{pct}%",
        "completed_lesson_ids": completed_ids,
    }


async def _recalculate_progress(db, student_id: str, course_id: str, course: dict):
    total = sum(len(ch.get("lessons", [])) for ch in course.get("chapters", []))
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