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

async def _attach_instructor_names(db, courses: list[dict]) -> list[dict]:
    instructor_object_ids = []
    for course in courses:
        instructor_id = course.get("instructor_id")
        if ObjectId.is_valid(instructor_id):
            instructor_object_ids.append(ObjectId(instructor_id))

    if not instructor_object_ids:
        return courses

    users = await db.users.find(
        {"_id": {"$in": instructor_object_ids}},
        {"full_name": 1},
    ).to_list(None)
    name_by_id = {
        str(user["_id"]): user.get("full_name")
        for user in users
        if user.get("full_name")
    }

    for course in courses:
        course["instructor_name"] = name_by_id.get(course.get("instructor_id"))

    return courses

# ─── LIST ALL COURSES (for students & catalog) ─────────────
@router.get("/")
async def list_courses():
    """List all courses (no chapters) — everyone can see."""
    db = get_db()
    courses = await db.courses.find({}, {"chapters": 0}).to_list(100)
    courses = await _attach_instructor_names(db, courses)
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
    courses = await _attach_instructor_names(db, courses)
    return [_course_from_doc(c) for c in courses]


# ─── GET FULL COURSE ───────────────────────────────────────
@router.get("/{course_id}")
async def get_course(course_id: str, token_data: TokenData = Depends(get_current_user)):
    """
    Get full course — any authenticated user can view any course.
    Instructors can view courses they don't own for preview/copy purposes.
    Edit/delete operations still enforce ownership separately.
    """
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")

    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    await _attach_instructor_names(db, [doc])
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
        array_filters=[{"chap.chapter_id": chapter_id}]
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

    if "chapters" in body:
        try:
            order_map = {
                c["chapter_id"]: int(c["order"])
                for c in body["chapters"]
            }
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid chapters reorder payload (400 Bad Request)")

        for chapter in chapters:
            chapter_id = chapter.get("chapter_id")
            if chapter_id in order_map:
                chapter["order"] = order_map[chapter_id]

        chapters.sort(key=lambda c: (c.get("is_deleted", False), c.get("order", 0)))

    if "lessons" in body:
        lessons_payload = body["lessons"]
        if not isinstance(lessons_payload, dict):
            raise HTTPException(status_code=400, detail="Invalid lessons reorder payload (400 Bad Request)")

        active_chapter_ids = {
            ch.get("chapter_id")
            for ch in chapters
            if not ch.get("is_deleted")
        }
        unknown_chapter_ids = set(lessons_payload) - active_chapter_ids
        if unknown_chapter_ids:
            raise HTTPException(status_code=400, detail="Lesson target chapter not found (400 Bad Request)")

        lesson_by_id = {}
        active_lesson_ids = set()
        for chapter in chapters:
            if chapter.get("is_deleted"):
                continue
            for lesson in chapter.get("lessons", []):
                if lesson.get("is_deleted"):
                    continue
                lesson_id = lesson.get("lesson_id")
                lesson_by_id[lesson_id] = lesson
                active_lesson_ids.add(lesson_id)

        requested_by_chapter = {}
        requested_lesson_ids = []
        for chapter_id, lesson_orders in lessons_payload.items():
            if not isinstance(lesson_orders, list):
                raise HTTPException(status_code=400, detail="Invalid lessons reorder payload (400 Bad Request)")
            try:
                ordered_entries = sorted(lesson_orders, key=lambda item: int(item["order"]))
                lesson_ids = [item["lesson_id"] for item in ordered_entries]
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Invalid lessons reorder payload (400 Bad Request)")

            requested_by_chapter[chapter_id] = lesson_ids
            requested_lesson_ids.extend(lesson_ids)

        if len(requested_lesson_ids) != len(set(requested_lesson_ids)):
            raise HTTPException(status_code=400, detail="Duplicate lesson in reorder payload (400 Bad Request)")

        requested_lesson_id_set = set(requested_lesson_ids)
        unknown_lesson_ids = requested_lesson_id_set - active_lesson_ids
        if unknown_lesson_ids:
            raise HTTPException(status_code=400, detail="Lesson not found in this course (400 Bad Request)")

        if requested_lesson_id_set == active_lesson_ids:
            # Complete payload: rebuild active lessons in their target chapters, enabling cross-chapter moves.
            for chapter in chapters:
                if chapter.get("is_deleted"):
                    continue
                chapter_id = chapter.get("chapter_id")
                deleted_lessons = [
                    lesson for lesson in chapter.get("lessons", [])
                    if lesson.get("is_deleted")
                ]
                active_lessons = []
                for order, lesson_id in enumerate(requested_by_chapter.get(chapter_id, [])):
                    lesson = lesson_by_id[lesson_id]
                    lesson["order"] = order
                    active_lessons.append(lesson)
                chapter["lessons"] = active_lessons + deleted_lessons
        else:
            # Partial payload: keep legacy behavior and only reorder lessons inside their current chapters.
            for chapter in chapters:
                chapter_id = chapter.get("chapter_id")
                if chapter_id in requested_by_chapter:
                    order_map = {
                        lesson_id: order
                        for order, lesson_id in enumerate(requested_by_chapter[chapter_id])
                    }
                    for lesson in chapter.get("lessons", []):
                        lesson_id = lesson.get("lesson_id")
                        if lesson_id in order_map:
                            lesson["order"] = order_map[lesson_id]
                    chapter["lessons"].sort(key=lambda l: order_map.get(l.get("lesson_id"), l.get("order", 0)))

    await db.courses.update_one(
        {"_id": oid},
        {"$set": {"chapters": chapters, "updated_at": utc_now()}},
    )
    return {"message": "Reordered successfully"}
