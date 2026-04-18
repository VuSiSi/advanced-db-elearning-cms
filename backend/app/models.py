from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime

# LESSON  (embedded inside Chapter)
class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_index: int

class LessonBase(BaseModel):
    title: str
    order: int
    type: Literal["video", "quiz", "document"]
    # video fields
    video_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    # document fields
    content: Optional[str] = None
    # quiz fields
    questions: Optional[List[QuizQuestion]] = None

class LessonCreate(LessonBase):
    pass

class Lesson(LessonBase):
    lesson_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))

# CHAPTER  (embedded inside Course)
class ChapterBase(BaseModel):
    title: str
    order: int

class ChapterCreate(ChapterBase):
    pass

class Chapter(ChapterBase):
    chapter_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    lessons: List[Lesson] = []

# COURSE  (top-level collection)
class CourseBase(BaseModel):
    title: str
    description: Optional[str] = None

class CourseCreate(CourseBase):
    pass

class Course(CourseBase):
    instructor_id: str
    chapters: List[Chapter] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# USER  (separate collection — not embedded)
class UserBase(BaseModel):
    email: str
    full_name: str
    role: Literal["student", "instructor"]

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class LoginRequest(BaseModel):
    email: str
    password: str

class UserOut(UserBase):
    id: str

# STUDENT PROGRESS  (separate collection — not embedded)
# Reason: grows unbounded (students × lessons), never read together with course
class LessonCompletion(BaseModel):
    lesson_id: str
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    score: Optional[float] = None   # None for video/doc, float for quiz

class ProgressCreate(BaseModel):
    student_id: str
    course_id: str

class Progress(ProgressCreate):
    lesson_completions: List[LessonCompletion] = []
    overall_progress_pct: float = 0.0
    last_updated: datetime = Field(default_factory=datetime.utcnow)

# AUTH
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None