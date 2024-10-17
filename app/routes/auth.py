from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta

from app.models.user import User
from app.schemas.user import Token
from app.utils.security import create_access_token, verify_password, is_valid, verify_url
from dependencies import get_db
from config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas.user import UserLogin
router = APIRouter()

@router.post("/token", response_model=Token)
async def login_for_access_token(
    user_login: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    # Сначала проверяем URL
    if not verify_url(user_login.url):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid URL signature",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Затем ищем пользователя
    user = await db.scalar(select(User).filter(User.vk_id == user_login.vk_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = create_access_token(
        data={"sub": str(user.vk_id)}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}