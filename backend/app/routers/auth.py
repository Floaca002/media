from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.config import Settings, get_settings
from app.db import User, get_session
from app.dependencies import get_jellyfin
from app.schemas import (
    LoginRequest,
    LoginResponse,
    RequestPasswordResetBody,
    RequestPasswordResetResponse,
    ResetPasswordBody,
)
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


@router.post("/request-password-reset", response_model=RequestPasswordResetResponse)
async def request_password_reset(
    body: RequestPasswordResetBody, jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> RequestPasswordResetResponse:
    """
    Kicks off Jellyfin's built-in filesystem-based reset: Jellyfin writes a
    one-time PIN to a file inside its own container. There is deliberately
    no way to complete a reset from this endpoint alone — the PIN has to be
    read off disk (docker exec), which is what proves the caller actually
    controls the server, not just the login page.
    """
    try:
        result = await jellyfin.request_password_reset_pin(body.username)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc

    if result.get("Action") != "PinCode":
        raise HTTPException(
            status_code=400,
            detail="Jellyfin did not issue a reset PIN for this account "
            "(check the username, or that password resets are allowed from this network).",
        )
    return RequestPasswordResetResponse(pin_file=result.get("PinFile"))


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordBody, jellyfin: JellyfinClient = Depends(get_jellyfin)
) -> dict:
    try:
        redeemed = await jellyfin.redeem_password_reset_pin(body.pin)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc

    if not redeemed.get("Success"):
        raise HTTPException(status_code=400, detail="Invalid or expired PIN")

    reset_usernames = {u.lower() for u in redeemed.get("UsersReset", [])}
    if body.username.lower() not in reset_usernames:
        raise HTTPException(
            status_code=400, detail="Username does not match the account this PIN was issued for"
        )

    user = await jellyfin.find_user_by_name(body.username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    await jellyfin.set_password_as_admin(user["Id"], body.new_password)
    return {"ok": True}
