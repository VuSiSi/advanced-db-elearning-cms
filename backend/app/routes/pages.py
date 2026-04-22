from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/", include_in_schema=False)
async def index(request: Request):
    """Redirect root to /courses."""
    return RedirectResponse(url="/courses")

@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """Login / Register page."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/courses", include_in_schema=False)
async def courses_page(request: Request):
    """Course catalog page — course creation is handled via modal on this page."""
    return templates.TemplateResponse("courses.html", {"request": request})


@router.get("/courses/new", include_in_schema=False)
async def new_course_redirect(request: Request):
    """
    /courses/new no longer exists as a standalone page.
    Course creation is now a modal on /courses.
    Redirect anyone who lands here (e.g. stale bookmark) back to the list.
    """
    return RedirectResponse(url="/courses")


@router.get("/courses/{course_id}/learn", include_in_schema=False)
async def course_learn_page(course_id: str, request: Request):
    """Student-facing course learning page."""
    return templates.TemplateResponse(
        "course_learn.html",
        {"request": request, "course_id": course_id},
    )


@router.get("/courses/{course_id}", include_in_schema=False)
async def course_detail_page(course_id: str, request: Request):
    """
    Course editor for an existing course.
    course_id is passed to the template so JS can call
    GET /api/courses/{course_id} to load real data.
    """
    return templates.TemplateResponse(
        "course_editor.html",
        {"request": request, "course_id": course_id},
    )


@router.get("/lesson", include_in_schema=False)
async def lesson_view_page(request: Request):
    return templates.TemplateResponse("lesson_view.html", {"request": request})


@router.get("/progress", include_in_schema=False)
async def progress_page(request: Request):
    return templates.TemplateResponse("progress.html", {"request": request})

@router.get("/analytics", include_in_schema=False)
async def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})
