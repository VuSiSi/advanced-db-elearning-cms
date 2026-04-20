from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.models import CourseCreate, ChapterCreate, Chapter, LessonCreate, Lesson
from app.middleware.auth import get_current_user, require_instructor, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime, timezone

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _course_from_doc(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc

# GET /api/courses
@router.get("/")
async def list_courses():
    # List all courses — public, no auth required.
    db = get_db()
    courses = await db.courses.find({}, {"chapters": 0}).to_list(100)
    return [_course_from_doc(c) for c in courses]

# POST /api/courses
@router.post("/", status_code=201)
async def create_course(
    course_in: CourseCreate,
    token_data: TokenData = Depends(require_instructor),
):
    # Create a course. Instructor only.
    db = get_db()
    doc = {
        **course_in.model_dump(),
        "instructor_id": token_data.user_id,
        "chapters": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.courses.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc

# GET /api/courses/{course_id}
@router.get("/{course_id}")
async def get_course(course_id: str):
    # Get full course structure (chapters + lessons) in ONE query.
    # This is the core MongoDB advantage — no JOINs needed.
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_from_doc(doc)

# PUT /api/courses/{course_id}
@router.put("/{course_id}")
async def update_course(
    course_id: str,
    course_in: CourseCreate,
    token_data: TokenData = Depends(require_instructor),
):
    # Update course title/description. Instructor only.
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")

    result = await db.courses.update_one(
        {"_id": oid, "instructor_id": token_data.user_id},
        {
            "$set": {
                "title": course_in.title,
                "description": course_in.description,
                "updated_at": datetime.now(timezone.utc),
            }
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"message": "Course updated"}

# DELETE /api/courses/{course_id}
@router.delete("/{course_id}", status_code=204)
async def delete_course(
    course_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    # Permanently delete a course and all its embedded chapters/lessons.
    # Also cleans up all related student_progress documents to avoid orphaned data.
    # Instructor only — and only the owning instructor can delete.
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")

    result = await db.courses.delete_one(
        {"_id": oid, "instructor_id": token_data.user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="Course not found or you don't have permission to delete it",
        )

    # Clean up orphaned progress records for the deleted course
    await db.student_progress.delete_many({"course_id": course_id})

# POST /api/courses/{course_id}/chapters
@router.post("/{course_id}/chapters", status_code=201)
async def add_chapter(
    course_id: str,
    chapter_in: ChapterCreate,
    token_data: TokenData = Depends(require_instructor)
):
    # Add a chapter to an existing course. Instructor only.
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")

    chapter = Chapter(**chapter_in.model_dump())
    result = await db.courses.update_one(
        {"_id": oid},
        {
            "$push": {"chapters": chapter.model_dump()},
            "$set":  {"updated_at": datetime.now(timezone.utc)},
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return chapter.model_dump()

# DELETE /api/courses/{course_id}/chapters/{chapter_id}
@router.delete("/{course_id}/chapters/{chapter_id}", status_code=204)
async def delete_chapter(
    course_id: str,
    chapter_id: str,
    token_data: TokenData = Depends(require_instructor)
):
    # Delete a chapter (and all its lessons). Instructor only.
    db = get_db()
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")

    result = await db.courses.update_one(
        {"_id": oid},
        {
            "$pull": {"chapters": {"chapter_id": chapter_id}},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    
# POST /api/courses/{course_id}/chapters/{chapter_id}/lessons
@router.post("/{course_id}/chapters/{chapter_id}/lessons", status_code=201)
async def add_lesson(
    course_id: str,
    chapter_id: str,
    lesson_in: LessonCreate,
    token_data: TokenData = Depends(require_instructor),
):
    # Add a lesson to a chapter. Validates lesson type vs fields.
    db = get_db()

    # Validate: each lesson type must carry its required fields
    if lesson_in.type == "video" and not lesson_in.video_url:
        raise HTTPException(status_code=422, detail="video_url required for video lessons")
    if lesson_in.type == "quiz" and lesson_in.questions is None:
        raise HTTPException(status_code=422, detail="questions required for quiz lessons")
    if lesson_in.type == "document" and not lesson_in.content:
        raise HTTPException(status_code=422, detail="content required for document lessons")

    lesson = Lesson(**lesson_in.model_dump())
    result = await db.courses.update_one(
        {"_id": ObjectId(course_id), "chapters.chapter_id": chapter_id},
        {
            "$push": {"chapters.$.lessons": lesson.model_dump()},
            "$set":  {"updated_at": datetime.now(timezone.utc)},
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course or chapter not found")
    return lesson.model_dump()

# PUT /api/courses/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}
@router.put("/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}")
async def update_lesson(
    course_id: str,
    chapter_id: str,
    lesson_id: str,
    lesson_in: LessonCreate,
    token_data: TokenData = Depends(require_instructor),
):
    # Update a lesson's content. Validates lesson type vs fields.
    db = get_db()

    lesson_dict = lesson_in.model_dump(exclude_unset=True)

    result = await db.courses.update_one(
        {
            "_id": ObjectId(course_id),
            "chapters.chapter_id": chapter_id,
            "chapters.lessons.lesson_id": lesson_id
        },
        {
            "$set": {
                "chapters.$[ch].lessons.$[ls].title": lesson_dict.get("title"),
                "chapters.$[ch].lessons.$[ls].type": lesson_dict.get("type"),
                "chapters.$[ch].lessons.$[ls].video_url": lesson_dict.get("video_url"),
                "chapters.$[ch].lessons.$[ls].duration_seconds": lesson_dict.get("duration_seconds"),
                "chapters.$[ch].lessons.$[ls].content": lesson_dict.get("content"),
                "chapters.$[ch].lessons.$[ls].questions": lesson_dict.get("questions"),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        array_filters=[
            {"ch.chapter_id": chapter_id},
            {"ls.lesson_id": lesson_id}
        ]
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course, chapter, or lesson not found")
    return {"message": "Lesson updated"}

# DELETE /api/courses/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}
@router.delete("/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}", status_code=204)
async def delete_lesson(
    course_id: str,
    chapter_id: str,
    lesson_id: str,
    token_data: TokenData = Depends(require_instructor),
):
    db = get_db()
    result = await db.courses.update_one(
        {
            "_id": ObjectId(course_id), 
            "chapters.chapter_id": chapter_id
        },
        {
            "$pull": {"chapters.$.lessons": {"lesson_id": lesson_id}},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course, chapter, or lesson not found")

# PUT /api/courses/{course_id}/reorder
class ReorderRequest(BaseModel):
    chapters: list

@router.put("/{course_id}/reorder")
async def reorder_course(
    course_id: str,
    reorder_in: ReorderRequest,
    token_data: TokenData = Depends(require_instructor),
):
    # Reorder chapters and lessons based on the provided structure.
    db = get_db()
    result = await db.courses.update_one(
        {"_id": ObjectId(course_id)},
        {
            "$set": {
                "chapters": reorder_in.chapters,
                "updated_at": datetime.now(timezone.utc),
            }
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"message": "Course reordered"}