import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv

# 1. LOAD BIẾN MÔI TRƯỜNG
load_dotenv()
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

# 2. KẾT NỐI MONGODB
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
users_collection = db.get_collection("users")

# 3. MODELS
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

# 4. BẢO MẬT & JWT
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 5. API ENDPOINTS
app = FastAPI(title="E-Learning API")

@app.post("/register")
async def register(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email này đã được đăng ký!")
    
    hashed_password = get_password_hash(user.password)
    new_user = {
        "email": user.email,
        "full_name": user.full_name,
        "password": hashed_password
    }
    await users_collection.insert_one(new_user)
    return {"message": "Đăng ký thành công!", "email": user.email}

@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db_user = await users_collection.find_one({"email": form_data.username})
    if not db_user:
        raise HTTPException(status_code=400, detail="Sai email hoặc mật khẩu")
    
    if not verify_password(form_data.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Sai mật khẩu")
    
    access_token = create_access_token(data={"sub": db_user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
async def lay_thong_tin_cua_toi(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token bị lỗi hoặc hết hạn")
    
    user = await users_collection.find_one({"email": email})
    return {
        "xin_chao": user["full_name"],
        "email": user["email"]
    }