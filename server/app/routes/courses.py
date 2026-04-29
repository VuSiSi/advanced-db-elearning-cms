from fastapi import APIRouter, Depends, HTTPException
from app.models import CourseCreate, ChapterCreate, LessonCreate, LessonBase
from app.middleware.auth import get_current_user, require_instructor, require_student, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/courses", tags=["courses"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _course_from_doc(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))

    if "chapters" in doc:
        active_chapters = []
        for ch in doc["chapters"]:
            if not ch.get("is_deleted"):
                ch["lessons"] = [ls for ls in ch.get("lessons", []) if not ls.get("is_deleted")]
                active_chapters.append(ch)
        doc["chapters"] = active_chapters

    return doc


# ─── LIST ALL COURSES (for students & catalog) ─────────────
@router.get("/")
async def list_courses():
    """List all courses (no chapters) — everyone can see."""
    db = get_db()
    courses = await db.courses.find({}, {"chapters": 0}).to_list(100)
    return [_course_from_doc(c) for c in courses]


# ─── MY COURSES (for instructor only) ──────────────────────
@router.get("/my")
async def my_courses(token_data: TokenData = Depends(require_instructor)):
    """List only the instructor's own courses."""
    db = get_db()
    courses = await db.courses.find(
        {"instructor_id": token_data.user_id},
        {"chapters": 0}
    ).to_list(100)
    return [_course_from_doc(c) for c in courses]


# ─── GET FULL COURSE ───────────────────────────────────────
@router.get("/{course_id}")
async def get_course(course_id: str, token_data: TokenData = Depends(get_current_user)):
    """
    Get full course with authorization:
    - Instructor can only see their own course
    - Student can see any course
    """
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")
    
    # Authorization: instructor can only see own course
    if token_data.role == "instructor" and doc.get("instructor_id") != token_data.user_id:
        raise HTTPException(status_code=403, detail="You can only view your own courses (403 Forbidden)")
    
    return _course_from_doc(doc)


# ─── GET LESSON ────────────────────────────────────────────
@router.get("/{course_id}/lessons/{lesson_id}")
async def get_lesson(course_id: str, lesson_id: str, token_data: TokenData = Depends(get_current_user)):
    """Get one lesson by ID (for editor panel or viewing)."""
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")
    
    # Authorization: instructor can only see their own course lessons
    if token_data.role == "instructor" and doc.get("instructor_id") != token_data.user_id:
        raise HTTPException(status_code=403, detail="You can only view your own course lessons (403 Forbidden)")
    
    for chapter in doc.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            if lesson.get("lesson_id") == lesson_id:
                return lesson
    raise HTTPException(status_code=404, detail="Lesson not found (404 Not Found)")


# ─── CREATE COURSE ─────────────────────────────────────────
@router.post("/", status_code=201)
async def create_course(
    course_in: CourseCreate,
    token_data: TokenData = Depends(require_instructor),
):
    db = get_db()
    doc = {
        **course_in.model_dump(),
        "instructor_id": token_data.user_id,
        "chapters": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    result = await db.courses.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


# ─── UPDATE COURSE METADATA ────────────────────────────────
@router.put("/{course_id}")
async def update_course(
    course_id: str,
    course_in: CourseCreate,
    token_data: TokenData = Depends(require_instructor),
):
    """Update course — only the owner instructor can update."""
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {"$set": {**course_in.model_dump(), "updated_at": utc_now()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission to edit it (403 Forbidden)")
    return {"message": "Course updated"}


# ─── ADD CHAPTER ──────────────────────────────────────────
@router.post("/{course_id}/chapters", status_code=201)
async def add_chapter(
    course_id: str,
    chapter_in: ChapterCreate,
    token_data: TokenData = Depends(require_instructor),
):
    """Add chapter to course — only the owner instructor can add."""
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    # Get current chapters count and verify ownership
    doc = await db.courses.find_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {"chapters": 1}
    )
    if not doc:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission to edit it (403 Forbidden)")

    order = len(doc.get("chapters", []))
    chapter = {
        "chapter_id": str(uuid.uuid4()),
        "title": chapter_in.title,
        "order": chapter_in.order if chapter_in.order else order,
        "lessons": [],
    }

    result = await db.courses.update_one(
        {"_id": oid},
        {
            "$push": {"chapters": chapter},
            "$set": {"updated_at": utc_now()},
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")
    return {"chapter_id": chapter["chapter_id"], "message": "Chapter added"}


# ─── DELETE CHAPTER ────────────────────────────────────────
@router.delete("/{course_id}/chapters/{chapter_id}")
async def delete_chapter(
    course_id: str,
    chapter_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    """Delete chapter — only the owner instructor can delete."""
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {
            "$set": {
                "chapters.$[chap].is_deleted": True,
                "updated_at": utc_now()
            },
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission (403 Forbidden)")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Chapter not found (404 Not Found)")
    return {"message": "Chapter deleted"}


# ─── ADD LESSON ────────────────────────────────────────────
@router.post("/{course_id}/chapters/{chapter_id}/lessons", status_code=201)
async def add_lesson(
    course_id: str,
    chapter_id: str,
    lesson_in: LessonCreate,
    token_data: TokenData = Depends(require_instructor),
):
    """Add lesson — only the owner instructor can add."""
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    lesson = {
        "lesson_id": str(uuid.uuid4()),
        **lesson_in.model_dump(),
    }

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id, "chapters.chapter_id": chapter_id},
        {
            "$push": {"chapters.$.lessons": lesson},
            "$set": {"updated_at": utc_now()},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission (403 Forbidden)")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Chapter not found (404 Not Found)")
    return {"lesson_id": lesson["lesson_id"], "message": "Lesson added"}


# ─── UPDATE LESSON ─────────────────────────────────────────
@router.put("/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}")
async def update_lesson(
    course_id: str,
    chapter_id: str,
    lesson_id: str,
    lesson_in: LessonCreate,
    token_data: TokenData = Depends(require_instructor),
):
    """Update lesson — only the owner instructor can update."""
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    # Build the $set payload for the specific nested lesson
    update_fields = {
        f"chapters.$[chap].lessons.$[les].{k}": v
        for k, v in lesson_in.model_dump(exclude_unset=True).items()
    }
    update_fields["updated_at"] = utc_now()

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {"$set": update_fields},
        array_filters=[
            {"chap.chapter_id": chapter_id},
            {"les.lesson_id": lesson_id},
        ],
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission (403 Forbidden)")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Lesson not found (404 Not Found)")
    return {"message": "Lesson updated"}


# ─── DELETE LESSON ─────────────────────────────────────────
@router.delete("/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}")
async def delete_lesson(
    course_id: str,
    chapter_id: str,
    lesson_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    """Delete lesson — only the owner instructor can delete."""
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id, "chapters.chapter_id": chapter_id},
        {
            "$set": {
                "chapters.$[chap].lessons.$[les].is_deleted": True,
                "updated_at": utc_now()
            }
        },
        array_filters=[
            {"chap.chapter_id": chapter_id},
            {"les.lesson_id": lesson_id},
        ],
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission (403 Forbidden)")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Lesson not found (404 Not Found)")
    return {"message": "Lesson deleted"}


# ─── REORDER ───────────────────────────────────────────────
@router.put("/{course_id}/reorder")
async def reorder_course(
    course_id: str,
    body: dict,
    token_data: TokenData = Depends(require_instructor),
):
    """
    Reorder chapters and lessons — only owner can reorder.
    body = {
      "chapters": [{"chapter_id": "...", "order": 0}, ...],
      "lessons": {"chapter_id": [{"lesson_id": "...", "order": 0}, ...]}
    }
    """
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    doc = await db.courses.find_one(
        {"_id": oid, "instructor_id": token_data.user_id}
    )
    if not doc:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission (403 Forbidden)")

    chapters = doc.get("chapters", [])

    # Reorder chapters
    if "chapters" in body:
        order_map = {c["chapter_id"]: c["order"] for c in body["chapters"]}
        chapters.sort(key=lambda c: order_map.get(c["chapter_id"], c.get("order", 0)))

    # Reorder lessons within chapters
    if "lessons" in body:
        for ch in chapters:
            ch_id = ch["chapter_id"]
            if ch_id in body["lessons"]:
                order_map = {l["lesson_id"]: l["order"] for l in body["lessons"][ch_id]}
                ch["lessons"].sort(key=lambda l: order_map.get(l["lesson_id"], l.get("order", 0)))

    await db.courses.update_one(
        {"_id": oid},
        {"$set": {"chapters": chapters, "updated_at": utc_now()}},
    )
    return {"message": "Reordered successfully"}
