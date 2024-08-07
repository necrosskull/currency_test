from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    telegram_id: int | None = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class SubscriptionCreate(BaseModel):
    symbol: str
    price: float | None = None