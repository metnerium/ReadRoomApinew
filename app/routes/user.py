from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List

from sqlalchemy.orm import joinedload

from app.models.user import User, UserRole
from app.models.story import Story
from app.models.social import UserFollow, Like
from app.schemas.user import UserCreate, UserUpdate, UserInDB, UserProfile, Token
from app.schemas.story import StoryResponse
from app.utils.security import get_password_hash, create_access_token, get_current_user
from dependencies import get_db

router = APIRouter()

@router.post("/register", response_model=Token)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await db.scalar(select(User).filter(User.email == user.email))
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        pseudonym=user.pseudonym,
        bio=user.bio,
        avatar_url=user.avatar_url,
        role=user.role
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserInDB)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/me", response_model=UserInDB)
async def update_user_me(
        user_update: UserUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)
    return current_user

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
        email=user.email,
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
@router.get("/authors", response_model=List[UserProfile])
async def get_authors(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    query = select(User).filter(User.role == UserRole.AUTHOR).offset(skip).limit(limit)
    result = await db.execute(query)
    authors = result.scalars().all()

    author_profiles = []
    for author in authors:
        followers_count = await db.scalar(select(func.count()).where(UserFollow.followed_id == author.id))
        following_count = await db.scalar(select(func.count()).where(UserFollow.follower_id == author.id))
        stories_count = await db.scalar(select(func.count()).where(Story.author_id == author.id))

        author_profiles.append(
            UserProfile(
                **author.__dict__,
                followers_count=followers_count,
                following_count=following_count,
                stories_count=stories_count
            )
        )

    return author_profiles

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
            follower_count=follower_counts.get(story.author_id, 0)
        )
        for story in stories
    ]
