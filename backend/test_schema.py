"""
Day 1 test script to validate MongoDB schema design for E-Learning CMS.
Make sure MongoDB is running and .env is configured before running.

How to run:
    cd backend
    python test_schema.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DATABASE_NAME", "elearning_cms")


async def test_schema():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]

    print("=" * 50)
    print("Testing E-Learning CMS MongoDB Schema")
    print(f"MongoDB URL: {MONGODB_URL}")
    print(f"Database Name: {DB_NAME}")
    print("=" * 50)

    # Test 1: Insert a user
    print("\n[1] Inserting test instructor...")
    user = {
        "email": "instructor@test.com",
        "full_name": "Test Instructor",
        "role": "instructor",
        "hashed_password": "hashed_dummy",
    }
    result = await db.users.insert_one(user)
    instructor_id = str(result.inserted_id)
    print(f"\tInserted user ID: {instructor_id}")

    # Test 2: Insert a course with nested structure
    print("\n[2] Inserting test course with chapters + lessons...")
    course = {
        "title": "Introduction to Python",
        "description": "Learn Python from scratch",
        "instructor_id": instructor_id,
        "chapters": [
            {
                "chapter_id": "ch-001",
                "title": "Getting Started",
                "order": 1,
                "lessons": [
                    {
                        "lesson_id": "ls-001",
                        "title": "What is Python?",
                        "order": 1,
                        "type": "video",
                        "video_url": "https://example.com/video1",
                        "duration_seconds": 300,
                    },
                    {
                        "lesson_id": "ls-002",
                        "title": "Chapter 1 Quiz",
                        "order": 2,
                        "type": "quiz",
                        "questions": [
                            {
                                "question": "Python is a...",
                                "options": ["compiled", "interpreted", "both"],
                                "correct_index": 1,
                            }
                        ],
                    },
                ],
            }
        ],
    }
    result = await db.courses.insert_one(course)
    course_id = str(result.inserted_id)
    print(f"\tInserted course ID: {course_id}")

    # Test 3: Fetch full course in ONE query
    print("\n[3] Fetching full course structure (1 query)...")
    from bson import ObjectId
    fetched = await db.courses.find_one({"_id": ObjectId(course_id)})
    chapters = fetched.get("chapters", [])
    print(f"\tCourse title: {fetched['title']}")
    print(f"\tChapters: {len(chapters)}")
    print(f"\tLessons in chapter 1: {len(chapters[0]['lessons'])}")
    print(f"\tLesson types: {[l['type'] for l in chapters[0]['lessons']]}")

    # Test 4: Insert student progress 
    print("\n[4] Inserting student progress...")
    student = {
        "email": "student@test.com",
        "full_name": "Test Student",
        "role": "student",
        "hashed_password": "hashed_dummy",
    }
    result = await db.users.insert_one(student)
    student_id = str(result.inserted_id)

    progress = {
        "student_id": student_id,
        "course_id": course_id,
        "lesson_completions": [
            {
                "lesson_id": "ls-001",
                "completed_at": "2024-01-01T10:00:00",
                "score": None,        # video — no score
            },
            {
                "lesson_id": "ls-002",
                "completed_at": "2024-01-01T10:15:00",
                "score": 85.0,        # quiz score
            },
        ],
        "overall_progress_pct": 100.0,
    }
    await db.student_progress.insert_one(progress)
    print(f"\tProgress inserted for student: {student_id}")

    # Test 5: List all collections 
    print("\n[5] Collections in database:")
    collections = await db.list_collection_names()
    for name in collections:
        count = await db[name].count_documents({})
        print(f"\t{name}: {count} document(s)")

    # Cleanup test data
    print("\n[Cleanup] Dropping test data...")
    await db.users.drop()
    await db.courses.drop()
    await db.student_progress.drop()
    print("\tDone.")

    client.close()
    print("\nAll tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(test_schema())