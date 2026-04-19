import asyncio
from fastapi import APIRouter, Depends, HTTPException
from app.middleware.auth import require_instructor, TokenData
from app.database import get_db
from bson import ObjectId

router = APIRouter(prefix="/api/stats", tags=["stats"])

# GET /api/stats/course/{course_id}
@router.get("/course/{course_id}")
async def get_course_stats(
    course_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    """
    Course overview statistics — instructor only.

    Returns:
    - total_students   : number of enrolled students
    - avg_progress_pct : average progress across all students (%)
    - completion_rate  : percentage of students who reached 100% (%)
    - avg_quiz_score   : average quiz score, NULL scores (video/doc) excluded
    - per_lesson_stats : completion count + avg score per lesson

    === MONGODB AGGREGATION PIPELINE ===
    Both pipelines run entirely inside the DB — no raw data pulled into Python.
    This is a core advantage of MongoDB over manual SQL JOINs.
    """
    db = get_db()

    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")

    course = await db.courses.find_one({"_id": oid}, {"title": 1})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # ─────────────────────────────────────────────
    # PIPELINE 1: Course overview
    # Input collection: student_progress
    # ─────────────────────────────────────────────
    overview_pipeline = [
        # Stage 1: Filter to this course only
        {"$match": {"course_id": course_id}},

        # Stage 2: Unwind lesson_completions array into individual documents.

        {"$unwind": {
            "path": "$lesson_completions",
            "preserveNullAndEmptyArrays": True   # keep students with 0 completions
        }},

        # Stage 3: Group back by student — collect per-student progress and quiz scores.
        {"$group": {
            "_id": "$student_id",
            "progress_pct": {"$first": "$overall_progress_pct"},
            "quiz_scores": {
                "$push": "$lesson_completions.score"   # null for video/doc — filtered below
            }
        }},

        # Stage 4: Aggregate across all students
        {"$group": {
            "_id": None,
            "total_students":   {"$sum": 1},
            "avg_progress_pct": {"$avg": "$progress_pct"},
            "completed_count": {
                "$sum": {
                    "$cond": [{"$eq": ["$progress_pct", 100.0]}, 1, 0]
                }
            },
            "all_quiz_scores": {"$push": "$quiz_scores"},
        }},

        # Stage 5: Flatten the array-of-arrays, then filter out null values (null = video/doc lessons with no score).
        {"$project": {
            "_id": 0,
            "total_students":   1,
            "avg_progress_pct": {"$round": ["$avg_progress_pct", 1]},
            "completion_rate": {
                "$round": [
                    {"$multiply": [
                        {"$divide": ["$completed_count", "$total_students"]},
                        100
                    ]},
                    1
                ]
            },
            # Flatten nested arrays, then strip nulls explicitly
            "flat_scores": {
                "$filter": {
                    "input": {
                        "$reduce": {
                            "input": "$all_quiz_scores",
                            "initialValue": [],
                            "in": {"$concatArrays": ["$$value", "$$this"]}
                        }
                    },
                    "as": "s",
                    "cond": {"$ne": ["$$s", None]}   # drop null (video/doc) scores
                }
            }
        }},

        # Stage 6: Compute avg_quiz_score from the clean flat array
        {"$project": {
            "total_students":   1,
            "avg_progress_pct": 1,
            "completion_rate":  1,
            "avg_quiz_score": {
                "$cond": [
                    {"$gt": [{"$size": "$flat_scores"}, 0]},
                    {"$round": [{"$avg": "$flat_scores"}, 1]},
                    None    # no quiz attempted yet
                ]
            }
        }}
    ]

    # ─────────────────────────────────────────────
    # PIPELINE 2: Per-lesson stats
    # Useful for instructors to identify hard / easy lessons
    # ─────────────────────────────────────────────
    per_lesson_pipeline = [
        {"$match": {"course_id": course_id}},
        # No preserveNullAndEmptyArrays here — we only want actual completions
        {"$unwind": "$lesson_completions"},
        {"$group": {
            "_id": "$lesson_completions.lesson_id",
            "completion_count": {"$sum": 1},
            # avg in group ignores null values, so video/doc nulls are excluded
            "avg_score": {
                "$avg": {
                    "$cond": [
                        {"$ne": ["$lesson_completions.score", None]},
                        "$lesson_completions.score",
                        None
                    ]
                }
            }
        }},
        {"$project": {
            "_id": 0,
            "lesson_id":        "$_id",
            "completion_count": 1,
            "avg_score": {
                "$cond": [
                    {"$ne": ["$avg_score", None]},
                    {"$round": ["$avg_score", 1]},
                    None
                ]
            }
        }},
        {"$sort": {"lesson_id": 1}}
    ]

    overview_result, per_lesson_result = await asyncio.gather(
        db.student_progress.aggregate(overview_pipeline).to_list(1),
        db.student_progress.aggregate(per_lesson_pipeline).to_list(1000),
    )

    # No students enrolled yet
    if not overview_result:
        return {
            "course_id":        course_id,
            "course_title":     course["title"],
            "total_students":   0,
            "avg_progress_pct": 0.0,
            "completion_rate":  0.0,
            "avg_quiz_score":   None,
            "per_lesson_stats": []
        }

    stats = overview_result[0]
    return {
        "course_id":        course_id,
        "course_title":     course["title"],
        **stats,
        "per_lesson_stats": per_lesson_result
    }