from fastapi import HTTPException
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.models.chapter import Chapter
from app.models.story import Story


class ChapterFloodProtection:
    """Anti-flood protection for chapter creation."""

    def __init__(self, max_chapters: int = 10, time_window: int = 20):
        """
        Initialize flood protection for chapters.

        Args:
            max_chapters: Maximum number of chapters allowed in time window
            time_window: Time window in minutes
        """
        self.max_chapters = max_chapters
        self.time_window = time_window

    async def check_rate_limit(self, story_id: int, user_id: int, db: AsyncSession) -> bool:
        """
        Check if user has exceeded the chapter creation rate limit.

        Args:
            story_id: ID of the story
            user_id: ID of the user
            db: Database session

        Returns:
            bool: True if user can create chapter, False if limit exceeded

        Raises:
            HTTPException: If rate limit is exceeded
        """
        # Calculate the timestamp for the start of our time window
        time_threshold = datetime.utcnow() - timedelta(minutes=self.time_window)

        # Query to count chapters created by user in time window
        # We join with Story to ensure we only count chapters for stories owned by the user
        query = select(func.count()).select_from(Chapter).join(
            Story, Story.id == Chapter.story_id
        ).filter(
            and_(
                Story.author_id == user_id,
                Chapter.created_at >= time_threshold
            )
        )

        result = await db.execute(query)
        chapter_count = result.scalar()

        if chapter_count >= self.max_chapters:
            remaining_time = time_threshold + timedelta(minutes=self.time_window) - datetime.utcnow()
            minutes = int(remaining_time.total_seconds() / 60)
            seconds = int(remaining_time.total_seconds() % 60)

            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. You can create new chapter in {minutes} minutes and {seconds} seconds"
            )

        return True