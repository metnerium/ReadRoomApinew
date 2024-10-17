from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import timedelta

from app.models.user import User
from app.schemas.user import Token
from app.utils.security import create_access_token, verify_password, is_valid
from dependencies import get_db
from config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas.user import UserLogin
router = APIRouter()

@router.post("/token", response_model=Token)
async def login_for_access_token(
    user: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(select(User).filter(User.vk_id == user.vk_id))
    if not user or not is_valid(user.url):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = create_access_token(
        data={"sub": user.vk_id}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}
