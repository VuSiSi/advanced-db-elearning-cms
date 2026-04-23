from fastapi import APIRouter, HTTPException
from app.database import get_db
from app.models import CourseCreate, ChapterCreate, LessonCreate
from datetime import datetime, timezone
import asyncio
import uuid

router = APIRouter(prefix="/api/stress-test", tags=["stress-test"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# ─── KIỂM TRA ROUTER HOẠT ĐỘNG ──────────────────────────────
@router.get("/")
async def stress_test_root():
    """Kiểm tra xem module stress test đã được kết nối thành công chưa."""
    return {"message": "Stress test API is working! Welcome."}

# ─── GENERATE TEST DATA ─────────────────────────────────────
# Đổi thành api_route để hỗ trợ cả GET (dùng trên trình duyệt) và POST
@router.api_route("/generate-courses", methods=["GET", "POST"])
async def generate_test_courses(count: int = 10):
    """Generate N test courses with chapters and lessons for stress testing."""
    if count > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 courses at once")
    
    db = get_db()
    instructor_id = str(uuid.uuid4())
    created_courses = []
    
    try:
        for i in range(count):
            course_data = {
                "title": f"Stress Test Course {i+1}",
                "description": f"This is a test course for stress testing - {uuid.uuid4()}",
                "instructor_id": instructor_id,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "chapters": [
                    {
                        "id": str(uuid.uuid4()),
                        "title": f"Chapter {j+1}",
                        "description": f"Test chapter {j+1}",
                        "order": j,
                        "is_deleted": False,
                        "lessons": [
                            {
                                "id": str(uuid.uuid4()),
                                "title": f"Lesson {k+1}",
                                "description": f"Test lesson {k+1}",
                                "type": ["video", "quiz", "document"][k % 3],
                                "content": f"Sample content for lesson {k+1}" * 50,
                                "duration": 10 + k,
                                "order": k,
                                "is_deleted": False,
                            }
                            for k in range(3)
                        ]
                    }
                    for j in range(2)
                ]
            }
            
            result = await db.courses.insert_one(course_data)
            created_courses.append({
                "course_id": str(result.inserted_id),
                "title": course_data["title"],
                "instructor_id": instructor_id
            })
        
        return {
            "status": "success",
            "created": len(created_courses),
            "instructor_id": instructor_id,
            "courses": created_courses
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── CONCURRENT READ TEST ──────────────────────────────────
@router.get("/concurrent-reads")
async def concurrent_reads(num_tasks: int = 10):
    """Simulate concurrent read operations."""
    if num_tasks > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 concurrent tasks")
    
    db = get_db()
    
    async def read_courses():
        return await db.courses.find({}, {"chapters": 0}).to_list(100)
    
    try:
        start_time = datetime.now(timezone.utc)
        results = await asyncio.gather(*[read_courses() for _ in range(num_tasks)])
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        return {
            "status": "success",
            "concurrent_tasks": num_tasks,
            "total_documents_read": sum(len(r) for r in results),
            "duration_seconds": duration,
            "avg_time_per_task_ms": (duration * 1000) / num_tasks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── CONCURRENT WRITE TEST ─────────────────────────────────
@router.api_route("/concurrent-writes", methods=["GET", "POST"])
async def concurrent_writes(num_tasks: int = 10):
    """Simulate concurrent write operations."""
    if num_tasks > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 concurrent tasks")
    
    db = get_db()
    instructor_id = str(uuid.uuid4())
    
    async def create_course():
        course_data = {
            "title": f"Concurrent Test {uuid.uuid4()}",
            "description": "Concurrent write test",
            "instructor_id": instructor_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "chapters": []
        }
        return await db.courses.insert_one(course_data)
    
    try:
        start_time = datetime.now(timezone.utc)
        results = await asyncio.gather(*[create_course() for _ in range(num_tasks)])
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        return {
            "status": "success",
            "concurrent_tasks": num_tasks,
            "total_documents_created": len(results),
            "instructor_id": instructor_id,
            "duration_seconds": duration,
            "avg_time_per_write_ms": (duration * 1000) / num_tasks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── QUERY PERFORMANCE TEST ────────────────────────────────
@router.get("/query-performance")
async def query_performance():
    """Test various query patterns and measure performance."""
    db = get_db()
    results = {}
    
    try:
        # Test 1: Find all courses
        start = datetime.now(timezone.utc)
        all_courses = await db.courses.find({}).to_list(1000)
        results["find_all_courses"] = {
            "duration_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
            "count": len(all_courses)
        }
        
        # Test 2: Aggregation - courses by instructor
        start = datetime.now(timezone.utc)
        agg_result = await db.courses.aggregate([
            {"$group": {"_id": "$instructor_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]).to_list(None)
        results["group_by_instructor"] = {
            "duration_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
            "results_count": len(agg_result)
        }
        
        # Test 3: Indexed query (if index exists)
        start = datetime.now(timezone.utc)
        instructor_courses = await db.courses.find(
            {"instructor_id": "test-instructor"}
        ).to_list(100)
        results["find_by_instructor"] = {
            "duration_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
            "count": len(instructor_courses)
        }
        
        return {
            "status": "success",
            "tests": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── CLEANUP TEST DATA ──────────────────────────────────────
@router.api_route("/cleanup", methods=["GET", "DELETE"])
async def cleanup_test_data(instructor_id: str):
    """Delete all test courses by instructor ID."""
    db = get_db()
    
    try:
        result = await db.courses.delete_many({"instructor_id": instructor_id})
        return {
            "status": "success",
            "deleted_count": result.deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── DATABASE STATS ────────────────────────────────────────
@router.get("/db-stats")
async def get_database_stats():
    """Get database statistics."""
    db = get_db()
    
    try:
        courses_count = await db.courses.count_documents({})
        students_count = await db.users.count_documents({"role": "student"})
        instructors_count = await db.users.count_documents({"role": "instructor"})
        progress_count = await db.student_progress.count_documents({})
        
        return {
            "status": "success",
            "courses": courses_count,
            "students": students_count,
            "instructors": instructors_count,
            "progress_records": progress_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
