from datetime import datetime, timezone
import os
import time
import uuid
from typing import Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo import UpdateOne

from app.database import get_db
from app.middleware.auth import TokenData, hash_password, require_instructor


router = APIRouter(prefix="/api/stress-test", tags=["stress-test"])

MIN_LOOPS = 50
CHAPTERS_PER_COURSE = 2
LESSONS_PER_CHAPTER = 3
STRESS_SCHEMA = "stress_test"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StressRunRequest(BaseModel):
    loops: int = Field(..., ge=MIN_LOOPS)
    db_type: Literal["mongo", "postgres", "postgresql", "sql"] = "mongo"


class StressCleanupRequest(BaseModel):
    batch_id: str
    db_type: Optional[Literal["mongo", "postgres", "postgresql", "sql"]] = None


@router.get("/")
async def stress_test_root():
    return {"message": "Stress test API is working"}


@router.post("/run")
async def run_stress_test(
    body: StressRunRequest,
    token_data: TokenData = Depends(require_instructor),
):
    db_type = _normalize_db_type(body.db_type)
    started = time.perf_counter()

    if db_type == "mongo":
        result = await _run_mongo_stress(body.loops, token_data.user_id)
    else:
        result = await _run_postgres_stress(body.loops, token_data.user_id)

    result["time_taken"] = round(time.perf_counter() - started, 3)
    return result


@router.api_route("/cleanup", methods=["POST", "DELETE"])
async def cleanup_test_data(
    body: Optional[StressCleanupRequest] = Body(None),
    batch_id: Optional[str] = Query(None),
    db_type: Optional[str] = Query(None),
    token_data: TokenData = Depends(require_instructor),
):
    resolved_batch_id = body.batch_id if body else batch_id
    resolved_db_type = body.db_type if body and body.db_type else db_type

    if not resolved_batch_id:
        raise HTTPException(status_code=400, detail="batch_id is required")

    normalized_db_type = _normalize_db_type(resolved_db_type or "mongo")
    if normalized_db_type == "mongo":
        result = await _cleanup_mongo_stress(resolved_batch_id, token_data.user_id)
    else:
        result = await _cleanup_postgres_stress(resolved_batch_id, token_data.user_id)

    return {"status": "success", "batch_id": resolved_batch_id, "db_type": normalized_db_type, **result}


@router.get("/db-stats")
async def get_database_stats(token_data: TokenData = Depends(require_instructor)):
    db = get_db()
    active_filter = {"is_deleted": {"$ne": True}}

    try:
        courses_count = await db.courses.count_documents(active_filter)
        students_count = await db.users.count_documents({"role": "student", **active_filter})
        instructors_count = await db.users.count_documents({"role": "instructor", **active_filter})
        progress_count = await db.student_progress.count_documents(active_filter)

        return {
            "status": "success",
            "courses": courses_count,
            "students": students_count,
            "instructors": instructors_count,
            "progress_records": progress_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _normalize_db_type(db_type: str) -> str:
    normalized = (db_type or "mongo").lower()
    if normalized == "mongo":
        return "mongo"
    if normalized in {"postgres", "postgresql", "sql"}:
        return "postgres"
    raise HTTPException(status_code=400, detail="Unsupported database engine")


def _build_course_shape(index: int) -> tuple[list[dict], list[str]]:
    lesson_ids = []
    chapters = []

    for chapter_index in range(CHAPTERS_PER_COURSE):
        lessons = []
        for lesson_index in range(LESSONS_PER_CHAPTER):
            lesson_id = str(uuid.uuid4())
            lesson_ids.append(lesson_id)
            lessons.append(
                {
                    "lesson_id": lesson_id,
                    "title": f"Stress Lesson {index + 1}.{chapter_index + 1}.{lesson_index + 1}",
                    "order": lesson_index,
                    "type": ["video", "quiz", "document"][lesson_index % 3],
                    "content": f"Generated stress-test content {uuid.uuid4()}",
                    "duration_seconds": 300 + lesson_index * 60,
                    "is_deleted": False,
                }
            )

        chapters.append(
            {
                "chapter_id": str(uuid.uuid4()),
                "title": f"Stress Chapter {index + 1}.{chapter_index + 1}",
                "order": chapter_index,
                "lessons": lessons,
                "is_deleted": False,
            }
        )

    return chapters, lesson_ids


async def _run_mongo_stress(loops: int, owner_instructor_id: str) -> dict:
    db = get_db()
    batch_id = str(uuid.uuid4())
    now = utc_now()
    password_hash = hash_password("StressTest@123")

    instructors = []
    students = []
    for index in range(loops):
        instructors.append(
            {
                "_id": ObjectId(),
                "email": f"stress-instructor-{batch_id}-{index}@local.test",
                "full_name": f"Stress Instructor {index + 1}",
                "role": "instructor",
                "hashed_password": password_hash,
                "created_at": now,
                "stress_test": True,
                "stress_batch_id": batch_id,
                "stress_owner_id": owner_instructor_id,
                "is_deleted": False,
            }
        )
        students.append(
            {
                "_id": ObjectId(),
                "email": f"stress-student-{batch_id}-{index}@local.test",
                "full_name": f"Stress Student {index + 1}",
                "role": "student",
                "hashed_password": password_hash,
                "created_at": now,
                "stress_test": True,
                "stress_batch_id": batch_id,
                "stress_owner_id": owner_instructor_id,
                "is_deleted": False,
            }
        )

    courses = []
    course_lesson_ids = []
    for index, instructor in enumerate(instructors):
        chapters, lesson_ids = _build_course_shape(index)
        course_lesson_ids.append(lesson_ids)
        courses.append(
            {
                "_id": ObjectId(),
                "title": f"Stress Test Course {index + 1}",
                "description": f"Generated by stress test batch {batch_id}",
                "instructor_id": str(instructor["_id"]),
                "chapters": chapters,
                "created_at": now,
                "updated_at": now,
                "stress_test": True,
                "stress_batch_id": batch_id,
                "stress_owner_id": owner_instructor_id,
                "is_deleted": False,
            }
        )

    progress_docs = []
    for index, student in enumerate(students):
        course = courses[index % loops]
        completions = [
            {
                "lesson_id": lesson_id,
                "completed_at": now,
                "score": 80 + (index % 20) if offset % 3 == 1 else None,
            }
            for offset, lesson_id in enumerate(course_lesson_ids[index % loops])
        ]
        progress_docs.append(
            {
                "student_id": str(student["_id"]),
                "course_id": str(course["_id"]),
                "lesson_completions": completions,
                "overall_progress_pct": 100.0,
                "last_updated": now,
                "stress_test": True,
                "stress_batch_id": batch_id,
                "stress_owner_id": owner_instructor_id,
                "is_deleted": False,
            }
        )

    try:
        await db.users.insert_many(instructors + students)
        await db.courses.insert_many(courses)
        await db.student_progress.insert_many(progress_docs)

        update_ops = [
            UpdateOne(
                {"_id": course["_id"]},
                {
                    "$set": {
                        "title": f"{course['title']} (edited)",
                        "updated_at": utc_now(),
                        "stress_last_edit": "metadata_update",
                    }
                },
            )
            for course in courses
        ]
        if update_ops:
            await db.courses.bulk_write(update_ops)
    except Exception as exc:
        await _cleanup_mongo_stress(batch_id, owner_instructor_id)
        raise HTTPException(status_code=500, detail=f"MongoDB stress test failed: {exc}")

    return {
        "status": "success",
        "db_type": "mongo",
        "batch_id": batch_id,
        "loops": loops,
        "instructors_created": len(instructors),
        "students_created": len(students),
        "courses_created": len(courses),
        "progress_records": len(progress_docs),
        "lesson_completions": loops * CHAPTERS_PER_COURSE * LESSONS_PER_CHAPTER,
    }


async def _cleanup_mongo_stress(batch_id: str, owner_instructor_id: str) -> dict:
    db = get_db()
    now = utc_now()
    filter_doc = {
        "stress_test": True,
        "stress_batch_id": batch_id,
        "stress_owner_id": owner_instructor_id,
        "is_deleted": {"$ne": True},
    }
    update_doc = {
        "$set": {
            "is_deleted": True,
            "deleted_at": now,
            "updated_at": now,
        }
    }

    users_result = await db.users.update_many(filter_doc, update_doc)
    courses_result = await db.courses.update_many(filter_doc, update_doc)
    progress_result = await db.student_progress.update_many(filter_doc, update_doc)

    return {
        "soft_deleted_users": users_result.modified_count,
        "soft_deleted_courses": courses_result.modified_count,
        "soft_deleted_progress_records": progress_result.modified_count,
    }


async def _run_postgres_stress(loops: int, owner_instructor_id: str) -> dict:
    pool = await _create_postgres_pool()
    batch_id = uuid.uuid4()
    now = utc_now()
    password_hash = hash_password("StressTest@123")

    instructors = []
    students = []
    courses = []
    chapters = []
    lessons = []
    progress_rows = []
    completion_rows = []

    for index in range(loops):
        instructor_id = uuid.uuid4()
        student_id = uuid.uuid4()
        course_id = uuid.uuid4()

        instructors.append(
            (
                instructor_id,
                batch_id,
                f"stress-instructor-{batch_id}-{index}@local.test",
                f"Stress Instructor {index + 1}",
                "instructor",
                password_hash,
                now,
                False,
            )
        )
        students.append(
            (
                student_id,
                batch_id,
                f"stress-student-{batch_id}-{index}@local.test",
                f"Stress Student {index + 1}",
                "student",
                password_hash,
                now,
                False,
            )
        )
        courses.append(
            (
                course_id,
                batch_id,
                instructor_id,
                f"Stress Test Course {index + 1} (edited)",
                f"Generated by stress test batch {batch_id}",
                now,
                now,
                False,
            )
        )

        lesson_ids_for_course = []
        for chapter_index in range(CHAPTERS_PER_COURSE):
            chapter_id = uuid.uuid4()
            chapters.append(
                (
                    chapter_id,
                    course_id,
                    f"Stress Chapter {index + 1}.{chapter_index + 1}",
                    chapter_index,
                    False,
                )
            )
            for lesson_index in range(LESSONS_PER_CHAPTER):
                lesson_id = uuid.uuid4()
                lesson_ids_for_course.append(lesson_id)
                lessons.append(
                    (
                        lesson_id,
                        chapter_id,
                        f"Stress Lesson {index + 1}.{chapter_index + 1}.{lesson_index + 1}",
                        ["video", "quiz", "document"][lesson_index % 3],
                        f"Generated stress-test content {uuid.uuid4()}",
                        300 + lesson_index * 60,
                        lesson_index,
                        False,
                    )
                )

        progress_id = uuid.uuid4()
        progress_rows.append((progress_id, batch_id, student_id, course_id, 100.0, now, False))
        for offset, lesson_id in enumerate(lesson_ids_for_course):
            completion_rows.append(
                (
                    uuid.uuid4(),
                    progress_id,
                    lesson_id,
                    now,
                    80 + (index % 20) if offset % 3 == 1 else None,
                )
            )

    try:
        async with pool.acquire() as conn:
            await _ensure_postgres_schema(conn)
            async with conn.transaction():
                await conn.execute(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.batches
                            (batch_id, owner_instructor_id, loops, started_at, completed_at, is_deleted)
                        VALUES ($1, $2, $3, $4, $4, false)
                        """,
                        batch_id,
                        owner_instructor_id,
                        loops,
                        now,
                )
                await conn.executemany(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.users
                            (id, batch_id, email, full_name, role, hashed_password, created_at, is_deleted)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        instructors + students,
                )
                await conn.executemany(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.courses
                            (id, batch_id, instructor_id, title, description, created_at, updated_at, is_deleted)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        courses,
                )
                await conn.executemany(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.chapters
                            (id, course_id, title, order_index, is_deleted)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        chapters,
                )
                await conn.executemany(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.lessons
                            (id, chapter_id, title, lesson_type, content, duration_seconds, order_index, is_deleted)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """,
                        lessons,
                )
                await conn.executemany(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.student_progress
                            (id, batch_id, student_id, course_id, overall_progress_pct, last_updated, is_deleted)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        progress_rows,
                )
                await conn.executemany(
                        f"""
                        INSERT INTO {STRESS_SCHEMA}.lesson_completions
                            (id, progress_id, lesson_id, completed_at, score)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        completion_rows,
                )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PostgreSQL stress test failed: {exc}")
    finally:
        await pool.close()

    return {
        "status": "success",
        "db_type": "postgres",
        "batch_id": str(batch_id),
        "loops": loops,
        "instructors_created": len(instructors),
        "students_created": len(students),
        "courses_created": len(courses),
        "progress_records": len(progress_rows),
        "lesson_completions": len(completion_rows),
    }


async def _cleanup_postgres_stress(batch_id: str, owner_instructor_id: str) -> dict:
    try:
        batch_uuid = uuid.UUID(batch_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid PostgreSQL batch_id")

    pool = await _create_postgres_pool()
    now = utc_now()
    try:
        async with pool.acquire() as conn:
            await _ensure_postgres_schema(conn)
            owner = await conn.fetchval(
                f"""
                SELECT owner_instructor_id
                FROM {STRESS_SCHEMA}.batches
                WHERE batch_id = $1
                """,
                batch_uuid,
            )
            if owner != owner_instructor_id:
                raise HTTPException(status_code=404, detail="Stress test batch not found")

            async with conn.transaction():
                users_result = await conn.execute(
                    f"""
                    UPDATE {STRESS_SCHEMA}.users
                    SET is_deleted = true, deleted_at = $2
                    WHERE batch_id = $1 AND is_deleted = false
                    """,
                    batch_uuid,
                    now,
                )
                courses_result = await conn.execute(
                    f"""
                    UPDATE {STRESS_SCHEMA}.courses
                    SET is_deleted = true, deleted_at = $2, updated_at = $2
                    WHERE batch_id = $1 AND is_deleted = false
                    """,
                    batch_uuid,
                    now,
                )
                progress_result = await conn.execute(
                    f"""
                    UPDATE {STRESS_SCHEMA}.student_progress
                    SET is_deleted = true, deleted_at = $2, last_updated = $2
                    WHERE batch_id = $1 AND is_deleted = false
                    """,
                    batch_uuid,
                    now,
                )
                await conn.execute(
                    f"""
                    UPDATE {STRESS_SCHEMA}.batches
                    SET is_deleted = true, deleted_at = $2
                    WHERE batch_id = $1
                    """,
                    batch_uuid,
                    now,
                )
    finally:
        await pool.close()

    return {
        "soft_deleted_users": _postgres_affected_rows(users_result),
        "soft_deleted_courses": _postgres_affected_rows(courses_result),
        "soft_deleted_progress_records": _postgres_affected_rows(progress_result),
    }


async def _create_postgres_pool():
    try:
        import asyncpg
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="asyncpg is not installed. Run: pip install -r server/requirements.txt",
        )

    dsn = (
        os.getenv("POSTGRES_DSN")
        or os.getenv("POSTGRES_URL")
        or os.getenv("DATABASE_URL")
        or "postgresql://postgres:postgres@localhost:5432/elearning_cms"
    )
    try:
        return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cannot connect to PostgreSQL: {exc}")


async def _ensure_postgres_schema(conn):
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {STRESS_SCHEMA}")
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.batches (
            batch_id uuid PRIMARY KEY,
            owner_instructor_id text NOT NULL,
            loops integer NOT NULL,
            started_at timestamptz NOT NULL,
            completed_at timestamptz,
            is_deleted boolean NOT NULL DEFAULT false,
            deleted_at timestamptz
        )
        """
    )
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.users (
            id uuid PRIMARY KEY,
            batch_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.batches(batch_id),
            email text NOT NULL,
            full_name text NOT NULL,
            role text NOT NULL CHECK (role IN ('student', 'instructor')),
            hashed_password text NOT NULL,
            created_at timestamptz NOT NULL,
            is_deleted boolean NOT NULL DEFAULT false,
            deleted_at timestamptz
        )
        """
    )
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.courses (
            id uuid PRIMARY KEY,
            batch_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.batches(batch_id),
            instructor_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.users(id),
            title text NOT NULL,
            description text,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            is_deleted boolean NOT NULL DEFAULT false,
            deleted_at timestamptz
        )
        """
    )
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.chapters (
            id uuid PRIMARY KEY,
            course_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.courses(id),
            title text NOT NULL,
            order_index integer NOT NULL,
            is_deleted boolean NOT NULL DEFAULT false
        )
        """
    )
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.lessons (
            id uuid PRIMARY KEY,
            chapter_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.chapters(id),
            title text NOT NULL,
            lesson_type text NOT NULL,
            content text,
            duration_seconds integer,
            order_index integer NOT NULL,
            is_deleted boolean NOT NULL DEFAULT false
        )
        """
    )
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.student_progress (
            id uuid PRIMARY KEY,
            batch_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.batches(batch_id),
            student_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.users(id),
            course_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.courses(id),
            overall_progress_pct numeric(5, 2) NOT NULL,
            last_updated timestamptz NOT NULL,
            is_deleted boolean NOT NULL DEFAULT false,
            deleted_at timestamptz
        )
        """
    )
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STRESS_SCHEMA}.lesson_completions (
            id uuid PRIMARY KEY,
            progress_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.student_progress(id),
            lesson_id uuid NOT NULL REFERENCES {STRESS_SCHEMA}.lessons(id),
            completed_at timestamptz NOT NULL,
            score numeric(5, 2)
        )
        """
    )
    await conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_stress_users_batch ON {STRESS_SCHEMA}.users(batch_id)"
    )
    await conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_stress_courses_batch ON {STRESS_SCHEMA}.courses(batch_id)"
    )
    await conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_stress_progress_batch ON {STRESS_SCHEMA}.student_progress(batch_id)"
    )


def _postgres_affected_rows(command_status: str) -> int:
    try:
        return int(command_status.split()[-1])
    except (AttributeError, ValueError, IndexError):
        return 0
