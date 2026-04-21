import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect_db, close_db, get_db
from app.routes import auth, courses, pages
from app.routes.progress import router as progress_router
from app.routes.stats import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    await connect_db()
    db = get_db()

    # Create compound index for progress (idempotency + performance)
    await db.student_progress.create_index(
        [("student_id", 1), ("course_id", 1)],
        name="progress_student_course_idx"
    )
    print("✅ MongoDB indexes created successfully!")

    yield  # ← app runs here

    # ── Shutdown ──
    await close_db()


app = FastAPI(title="E-Learning CMS", lifespan=lifespan)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ───────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Routers ────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(progress_router)
app.include_router(stats_router)
app.include_router(pages.router)   # pages last (catch-all HTML routes)


# ── Optional: request timing middleware ───────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start:.4f}s"
    return response