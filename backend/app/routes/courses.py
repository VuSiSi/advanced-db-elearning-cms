from fastapi import APIRouter, Depends, HTTPException
from app.models import CourseCreate, Course
from app.middleware.auth import get_current_user, require_instructor, TokenData
from app.database import get_db
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _course_from_doc(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("/")
async def list_courses():
    """List all courses — public, no auth required."""
    db = get_db()
    courses = await db.courses.find({}, {"chapters": 0}).to_list(100)
    return [_course_from_doc(c) for c in courses]


@router.get("/{course_id}")
async def get_course(course_id: str):
    """
    Get full course structure (chapters + lessons) in ONE query.
    This is the core MongoDB advantage — no JOINs needed.
    """
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_from_doc(doc)


@router.post("/", status_code=201)
async def create_course(
    course_in: CourseCreate,
    token_data: TokenData = Depends(require_instructor),
):
    """Create a course. Instructor only."""
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