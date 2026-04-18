from fastapi import APIRouter, Depends, HTTPException
from app.models import CourseCreate, ChapterCreate, Chapter, LessonCreate, Lesson
from app.middleware.auth import get_current_user, require_instructor, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime

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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
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
            "$set":  {"updated_at": datetime.utcnow()},
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return chapter.model_dump()

# DELETE /api/courses/{course_id}/chapters/{chapter_id}

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
    if lesson_in.type == "quiz" and not lesson_in.questions:
        raise HTTPException(status_code=422, detail="questions required for quiz lessons")
    if lesson_in.type == "document" and not lesson_in.content:
        raise HTTPException(status_code=422, detail="content required for document lessons")

    lesson = Lesson(**lesson_in.model_dump())
    result = await db.courses.update_one(
        {"_id": ObjectId(course_id), "chapters.chapter_id": chapter_id},
        {
            "$push": {"chapters.$.lessons": lesson.model_dump()},
            "$set":  {"updated_at": datetime.utcnow()},
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course or chapter not found")
    return lesson.model_dump()

# PUT /api/courses/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}

# DELETE /api/courses/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}

# PUT /api/courses/{course_id}/reorder