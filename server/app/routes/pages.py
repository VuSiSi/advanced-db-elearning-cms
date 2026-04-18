from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.database import get_db

router = APIRouter(tags=["pages"], include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


def _course_from_doc(doc: dict) -> dict:
    doc["id"] = str(doc.pop("_id"))
    return doc


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/courses", response_class=HTMLResponse)
async def courses_page(request: Request):
    return templates.TemplateResponse("courses.html", {"request": request})


@router.get("/courses/{course_id}", response_class=HTMLResponse)
async def course_editor_page(request: Request, course_id: str):
    db = get_db()
    try:
        doc = await db.courses.find_one({"_id": ObjectId(course_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid course ID")
    if not doc:
        raise HTTPException(status_code=404, detail="Course not found")

    course = _course_from_doc(doc)
    return templates.TemplateResponse(
        "course_editor.html",
        {"request": request, "course": course},
    )
