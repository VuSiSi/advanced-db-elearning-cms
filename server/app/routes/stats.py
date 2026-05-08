from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.middleware.auth import TokenData, require_instructor


router = APIRouter(prefix="/api/stats", tags=["analytics"])


@router.get("/course/{course_id}")
async def get_course_stats(
    course_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    db = get_db()

    try:
        course = await db.courses.find_one({"_id": ObjectId(course_id), "is_deleted": {"$ne": True}})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not course:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    all_lessons = []
    for chapter in course.get("chapters", []):
        if chapter.get("is_deleted"):
            continue
        for lesson in chapter.get("lessons", []):
            if not lesson.get("is_deleted"):
                all_lessons.append(lesson)

    total_lessons = len(all_lessons)

    pipeline_students = [
        {"$match": {"course_id": course_id, "is_deleted": {"$ne": True}}},
        {"$unwind": "$lesson_completions"},
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
                "lesson_completions": {
                    "$push": {
                        "lesson_id": "$lesson_completions.lesson_id",
                        "completed_at": "$lesson_completions.completed_at",
                        "score": "$lesson_completions.score",
                    }
                },
                "quiz_scores": {
                    "$push": {
                        "$cond": [
                            {"$ne": ["$lesson_completions.score", None]},
                            "$lesson_completions.score",
                            "$$REMOVE",
                        ]
                    }
                },
            }
        },
    ]

    cursor = db.student_progress.aggregate(pipeline_students)
    student_results = await cursor.to_list(length=None)

    object_ids = []
    for result in student_results:
        try:
            object_ids.append(ObjectId(result["_id"]))
        except Exception:
            continue

    users_cursor = db.users.find({"_id": {"$in": object_ids}, "role": "student", "is_deleted": {"$ne": True}})
    users_list = await users_cursor.to_list(length=None)
    id_to_user = {
        str(user["_id"]): {
            "full_name": user.get("full_name") or user.get("email", "Unknown student"),
            "email": user.get("email", "unknown"),
        }
        for user in users_list
    }
    student_results = [
        result
        for result in student_results
        if result["_id"] in id_to_user
    ]

    lesson_completion_map = {
        lesson["lesson_id"]: 0
        for lesson in all_lessons
        if lesson.get("lesson_id")
    }
    lesson_students_map = {
        lesson["lesson_id"]: []
        for lesson in all_lessons
        if lesson.get("lesson_id")
    }
    all_quiz_scores = []
    students_summary = []

    for result in student_results:
        student_id = result["_id"]
        student = id_to_user.get(
            student_id,
            {"full_name": "Unknown student", "email": "unknown"},
        )

        completed_lesson_ids_for_student = set()
        for completion in result.get("lesson_completions", []):
            lesson_id = completion.get("lesson_id")
            if lesson_id not in lesson_completion_map:
                continue
            if lesson_id in completed_lesson_ids_for_student:
                continue

            completed_lesson_ids_for_student.add(lesson_id)
            lesson_completion_map[lesson_id] += 1
            lesson_students_map[lesson_id].append(
                {
                    "student_id": student_id,
                    "full_name": student["full_name"],
                    "email": student["email"],
                    "completed_at": completion.get("completed_at"),
                }
            )

        scores = [
            score
            for score in result.get("quiz_scores", [])
            if isinstance(score, (int, float))
        ]
        all_quiz_scores.extend(scores)

        completed_count = len(completed_lesson_ids_for_student)
        students_summary.append(
            {
                "student_id": student_id,
                "full_name": student["full_name"],
                "email": student["email"],
                "completed": completed_count,
                "completion_pct": (
                    round((completed_count / total_lessons) * 100, 1)
                    if total_lessons
                    else 0
                ),
            }
        )

    total_students = len(student_results)
    avg_completion_pct = (
        round(sum(s["completion_pct"] for s in students_summary) / total_students, 1)
        if total_students
        else 0
    )
    avg_quiz_score = (
        round(sum(all_quiz_scores) / len(all_quiz_scores), 1)
        if all_quiz_scores
        else None
    )

    per_lesson_stats = []
    for lesson in all_lessons:
        lesson_id = lesson.get("lesson_id")
        per_lesson_stats.append(
            {
                "lesson_id": lesson_id,
                "title": lesson.get("title") or "Untitled lesson",
                "type": lesson.get("type") or "lesson",
                "completed_count": lesson_completion_map.get(lesson_id, 0),
                "completed_students": lesson_students_map.get(lesson_id, []),
            }
        )

    return {
        "course_id": course_id,
        "course_title": course.get("title"),
        "total_lessons": total_lessons,
        "total_students": total_students,
        "avg_completion_pct": avg_completion_pct,
        "avg_quiz_score": avg_quiz_score,
        "lesson_stats": lesson_completion_map,
        "per_lesson_stats": per_lesson_stats,
        "students": students_summary,
        "tech_note": "Powered by MongoDB Aggregation Pipeline with edge-case filtering",
    }
