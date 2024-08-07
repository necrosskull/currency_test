import asyncio
import datetime
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

import coloredlogs
import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import (
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import Base, Session, engine, get_db
from app.models import Subscription, User
from app.schemas import SubscriptionCreate, Token, TokenData, UserCreate

logger = logging.getLogger()


coloredlogs.install(
    level="INFO",
    fmt="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    asyncio.create_task(fetch_prices())
    yield


telegram_token = settings.TELEGRAM_TOKEN
app = FastAPI(lifespan=lifespan)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.now(datetime.UTC) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.UTC) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_user(db, username: str):
    result = await db.execute(select(User).where(User.username == username))

    return result.scalars().first()


async def authenticate_user(db, username: str, password: str):
    user = await get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def get_current_user(db=Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception
    user = await get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def send_telegram_message(token: str, chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)


@app.post("/register", response_model=Token)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    hashed_password = get_password_hash(user.password)
    user_in_db = User(
        username=user.username,
        hashed_password=hashed_password,
        telegram_id=user.telegram_id,
    )

    db.add(user_in_db)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    await db.refresh(user_in_db)
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/subscribe", response_model=SubscriptionCreate)
async def create_subscription(
    subscription: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserCreate = Depends(get_current_user),
):
    sub = Subscription(
        user_id=current_user.id, symbol=subscription.symbol, price=subscription.price
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    return subscription


async def fetch_prices():
    while True:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.binance.com/api/v3/ticker/price")
            prices = response.json()

            async with Session() as session:
                result = await session.execute(select(Subscription))
                subscriptions = result.scalars().all()

                for sub in subscriptions:
                    logger.info(f"Subscriptions: {sub.symbol} {sub.price}")

                for sub in subscriptions:
                    for price in prices:
                        if price["symbol"] == sub.symbol:
                            logger.info(
                                f"Founded Price for {sub.symbol} is {price['price']} in db {sub.price}"
                            )

                            current_price = float(price["price"])
                            if sub.price is None or current_price <= sub.price:
                                user_tg_id = await session.execute(
                                    select(User.telegram_id).where(
                                        User.id == sub.user_id
                                    )
                                )
                                tg_id = str(user_tg_id.scalar())

                                logger.info(
                                    f"Alert Price for {sub.symbol} is {current_price}, sending message to {tg_id}"
                                )

                                await send_telegram_message(
                                    telegram_token,
                                    tg_id,
                                    f"Alert Price for {sub.symbol} is {current_price}",
                                )

                await session.commit()

        await asyncio.sleep(5)
