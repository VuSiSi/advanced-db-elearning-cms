# API List — E-Learning CMS
# Schema v1 | Day 1

## Auth
| Method | Endpoint           | Auth | Who calls it         | Day |
|--------|--------------------|------|----------------------|-----|
| POST   | /api/auth/register | No   | Register page        | 1   |
| POST   | /api/auth/login    | No   | Login page           | 1   |

## Courses
| Method | Endpoint                                    | Auth       | Description                        | Day |
|--------|---------------------------------------------|------------|------------------------------------|-----|
| GET    | /api/courses/                               | No         | List all courses (no chapters)     | 2   |
| GET    | /api/courses/{id}                           | No         | Full course tree (1 query)         | 2   |
| POST   | /api/courses/                               | Instructor | Create a course                    | 2   |
| POST   | /api/courses/{id}/chapters                  | Instructor | Add chapter to course              | 2   |
| POST   | /api/courses/{id}/chapters/{ch}/lessons     | Instructor | Add lesson to chapter              | 2   |
| PUT    | /api/courses/{id}                           | Instructor | Update course metadata             | 3   |
| PUT    | /api/courses/{id}/chapters/{ch}/lessons/{l} | Instructor | Edit a lesson                      | 3   |
| DELETE | /api/courses/{id}/chapters/{ch}             | Instructor | Delete a chapter                   | 3   |
| DELETE | /api/courses/{id}/chapters/{ch}/lessons/{l} | Instructor | Delete a lesson                    | 3   |
| PUT    | /api/courses/{id}/reorder                   | Instructor | Reorder chapters/lessons           | 3   |

## Progress
| Method | Endpoint                             | Auth    | Description                        | Day |
|--------|--------------------------------------|---------|------------------------------------|-----|
| POST   | /api/progress/complete               | Student | Mark lesson as complete            | 3   |
| GET    | /api/progress/{course_id}            | Student | Get my progress in a course        | 3   |

## Analytics (Aggregation Pipeline)
| Method | Endpoint                     | Auth       | Description                           | Day |
|--------|------------------------------|------------|---------------------------------------|-----|
| GET    | /api/stats/course/{id}       | Instructor | Completion rate + avg score (no "V")  | 4   |