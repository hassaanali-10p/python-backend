"""Authentication endpoints: register, login, refresh, logout."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.schemas.token import RefreshRequest, TokenPair
from app.schemas.user import UserCreate, UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(data: UserCreate, session: SessionDep) -> UserRead:
    try:
        user = await auth_service.register_user(session, data)
    except auth_service.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair, summary="Log in and obtain tokens")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
) -> TokenPair:
    # OAuth2 password form: `username` carries the email.
    user = await auth_service.authenticate(session, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, expires_in, refresh_token = await auth_service.issue_token_pair(session, user)
    return TokenPair(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
async def refresh(data: RefreshRequest, session: SessionDep) -> TokenPair:
    try:
        _, access_token, expires_in, refresh_token = await auth_service.rotate_refresh_token(
            session, data.refresh_token
        )
    except auth_service.InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenPair(
        access_token=access_token, refresh_token=refresh_token, expires_in=expires_in
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
async def logout(data: RefreshRequest, session: SessionDep) -> None:
    await auth_service.revoke_refresh_token(session, data.refresh_token)
