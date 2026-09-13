from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlmodel import select

from app.config import Settings, get_settings
from app.db import User, get_session

_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(subject: str, settings: Settings) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.vault_jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.vault_jwt_secret, algorithm="HS256")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings.vault_jwt_secret, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        if username is None:
            raise unauthorized
    except JWTError as exc:
        raise unauthorized from exc

    with get_session() as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            raise unauthorized
        session.expunge(user)
        return user
