from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.models.chapter import Chapter
from app.models.story import Story
from app.models.user import User
from app.schemas.chapter import ChapterCreate, ChapterUpdate, ChapterInDB
from dependencies import get_current_user, get_db

router = APIRouter()

@router.post("/", response_model=ChapterInDB)
async def create_chapter(
    chapter: ChapterCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    story = await db.get(Story, chapter.story_id)
    if not story or story.author_id != current_user.id:
        raise HTTPException(status_code=404, detail="Story not found or you're not the author")

    db_chapter = Chapter(**chapter.dict())
    db.add(db_chapter)
    await db.commit()
    await db.refresh(db_chapter)
    return db_chapter

@router.get("/{chapter_id}", response_model=ChapterInDB)
async def get_chapter(
    chapter_id: int,
    db: AsyncSession = Depends(get_db)
):
    chapter = await db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter

@router.put("/{chapter_id}", response_model=ChapterInDB)
async def update_chapter(
    chapter_id: int,
    chapter_update: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_chapter = await db.get(Chapter, chapter_id)
    if not db_chapter or db_chapter.story.author_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chapter not found or you're not the author")

    for field, value in chapter_update.dict(exclude_unset=True).items():
        setattr(db_chapter, field, value)

    await db.commit()
    await db.refresh(db_chapter)
    return db_chapter

@router.delete("/{chapter_id}", status_code=204)
async def delete_chapter(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_chapter = await db.get(Chapter, chapter_id)
    if not db_chapter or db_chapter.story.author_id != current_user.id:
        raise HTTPException(status_code=404, detail="Chapter not found or you're not the author")

    await db.delete(db_chapter)
    await db.commit()

@router.get("/story/{story_id}", response_model=List[ChapterInDB])
async def list_chapters(
    story_id: int,
    db: AsyncSession = Depends(get_db)
):
    query = select(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.chapter_number)
    result = await db.execute(query)
    chapters = result.scalars().all()
    return chapters