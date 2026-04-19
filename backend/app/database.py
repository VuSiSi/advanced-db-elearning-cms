from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "elearning_cms")

client: AsyncIOMotorClient = None


async def connect_db():
    global client
    client = AsyncIOMotorClient(MONGODB_URL)

    db = client[DATABASE_NAME]

    # Index for fast course lookup by instructor_id
    await db.users.create_index("instructor_id")

    #Compound index for progress lookup by student_id + course_id - most common query pattern
    await db.student_progress.create_index(
        [("student_id", 1), ("course_id", 1)],
        unique=True # one progress document per student-course pair
    )

    # Index for stats aggregation to quickly group by course_id
    await db.student_progress.create_index("course_id")

    print(f"Connected to MongoDB: {DATABASE_NAME}")


async def close_db():
    global client
    if client:
        client.close()
        print("MongoDB connection closed")


def get_db():
    return client[DATABASE_NAME]