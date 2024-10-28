from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from typing import List
import asyncio

from app.models.social import Like, Bookmark, UserFollow
from app.models.user import User
from app.models.story import Story
from app.schemas.social import (
    LikeCreate, LikeResponse,
    BookmarkCreate, BookmarkResponse,
    UserFollowCreate, UserFollowResponse
)
from dependencies import get_current_user, get_db, logger

router = APIRouter()


@router.post("/likes", response_model=LikeResponse, status_code=status.HTTP_201_CREATED)
async def create_like(
        like: LikeCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Create a new like with proper validation and conflict handling."""
    try:
        # Check if user is active
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        # Check if story exists and is available
        story = await db.scalar(
            select(Story)
            .options(joinedload(Story.author))
            .filter(Story.id == like.story_id)
        )

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

        # Check for existing like
        existing_like = await db.scalar(
            select(Like).filter(
                and_(
                    Like.user_id == current_user.id,
                    Like.story_id == like.story_id
                )
            )
        )

        if existing_like:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already liked this story"
            )

        # Create like
        db_like = Like(user_id=current_user.id, story_id=like.story_id)
        db.add(db_like)
        await db.commit()
        await db.refresh(db_like)

        # Get updated likes count
        likes_count = await db.scalar(
            select(func.count())
            .select_from(Like)
            .filter(Like.story_id == like.story_id)
        )

        return LikeResponse(
            id=db_like.id,
            user_id=current_user.id,
            story_id=like.story_id,
            created_at=db_like.created_at,
            likes_count=likes_count
        )

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already liked this story"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating like: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create like"
        )


@router.delete("/likes/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_like(
        story_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Remove a like with proper validation."""
    try:
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        # Find like
        like = await db.scalar(
            select(Like).filter(
                and_(
                    Like.user_id == current_user.id,
                    Like.story_id == story_id
                )
            )
        )

        if not like:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Like not found"
            )

        await db.delete(like)
        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting like: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete like"
        )


@router.post("/bookmarks", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
async def create_bookmark(
        bookmark: BookmarkCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Create a new bookmark with validation and conflict handling."""
    try:
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        # Check if story exists and is available
        story = await db.scalar(
            select(Story)
            .options(joinedload(Story.author))
            .filter(Story.id == bookmark.story_id)
        )

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

        # Verify chapter number if provided
        if bookmark.last_read_chapter is not None:
            chapter_exists = await db.scalar(
                select(func.count())
                .select_from(Story)
                .filter(
                    and_(
                        Story.id == bookmark.story_id,
                        Story.chapters >= bookmark.last_read_chapter
                    )
                )
            )
            if not chapter_exists:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid chapter number"
                )

        # Check for existing bookmark
        existing_bookmark = await db.scalar(
            select(Bookmark).filter(
                and_(
                    Bookmark.user_id == current_user.id,
                    Bookmark.story_id == bookmark.story_id
                )
            )
        )

        if existing_bookmark:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You have already bookmarked this story"
            )

        # Create bookmark
        db_bookmark = Bookmark(
            user_id=current_user.id,
            story_id=bookmark.story_id,
            last_read_chapter=bookmark.last_read_chapter
        )
        db.add(db_bookmark)
        await db.commit()
        await db.refresh(db_bookmark)

        # Get updated bookmarks count
        bookmarks_count = await db.scalar(
            select(func.count())
            .select_from(Bookmark)
            .filter(Bookmark.story_id == bookmark.story_id)
        )

        return BookmarkResponse(
            id=db_bookmark.id,
            user_id=current_user.id,
            story_id=bookmark.story_id,
            last_read_chapter=db_bookmark.last_read_chapter,
            created_at=db_bookmark.created_at,
            bookmarks_count=bookmarks_count
        )

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already bookmarked this story"
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating bookmark: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create bookmark"
        )


@router.delete("/bookmarks/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(
        story_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """Remove a bookmark with proper validation."""
    try:
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not active"
            )

        bookmark = await db.scalar(
            select(Bookmark).filter(
                and_(
                    Bookmark.user_id == current_user.id,
                    Bookmark.story_id == story_id
                )
            )
        )

        if not bookmark:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found"
            )

        await db.delete(bookmark)
        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting bookmark: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete bookmark"
        )

    @router.post("/follow", response_model=UserFollowResponse, status_code=status.HTTP_201_CREATED)
    async def follow_user(
            follow: UserFollowCreate,
            current_user: User = Depends(get_current_user),
            db: AsyncSession = Depends(get_db)
    ):
        """Create a new follow relationship with proper validation."""
        try:
            if not current_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is not active"
                )

            # Prevent self-following
            if follow.followed_id == current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="You cannot follow yourself"
                )

            # Check if target user exists and is active
            followed_user = await db.scalar(
                select(User).filter(User.id == follow.followed_id)
            )

            if not followed_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )

            if not followed_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This user is not available"
                )

            # Check existing follow
            existing_follow = await db.scalar(
                select(UserFollow).filter(
                    and_(
                        UserFollow.follower_id == current_user.id,
                        UserFollow.followed_id == follow.followed_id
                    )
                )
            )

            if existing_follow:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You are already following this user"
                )

            # Create follow
            db_follow = UserFollow(
                follower_id=current_user.id,
                followed_id=follow.followed_id
            )
            db.add(db_follow)
            await db.commit()
            await db.refresh(db_follow)

            # Get follower count
            follower_count = await db.scalar(
                select(func.count())
                .select_from(UserFollow)
                .filter(UserFollow.followed_id == follow.followed_id)
            )

            return UserFollowResponse(
                id=db_follow.id,
                follower_id=current_user.id,
                followed_id=follow.followed_id,
                created_at=db_follow.created_at,
                follower_name=current_user.pseudonym or current_user.full_name,
                followed_name=followed_user.pseudonym or followed_user.full_name,
                follower_count=follower_count
            )

        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already following this user"
            )
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating follow: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to follow user"
            )

    @router.delete("/unfollow/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def unfollow_user(
            user_id: int,
            current_user: User = Depends(get_current_user),
            db: AsyncSession = Depends(get_db)
    ):
        """Remove a follow relationship with proper validation."""
        try:
            if not current_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is not active"
                )

            follow = await db.scalar(
                select(UserFollow).filter(
                    and_(
                        UserFollow.follower_id == current_user.id,
                        UserFollow.followed_id == user_id
                    )
                )
            )

            if not follow:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Follow relationship not found"
                )

            await db.delete(follow)
            await db.commit()

        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error unfollowing user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to unfollow user"
            )