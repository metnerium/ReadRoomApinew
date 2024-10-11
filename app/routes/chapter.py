from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
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
    try:
        query = select(Story).filter(Story.id == chapter.story_id)
        result = await db.execute(query)
        story = result.scalar_one_or_none()

        if not story:
            logger.warning(f"Story with id {chapter.story_id} not found")
            raise HTTPException(status_code=404, detail="Story not found")
        if story.author_id != current_user.id:
            logger.warning(f"User {current_user.id} is not the author of story {chapter.story_id}")
            raise HTTPException(status_code=403, detail="You're not the author of this story")

        db_chapter = Chapter(**chapter.dict())
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
    try:
        query = select(Chapter).filter(Chapter.id == chapter_id)
        result = await db.execute(query)
        chapter = result.scalar_one_or_none()
        if not chapter:
            logger.warning(f"Chapter with id {chapter_id} not found")
            raise HTTPException(status_code=404, detail="Chapter not found")
        return chapter
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error fetching chapter {chapter_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while fetching the chapter")

@router.put("/{chapter_id}", response_model=ChapterInDB)
async def update_chapter(
    chapter_id: int,
    chapter_update: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Chapter).options(joinedload(Chapter.story)).filter(Chapter.id == chapter_id)
        result = await db.execute(query)
        db_chapter = result.scalar_one_or_none()

        if not db_chapter:
            logger.warning(f"Chapter with id {chapter_id} not found")
            raise HTTPException(status_code=404, detail="Chapter not found")
        if db_chapter.story.author_id != current_user.id:
            logger.warning(f"User {current_user.id} is not the author of the story for chapter {chapter_id}")
            raise HTTPException(status_code=403, detail="You're not the author of this story")

        for field, value in chapter_update.dict(exclude_unset=True).items():
            setattr(db_chapter, field, value)

        await db.commit()
        await db.refresh(db_chapter)
        logger.info(f"Successfully updated chapter {chapter_id}")
        return db_chapter
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error updating chapter {chapter_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while updating the chapter")
@router.delete("/{chapter_id}", status_code=204)
async def delete_chapter(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Используем select вместо db.get для асинхронного получения главы
        query = select(Chapter).options(joinedload(Chapter.story)).filter(Chapter.id == chapter_id)
        result = await db.execute(query)
        db_chapter = result.scalar_one_or_none()

        if not db_chapter:
            logger.warning(f"Chapter with id {chapter_id} not found")
            raise HTTPException(status_code=404, detail="Chapter not found")

        if db_chapter.story.author_id != current_user.id:
            logger.warning(f"User {current_user.id} is not the author of the story for chapter {chapter_id}")
            raise HTTPException(status_code=403, detail="You're not the author of this story")

        await db.delete(db_chapter)
        await db.commit()
        logger.info(f"Successfully deleted chapter {chapter_id}")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error deleting chapter {chapter_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while deleting the chapter")

@router.get("/story/{story_id}", response_model=List[ChapterInDB])
async def list_chapters(
    story_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Chapter).filter(Chapter.story_id == story_id).order_by(Chapter.chapter_number)
        result = await db.execute(query)
        chapters = result.scalars().all()
        return chapters
    except Exception as e:
        logger.error(f"Error listing chapters for story {story_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while listing chapters")