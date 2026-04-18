E-Learning CMS — Advanced Database BTL
Tech Stack
Backend: FastAPI (Python)
Database: MongoDB (via Motor async driver)
Frontend: HTML + Jinja2 Templates + Vanilla JS
Auth: JWT (python-jose + passlib/bcrypt)
Project Structure
project/
├── backend/
│   ├── app/
│   │   ├── main.py             ← FastAPI entry point
│   │   ├── database.py         ← MongoDB connection
│   │   ├── models.py           ← Pydantic schemas (3 collections)
│   │   ├── middleware/
│   │   │   └── auth.py         ← JWT helpers + route guards
│   │   ├── routes/
│   │   │   ├── auth.py         ← POST /register, POST /login
│   │   │   ├── courses.py      ← Course CRUD
│   │   │   └── progress.py     ← Student progress (Day 3)
│   │   ├── templates/          ← Jinja2 HTML (Day 2+)
│   │   │   ├──
│   │   └── static/             ← CSS + JS
│   │       ├──
│   ├── test_schema.py          ← Thanh runs this on Day 1
│   ├── requirements.txt
│   └── .env
└── docs/
    ├── api_list.md             ← All API endpoints
    └── schema_notes.md         ← Notes for report Part 2
Setup (Day 1)
1. Prerequisites
Python 3.11+
MongoDB running locally (or Atlas connection string)
2. Install dependencies
cd .../backend
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
3. Configure environment
Edit backend/.env:

MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=elearning_cms
JWT_SECRET_KEY=your-secret-key-change-this
4. Run the server
cd backend
uvicorn app.main:app --reload
API docs available at: http://localhost:8000/docs

5. Test MongoDB schema (Thanh — Day 1)
cd backend
python test_schema.py
MongoDB Collections
Collection	Strategy	Reason
courses	Embedded	chapters + lessons always read together
users	Reference	shared across courses, exists independently
student_progress	Reference	unbounded growth (students × lessons)
API Endpoints
See docs/api_list.md for the full list.