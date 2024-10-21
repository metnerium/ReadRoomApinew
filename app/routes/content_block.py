from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.story import Story
from app.models.content_block import Block
from app.schemas.content_block import StoryBlock
from dependencies import get_current_user, get_db

router = APIRouter()


@router.post("/complaint", status_code=200)
async def create_story_complaint(
        content: StoryBlock,
        db: AsyncSession = Depends(get_db)
):

    # Создаем новую жалобу
    new_complaint = Block(
        story_id=content.story_id,
        user_id=content.user_id,
        author_id=content.author_id,
        reason=content.reason
    )

    db.add(new_complaint)
    await db.commit()
    await db.refresh(new_complaint)

    return {"message": "Complaint submitted successfully", "complaint_id": new_complaint.story_id}