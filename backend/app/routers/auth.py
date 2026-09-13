from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.config import Settings, get_settings
from app.db import User, get_session
from app.dependencies import get_jellyfin
from app.schemas import LoginRequest, LoginResponse
from app.security import create_access_token, get_current_user
from app.services.jellyfin import JellyfinAuthError, JellyfinClient, JellyfinUnavailableError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    jellyfin: JellyfinClient = Depends(get_jellyfin),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """
    Vault delegates authentication to Jellyfin: if these credentials work
    against Jellyfin, they're good enough for Vault. The resulting Jellyfin
    user id + access token are stored server-side and never returned to
    the browser — the browser only ever holds Vault's own JWT.
    """
    try:
        auth = await jellyfin.authenticate_by_name(body.username, body.password)
    except JellyfinAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc

    jellyfin_user_id = auth["User"]["Id"]
    jellyfin_token = auth["AccessToken"]

    with get_session() as session:
        user = session.exec(select(User).where(User.username == body.username)).first()
        if user is None:
            user = User(
                username=body.username,
                jellyfin_user_id=jellyfin_user_id,
                jellyfin_access_token=jellyfin_token,
            )
        else:
            user.jellyfin_user_id = jellyfin_user_id
            user.jellyfin_access_token = jellyfin_token
        session.add(user)
        session.commit()

    token = create_access_token(subject=body.username, settings=settings)
    return LoginResponse(access_token=token, username=body.username, jellyfin_user_id=jellyfin_user_id)


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {"username": user.username, "jellyfin_user_id": user.jellyfin_user_id}
