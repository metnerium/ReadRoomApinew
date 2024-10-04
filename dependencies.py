import logging
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.security import get_current_user
from app.utils.exceptions import CREDENTIALS_EXCEPTION, USER_NOT_FOUND_EXCEPTION
from app.models.user import User
from database import get_db

logger = logging.getLogger(__name__)

async def get_current_user_dependency(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        logger.info(f"Attempting to get user with ID: {current_user.id}")
        user = await User.get_by_email(db, current_user.email)
        if not user:
            logger.error(f"User not found for email: {current_user.email}")
            raise USER_NOT_FOUND_EXCEPTION
        logger.info(f"User found: {user.id}")
        return user
    except Exception as e:
        logger.error(f"Error in get_current_user_dependency: {str(e)}")
        raise CREDENTIALS_EXCEPTION