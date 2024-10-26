from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import text
from typing import List, Optional
from datetime import datetime

from starlette import status

from app.models.social import  Like, Bookmark, UserFollow
from app.models.user import User
from app.models.story import Story
from app.schemas.social import (
    CommentCreate, CommentUpdate, CommentResponse,
    LikeCreate, LikeResponse,
    BookmarkCreate, BookmarkUpdate, BookmarkResponse,
    UserFollowCreate, UserFollowResponse
)
from app.schemas.story import StoryResponse
from dependencies import get_current_user, get_db

router = APIRouter()

# Likes with optimistic locking
@router.post("/likes", response_model=LikeResponse)
async def create_like(
        like: LikeCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Проверяем существование истории
        story = await db.scalar(
            select(Story).filter(Story.id == like.story_id)
        )
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        # Проверяем, не существует ли уже лайк
        existing_like = await db.scalar(
            select(Like).filter(
                and_(
                    Like.user_id == current_user.id,
                    Like.story_id == like.story_id
                )
            )
        )
        if existing_like:
            raise HTTPException(status_code=400, detail="Already liked")

        # Создаем новый лайк
        db_like = Like(user_id=current_user.id, story_id=like.story_id)
        db.add(db_like)
        await db.commit()
        await db.refresh(db_like)

        # Получаем общее количество лайков
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
        raise HTTPException(status_code=400, detail="Already liked")
    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/likes/{story_id}", status_code=204)
async def delete_like(
        story_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Удаляем лайк
        result = await db.execute(
            select(Like).filter(
                and_(
                    Like.user_id == current_user.id,
                    Like.story_id == story_id
                )
            )
        )
        like = result.scalar_one_or_none()

        if not like:
            raise HTTPException(status_code=404, detail="Like not found")

        await db.delete(like)
        await db.commit()

    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bookmarks", response_model=BookmarkResponse)
async def create_bookmark(
        bookmark: BookmarkCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Проверяем существование истории
        story = await db.scalar(
            select(Story).filter(Story.id == bookmark.story_id)
        )
        if not story:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Story not found"
            )

        # Проверяем существующую закладку
        existing_bookmark = await db.scalar(
            select(Bookmark).filter(
                and_(
                    Bookmark.user_id == current_user.id,
                    Bookmark.story_id == bookmark.story_id
                )
            )
        )

        if existing_bookmark:
            # Если закладка уже существует, возвращаем ошибку
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bookmark already exists"
            )

        # Создаем новую закладку
        db_bookmark = Bookmark(
            user_id=current_user.id,
            story_id=bookmark.story_id,
            last_read_chapter=bookmark.last_read_chapter
        )
        db.add(db_bookmark)
        await db.commit()
        await db.refresh(db_bookmark)

        # Получаем общее количество закладок для истории
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bookmark already exists"
        )
    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating bookmark"
        )


@router.delete("/bookmarks/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bookmark(
        story_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Находим и удаляем закладку
        result = await db.execute(
            select(Bookmark).filter(
                and_(
                    Bookmark.user_id == current_user.id,
                    Bookmark.story_id == story_id
                )
            )
        )
        bookmark = result.scalar_one_or_none()

        if not bookmark:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bookmark not found"
            )

        await db.delete(bookmark)
        await db.commit()

    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting bookmark"
        )


# User Follow with unique constraint
@router.post("/follow", response_model=UserFollowResponse)
async def follow_user(
        follow: UserFollowCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Проверка на подписку на самого себя
        if follow.followed_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can't follow yourself"
            )

        # Проверяем существование пользователя
        followed_user = await db.scalar(
            select(User).filter(User.id == follow.followed_id)
        )
        if not followed_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Проверяем существующую подписку
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
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already following"
            )

        # Создаем подписку
        db_follow = UserFollow(
            follower_id=current_user.id,
            followed_id=follow.followed_id
        )
        db.add(db_follow)
        await db.commit()
        await db.refresh(db_follow)

        # Получаем количество подписчиков
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already following"
        )
    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while following user"
        )


@router.delete("/unfollow/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow_user(
        user_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Находим подписку
        result = await db.execute(
            select(UserFollow).filter(
                and_(
                    UserFollow.follower_id == current_user.id,
                    UserFollow.followed_id == user_id
                )
            )
        )
        follow = result.scalar_one_or_none()

        if not follow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Follow not found"
            )

        await db.delete(follow)
        await db.commit()

    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while unfollowing user"
        )


@router.get("/followers/{user_id}", response_model=List[UserFollowResponse])
async def get_followers(
        user_id: int,
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Проверяем существование пользователя
        user = await db.scalar(select(User).filter(User.id == user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Получаем подписчиков
        query = (
            select(UserFollow)
            .options(
                joinedload(UserFollow.follower),
                joinedload(UserFollow.followed)
            )
            .filter(UserFollow.followed_id == user_id)
            .order_by(UserFollow.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await db.execute(query)
        follows = result.unique().scalars().all()

        # Получаем общее количество подписчиков
        follower_count = await db.scalar(
            select(func.count())
            .select_from(UserFollow)
            .filter(UserFollow.followed_id == user_id)
        )

        return [
            UserFollowResponse(
                id=follow.id,
                follower_id=follow.follower_id,
                followed_id=follow.followed_id,
                created_at=follow.created_at,
                follower_name=follow.follower.pseudonym or follow.follower.full_name,
                followed_name=follow.followed.pseudonym or follow.followed.full_name,
                follower_count=follower_count
            ) for follow in follows
        ]

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while getting followers"
        )