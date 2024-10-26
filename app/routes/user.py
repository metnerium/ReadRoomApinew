import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from typing import List

from sqlalchemy.orm import joinedload, selectinload
from starlette import status

from app.models.user import User
from app.models.story import Story
from app.models.social import UserFollow, Like, Bookmark
from app.schemas.user import UserCreate, UserUpdate, UserInDB, UserProfile, Token
from app.schemas.story import StoryResponse
from app.utils.image_security import ImageSecurityUtils
from app.utils.security import get_password_hash, create_access_token, get_current_user, verify_url
from dependencies import get_db

router = APIRouter()

@router.get("/me", response_model=UserInDB)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserInDB)
async def update_user_me(
        user_update: UserUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    update_data = user_update.dict(exclude_unset=True)

    # Handle avatar_url separately if it's being updated
    if 'avatar_url' in update_data:
        # If it's already a data URL, validate it
        if update_data['avatar_url'].startswith('data:'):
            if not ImageSecurityUtils.validate_data_url(update_data['avatar_url']):
                raise HTTPException(status_code=400, detail="Invalid image data URL")
        else:
            # Download, validate and convert to data URL
            data_url = await ImageSecurityUtils.download_and_validate_image(update_data['avatar_url'])
            if not data_url:
                raise HTTPException(status_code=400, detail="Invalid image URL")
            update_data['avatar_url'] = data_url

    # Update user fields
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)
    return current_user


# Similar changes should be made to the register endpoint if it accepts avatar_url
@router.post("/register", response_model=Token)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await db.scalar(select(User).filter(User.vk_id == user.vk_id))
    if db_user:
        raise HTTPException(status_code=400, detail="User already registered")

    if verify_url(user.url, user.vk_id):
        # Handle avatar_url if provided
        if user.avatar_url:
            if user.avatar_url.startswith('data:'):
                if not ImageSecurityUtils.validate_data_url(user.avatar_url):
                    raise HTTPException(status_code=400, detail="Invalid image data URL")
            else:
                data_url = await ImageSecurityUtils.download_and_validate_image(user.avatar_url)
                if not data_url:
                    raise HTTPException(status_code=400, detail="Invalid image URL")
                user.avatar_url = data_url

        db_user = User(
            vk_id=user.vk_id,
            full_name=user.full_name,
            pseudonym=user.pseudonym,
            bio=user.bio,
            avatar_url=user.avatar_url,
            role=user.role
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        access_token = create_access_token(data={"sub": user.vk_id})
        return {"access_token": access_token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=400, detail="Invalid signature")

@router.get("/profile/{user_id}", response_model=UserProfile)
async def get_user_profile(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    followers_count = await db.scalar(select(func.count()).where(UserFollow.followed_id == user_id))
    following_count = await db.scalar(select(func.count()).where(UserFollow.follower_id == user_id))
    stories_count = await db.scalar(select(func.count()).where(User.stories.any(User.id == user_id)))

    return UserProfile(
        id=user.id,
        vk_id=user.vk_id,
        # email=user.email,
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
        stories_count=stories_count
    )

@router.get("/bookmarks", response_model=List[StoryResponse])
async def get_bookmarked_stories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Story).join(Story.bookmarks).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    ).filter(Story.bookmarks.any(user_id=current_user.id))

    result = await db.execute(query)
    stories = result.unique().scalars().all()

    # Get likes and follows for the current user
    user_likes = await db.execute(select(Like).filter(Like.user_id == current_user.id))
    user_likes = set(like.story_id for like in user_likes.scalars().all())

    user_follows = await db.execute(select(UserFollow).filter(UserFollow.follower_id == current_user.id))
    user_follows = set(follow.followed_id for follow in user_follows.scalars().all())

    # Get follower counts for all authors
    author_ids = [story.author_id for story in stories]
    follower_counts = await db.execute(
        select(UserFollow.followed_id, func.count(UserFollow.follower_id))
        .where(UserFollow.followed_id.in_(author_ids))
        .group_by(UserFollow.followed_id)
    )
    follower_counts = dict(follower_counts.fetchall())

    return [
        StoryResponse(
            **story.__dict__,
            author_name=story.author.pseudonym or story.author.full_name,
            author_avatar_url=story.author.avatar_url,
            likes_count=len(story.likes),
            bookmarks_count=len(story.bookmarks),
            is_liked=story.id in user_likes,
            is_bookmarked=True,  # The story is bookmarked since it's in the bookmarks list
            is_following_author=story.author_id in user_follows,
            is_my_story=story.author_id == current_user.id,
            follower_count=follower_counts.get(story.author_id, 0)

    )
        for story in stories
    ]

@router.get("/bookmarks", response_model=List[StoryResponse])
async def get_bookmarked_stories(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    try:
        # Оптимизированный запрос с единым JOIN и подзапросами
        base_query = (
            select(Story)
            .join(Bookmark, and_(
                Story.id == Bookmark.story_id,
                Bookmark.user_id == current_user.id
            ))
            .options(
                # Используем selectinload вместо joinedload для оптимизации
                selectinload(Story.author),
                selectinload(Story.likes),
                selectinload(Story.bookmarks)
            )
            .order_by(Story.updated_at.desc())
        )

        # Выполняем основной запрос
        result = await db.execute(base_query)
        stories = result.unique().scalars().all()

        # Если истории не найдены, возвращаем пустой список
        if not stories:
            return []

        # Получаем все необходимые ID для оптимизации подзапросов
        story_ids = [story.id for story in stories]
        author_ids = {story.author_id for story in stories}

        # Выполняем все дополнительные запросы параллельно
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

        # Выполняем запросы асинхронно
        likes_result, follows_result, follower_counts_result = await asyncio.gather(
            db.execute(likes_query),
            db.execute(follows_query),
            db.execute(follower_counts_query)
        )

        # Преобразуем результаты в множества для быстрого поиска
        user_likes = {like[0] for like in likes_result.fetchall()}
        user_follows = {follow[0] for follow in follows_result.fetchall()}
        follower_counts = dict(follower_counts_result.fetchall())

        # Формируем ответ
        response = [
            StoryResponse(
                **story.__dict__,
                author_name=story.author.pseudonym or story.author.full_name,
                author_avatar_url=story.author.avatar_url,
                likes_count=len(story.likes),
                bookmarks_count=len(story.bookmarks),
                is_liked=story.id in user_likes,
                is_bookmarked=True,
                is_following_author=story.author_id in user_follows,
                is_my_story=story.author_id == current_user.id,
                follower_count=follower_counts.get(story.author_id, 0)
            )
            for story in stories
        ]

        return response

    except Exception as e:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching bookmarked stories"
        )
