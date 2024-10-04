from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(check_and_create_tables)

def check_and_create_tables(conn):
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if not existing_tables:
        Base.metadata.create_all(bind=conn)
    else:
        print("Tables already exist. Skipping table creation.")

async def get_db():
    async with async_session() as db:
        yield db