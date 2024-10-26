from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import desc, func, and_, update
from typing import List, Optional
from datetime import datetime, timedelta

from app.models.social import Bookmark, Like, UserFollow
from app.models.story import Story, Genre
from app.models.user import User
from app.schemas.story import StoryCreate, StoryUpdate, StoryResponse, StoryListResponse
from app.utils.image_security import ImageSecurityUtils
from dependencies import get_current_user, get_db, logger

router = APIRouter()

@router.post("/", response_model=StoryResponse)
async def create_story(
    story: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new story with secure image handling."""
    try:
        story_data = story.dict()

        # Handle cover image if provided
        if story_data.get('cover_image_url'):
            try:
                story_data['cover_image_url'] = await ImageSecurityUtils.handle_image_upload(
                    story_data['cover_image_url']
                )
            except HTTPException as e:
                logger.error(f"Image upload failed: {str(e)}")
                raise

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

    except Exception as e:
        await db.rollback()
        logger.error(f"Error in create_story: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create story")

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
        # Build base query
        query = select(Story).options(
            joinedload(Story.author),
            joinedload(Story.likes),
            joinedload(Story.bookmarks)
        )

        # Apply filters
        if genre:
            query = query.filter(Story.genre == genre)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                Story.title.ilike(search_term) |
                Story.summary.ilike(search_term)
            )

        # Get total count for pagination
        total_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(total_query)

        # Apply sorting and pagination
        query = query.order_by(desc(getattr(Story, sort_by)))
        query = query.offset(skip).limit(limit)

        # Execute main query
        result = await db.execute(query)
        stories = result.unique().scalars().all()

        if not stories:
            return StoryListResponse(
                stories=[],
                total=0,
                page=skip // limit + 1,
                per_page=limit
            )

        # Get user interactions efficiently
        story_ids = [story.id for story in stories]
        author_ids = [story.author_id for story in stories]

        # Get likes
        user_likes_query = select(Like.story_id).filter(
            and_(Like.user_id == current_user.id, Like.story_id.in_(story_ids))
        )
        user_likes_result = await db.execute(user_likes_query)
        user_likes = set(like[0] for like in user_likes_result)

        # Get bookmarks
        user_bookmarks_query = select(Bookmark.story_id).filter(
            and_(Bookmark.user_id == current_user.id, Bookmark.story_id.in_(story_ids))
        )
        user_bookmarks_result = await db.execute(user_bookmarks_query)
        user_bookmarks = set(bookmark[0] for bookmark in user_bookmarks_result)

        # Get follows
        user_follows_query = select(UserFollow.followed_id).filter(
            and_(UserFollow.follower_id == current_user.id, UserFollow.followed_id.in_(author_ids))
        )
        user_follows_result = await db.execute(user_follows_query)
        user_follows = set(follow[0] for follow in user_follows_result)

        # Get follower counts
        follower_counts_query = (
            select(UserFollow.followed_id, func.count().label('count'))
            .filter(UserFollow.followed_id.in_(author_ids))
            .group_by(UserFollow.followed_id)
        )
        follower_counts_result = await db.execute(follower_counts_query)
        follower_counts = dict(follower_counts_result.fetchall())

        # Construct response
        stories_response = [
            StoryResponse(
                **story.__dict__,
                author_name=story.author.pseudonym or story.author.full_name,
                author_avatar_url=story.author.avatar_url,
                likes_count=len(story.likes),
                bookmarks_count=len(story.bookmarks),
                is_liked=story.id in user_likes,
                is_bookmarked=story.id in user_bookmarks,
                is_following_author=story.author_id in user_follows,
                is_my_story=story.author_id == current_user.id,
                follower_count=follower_counts.get(story.author_id, 0)
            )
            for story in stories
        ]

        return StoryListResponse(
            stories=stories_response,
            total=total,
            page=skip // limit + 1,
            per_page=limit
        )

    except Exception as e:
        logger.error(f"Error in list_stories: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch stories")

@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single story by ID with atomic view counter update."""
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
            raise HTTPException(status_code=404, detail="Story not found")

        # Atomically update views
        await db.execute(
            update(Story)
            .where(Story.id == story_id)
            .values(views=Story.views + 1)
        )
        await db.commit()

        # Get user interactions
        is_liked = await db.scalar(
            select(func.count())
            .select_from(Like)
            .filter(Like.user_id == current_user.id, Like.story_id == story_id)
        ) > 0

        is_bookmarked = await db.scalar(
            select(func.count())
            .select_from(Bookmark)
            .filter(Bookmark.user_id == current_user.id, Bookmark.story_id == story_id)
        ) > 0

        is_following_author = await db.scalar(
            select(func.count())
            .select_from(UserFollow)
            .filter(
                UserFollow.follower_id == current_user.id,
                UserFollow.followed_id == story.author_id
            )
        ) > 0

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
            is_following_author=is_following_author,
            is_my_story=story.author_id == current_user.id,
            follower_count=follower_count or 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_story: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch story")

@router.put("/{story_id}", response_model=StoryResponse)
async def update_story(
    story_id: int,
    story_update: StoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a story with secure image handling."""
    try:
        # Check story ownership
        query = select(Story).filter(
            Story.id == story_id,
            Story.author_id == current_user.id
        )
        result = await db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            raise HTTPException(
                status_code=404,
                detail="Story not found or you're not the author"
            )

        # Process updates
        update_data = story_update.dict(exclude_unset=True)

        # Handle cover image update
        if 'cover_image_url' in update_data and update_data['cover_image_url']:
            try:
                update_data['cover_image_url'] = await ImageSecurityUtils.handle_image_upload(
                    update_data['cover_image_url']
                )
            except HTTPException as e:
                logger.error(f"Image upload failed in update: {str(e)}")
                raise

        # Update story
        for field, value in update_data.items():
            setattr(story, field, value)

        await db.commit()
        await db.refresh(story)

        # Get current counts
        likes_count = await db.scalar(
            select(func.count()).where(Like.story_id == story_id)
        )
        bookmarks_count = await db.scalar(
            select(func.count()).where(Bookmark.story_id == story_id)
        )
        follower_count = await db.scalar(
            select(func.count()).where(UserFollow.followed_id == current_user.id)
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
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in update_story: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update story")

@router.delete("/{story_id}", status_code=204)
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a story."""
    try:
        query = select(Story).filter(
            Story.id == story_id,
            Story.author_id == current_user.id
        )
        result = await db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            raise HTTPException(
                status_code=404,
                detail="Story not found or you're not the author"
            )

        await db.delete(story)
        await db.commit()

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in delete_story: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete story")