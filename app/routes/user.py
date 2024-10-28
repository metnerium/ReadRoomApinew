from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import func, and_
from typing import List
import asyncio

from starlette import status

from app.models.user import User
from app.models.story import Story
from app.models.social import UserFollow, Like, Bookmark
from app.schemas.user import UserCreate, UserUpdate, UserInDB, UserProfile, Token
from app.schemas.story import StoryResponse
from app.utils.image_security import ImageSecurityUtils
from app.utils.security import get_password_hash, create_access_token, verify_url
from dependencies import get_db, get_current_user, logger

router = APIRouter()

@router.get("/me", response_model=UserInDB)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user

@router.put("/me", response_model=UserInDB)
async def update_user_me(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile with secure image handling and length validation."""
    try:
        update_data = user_update.dict(exclude_unset=True)

        # Handle avatar update
        if 'avatar_url' in update_data and update_data['avatar_url']:
            try:
                update_data['avatar_url'] = await ImageSecurityUtils.handle_image_upload(
                    update_data['avatar_url']
                )
            except HTTPException as e:
                logger.error(f"Avatar upload failed: {str(e)}")
                raise

        # Additional validation checks (belt and suspenders approach)
        if 'full_name' in update_data:
            if len(update_data['full_name']) < 3:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Full name must be at least 3 characters long"
                )
            if len(update_data['full_name']) > 30:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Full name must not exceed 30 characters"
                )

        if 'pseudonym' in update_data:
            if len(update_data['pseudonym']) < 3:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Pseudonym must be at least 3 characters long"
                )
            if len(update_data['pseudonym']) > 30:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Pseudonym must not exceed 30 characters"
                )

        # Update user fields
        for field, value in update_data.items():
            setattr(current_user, field, value)

        await db.commit()
        await db.refresh(current_user)
        return current_user

    except ValueError as ve:
        # Handle Pydantic validation errors
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(ve)
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in update_user_me: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )


@router.post("/register", response_model=Token)
async def register_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user with secure image handling."""
    try:
        # Check if user already exists
        existing_user = await db.scalar(
            select(User).filter(User.vk_id == user.vk_id)
        )
        if existing_user:
            raise HTTPException(status_code=400, detail="User already registered")

        # Verify VK signature
        if not verify_url(user.url, user.vk_id):
            raise HTTPException(status_code=400, detail="Invalid signature")

        # Handle avatar if provided
        user_data = user.dict()
        if user_data.get('avatar_url'):
            try:
                user_data['avatar_url'] = await ImageSecurityUtils.handle_image_upload(
                    user_data['avatar_url']
                )
            except HTTPException as e:
                logger.error(f"Avatar upload failed during registration: {str(e)}")
                raise

        # Create new user
        db_user = User(
            vk_id=user_data['vk_id'],
            full_name=user_data['full_name'],
            pseudonym=user_data.get('pseudonym'),
            bio=user_data.get('bio'),
            avatar_url=user_data.get('avatar_url'),
            role=user_data.get('role', 'AUTHOR')
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        # Generate access token
        access_token = create_access_token(data={"sub": str(user.vk_id)})
        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in register_user: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to register user")

@router.get("/profile/{user_id}", response_model=UserProfile)
async def get_user_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user profile with statistics."""
    try:
        # Fetch user with related counts
        user = await db.scalar(select(User).filter(User.id == user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Execute count queries in parallel
        counts_queries = await asyncio.gather(
            db.scalar(
                select(func.count())
                .where(UserFollow.followed_id == user_id)
            ),
            db.scalar(
                select(func.count())
                .where(UserFollow.follower_id == user_id)
            ),
            db.scalar(
                select(func.count())
                .where(Story.author_id == user_id)
            ),
            db.scalar(
                select(func.count())
                .where(and_(
                    UserFollow.follower_id == current_user.id,
                    UserFollow.followed_id == user_id
                ))
            )
        )

        followers_count, following_count, stories_count, is_following = counts_queries

        return UserProfile(
            id=user.id,
            vk_id=user.vk_id,
            full_name=user.full_name,
            pseudonym=user.pseudonym,
            bio=user.bio,
            avatar_url=user.avatar_url,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            followers_count=followers_count,
            following_count=following_count,
            stories_count=stories_count,
            is_following=bool(is_following),
            is_self=user.id == current_user.id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_user_profile: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch user profile")

@router.get("/bookmarks", response_model=List[StoryResponse])
async def get_bookmarked_stories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's bookmarked stories with optimized queries."""
    try:
        # Fetch bookmarked stories with related data
        query = (
            select(Story)
            .join(Bookmark, and_(
                Story.id == Bookmark.story_id,
                Bookmark.user_id == current_user.id
            ))
            .options(
                joinedload(Story.author),
                joinedload(Story.likes),
                joinedload(Story.bookmarks)
            )
            .order_by(Story.updated_at.desc())
        )

        result = await db.execute(query)
        stories = result.unique().scalars().all()

        if not stories:
            return []

        # Gather IDs for batch queries
        story_ids = [story.id for story in stories]
        author_ids = {story.author_id for story in stories}

        # Execute all additional queries in parallel
        likes_query = select(Like.story_id).filter(
            and_(
                Like.user_id == current_user.id,
                Like.story_id.in_(story_ids)
            )
        )

        follows_query = select(UserFollow.followed_id).filter(
            and_(
                UserFollow.follower_id == current_user.id,
                UserFollow.followed_id.in_(author_ids)
            )
        )

        follower_counts_query = (
            select(
                UserFollow.followed_id,
                func.count(UserFollow.follower_id).label('count')
            )
            .filter(UserFollow.followed_id.in_(author_ids))
            .group_by(UserFollow.followed_id)
        )

        # Execute queries concurrently
        likes_result, follows_result, follower_counts_result = await asyncio.gather(
            db.execute(likes_query),
            db.execute(follows_query),
            db.execute(follower_counts_query)
        )

        # Process results
        user_likes = {like[0] for like in likes_result.fetchall()}
        user_follows = {follow[0] for follow in follows_result.fetchall()}
        follower_counts = dict(follower_counts_result.fetchall())

        # Construct response
        return [
            StoryResponse(
                **story.__dict__,
                author_name=story.author.pseudonym or story.author.full_name,
                author_avatar_url=story.author.avatar_url,
                likes_count=len(story.likes),
                bookmarks_count=len(story.bookmarks),
                is_liked=story.id in user_likes,
                is_bookmarked=True,  # Always true for bookmarked stories
                is_following_author=story.author_id in user_follows,
                is_my_story=story.author_id == current_user.id,
                follower_count=follower_counts.get(story.author_id, 0)
            )
            for story in stories
        ]

    except Exception as e:
        logger.error(f"Error in get_bookmarked_stories: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch bookmarked stories"
        )
