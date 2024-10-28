from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import desc, func, and_, update
from typing import List, Optional
from datetime import datetime, timedelta

from starlette import status

from app.flood_protection import FloodProtection
from app.models.social import Bookmark, Like, UserFollow, StoryView
from app.models.story import Story, Genre
from app.models.user import User
from app.schemas.story import StoryCreate, StoryUpdate, StoryResponse, StoryListResponse
from app.utils.image_security import ImageSecurityUtils
from dependencies import get_current_user, get_db, logger

router = APIRouter()
flood_protection = FloodProtection(max_stories=5, time_window=20)

@router.post("/", response_model=StoryResponse, status_code=status.HTTP_201_CREATED)
async def create_story(
    story: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new story with flood protection and secure image handling."""
    try:
        # Check if user is banned or inactive
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        # Check flood protection
        await flood_protection.check_rate_limit(current_user.id, db)

        story_data = story.dict()

        # Validate story title length
        if len(story_data['title']) < 3:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Story title must be at least 3 characters long"
            )
        if len(story_data['title']) > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Story title must not exceed 100 characters"
            )

        # Handle cover image if provided
        if story_data.get('cover_image_url'):
            try:
                story_data['cover_image_url'] = await ImageSecurityUtils.handle_image_upload(
                    story_data['cover_image_url']
                )
            except HTTPException as e:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Invalid image format or size"
                )

        # Create story
        db_story = Story(**story_data, author_id=current_user.id)
        db.add(db_story)
        await db.commit()
        await db.refresh(db_story)

        return StoryResponse(
            **db_story.__dict__,
            author_name=current_user.pseudonym or current_user.full_name,
            author_avatar_url=current_user.avatar_url,
            likes_count=0,
            bookmarks_count=0,
            is_liked=False,
            is_bookmarked=False,
            is_following_author=False,
            is_my_story=True,
            follower_count=0
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating story: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create story"
        )

@router.get("/", response_model=StoryListResponse)
async def list_stories(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    genre: Optional[Genre] = None,
    search: Optional[str] = None,
    sort_by: str = Query("rating", regex="^(rating|views|created_at)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List stories with filtering, sorting, and pagination."""
    try:
        # Validate pagination parameters
        if skip < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Skip value cannot be negative"
            )
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Limit must be between 1 and 100"
            )

        # Validate search term length
        if search and len(search) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Search term must be at least 2 characters long"
            )

        # Build query
        query = select(Story).options(
            joinedload(Story.author),
            joinedload(Story.likes),
            joinedload(Story.bookmarks)
        ).filter(Story.author.has(is_active=True))  # Only stories from active users

        if genre:
            query = query.filter(Story.genre == genre)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                Story.title.ilike(search_term) |
                Story.summary.ilike(search_term)
            )

        # Get total count
        total_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(total_query)

        # Apply sorting and pagination
        if sort_by not in ["rating", "views", "created_at"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid sort parameter"
            )

        query = query.order_by(desc(getattr(Story, sort_by)))
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        stories = result.unique().scalars().all()

        # Process stories and return response
        story_responses = []
        for story in stories:
            is_liked = any(like.user_id == current_user.id for like in story.likes)
            is_bookmarked = any(bookmark.user_id == current_user.id for bookmark in story.bookmarks)
            is_following = await db.scalar(
                select(UserFollow)
                .filter(
                    and_(
                        UserFollow.follower_id == current_user.id,
                        UserFollow.followed_id == story.author_id
                    )
                )
            )

            story_responses.append(
                StoryResponse(
                    **story.__dict__,
                    author_name=story.author.pseudonym or story.author.full_name,
                    author_avatar_url=story.author.avatar_url,
                    likes_count=len(story.likes),
                    bookmarks_count=len(story.bookmarks),
                    is_liked=is_liked,
                    is_bookmarked=is_bookmarked,
                    is_following_author=bool(is_following),
                    is_my_story=story.author_id == current_user.id,
                    follower_count=await db.scalar(
                        select(func.count())
                        .select_from(UserFollow)
                        .filter(UserFollow.followed_id == story.author_id)
                    )
                )
            )

        return StoryListResponse(
            stories=story_responses,
            total=total,
            page=skip // limit + 1,
            per_page=limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing stories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch stories"
        )

@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single story by ID with view tracking."""
    try:
        # Fetch story with related data
        query = select(Story).options(
            joinedload(Story.author),
            joinedload(Story.likes),
            joinedload(Story.bookmarks)
        ).filter(Story.id == story_id)

        result = await db.execute(query)
        story = result.unique().scalar_one_or_none()

        if not story:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Story not found"
            )

        if not story.author.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This story is not available"
            )

        # Track view if not already viewed
        existing_view = await db.scalar(
            select(StoryView).filter(
                and_(
                    StoryView.story_id == story_id,
                    StoryView.user_id == current_user.id
                )
            )
        )

        if not existing_view:
            new_view = StoryView(
                story_id=story_id,
                user_id=current_user.id
            )
            story.views += 1
            db.add(new_view)
            await db.commit()
            await db.refresh(story)

        # Get user interactions
        is_liked = any(like.user_id == current_user.id for like in story.likes)
        is_bookmarked = any(bookmark.user_id == current_user.id for bookmark in story.bookmarks)
        is_following = await db.scalar(
            select(UserFollow).filter(
                and_(
                    UserFollow.follower_id == current_user.id,
                    UserFollow.followed_id == story.author_id
                )
            )
        )

        follower_count = await db.scalar(
            select(func.count())
            .select_from(UserFollow)
            .filter(UserFollow.followed_id == story.author_id)
        )

        return StoryResponse(
            **story.__dict__,
            author_name=story.author.pseudonym or story.author.full_name,
            author_avatar_url=story.author.avatar_url,
            likes_count=len(story.likes),
            bookmarks_count=len(story.bookmarks),
            is_liked=is_liked,
            is_bookmarked=is_bookmarked,
            is_following_author=bool(is_following),
            is_my_story=story.author_id == current_user.id,
            follower_count=follower_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching story {story_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch story"
        )

@router.put("/{story_id}", response_model=StoryResponse)
async def update_story(
    story_id: int,
    story_update: StoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a story with validation and secure image handling."""
    try:
        # Check if user is active
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        # Fetch story with verification
        query = select(Story).filter(Story.id == story_id)
        result = await db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Story not found"
            )

        # Check ownership
        if story.author_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own stories"
            )

        update_data = story_update.dict(exclude_unset=True)

        # Validate title length if provided
        if 'title' in update_data:
            if len(update_data['title']) < 3:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Story title must be at least 3 characters long"
                )
            if len(update_data['title']) > 100:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Story title must not exceed 100 characters"
                )

        # Handle cover image update
        if 'cover_image_url' in update_data and update_data['cover_image_url']:
            try:
                update_data['cover_image_url'] = await ImageSecurityUtils.handle_image_upload(
                    update_data['cover_image_url']
                )
            except HTTPException:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail="Invalid image format or size"
                )

        # Update story
        for field, value in update_data.items():
            setattr(story, field, value)

        await db.commit()
        await db.refresh(story)

        # Get current counts
        likes_count = len(story.likes)
        bookmarks_count = len(story.bookmarks)
        follower_count = await db.scalar(
            select(func.count())
            .select_from(UserFollow)
            .filter(UserFollow.followed_id == current_user.id)
        )

        return StoryResponse(
            **story.__dict__,
            author_name=current_user.pseudonym or current_user.full_name,
            author_avatar_url=current_user.avatar_url,
            likes_count=likes_count,
            bookmarks_count=bookmarks_count,
            is_liked=False,
            is_bookmarked=False,
            is_following_author=False,
            is_my_story=True,
            follower_count=follower_count
        )

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating story {story_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update story"
        )

@router.delete("/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a story with proper authorization checks."""
    try:
        # Check if user is active
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        # Fetch story
        query = select(Story).filter(Story.id == story_id)
        result = await db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Story not found"
            )

        # Check ownership
        if story.author_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own stories"
            )

        # Delete story and related data (cascade should handle relations)
        await db.delete(story)
        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting story {story_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete story"
        )