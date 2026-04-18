from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import close_db, connect_db
from app.routes import auth, courses, pages, progress


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="E-Learning CMS",
    description="Course Management System — Advanced Database BTL",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files (CSS, JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(progress.router)


@app.get("/")
async def root():
    return {"message": "E-Learning CMS API is running"}
