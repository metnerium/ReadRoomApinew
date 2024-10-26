from datetime import datetime, timedelta
from typing import Optional
from base64 import b64encode
from collections import OrderedDict
from hashlib import sha256
from hmac import HMAC
from urllib.parse import urlparse, parse_qsl, urlencode

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.user import User
from app.schemas.user import TokenData
from database import get_db
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, CLIENT_SECRET

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_valid(*, query: dict, secret: str) -> bool:
    """Check VK Apps signature"""
    if "sign" not in query:
        logger.error("No 'sign' parameter in the query")
        return False

    vk_subset = OrderedDict(sorted(x for x in query.items() if x[0][:3] == "vk_"))
    if not vk_subset:
        logger.error("No VK parameters found in the query")
        return False

    hash_code = b64encode(HMAC(secret.encode(), urlencode(vk_subset, doseq=True).encode(), sha256).digest())
    decoded_hash_code = hash_code.decode('utf-8')[:-1].replace('+', '-').replace('/', '_')

    return query["sign"] == decoded_hash_code


def verify_url(url: str, vk_id: int) -> bool:
    try:
        # Разбираем строку URL напрямую
        query_params = dict(parse_qsl(url, keep_blank_values=True))
        logger.info(f"Parsed query params: {query_params}")

        if not query_params:
            logger.error("No query parameters found in the URL")
            return False
        if query_params["vk_user_id"] != str(vk_id):
            return False
        status = is_valid(query=query_params, secret=CLIENT_SECRET)
        return status
    except Exception as e:
        logger.error(f"Error in verify_url: {str(e)}")
        return False

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        vk_id: int = payload.get("sub")
        if vk_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        token_data = TokenData(vk_id=vk_id)
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    token_data = decode_access_token(token)
    user = await db.scalar(select(User).filter(User.vk_id == token_data.vk_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user