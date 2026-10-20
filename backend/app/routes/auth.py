from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .. import auth as authlib
from ..deps import get_state
from ..state import AppState

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response, state: AppState = Depends(get_state)):
    ip = request.client.host if request.client else "unknown"
    authlib.check_rate_limit(ip)
    if not authlib.verify_password(body.password, state.settings):
        raise HTTPException(status_code=401, detail="Wrong password")
    authlib.set_session_cookie(request, response, state.settings)
    return {"ok": True, "mode": "session"}


@router.post("/logout")
async def logout(response: Response):
    authlib.clear_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    mode = authlib.auth_mode(request)
    return {"authenticated": mode is not None, "mode": mode, "read_only": mode == "kiosk"}
