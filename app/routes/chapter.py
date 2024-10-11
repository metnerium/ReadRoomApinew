from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.models.chapter import Chapter
from app.models.story import Story
from app.models.user import User
from app.schemas.chapter import ChapterCreate, ChapterUpdate, ChapterInDB
from dependencies import get_current_user, get_db
import logging
router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/", response_model=ChapterInDB)
async def create_chapter(
    chapter: ChapterCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"Attempting to create chapter for story_id: {chapter.story_id}")
    try:
        story = await db.get(Story, chapter.story_id)
        if not story:
            logger.warning(f"Story with id {chapter.story_id} not found")
            raise HTTPException(status_code=404, detail="Story not found")
        if story.author_id != current_user.id:
            logger.warning(f"User {current_user.id} is not the author of story {chapter.story_id}")
            raise HTTPException(status_code=403, detail="You're not the author of this story")

        # Check if chapter_number already exists for this story
        existing_chapter = await db.execute(
            select(Chapter).filter(
                Chapter.story_id == chapter.story_id,
                Chapter.chapter_number == chapter.chapter_number
            )
        )
        if existing_chapter.scalar_one_or_none():
            logger.warning(f"Chapter number {chapter.chapter_number} already exists for story {chapter.story_id}")
            raise HTTPException(status_code=400, detail="Chapter number already exists for this story")

        db_chapter = Chapter(
            title=chapter.title,
            content=chapter.content,
            chapter_number=chapter.chapter_number,
            story_id=chapter.story_id
        )
        db.add(db_chapter)
        await db.commit()
        await db.refresh(db_chapter)
        logger.info(f"Successfully created chapter {db_chapter.id} for story {chapter.story_id}")
        return db_chapter
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error creating chapter: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while creating the chapter")

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