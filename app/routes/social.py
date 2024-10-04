from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from sqlalchemy.orm import selectinload

from app.models.social import Comment, Like, Bookmark, UserFollow
from app.models.user import User
from app.models.story import Story
from app.schemas.social import (
    CommentCreate, CommentUpdate, CommentResponse,
    LikeCreate, LikeInDB,
    BookmarkCreate, BookmarkUpdate, BookmarkInDB,
    UserFollowCreate, UserFollowResponse
)
from dependencies import get_current_user, get_db

router = APIRouter()

# Comments
@router.post("/comments", response_model=CommentResponse)
async def create_comment(
    comment: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    async with db.begin():
        story = await db.get(Story, comment.story_id)
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        db_comment = Comment(**comment.dict(), user_id=current_user.id)
        db.add(db_comment)
        await db.flush()
        await db.refresh(db_comment)

    return CommentResponse(
        **db_comment.__dict__,
        user_name=current_user.pseudonym or current_user.full_name
    )

@router.get("/comments/{story_id}", response_model=List[CommentResponse])
async def list_comments(story_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Comment).filter(Comment.story_id == story_id).options(
        selectinload(Comment.user)
    ).order_by(Comment.created_at.desc())
    result = await db.execute(query)
    comments = result.unique().scalars().all()

    return [
        CommentResponse(
            **comment.__dict__,
            user_name=comment.user.pseudonym or comment.user.full_name
        ) for comment in comments
    ]

@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: int,
    comment_update: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    async with db.begin():
        db_comment = await db.get(Comment, comment_id)
        if not db_comment or db_comment.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Comment not found or you're not the author")

        for key, value in comment_update.dict().items():
            setattr(db_comment, key, value)
        await db.flush()
        await db.refresh(db_comment)

    return CommentResponse(
        **db_comment.__dict__,
        user_name=current_user.pseudonym or current_user.full_name
    )

@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    async with db.begin():
        db_comment = await db.get(Comment, comment_id)
        if not db_comment or db_comment.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Comment not found or you're not the author")

        await db.delete(db_comment)

# Likes
@router.post("/likes", response_model=LikeInDB)
async def create_like(
    like: LikeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    story = await db.get(Story, like.story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    existing_like = await db.execute(
        select(Like).filter(Like.user_id == current_user.id, Like.story_id == like.story_id)
    )
    if existing_like.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You've already liked this story")

    db_like = Like(**like.dict(), user_id=current_user.id)
    db.add(db_like)
    await db.flush()
    await db.refresh(db_like)

    return db_like

@router.delete("/likes/{story_id}", status_code=204)
async def delete_like(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_like = await db.execute(
        select(Like).filter(Like.user_id == current_user.id, Like.story_id == story_id)
    )
    db_like = db_like.scalar_one_or_none()
    if not db_like:
        raise HTTPException(status_code=404, detail="Like not found")

    await db.delete(db_like)
    await db.flush()

# Bookmarks
@router.post("/bookmarks", response_model=BookmarkInDB)
async def create_bookmark(
    bookmark: BookmarkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    story = await db.get(Story, bookmark.story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    existing_bookmark = await db.execute(
        select(Bookmark).filter(Bookmark.user_id == current_user.id, Bookmark.story_id == bookmark.story_id)
    )
    if existing_bookmark.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You've already bookmarked this story")

    db_bookmark = Bookmark(**bookmark.dict(), user_id=current_user.id)
    db.add(db_bookmark)
    await db.flush()
    await db.refresh(db_bookmark)

    return db_bookmark
@router.put("/bookmarks/{story_id}", response_model=BookmarkInDB)
async def update_bookmark(
    story_id: int,
    bookmark_update: BookmarkUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_bookmark = await db.execute(
        select(Bookmark).filter(Bookmark.user_id == current_user.id, Bookmark.story_id == story_id)
    )
    db_bookmark = db_bookmark.scalar_one_or_none()
    if not db_bookmark:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    for key, value in bookmark_update.dict().items():
        setattr(db_bookmark, key, value)
    await db.flush()
    await db.refresh(db_bookmark)

    return db_bookmark

@router.delete("/bookmarks/{story_id}", status_code=204)
async def delete_bookmark(
    story_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_bookmark = await db.execute(
        select(Bookmark).filter(Bookmark.user_id == current_user.id, Bookmark.story_id == story_id)
    )
    db_bookmark = db_bookmark.scalar_one_or_none()
    if not db_bookmark:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    await db.delete(db_bookmark)
    await db.flush()

# User Follow
@router.post("/follow", response_model=UserFollowResponse)
async def follow_user(
    follow: UserFollowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if follow.followed_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't follow yourself")

    followed_user = await db.get(User, follow.followed_id)
    if not followed_user:
        raise HTTPException(status_code=404, detail="User to follow not found")

    existing_follow = await db.execute(
        select(UserFollow).filter(
            UserFollow.follower_id == current_user.id,
            UserFollow.followed_id == follow.followed_id
        )
    )
    if existing_follow.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You're already following this user")

    db_follow = UserFollow(follower_id=current_user.id, followed_id=follow.followed_id)
    db.add(db_follow)
    await db.flush()
    await db.refresh(db_follow)

    return UserFollowResponse(
        **db_follow.__dict__,
        follower_name=current_user.pseudonym or current_user.full_name,
        followed_name=followed_user.pseudonym or followed_user.full_name
    )

@router.delete("/unfollow/{user_id}", status_code=204)
async def unfollow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    db_follow = await db.execute(
        select(UserFollow).filter(
            UserFollow.follower_id == current_user.id,
            UserFollow.followed_id == user_id
        )
    )
    db_follow = db_follow.scalar_one_or_none()
    if not db_follow:
        raise HTTPException(status_code=404, detail="You're not following this user")

    await db.delete(db_follow)
    await db.flush()

@router.get("/followers/{user_id}", response_model=List[UserFollowResponse])
async def get_followers(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    query = select(UserFollow).filter(UserFollow.followed_id == user_id).options(
        selectinload(UserFollow.follower),
        selectinload(UserFollow.followed)
    )
    result = await db.execute(query)
    followers = result.unique().scalars().all()

    return [
        UserFollowResponse(
            id=follow.id,
            follower_id=follow.follower_id,
            followed_id=follow.followed_id,
            created_at=follow.created_at,
            follower_name=follow.follower.pseudonym or follow.follower.full_name,
            followed_name=follow.followed.pseudonym or follow.followed.full_name
        )
        for follow in followers
    ]

@router.get("/following/{user_id}", response_model=List[UserFollowResponse])
async def get_following(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    query = select(UserFollow).filter(UserFollow.follower_id == user_id).options(
        selectinload(UserFollow.follower),
        selectinload(UserFollow.followed)
    )
    result = await db.execute(query)
    following = result.unique().scalars().all()

    return [
        UserFollowResponse(
            id=follow.id,
            follower_id=follow.follower_id,
            followed_id=follow.followed_id,
            created_at=follow.created_at,
            follower_name=follow.follower.pseudonym or follow.follower.full_name,
            followed_name=follow.followed.pseudonym or follow.followed.full_name
        )
        for follow in following
    ]