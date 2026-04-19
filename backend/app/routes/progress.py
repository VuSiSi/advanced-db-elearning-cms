from fastapi import APIRouter, Depends, HTTPException
from app.models import ProgressCreate, LessonCompletion
from app.middleware.auth import get_current_user, require_student, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/api/progress", tags=["progress"])

def _progress_from_doc(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc

# GET /api/progress/{student_id}/{course_id}
@router.get("/{student_id}/{course_id}")
async def get_progress(
    student_id: str,
    course_id: str,
    token_data: TokenData = Depends(get_current_user)
):
    """Lấy tiến độ của một student trong một course."""
    # Chỉ cho phép student tự xem hoặc instructor xem (tuỳ ý)
    if token_data.role == "student" and token_data.user_id != student_id:
        raise HTTPException(status_code=403, detail="Not your progress")
    db = get_db()
    progress = await db.student_progress.find_one({
        "student_id": student_id,
        "course_id": course_id
    })
    if not progress:
        return {"student_id": student_id, "course_id": course_id, "lesson_completions": [], "overall_progress_pct": 0.0}
    return _progress_from_doc(progress)

# POST /api/progress/complete
@router.post("/complete")
async def mark_lesson_complete(
    student_id: str,
    course_id: str,
    lesson_id: str,
    score: float = None,
    token_data: TokenData = Depends(require_student)
):
    """Đánh dấu một bài học đã hoàn thành, cập nhật overall_progress_pct."""
    if token_data.user_id != student_id:
        raise HTTPException(status_code=403, detail="Cannot update other student's progress")
    
    db = get_db()
    # Lấy course để biết tổng số lessons
    course = await db.courses.find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    total_lessons = 0
    for ch in course.get("chapters", []):
        total_lessons += len(ch.get("lessons", []))
    if total_lessons == 0:
        total_lessons = 1  # tránh chia 0
    
    # Tìm progress document
    progress = await db.student_progress.find_one({
        "student_id": student_id,
        "course_id": course_id
    })
    
    now = datetime.now(timezone.utc)
    completion = {
        "lesson_id": lesson_id,
        "completed_at": now,
        "score": score
    }
    
    if not progress:
        # Tạo mới
        new_progress = {
            "student_id": student_id,
            "course_id": course_id,
            "lesson_completions": [completion],
            "overall_progress_pct": (1 / total_lessons) * 100,
            "last_updated": now
        }
        result = await db.student_progress.insert_one(new_progress)
        return {"id": str(result.inserted_id), **new_progress}
    else:
        # Cập nhật: nếu lesson đã có thì ghi đè hoặc bỏ qua
        existing_completions = progress.get("lesson_completions", [])
        # Tìm và thay thế hoặc thêm mới
        updated = False
        for idx, lc in enumerate(existing_completions):
            if lc["lesson_id"] == lesson_id:
                existing_completions[idx] = completion
                updated = True
                break
        if not updated:
            existing_completions.append(completion)
        
        # Tính lại % hoàn thành
        completed_count = len(set(lc["lesson_id"] for lc in existing_completions))
        overall_pct = (completed_count / total_lessons) * 100
        
        await db.student_progress.update_one(
            {"_id": progress["_id"]},
            {"$set": {
                "lesson_completions": existing_completions,
                "overall_progress_pct": overall_pct,
                "last_updated": now
            }}
        )
        return {"message": "progress updated", "overall_progress_pct": overall_pct}