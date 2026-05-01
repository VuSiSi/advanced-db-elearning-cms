import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import connect_db, close_db, get_db
from app.routes import auth, courses, pages, upload, stress_test
from app.routes.progress import router as progress_router
from app.routes.stats import router as stats_router

from starlette.middleware.base import BaseHTTPMiddleware

ip_request_counts = {}

class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()
        
        # CẤU HÌNH Ở ĐÂY: 100 request trong vòng 60 giây
        RATE_LIMIT = 100
        TIME_WINDOW = 60

        if client_ip in ip_request_counts:
            count, start_time = ip_request_counts[client_ip]
            
            # Đã qua 60 giây -> Xóa án tích, đếm lại từ đầu
            if current_time - start_time > TIME_WINDOW:
                ip_request_counts[client_ip] = (1, current_time)
            
            # Spam quá giới hạn -> Chặn đứng
            elif count >= RATE_LIMIT:
                m, s = divmod(TIME_WINDOW, 60)
                return JSONResponse(
                    status_code=429, 
                    content={"detail": f"Bạn thao tác quá nhanh! Vui lòng đợi{f' {m} phút' if m else ''}{f' {s} giây' if s else ''} rồi thử lại (429 Too Many Requests)"}
                )
            
            # Bình thường -> Tăng số lần đếm lên 1
            else:
                ip_request_counts[client_ip] = (count + 1, start_time)
        else:
            # Người mới lần đầu truy cập
            ip_request_counts[client_ip] = (1, current_time)

        # Cho phép đi tiếp vào trong hệ thống
        response = await call_next(request)
        return response

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
app.add_middleware(SimpleRateLimitMiddleware)

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
app.include_router(upload.router)
app.include_router(stress_test.router)
app.include_router(pages.router)        # pages last (catch-all HTML routes)


# ── Optional: request timing middleware ───────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start:.4f}s"
    return response