from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy import desc, func
from typing import List, Optional
from datetime import datetime, timedelta

from app.models.social import Bookmark
from app.models.story import Story, Genre
from app.models.user import User
from app.schemas.story import StoryCreate, StoryUpdate, StoryResponse, StoryListResponse
from dependencies import get_current_user, get_db

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
        likes_count=0,
        bookmarks_count=0
    )

@router.get("/", response_model=StoryListResponse)
async def list_stories(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        genre: Optional[Genre] = None,
        search: Optional[str] = None,
        sort_by: str = Query("rating", regex="^(rating|views|created_at)$"),
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

    return StoryListResponse(
        stories=[
            StoryResponse(
                **story.__dict__,
                author_name=story.author.pseudonym or story.author.full_name,
                likes_count=len(story.likes),
                bookmarks_count=len(story.bookmarks)
            )
            for story in stories
        ],
        total=total,
        page=skip // limit + 1,
        per_page=limit
    )

@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
        story_id: int,
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

    return StoryResponse(
        **story.__dict__,
        author_name=story.author.pseudonym or story.author.full_name,
        likes_count=len(story.likes),
        bookmarks_count=len(story.bookmarks)
    )

@router.put("/{story_id}", response_model=StoryResponse)
async def update_story(
        story_id: int,
        story_update: StoryUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    query = select(Story).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    ).filter(Story.id == story_id, Story.author_id == current_user.id)
    result = await db.execute(query)
    db_story = result.scalar_one_or_none()

    if not db_story:
        raise HTTPException(status_code=404, detail="Story not found or you're not the author")

    for field, value in story_update.dict(exclude_unset=True).items():
        setattr(db_story, field, value)

    await db.commit()
    await db.refresh(db_story)

    return StoryResponse(
        **db_story.__dict__,
        author_name=current_user.pseudonym or current_user.full_name,
        likes_count=len(db_story.likes),
        bookmarks_count=len(db_story.bookmarks)
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

@router.get("/continue-reading", response_model=List[StoryResponse])
async def get_continue_reading(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    query = select(Story).join(Story.bookmarks).options(
        joinedload(Story.author),
        joinedload(Story.likes),
        joinedload(Story.bookmarks)
    ).filter(
        Story.bookmarks.any(
            (Bookmark.user_id == current_user.id) &
            (Bookmark.last_read_chapter != None)
        )
    ).order_by(desc(Bookmark.updated_at)).limit(5)

    result = await db.execute(query)
    stories = result.unique().scalars().all()

    return [
        StoryResponse(
            id=story.id,
            title=story.title,
            summary=story.summary,
            genre=story.genre,
            cover_image_url=story.cover_image_url,
            author_id=story.author_id,
            created_at=story.created_at,
            updated_at=story.updated_at,
            author_name=story.author.pseudonym or story.author.full_name,
            likes_count=len(story.likes),
            bookmarks_count=len(story.bookmarks),
            rating=story.rating,
            views=story.views
        )
        for story in stories
    ]

@router.get("/popular", response_model=List[StoryResponse])
async def get_popular_stories(
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

    return [
        StoryResponse(
            id=story.id,
            title=story.title,
            summary=story.summary,
            genre=story.genre,
            cover_image_url=story.cover_image_url,
            author_id=story.author_id,
            created_at=story.created_at,
            updated_at=story.updated_at,
            author_name=story.author.pseudonym or story.author.full_name,
            likes_count=len(story.likes),
            bookmarks_count=len(story.bookmarks),
            rating=story.rating,
            views=story.views
        )
        for story in stories
    ]