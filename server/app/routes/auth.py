from fastapi import APIRouter, HTTPException, status
from app.models import UserCreate, UserOut, Token, LoginRequest
from app.middleware.auth import hash_password, verify_password, create_access_token
from app.database import get_db
from bson import ObjectId

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(user_in: UserCreate):
    db = get_db()

    # Check duplicate email
    existing = await db.users.find_one({"email": user_in.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered (400 Bad Request)")

    doc = {
        "email": user_in.email,
        "full_name": user_in.full_name,
        "role": user_in.role,
        "hashed_password": hash_password(user_in.password),
    }
    result = await db.users.insert_one(doc)
    return UserOut(
        id=str(result.inserted_id),
        email=user_in.email,
        full_name=user_in.full_name,
        role=user_in.role,
    )


@router.post("/login", response_model=Token)
async def login(user_in: LoginRequest):
    db = get_db()

    user = await db.users.find_one({"email": user_in.email})
    if not user or not verify_password(user_in.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password (401 Unauthorized)",
        )

    token = create_access_token(
        user_id=str(user["_id"]),
        role=user["role"],
    )
    return Token(access_token=token)
