import os
from dotenv import load_dotenv, find_dotenv
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv
from typing import List, Literal
from bson import ObjectId
from pydantic import Field
import uuid

# 1. LOAD BIẾN MÔI TRƯỜNG
load_dotenv()
env_path = find_dotenv()
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

# 2. KẾT NỐI MONGODB
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
users_collection = db.get_collection("users")

# 3. MODELS
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

# 4. BẢO MẬT & JWT
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 5. API ENDPOINTS
app = FastAPI(title="E-Learning API")

import time
from fastapi import Request

# ==========================================
# MIDDLEWARE: ĐO THỜI GIAN CHẠY API (BENCHMARK)
# ==========================================
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # In ra Terminal con số để cậu chụp ảnh bỏ vào Báo cáo
    print(f"⏱️ [BENCHMARK] API: {request.method} {request.url.path} | Thời gian: {process_time:.4f} giây")
    
    # Gắn vào Header trả về cho Frontend
    response.headers["X-Process-Time"] = str(process_time)
    return response

# ==========================================
# KHỞI TẠO TỰ ĐỘNG (CHẠY KHI BẬT SERVER)
# ==========================================

@app.on_event("startup")
async def setup_mongodb_indexes():
    # 1. Index cho bảng User: Đảm bảo email tìm cực nhanh và không bao giờ đăng ký trùng
    await users_collection.create_index("email", unique=True)
    
    # 2. Index cho bảng Progress (Giải quyết cả Performance & Edge Case Duplicate)
    # Gom 3 cột (email + course_id + lesson_id) thành 1 cái Index Độc Nhất
    await progress_collection.create_index(
        [("email", 1), ("course_id", 1), ("lesson_id", 1)],
        unique=True,
        name="unique_progress_index"
    )
    print("✅ Đã tạo MongoDB Indexes thành công để tối ưu tốc độ!")

@app.post("/register")
async def register(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")
    
    hashed_password = get_password_hash(user.password)
    new_user = {
        "email": user.email,
        "full_name": user.full_name,
        "password": hashed_password
    }
    await users_collection.insert_one(new_user)
    return {"message": "Đăng ký thành công!", "email": user.email}

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db_user = await users_collection.find_one({"email": form_data.username})
    if not db_user:
        raise HTTPException(status_code=400, detail="Sai email hoặc mật khẩu")
    
    if not verify_password(form_data.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Sai mật khẩu")
    
    access_token = create_access_token(data={"sub": db_user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
async def lay_thong_tin_cua_toi(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token bị lỗi hoặc hết hạn")
    
    user = await users_collection.find_one({"email": email})
    return {
        "xin_chao": user["full_name"],
        "email": user["email"]
    }
    
    
    
# ==========================================
# PHẦN SCHEMA: VALIDATE DỮ LIỆU ĐẦU VÀO
# ==========================================

# 1. Lesson (Bài học)
class Lesson(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())) # Tự động sinh ID 
    title: str
    # ✅ YÊU CẦU 3: VALIDATE LESSON TYPE (Chỉ nhận "video" hoặc "quiz", sai sẽ báo lỗi 422 ngay lập tức)
    type: Literal["video", "quiz"] 
    content_url: str
    duration_minutes: int

# 2. Chapter (Chương)
class Chapter(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    lessons: List[Lesson] = [] # Mặc định là mảng trống

# 3. Course (Khóa học)
class CourseCreate(BaseModel):
    title: str
    description: str

courses_collection = db.get_collection("courses") # Collection chứa Khóa học

# ==========================================
# PHẦN API: THÊM VÀ LẤY DỮ LIỆU NESTED
# ==========================================

# (API mồi) Tạo khóa học rỗng để lấy course_id
@app.post("/courses")
async def create_course(course: CourseCreate):
    new_course = course.model_dump()
    new_course["chapters"] = [] # Tạo mảng chapters trống
    result = await courses_collection.insert_one(new_course)
    return {"message": "Tạo course thành công", "course_id": str(result.inserted_id)}


# ✅ YÊU CẦU 1: POST chapter vào course
@app.post("/courses/{course_id}/chapters")
async def add_chapter(course_id: str, chapter: Chapter):
    # Dùng lệnh $push của MongoDB để nhét data vào mảng chapters
    result = await courses_collection.update_one(
        {"_id": ObjectId(course_id)},
        {"$push": {"chapters": chapter.model_dump()}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy Course")
    return {"message": "Thêm Chapter thành công", "chapter_id": chapter.id}


# ✅ YÊU CẦU 2: POST lesson vào chapter
@app.post("/courses/{course_id}/chapters/{chapter_id}/lessons")
async def add_lesson(course_id: str, chapter_id: str, lesson: Lesson):
    # Cực hay: Dùng arrayFilters để tìm đúng chapter bên trong mảng chapters, rồi $push lesson vào
    result = await courses_collection.update_one(
        {"_id": ObjectId(course_id)},
        {"$push": {"chapters.$[chap].lessons": lesson.model_dump()}},
        array_filters=[{"chap.id": chapter_id}]
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Không tìm thấy Course hoặc Chapter")
    return {"message": "Thêm Lesson thành công", "lesson_id": lesson.id}


# ✅ YÊU CẦU 4: API trả JSON KHỔNG LỒ cho JS fetch
@app.get("/courses/{course_id}")
async def get_course_tree(course_id: str):
    course = await courses_collection.find_one({"_id": ObjectId(course_id)})
    if not course:
        raise HTTPException(status_code=404, detail="Không tìm thấy Course")
    
    # Bắt buộc phải biến ObjectId thành String thì JS mới đọc được JSON
    course["_id"] = str(course["_id"])
    return course

# ==========================================
# PHẦN 1: SCHEMA TIẾN ĐỘ HỌC (PROGRESS)
# ==========================================

# Dữ liệu gửi lên khi sinh viên bấm nút "Hoàn thành bài học"
class ProgressComplete(BaseModel):
    course_id: str
    lesson_id: str

progress_collection = db.get_collection("progress") # Tạo collection mới

# ==========================================
# PHẦN 2: API LƯU TIẾN ĐỘ & XEM BÁO CÁO
# ==========================================

# ✅ YÊU CẦU 1: POST /progress/complete (Đánh dấu hoàn thành bài học)
# Lưu ý: API này dùng JWT (Depends), bắt buộc phải có ổ khóa mới được chạy
@app.post("/progress/complete")
async def mark_lesson_complete(req: ProgressComplete, token: str = Depends(oauth2_scheme)):
    # 1. Giải mã token để biết sinh viên nào đang bấm nút
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Vui lòng đăng nhập!")

    # 2. Kiểm tra xem sinh viên này đã hoàn thành bài này trước đó chưa (Chống spam click)
    existing = await progress_collection.find_one({
        "email": email,
        "course_id": req.course_id,
        "lesson_id": req.lesson_id
    })
    if existing:
        return {"message": "Bạn đã hoàn thành bài học này trước đó rồi!"}

    # 3. Lưu vào database
    new_record = {
        "email": email,
        "course_id": req.course_id,
        "lesson_id": req.lesson_id,
        "completed_at": datetime.utcnow() # Lưu lại thời gian nộp bài
    }
    await progress_collection.insert_one(new_record)
    
    return {"message": "Chúc mừng! Bạn đã hoàn thành bài học."}


# ✅ YÊU CẦU 2: GET /progress/{student}/{course} (Xem báo cáo % tiến độ)
@app.get("/progress/{student_email}/{course_id}")
async def get_student_progress(student_email: str, course_id: str):
    # 1. Quét bảng Progress để lấy ra TẤT CẢ các bài học mà user này đã làm trong khóa này
    cursor = progress_collection.find({
        "email": student_email,
        "course_id": course_id
    })
    completed_records = await cursor.to_list(length=1000)
    
    # Rút trích ra 1 cái danh sách chỉ chứa lesson_id
    completed_lesson_ids = [record["lesson_id"] for record in completed_records]

    # 2. (Tính năng nâng cao) Đi tìm tổng số bài học của khóa học để tính Phần trăm (%)
    course = await courses_collection.find_one({"_id": ObjectId(course_id)})
    total_lessons = 0
    if course and "chapters" in course:
        for chapter in course["chapters"]:
            total_lessons += len(chapter.get("lessons", []))

    # 3. Tính tỷ lệ hoàn thành
    percentage = 0
    if total_lessons > 0:
        percentage = round((len(completed_lesson_ids) / total_lessons) * 100, 2)

    return {
        "student": student_email,
        "course_id": course_id,
        "total_lessons_in_course": total_lessons,
        "completed_lessons_count": len(completed_lesson_ids),
        "completion_percentage": f"{percentage}%",
        "completed_lesson_ids": completed_lesson_ids
    }
