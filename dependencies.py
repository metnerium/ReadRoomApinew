import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.security import get_current_user
from app.utils.exceptions import CREDENTIALS_EXCEPTION, USER_NOT_FOUND_EXCEPTION
from app.models.user import User
from database import get_db

logger = logging.getLogger(__name__)


async def get_current_user_dependency(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        logger.info(f"Attempting to get user with ID: {current_user.id}")

        # Используем select вместо прямого запроса
        result = await db.execute(
            select(User).filter(User.vk_id == current_user.vk_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.error(f"User not found for vk_id: {current_user.vk_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user"
            )

        logger.info(f"User found: {user.id}")
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user_dependency: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )