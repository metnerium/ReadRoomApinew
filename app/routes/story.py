from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime, timedelta

from app.models.social import Bookmark, Like, UserFollow
from app.models.story import Story, Genre
from app.models.user import User
from app.schemas.story import StoryCreate, StoryUpdate, StoryResponse, StoryListResponse
from dependencies import get_current_user, get_db, logger



router = APIRouter()


@router.post("/", response_model=StoryResponse)
async def create_story(
    story: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_story = Story(**story.dict(), author_id=current_user.id)
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
    query = select(Story).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    )
    if genre:
        query = query.filter(Story.genre == genre)
    if search:
        query = query.filter(Story.title.ilike(f"%{search}%"))

    total = await db.scalar(select(func.count()).select_from(query.subquery()))

    query = query.order_by(desc(getattr(Story, sort_by)))
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    stories = result.unique().scalars().all()

    # Get likes, bookmarks, and follows for the current user
    user_likes = await db.execute(select(Like).filter(Like.user_id == current_user.id))
    user_likes = set(like.story_id for like in user_likes.scalars().all())

    user_bookmarks = await db.execute(select(Bookmark).filter(Bookmark.user_id == current_user.id))
    user_bookmarks = set(bookmark.story_id for bookmark in user_bookmarks.scalars().all())

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

    return StoryListResponse(
        stories=[
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
        ],
        total=total,
        page=skip // limit + 1,
        per_page=limit
    )

@router.get("/continue-reading", response_model=List[StoryResponse])
async def get_continue_reading(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Story).join(Bookmark).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    ).filter(
        Bookmark.user_id == current_user.id,
        Bookmark.last_read_chapter != None
    ).order_by(desc(Bookmark.created_at)).limit(5)

    result = await db.execute(query)
    stories = result.unique().scalars().all()

    # Get likes, bookmarks, and follows for the current user
    user_likes = await db.execute(select(Like).filter(Like.user_id == current_user.id))
    user_likes = set(like.story_id for like in user_likes.scalars().all())

    user_bookmarks = await db.execute(select(Bookmark).filter(Bookmark.user_id == current_user.id))
    user_bookmarks = set(bookmark.story_id for bookmark in user_bookmarks.scalars().all())

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
            is_bookmarked=story.id in user_bookmarks,
            is_following_author=story.author_id in user_follows,
            is_my_story=story.author_id == current_user.id,
            follower_count=follower_counts.get(story.author_id, 0)
        )
        for story in stories
    ]

@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Story).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    ).filter(Story.id == story_id)
    result = await db.execute(query)
    story = result.unique().scalar_one_or_none()

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    story.views += 1
    await db.commit()

    # Check if the current user has liked the story
    is_liked = await db.scalar(
        select(func.count()).select_from(Like).filter(
            Like.user_id == current_user.id,
            Like.story_id == story_id
        )
    ) > 0

    # Check if the current user has bookmarked the story
    is_bookmarked = await db.scalar(
        select(func.count()).select_from(Bookmark).filter(
            Bookmark.user_id == current_user.id,
            Bookmark.story_id == story_id
        )
    ) > 0

    # Check if the current user is following the author
    is_following_author = await db.scalar(
        select(func.count()).select_from(UserFollow).filter(
            UserFollow.follower_id == current_user.id,
            UserFollow.followed_id == story.author_id
        )
    ) > 0

    # Get the follower count for the author
    follower_count = await db.scalar(
        select(func.count()).select_from(UserFollow).filter(
            UserFollow.followed_id == story.author_id
        )
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
        follower_count=follower_count
    )
@router.get("/popular", response_model=List[StoryResponse])
async def get_popular_stories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    one_week_ago = datetime.now() - timedelta(days=7)
    query = select(Story).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    ).filter(
        Story.created_at >= one_week_ago
    ).order_by(desc(Story.views)).limit(10)

    result = await db.execute(query)
    stories = result.unique().scalars().all()

    # Get likes, bookmarks, and follows for the current user
    user_likes = await db.execute(select(Like.story_id).filter(Like.user_id == current_user.id))
    user_likes = set(like.story_id for like in user_likes.scalars().all())

    user_bookmarks = await db.execute(select(Bookmark.story_id).filter(Bookmark.user_id == current_user.id))
    user_bookmarks = set(bookmark.story_id for bookmark in user_bookmarks.scalars().all())

    user_follows = await db.execute(select(UserFollow.followed_id).filter(UserFollow.follower_id == current_user.id))
    user_follows = set(follow.followed_id for follow in user_follows.scalars().all())

    # Get follower counts for all authors
    author_ids = [story.author_id for story in stories]
    follower_counts = await db.execute(
        select(UserFollow.followed_id, func.count(UserFollow.follower_id).label('count'))
        .where(UserFollow.followed_id.in_(author_ids))
        .group_by(UserFollow.followed_id)
    )
    follower_counts = dict(follower_counts.fetchall())

    return [
        StoryResponse(
            id=story.id,
            title=story.title,
            content=story.summary,
            genre=story.genre,
            created_at=story.created_at,
            updated_at=story.updated_at,
            views=story.views,
            rating=story.rating,
            author_id=story.author_id,
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

@router.put("/{story_id}", response_model=StoryResponse)
async def update_story(
    story_id: int,
    story_update: StoryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Change the query to not use joinedload for this operation
    query = select(Story).filter(Story.id == story_id, Story.author_id == current_user.id)
    result = await db.execute(query)
    db_story = result.scalar_one_or_none()

    if not db_story:
        raise HTTPException(status_code=404, detail="Story not found or you're not the author")

    for field, value in story_update.dict(exclude_unset=True).items():
        setattr(db_story, field, value)

    await db.commit()
    await db.refresh(db_story)

    # Fetch related data separately
    likes_count = await db.scalar(select(func.count()).where(Like.story_id == story_id))
    bookmarks_count = await db.scalar(select(func.count()).where(Bookmark.story_id == story_id))
    follower_count = await db.scalar(select(func.count()).where(UserFollow.followed_id == current_user.id))

    return StoryResponse(
        **db_story.__dict__,
        author_name=current_user.pseudonym or current_user.full_name,
        author_avatar_url=current_user.avatar_url,
        likes_count=likes_count,
        bookmarks_count=bookmarks_count,
        is_liked=False,  # The user can't like their own stories
        is_bookmarked=False,  # The user's own stories are not bookmarked
        is_following_author=False,  # The user can't follow themselves
        is_my_story=True,
        follower_count=follower_count
    )
@router.delete("/{story_id}", status_code=204)
async def delete_story(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Story).filter(Story.id == story_id, Story.author_id == current_user.id)
    result = await db.execute(query)
    db_story = result.scalar_one_or_none()

    if not db_story:
        raise HTTPException(status_code=404, detail="Story not found or you're not the author")

    await db.delete(db_story)
    await db.commit()

