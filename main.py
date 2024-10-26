from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette import status
from starlette.responses import JSONResponse

from app.routes import auth, user, story, chapter, social, usercontent, content_block
from database import create_tables

app = FastAPI(title="ReadRoom API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Подключаем роуты
app.include_router(auth.router, tags=["Authentication"])
app.include_router(user.router, prefix="/users", tags=["Users"])
app.include_router(story.router, prefix="/stories", tags=["Stories"])
app.include_router(chapter.router, prefix="/chapters", tags=["Chapters"])
app.include_router(social.router, prefix="/social", tags=["Social"])
app.include_router(content_block.router, prefix="/block", tags=["block"])

app.include_router(usercontent.router, prefix="/usercontent", tags=["UserContent"])

@app.on_event("startup")
async def startup_event():
    await create_tables()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)