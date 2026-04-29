from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db

router = APIRouter(tags=["pages"], include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


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


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("courses.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/courses", response_class=HTMLResponse)
async def courses_page(request: Request):
    return templates.TemplateResponse("courses.html", {"request": request})


@router.get("/courses/new", response_class=HTMLResponse)
async def new_course_page(request: Request):
    return templates.TemplateResponse("courses.html", {"request": request})


@router.get("/courses/{course_id}", response_class=HTMLResponse)
async def course_page(request: Request, course_id: str):
    """
    Role-based routing:
    - Instructor (owns course) → course_editor.html
    - Student / guest → lesson_view.html (no lesson selected)
    Client JS will redirect based on JWT role.
    """
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    course = _course_from_doc(doc)
    # We render both templates and let client-side JS decide based on role.
    # The page JS will redirect to /courses/{id}/lessons/{first_lesson} for students.
    return templates.TemplateResponse(
        "course_landing.html",
        {"request": request, "course": course},
    )


@router.get("/courses/{course_id}/edit", response_class=HTMLResponse)
async def course_editor_page(request: Request, course_id: str):
    """Instructor-only course editor."""
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    course = _course_from_doc(doc)
    return templates.TemplateResponse(
        "course_editor.html",
        {"request": request, "course": course},
    )


@router.get("/courses/{course_id}/lessons/{lesson_id}", response_class=HTMLResponse)
async def lesson_view_page(request: Request, course_id: str, lesson_id: str):
    """Student lesson viewer."""
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    course = _course_from_doc(doc)

    # Find the lesson
    lesson = None
    for ch in course.get("chapters", []):
        for ls in ch.get("lessons", []):
            if ls.get("lesson_id") == lesson_id:
                lesson = ls
                break
        if lesson:
            break

    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found (404 Not Found)")

    return templates.TemplateResponse(
        "lesson_view.html",
        {"request": request, "course": course, "lesson": lesson},
    )


@router.get("/analytics/{course_id}", response_class=HTMLResponse)
async def analytics_page(request: Request, course_id: str):
    """Instructor analytics dashboard."""
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID (400 Bad Request)")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found (404 Not Found)")

    course = _course_from_doc(doc)
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request, "course": course},
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    return templates.TemplateResponse("stats.html", {"request": request})


@router.get("/my-progress", response_class=HTMLResponse)
async def my_progress_page(request: Request):
    return templates.TemplateResponse("my_progress.html", {"request": request})
