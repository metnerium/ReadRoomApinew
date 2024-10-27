from fastapi import HTTPException
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.models.story import Story


class FloodProtection:
    """Anti-flood protection for story creation."""

    def __init__(self, max_stories: int = 5, time_window: int = 20):
        """
        Initialize flood protection.

        Args:
            max_stories: Maximum number of stories allowed in time window
            time_window: Time window in minutes
        """
        self.max_stories = max_stories
        self.time_window = time_window

    async def check_rate_limit(self, user_id: int, db: AsyncSession) -> bool:
        """
        Check if user has exceeded the rate limit.

        Args:
            user_id: ID of the user
            db: Database session

        Returns:
            bool: True if user can create story, False if limit exceeded

        Raises:
            HTTPException: If rate limit is exceeded
        """
        # Calculate the timestamp for the start of our time window
        time_threshold = datetime.utcnow() - timedelta(minutes=self.time_window)

        # Query to count stories created by user in time window
        query = select(func.count()).select_from(Story).filter(
            and_(
                Story.author_id == user_id,
                Story.created_at >= time_threshold
            )
        )

        result = await db.execute(query)
        story_count = result.scalar()

        if story_count >= self.max_stories:
            remaining_time = time_threshold + timedelta(minutes=self.time_window) - datetime.utcnow()
            minutes = int(remaining_time.total_seconds() / 60)
            seconds = int(remaining_time.total_seconds() % 60)

            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. You can create new story in {minutes} minutes and {seconds} seconds"
            )

        return True