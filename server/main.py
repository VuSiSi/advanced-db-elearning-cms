import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import close_db, connect_db, get_db
from app.middleware.auth import ALGORITHM, SECRET_KEY
from app.routes import auth, courses, pages, stress_test, upload
from app.routes.progress import router as progress_router
from app.routes.stats import router as stats_router


request_counts = {}

RATE_LIMIT = 100
TIME_WINDOW = 60


def get_user_id_from_request(request: Request):
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "", 1)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id") or payload.get("sub") or payload.get("id")
    except JWTError:
        return None


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        current_time = time.time()

        user_id = get_user_id_from_request(request)
        if user_id:
            rate_key = f"user:{user_id}"
        else:
            client_ip = request.client.host if request.client else "unknown"
            rate_key = f"ip:{client_ip}"

        if rate_key in request_counts:
            count, start_time = request_counts[rate_key]

            if current_time - start_time > TIME_WINDOW:
                request_counts[rate_key] = (1, current_time)
            elif count >= RATE_LIMIT:
                m, s = divmod(TIME_WINDOW, 60)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Ban thao tac qua nhanh! Vui long doi"
                            f"{f' {m} phut' if m else ''}"
                            f"{f' {s} giay' if s else ''}"
                            " roi thu lai (429 Too Many Requests)"
                        )
                    },
                )
            else:
                request_counts[rate_key] = (count + 1, start_time)
        else:
            request_counts[rate_key] = (1, current_time)

        response = await call_next(request)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    db = get_db()

    await db.student_progress.create_index(
        [("student_id", 1), ("course_id", 1)],
        name="progress_student_course_idx",
    )
    print("MongoDB indexes created successfully!")

    yield

    await close_db()


app = FastAPI(title="E-Learning CMS", lifespan=lifespan)
app.add_middleware(SimpleRateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(progress_router)
app.include_router(stats_router)
app.include_router(upload.router)
app.include_router(stress_test.router)
app.include_router(pages.router)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start:.4f}s"
    return response
