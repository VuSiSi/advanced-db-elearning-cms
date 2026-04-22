from fastapi import APIRouter, Depends, HTTPException
from app.models import CourseCreate, ChapterCreate, LessonCreate, LessonBase
from app.middleware.auth import get_current_user, require_instructor, require_student, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _course_from_doc(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
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
        raise HTTPException(status_code=400, detail="Invalid course ID")
    
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Authorization: instructor can only see own course
    if token_data.role == "instructor" and doc.get("instructor_id") != token_data.user_id:
        raise HTTPException(status_code=403, detail="You can only view your own courses")
    
    return _course_from_doc(doc)


# ─── GET LESSON ────────────────────────────────────────────
@router.get("/{course_id}/lessons/{lesson_id}")
async def get_lesson(course_id: str, lesson_id: str, token_data: TokenData = Depends(get_current_user)):
    """Get one lesson by ID (for editor panel or viewing)."""
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Authorization: instructor can only see their own course lessons
    if token_data.role == "instructor" and doc.get("instructor_id") != token_data.user_id:
        raise HTTPException(status_code=403, detail="You can only view your own course lessons")
    
    for chapter in doc.get("chapters", []):
        for lesson in chapter.get("lessons", []):
            if lesson.get("lesson_id") == lesson_id:
                return lesson
    raise HTTPException(status_code=404, detail="Lesson not found")


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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {"$set": {**course_in.model_dump(), "updated_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission to edit it")
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    # Get current chapters count and verify ownership
    doc = await db.courses.find_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {"chapters": 1}
    )
    if not doc:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission to edit it")

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
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {
            "$pull": {"chapters": {"chapter_id": chapter_id}},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Chapter not found")
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    lesson = {
        "lesson_id": str(uuid.uuid4()),
        **lesson_in.model_dump(),
    }

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id, "chapters.chapter_id": chapter_id},
        {
            "$push": {"chapters.$.lessons": lesson},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Chapter not found")
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    # Build the $set payload for the specific nested lesson
    update_fields = {
        f"chapters.$[chap].lessons.$[les].{k}": v
        for k, v in lesson_in.model_dump().items()
        if v is not None
    }
    update_fields["updated_at"] = datetime.utcnow()

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {"$set": update_fields},
        array_filters=[
            {"chap.chapter_id": chapter_id},
            {"les.lesson_id": lesson_id},
        ],
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Lesson not found")
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id, "chapters.chapter_id": chapter_id},
        {
            "$pull": {"chapters.$.lessons": {"lesson_id": lesson_id}},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission")
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Lesson not found")
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
        raise HTTPException(status_code=400, detail="Invalid course ID")

    doc = await db.courses.find_one(
        {"_id": oid, "instructor_id": token_data.user_id}
    )
    if not doc:
        raise HTTPException(status_code=403, detail="Course not found or you don't have permission")

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
        {"$set": {"chapters": chapters, "updated_at": datetime.utcnow()}},
    )
    return {"message": "Reordered successfully"}