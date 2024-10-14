import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import desc
from typing import List
from app.models.story import Story
from app.models.user import User
from app.schemas.usercontent import UserStoryResponse
from dependencies import get_current_user, get_db

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/users/{user_id}/stories", response_model=List[UserStoryResponse])
async def get_user_stories(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"Fetching stories for user_id: {user_id}")
    try:
        # Check if the user exists
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        query = select(Story).options(
            joinedload(Story.likes),
            joinedload(Story.bookmarks)
        ).filter(Story.author_id == user_id).order_by(desc(Story.created_at))

        result = await db.execute(query)
        stories = result.unique().scalars().all()

        user_stories = []
        for story in stories:
            try:
                user_story = UserStoryResponse(
                    id=story.id,
                    title=story.title,
                    summary=story.summary,
                    genre=story.genre,
                    cover_image_url=story.cover_image_url,
                    created_at=story.created_at,
                    updated_at=story.updated_at,
                    likes_count=len(story.likes),
                    bookmarks_count=len(story.bookmarks),
                    views=story.views,
                    rating=float(story.rating) if story.rating is not None else 0.0
                )
                user_stories.append(user_story)
                logger.info(f"Processed story: {story.id}")
            except Exception as e:
                logger.error(f"Error processing story {story.id}: {str(e)}")
                # Optionally, you can choose to skip this story or handle the error differently

        logger.info(f"Returning {len(user_stories)} stories for user {user_id}")
        return user_stories
    except Exception as e:
        logger.error(f"Error in get_user_stories: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while fetching user stories")