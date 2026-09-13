from __future__ import annotations

import json
import os
from datetime import datetime, timezone

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
    body: ResetPasswordBody,
    jellyfin: JellyfinClient = Depends(get_jellyfin),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Validates the PIN by reading the same file Jellyfin wrote it to,
    directly, rather than calling Jellyfin's own PIN-redemption endpoint
    (whose exact path/behavior isn't reliable across Jellyfin versions).
    This doesn't weaken the security model: the PIN is still only ever
    knowable to someone who can read it off the server's filesystem, and
    the human still has to fetch and submit it manually.
    """
    container_prefix = settings.jellyfin_container_config_path
    if not body.pin_file.startswith(container_prefix):
        raise HTTPException(status_code=400, detail="Invalid reset request")

    mount_root = os.path.realpath(settings.jellyfin_config_mount_path)
    relative = body.pin_file[len(container_prefix) :].lstrip("/")
    local_path = os.path.realpath(os.path.join(mount_root, relative))
    if not local_path.startswith(mount_root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid reset request")

    try:
        with open(local_path) as f:
            pin_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Reset PIN file not found or expired") from exc

    if pin_data.get("Pin") != body.pin or pin_data.get("UserName", "").lower() != body.username.lower():
        raise HTTPException(status_code=400, detail="Invalid PIN")

    expiration = pin_data.get("ExpirationDate")
    if expiration:
        try:
            expires_at = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(status_code=400, detail="This reset PIN has expired")
        except ValueError:
            pass  # unparseable date shouldn't block an otherwise-valid reset

    try:
        user = await jellyfin.find_user_by_name(body.username)
    except JellyfinUnavailableError as exc:
        raise HTTPException(status_code=502, detail="Jellyfin unavailable") from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    await jellyfin.set_password_as_admin(user["Id"], body.new_password)

    try:
        os.remove(local_path)
    except OSError:
        pass  # best-effort: a PIN that fails to delete just expires normally later

    return {"ok": True}
