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
    Thống kê tổng quan cho một khoá học — instructor only.

    Trả về:
    - total_students   : số học viên đã enroll
    - avg_progress_pct : tiến độ trung bình (%)
    - completion_rate  : tỉ lệ học viên hoàn thành 100% (%)
    - avg_quiz_score   : điểm quiz trung bình (loại bỏ NULL — video/doc)
    - per_lesson_stats : số lượt hoàn thành + điểm TB cho từng bài quiz

    === MONGODB AGGREGATION PIPELINE ===
    Pipeline này chạy hoàn toàn trong DB, không kéo raw data lên Python.
    Đây là điểm mạnh cốt lõi của MongoDB so với SQL JOIN thủ công.
    """
    db = get_db()

    # Xác nhận course tồn tại
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")

    course = await db.courses.find_one({"_id": oid}, {"title": 1})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # ─────────────────────────────────────────────
    # PIPELINE 1: Tổng quan khoá học
    # Input collection: student_progress
    # ─────────────────────────────────────────────
    overview_pipeline = [
        # Stage 1: Lọc chỉ lấy progress của course này
        {"$match": {"course_id": course_id}},

        # Stage 2: Giải nén mảng lesson_completions thành từng document riêng
        # (để tính điểm quiz từng bài)
        {"$unwind": {
            "path": "$lesson_completions",
            "preserveNullAndEmpty": True   # giữ lại student chưa học bài nào
        }},

        # Stage 3: Nhóm lại theo student_id
        # Tính: tiến độ, đếm quiz có điểm (loại bỏ NULL của video/doc)
        {"$group": {
            "_id": "$student_id",
            "progress_pct":  {"$first": "$overall_progress_pct"},
            "quiz_scores":   {
                "$push": {
                    "$cond": [
                        {"$and": [
                            {"$gt": ["$lesson_completions.score", None]},
                            {"$gte": ["$lesson_completions.score", 0]},
                            {"$lte": ["$lesson_completions.score", 100]},
                        ]},
                        "$lesson_completions.score",
                        "$$REMOVE"   # bỏ qua video/doc (score = null)
                    ]
                }
            }
        }},

        # Stage 4: Tính toán tổng hợp trên toàn bộ học viên
        {"$group": {
            "_id": None,
            "total_students":   {"$sum": 1},
            "avg_progress_pct": {"$avg": "$progress_pct"},
            "completed_count":  {
                "$sum": {
                    "$cond": [{"$eq": ["$progress_pct", 100.0]}, 1, 0]
                }
            },
            # $avg trên array rỗng trả về null — được xử lý ở bước sau
            "all_quiz_scores":  {"$push": "$quiz_scores"},
        }},

        # Stage 5: Flatten mảng-của-mảng quiz scores, tính completion_rate
        {"$project": {
            "_id": 0,
            "total_students":   1,
            "avg_progress_pct": {"$round": ["$avg_progress_pct", 1]},
            "completion_rate":  {
                "$round": [
                    {"$multiply": [
                        {"$divide": ["$completed_count", "$total_students"]},
                        100
                    ]},
                    1
                ]
            },
            # Giải nén mảng lồng nhau thành 1 mảng phẳng
            "flat_scores": {
                "$reduce": {
                    "input": "$all_quiz_scores",
                    "initialValue": [],
                    "in": {"$concatArrays": ["$$value", "$$this"]}
                }
            }
        }},

        # Stage 6: Tính avg_quiz_score từ mảng phẳng
        {"$project": {
            "total_students":   1,
            "avg_progress_pct": 1,
            "completion_rate":  1,
            "avg_quiz_score": {
                "$cond": [
                    {"$gt": [{"$size": "$flat_scores"}, 0]},
                    {"$round": [{"$avg": "$flat_scores"}, 1]},
                    None   # chưa có quiz nào được làm
                ]
            }
        }}
    ]

    # ─────────────────────────────────────────────
    # PIPELINE 2: Thống kê từng bài học (per-lesson)
    # Hữu ích cho instructor biết bài nào khó / dễ
    # ─────────────────────────────────────────────
    per_lesson_pipeline = [
        {"$match": {"course_id": course_id}},
        {"$unwind": "$lesson_completions"},
        {"$group": {
            "_id": "$lesson_completions.lesson_id",
            "completion_count": {"$sum": 1},
            "avg_score": {
                "$avg": {
                    "$cond": [
                        {"$gt": ["$lesson_completions.score", None]},
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
                    {"$gt": ["$avg_score", None]},
                    {"$round": ["$avg_score", 1]},
                    None
                ]
            }
        }},
        {"$sort": {"lesson_id": 1}}
    ]

    # Chạy cả 2 pipeline song song
    overview_result = await db.student_progress.aggregate(
        overview_pipeline
    ).to_list(1)

    per_lesson_result = await db.student_progress.aggregate(
        per_lesson_pipeline
    ).to_list(1000)

    # Nếu chưa có học viên nào
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