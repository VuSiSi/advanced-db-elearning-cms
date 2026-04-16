# Schema Design Notes — Report Part 2

## Collections Overview

### 1. courses
- **Why embedded?** The entire course tree (chapters → lessons) is always read
  together in one operation. Embedding eliminates the need for JOINs and reflects
  MongoDB's document model correctly.
- **Embed vs Reference decision:**
  - EMBED: chapters, lessons (always read together, bounded size per course)
  - REFERENCE: instructor_id → users (user exists independently across many courses)

### 2. users
- Stored as a separate collection because users are shared entities — an instructor
  owns many courses, a student enrolls in many courses.
- Embedding user data inside each course would cause update anomalies.

### 3. student_progress
- **Why NOT embedded in courses?**
  - Unbounded growth: N students × M lessons per course
  - Never read together with course content (different use case)
  - Frequently updated independently of the course structure
- **Why NOT embedded in users?**
  - A student's progress across all courses would make the user document
    grow unbounded.

## Key MongoDB Advantage Demonstrated
Loading the full course structure (title, all chapters, all lessons with their
type-specific fields) requires exactly **1 query**:
    db.courses.find_one({"_id": ObjectId(course_id)})

The equivalent SQL would require:
```
SELECT * FROM courses
JOIN chapters ON courses.id = chapters.course_id
JOIN lessons ON chapters.id = lessons.chapter_id
LEFT JOIN video_lessons ON lessons.id = video_lessons.lesson_id
LEFT JOIN quiz_lessons ON lessons.id = quiz_lessons.lesson_id
LEFT JOIN quiz_questions ON quiz_lessons.id = quiz_questions.lesson_id
WHERE courses.id = ?
```

## Schema-less Advantage
Video lessons contain: video_url, duration_seconds
Quiz lessons contain: questions (array of question/options/correct_index)
Document lessons contain: content (markdown text)

In SQL, these would require separate tables or many nullable columns.
In MongoDB, each lesson document has a different shape based on its `type` field.
No ALTER TABLE needed to add new lesson types.