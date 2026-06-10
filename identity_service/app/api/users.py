"""User endpoints: own profile and admin-only user lookups."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep, require_role
from app.models.user import User, UserRole
from app.schemas.user import UserRead
from app.services.auth import get_user_by_id

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserRead, summary="Get the current user's profile")
async def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get(
    "/users",
    response_model=list[UserRead],
    summary="List users (admin only)",
    dependencies=[Depends(require_role(UserRole.admin))],
)
async def list_users(session: SessionDep) -> list[UserRead]:
    users = (await session.scalars(select(User).order_by(User.created_at))).all()
    return [UserRead.model_validate(u) for u in users]


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    summary="Get a user by ID (admin only)",
    dependencies=[Depends(require_role(UserRole.admin))],
)
async def get_user(user_id: uuid.UUID, session: SessionDep) -> UserRead:
    user = await get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.model_validate(user)
