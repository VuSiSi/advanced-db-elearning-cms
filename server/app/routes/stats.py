"""
GET /api/stats/course/{id} — Instructor analytics via MongoDB Aggregation Pipeline
Day 4: Aggregation + Polish
"""
from fastapi import APIRouter, Depends, HTTPException
from app.middleware.auth import require_instructor, TokenData
from app.database import get_db
from bson import ObjectId

router = APIRouter(prefix="/api/stats", tags=["analytics"])


@router.get("/course/{course_id}")
async def get_course_stats(
    course_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    """
    Full analytics for a course:
    - total students, avg completion %, avg quiz score
    - per-lesson completion counts
    - per-student progress summary
    - Filters out "V" / empty / null lesson_ids (edge-case cleaner)
    """
    db = get_db()

    # 1. Fetch course structure
    try:
        course = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Build flat lesson list
    all_lessons = []
    for ch in course.get("chapters", []):
        if ch.get("is_deleted"): 
            continue
        for ls in ch.get("lessons", []):
            if ls.get("is_deleted"): 
                continue
            all_lessons.append(ls)
    total_lessons = len(all_lessons)

    # 2. Aggregation: per-student completion counts
    pipeline_students = [
        {"$match": {"course_id": course_id}},
        {"$unwind": "$lesson_completions"},
        # Filter garbage lesson IDs
        {
            "$match": {
                "lesson_completions.lesson_id": {"$nin": ["V", "v", "", None]}
            }
        },
        {
            "$group": {
                "_id": "$student_id",
                "completed_count": {"$sum": 1},
                "completed_lesson_ids": {"$push": "$lesson_completions.lesson_id"},
                "quiz_scores": {
                    "$push": {
                        "$cond": [
                            {"$ne": ["$lesson_completions.score", None]},
                            "$lesson_completions.score",
                            "$$REMOVE"
                        ]
                    }
                },
            }
        },
    ]

    cursor = db.student_progress.aggregate(pipeline_students)
    student_results = await cursor.to_list(length=None)

    # 3. Resolve student emails
    student_ids = [r["_id"] for r in student_results]
    users_cursor = db.users.find(
        {"_id": {"$in": [ObjectId(sid) for sid in student_ids if sid]}}
    )
    users_list = await users_cursor.to_list(length=None)
    id_to_email = {str(u["_id"]): u.get("email", "unknown") for u in users_list}

    # 4. Build per-lesson completion map
    lesson_completion_map = {ls["lesson_id"]: 0 for ls in all_lessons}
    all_quiz_scores = []

    students_summary = []
    for r in student_results:
        sid = r["_id"]
        count = r["completed_count"]
        for lid in r.get("completed_lesson_ids", []):
            if lid in lesson_completion_map:
                lesson_completion_map[lid] += 1

        scores = [s for s in r.get("quiz_scores", []) if isinstance(s, (int, float))]
        all_quiz_scores.extend(scores)

        students_summary.append({
            "student_id": sid,
            "email": id_to_email.get(sid, "unknown"),
            "completed": count,
            "completion_pct": round((count / total_lessons) * 100, 1) if total_lessons else 0,
        })

    # 5. Compute aggregates
    total_students = len(student_results)
    avg_completion_pct = (
        round(sum(s["completion_pct"] for s in students_summary) / total_students, 1)
        if total_students else 0
    )
    avg_quiz_score = (
        round(sum(all_quiz_scores) / len(all_quiz_scores), 1)
        if all_quiz_scores else None
    )

    return {
        "course_id": course_id,
        "course_title": course.get("title"),
        "total_lessons": total_lessons,
        "total_students": total_students,
        "avg_completion_pct": avg_completion_pct,
        "avg_quiz_score": avg_quiz_score,
        "lesson_stats": lesson_completion_map,         # {lesson_id: count}
        "students": students_summary,
        "tech_note": "Powered by MongoDB Aggregation Pipeline with edge-case filtering",
    }