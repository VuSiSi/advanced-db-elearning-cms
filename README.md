# E-Learning CMS

An e-learning content management system built with FastAPI, MongoDB, Jinja2 templates, and vanilla JavaScript. The project supports instructor-managed course authoring, student lesson tracking, and course analytics backed by MongoDB aggregation pipelines.

## Overview

The application has two main user roles:

- `instructor`: creates courses, manages chapters and lessons, uploads learning assets, and views analytics
- `student`: browses courses, opens lessons, completes content, and tracks personal progress

The backend exposes JSON APIs under `/api/*` and also serves the HTML pages used by the browser UI.

## Tech Stack

- Backend: FastAPI
- Database: MongoDB with Motor
- Templating: Jinja2
- Frontend: HTML, CSS, vanilla JavaScript
- Authentication: JWT with `python-jose`
- Password hashing: `passlib` + `bcrypt`

## Repository Layout

```text
advanced-db-elearning-cms/
|-- server/
|   |-- main.py                  # FastAPI application entrypoint
|   |-- requirements.txt
|   |-- test_schema.py           # MongoDB schema smoke test
|   `-- app/
|       |-- database.py          # MongoDB connection helpers
|       |-- models.py            # Pydantic models and schema design
|       |-- middleware/
|       |   `-- auth.py          # JWT auth and role guards
|       |-- routes/
|       |   |-- auth.py          # Register/login APIs
|       |   |-- courses.py       # Course, chapter, lesson APIs
|       |   |-- progress.py      # Student progress APIs
|       |   |-- stats.py         # Instructor analytics APIs
|       |   |-- upload.py        # File upload API
|       |   `-- pages.py         # HTML page routes
|       |-- static/
|       |   |-- css/
|       |   |-- js/
|       |   `-- uploads/
|       `-- templates/
|           |-- base.html
|           |-- courses.html
|           |-- course_editor.html
|           |-- course_landing.html
|           |-- lesson_view.html
|           |-- analytics.html
|           |-- my_progress.html
|           |-- stats.html
|           `-- login.html
`-- docs/
    |-- api_list.md
    |-- schema_notes.md
    |-- performance_eval.md
    `-- test.md
```

## Core Features

- JWT-based authentication for students and instructors
- Course catalog and course detail pages
- Instructor-only course creation and editing
- Nested course structure with chapters and lessons embedded in the course document
- Support for `video`, `quiz`, and `document` lesson types
- Soft delete for chapters and lessons via `is_deleted`
- Student lesson completion tracking with optional quiz scores
- Instructor analytics for completion rate, quiz averages, and per-lesson activity
- Static asset upload endpoint for lesson content

## Data Model

The MongoDB design uses a mix of embedded documents and references:

- `courses`: embeds `chapters` and `lessons`
- `users`: stored separately because users exist independently of courses
- `student_progress`: stored separately because progress grows with `students x lessons`

This gives fast single-document reads for full course trees while keeping progress data scalable and queryable for analytics.

## Prerequisites

- Python 3.11+
- MongoDB running locally or a MongoDB Atlas connection string

## Setup

### 1. Create and activate a virtual environment

```powershell
cd server
python -m venv .venv
.venv\Scripts\activate
```

On macOS or Linux:

```bash
cd server
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create `server/.env` with:

```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=elearning_cms
JWT_SECRET_KEY=change-this-secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60
```

## Running the App

From the `server/` directory:

```bash
uvicorn main:app --reload
```

The app will be available at:

- UI: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

On startup, the app connects to MongoDB and creates a compound index on `student_progress(student_id, course_id)`.

## Main API Areas

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login`

### Courses

- `GET /api/courses/`
- `GET /api/courses/my`
- `GET /api/courses/{course_id}`
- `GET /api/courses/{course_id}/lessons/{lesson_id}`
- `POST /api/courses/`
- `PUT /api/courses/{course_id}`
- `POST /api/courses/{course_id}/chapters`
- `DELETE /api/courses/{course_id}/chapters/{chapter_id}`
- `POST /api/courses/{course_id}/chapters/{chapter_id}/lessons`
- `PUT /api/courses/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}`
- `DELETE /api/courses/{course_id}/chapters/{chapter_id}/lessons/{lesson_id}`
- `PUT /api/courses/{course_id}/reorder`

### Progress

- `POST /api/progress/complete`
- `GET /api/progress/{course_id}`
- `GET /api/progress/my/{course_id}`
- `GET /api/progress/instructor/{student_id}/{course_id}`

### Analytics

- `GET /api/stats/course/{course_id}`

### Uploads

- `POST /api/upload/`

## Main UI Routes

- `/` and `/courses`: course catalog
- `/login`: login page
- `/courses/{course_id}`: course landing page
- `/courses/{course_id}/edit`: instructor editor
- `/courses/{course_id}/lessons/{lesson_id}`: lesson viewer
- `/analytics/{course_id}`: analytics dashboard
- `/my-progress`: student progress page
- `/stats`: stats page

## Testing the Schema

The repository includes a simple MongoDB schema smoke test:

```bash
cd server
python test_schema.py
```

This script inserts sample users, courses, and progress documents, verifies the structure, then removes the test data.

## Notes

- Course, chapter, and lesson deletions are implemented as soft deletes.
- Uploads are stored in `server/app/static/uploads`.
- The upload route blocks pure audio files such as `.mp3`.
- Several supporting documents are available in [`docs/`](docs).
