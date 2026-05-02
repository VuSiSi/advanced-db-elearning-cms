import random
import time
import uuid

from fastapi import APIRouter, HTTPException, status

from app.database import get_db
from app.middleware.auth import create_access_token, hash_password, verify_password
from app.models import LoginRequest, Token, UserCreate, UserOut


router = APIRouter(prefix="/api/auth", tags=["auth"])

captcha_store = {}
CAPTCHA_TTL_SECONDS = 300


def cleanup_expired_captchas():
    now = time.time()
    expired_tokens = [
        token
        for token, captcha in captcha_store.items()
        if captcha["expires_at"] <= now
    ]
    for token in expired_tokens:
        captcha_store.pop(token, None)


def verify_captcha(captcha_token: str, captcha_answer: str):
    cleanup_expired_captchas()

    if not captcha_token or not captcha_answer:
        raise HTTPException(status_code=400, detail="Captcha is required")

    captcha = captcha_store.pop(captcha_token, None)
    if not captcha:
        raise HTTPException(status_code=400, detail="Captcha is invalid or expired")

    if str(captcha_answer).strip() != str(captcha["answer"]):
        raise HTTPException(status_code=400, detail="Captcha answer is incorrect")


@router.get("/captcha")
async def get_captcha():
    cleanup_expired_captchas()

    left = random.randint(1, 9)
    right = random.randint(1, 9)
    captcha_token = str(uuid.uuid4())

    captcha_store[captcha_token] = {
        "answer": left + right,
        "expires_at": time.time() + CAPTCHA_TTL_SECONDS,
    }

    return {
        "captcha_token": captcha_token,
        "question": f"{left} + {right} = ?",
    }


@router.post("/register", response_model=UserOut, status_code=201)
async def register(user_in: UserCreate):
    verify_captcha(user_in.captcha_token, user_in.captcha_answer)

    db = get_db()

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
    verify_captcha(user_in.captcha_token, user_in.captcha_answer)

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
