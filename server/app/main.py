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


# ✅ YÊU CẦU 2 (NÂNG CẤP): GET /progress/{student}/{course} (Dùng Aggregation Pipeline)
@app.get("/progress/{student_email}/{course_id}")
async def get_student_progress(student_email: str, course_id: str):
    # 1. Đi tìm tổng số bài học của khóa học
    course = await courses_collection.find_one({"_id": ObjectId(course_id)})
    total_lessons = 0
    if course and "chapters" in course:
        for chapter in course["chapters"]:
            total_lessons += len(chapter.get("lessons", []))

    # ========================================================
    # 🔥 TÍNH NĂNG NÂNG CAO: MONGODB AGGREGATION PIPELINE 🔥
    # ========================================================
    pipeline = [
        # STAGE 1: Tìm đúng sinh viên và đúng khóa học
        {
            "$match": {
                "email": student_email,
                "course_id": course_id
            }
        },
        # STAGE 2: LỌC NHIỄU (Loại bỏ rác làm gãy pipeline)
        # Ví dụ: Loại bỏ các record điểm danh bị lỗi chữ "V", rỗng, hoặc None
        {
            "$match": {
                "lesson_id": { "$nin": ["V", "v", "", None] }
            }
        },
        # STAGE 3: Gom nhóm và Đếm (Database tự đếm, cực kỳ tối ưu)
        {
            "$group": {
                "_id": "$course_id",
                "completed_count": { "$sum": 1 }, # Tự động cộng 1 cho mỗi bài học hợp lệ
                "completed_lesson_ids": { "$push": "$lesson_id" } # Gom các ID lại thành 1 mảng
            }
        }
    ]

    # Chạy lệnh Aggregation
    cursor = progress_collection.aggregate(pipeline)
    result_list = await cursor.to_list(length=1)

    # Rút trích kết quả từ Pipeline trả về
    if result_list:
        agg_result = result_list[0]
        completed_count = agg_result["completed_count"]
        completed_lesson_ids = agg_result["completed_lesson_ids"]
    else:
        # Nếu chưa học bài nào thì trả về 0
        completed_count = 0
        completed_lesson_ids = []

    # 3. Tính tỷ lệ hoàn thành
    percentage = 0
    if total_lessons > 0:
        percentage = round((completed_count / total_lessons) * 100, 2)

    return {
        "student": student_email,
        "course_id": course_id,
        "total_lessons_in_course": total_lessons,
        "completed_lessons_count": completed_count,
        "completion_percentage": f"{percentage}%",
        "completed_lesson_ids": completed_lesson_ids,
        "tech_note": "Data processed natively by MongoDB Aggregation Pipeline"
    }
