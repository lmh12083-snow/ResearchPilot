from pathlib import Path
from time import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    UserUpdate,
    PasswordChange,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ALLOWED_AVATAR_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


def _extract_token(authorization: Optional[str] = Header(None)) -> str:
    """Extract Bearer token from Authorization header."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    return authorization[7:]


def get_current_user(db: Session = Depends(get_db), token: str = Depends(_extract_token)) -> User:
    """Dependency — validates JWT and returns the current user."""
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(current_user: User = Depends(get_current_user)):
    """V1: stateless logout — frontend discards the token."""
    return {"message": "Logged out successfully"}


@router.patch("/me", response_model=UserResponse)
def update_me(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update username / email (only provided fields)."""
    if data.username is not None and data.username != current_user.username:
        if db.query(User).filter(User.username == data.username).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        current_user.username = data.username
    if data.email is not None and data.email != current_user.email:
        if db.query(User).filter(User.email == data.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        current_user.email = data.email
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/avatar", response_model=UserResponse)
def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a new avatar image (≤2MB, png/jpg/webp/gif)."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_AVATAR_EXT:
        raise HTTPException(status_code=400, detail="仅支持 png/jpg/webp/gif 图片")
    content = file.file.read()
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="头像图片不能超过 2MB")

    avatar_dir = Path(settings.UPLOAD_PATH) / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{current_user.id}_{int(time())}{ext}"
    (avatar_dir / filename).write_bytes(content)

    # Remove the previous avatar file, if any.
    if current_user.avatar:
        try:
            old = Path(settings.UPLOAD_PATH) / current_user.avatar
            if old.exists():
                old.unlink()
        except OSError:
            pass

    current_user.avatar = f"avatars/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/avatar")
def get_avatar(
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Serve the current user's avatar.

    Supports both header-based (axios) and query-param (``<img>``) auth, mirroring
    the paper-file endpoint.
    """
    auth_token = (
        authorization[7:]
        if authorization and authorization.startswith("Bearer ")
        else token
    )
    if not auth_token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    payload = decode_access_token(auth_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(payload.get("sub", 0))).first()
    if not user or not user.avatar:
        raise HTTPException(status_code=404, detail="Avatar not set")

    avatar_path = Path(settings.UPLOAD_PATH) / user.avatar
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="Avatar file not found")
    return FileResponse(path=str(avatar_path))


@router.delete("/avatar", response_model=UserResponse)
def delete_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove the avatar and reset to the default letter avatar."""
    if current_user.avatar:
        try:
            old = Path(settings.UPLOAD_PATH) / current_user.avatar
            if old.exists():
                old.unlink()
        except OSError:
            pass
        current_user.avatar = None
        db.commit()
        db.refresh(current_user)
    return current_user


@router.put("/password", status_code=status.HTTP_200_OK)
def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change password after verifying the current one."""
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    current_user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Password updated successfully"}
