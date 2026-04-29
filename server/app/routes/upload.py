from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.middleware.auth import require_instructor, TokenData
import shutil
import os
import uuid

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Khai báo và đảm bảo thư mục lưu trữ file tồn tại
UPLOAD_DIR = "app/static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    # Tùy chọn: Thêm token_data để chỉ instructor mới được phép upload file
    token_data: TokenData = Depends(require_instructor) 
):
    """
    API nhận file từ frontend, lưu trữ và trả về URL.
    Chặn các file thuần âm thanh (mp3, wav, audio/*).
    """
    
    # 1. Kiểm tra định dạng (Chặn audio như yêu cầu)
    if file.content_type.startswith("audio/") or file.filename.lower().endswith(".mp3"):
        raise HTTPException(
            status_code=400, 
            detail="Không hỗ trợ file thuần âm thanh. Vui lòng tải lên Video hoặc Tài liệu. (400 Bad Request)"
        )

    # 2. Tạo tên file duy nhất để tránh bị ghi đè khi upload trùng tên
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    file_location = os.path.join(UPLOAD_DIR, unique_filename)

    # 3. Lưu file vật lý vào thư mục static
    try:
        with open(file_location, "wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi lưu file: {str(e)}")

    # 4. Trả về đường dẫn tĩnh để frontend có thể lưu vào DB và hiển thị
    return {
        "message": "Upload thành công",
        "file_url": f"/static/uploads/{unique_filename}"
    }
