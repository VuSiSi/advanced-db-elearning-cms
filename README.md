
# Advanced Database Project - E-Learning CMS

## Folder Structure
```
advanced-db-project/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   └── routes.py
│   ├── requirements.txt
│   └── .env
│
├── frontend/        (React/Vue sau)
├── docs/            (report, diagram)
└── README.md
```

## Setup

### 1. Clone repo
```
git clone ...
cd backend
```

### 2. Setup environment

#### a. Window
```
python -m venv venv
venv/bin/activate
```

#### b. Mac/Linux
```
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```
pip install -r requirements.txt
```

### 4. Run server
```
uvicorn app.main:app --reload
```

## Tech Stack
- FastAPI
- MongoDB
- PyMongo

## Features
- CRUD Course
- Track learning progress