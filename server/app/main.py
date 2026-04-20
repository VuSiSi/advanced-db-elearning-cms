import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect_db, close_db, get_db
from app.routes import auth, courses, pages
from app.routes.progress import router as progress_router
from app.routes.progress import router_stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    await connect_db()
    db = get_db()

    # Create compound unique index for progress (idempotency + performance)
    await db.student_progress.create_index(
        [("student_id", 1), ("course_id", 1), ("lesson_id", 1)],
        unique=True,
        name="unique_student_course_lesson",
    )
    # Fast lookup for email
    await db.users.create_index("email", unique=True)
    print("✅ MongoDB indexes ready")

    yield

    # ── Shutdown ──
    await close_db()


app = FastAPI(title="E-Learning CMS", lifespan=lifespan)

# ── CORS ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── BENCHMARK MIDDLEWARE ──────────────────────────────────
@app.middleware("http")
async def benchmark_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    print(f"⏱  {request.method} {request.url.path} → {elapsed*1000:.2f}ms")
    response.headers["X-Process-Time"] = f"{elapsed:.4f}"
    return response

# ── STATIC FILES ──────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── ROUTERS ───────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(progress_router)
app.include_router(router_stats)
app.include_router(pages.router)