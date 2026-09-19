"""Spaces API router: hierarchical space/area/room management."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Space
from app.models.models import User as UserModel
from app.schemas.schemas import (
    ResponseWrapper,
    SpaceCreate,
    SpaceResponse,
    SpaceUpdate,
)

router = APIRouter(prefix="/api/spaces", tags=["spaces"])


def _build_space_tree(space: Space) -> SpaceResponse:
    return SpaceResponse(
        id=space.id, name=space.name, code=space.code,
        type=space.type, parent_id=space.parent_id,
        floor=space.floor or "", area=space.area or 0.0,
        capacity=space.capacity or 0, occupancy=space.occupancy or 0,
        access_level=space.access_level, settings_json=space.settings_json or {},
        is_active=space.is_active,
        children=[_build_space_tree(c) for c in (space.children or [])],
        created_at=space.created_at,
    )


def _space_to_response(space: Space) -> SpaceResponse:
    return SpaceResponse(
        id=space.id, name=space.name, code=space.code,
        type=space.type, parent_id=space.parent_id,
        floor=space.floor or "", area=space.area or 0.0,
        capacity=space.capacity or 0, occupancy=space.occupancy or 0,
        access_level=space.access_level, settings_json=space.settings_json or {},
        is_active=space.is_active,
        children=[],
        created_at=space.created_at,
    )


@router.get("", response_model=ResponseWrapper[list[SpaceResponse]])
async def list_spaces(
    type_filter: Optional[str] = Query(None, alias="type"),
    floor: Optional[str] = Query(None),
    parent_id: Optional[int] = Query(None),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("space:read")),
):
    query = select(Space).where(Space.tenant_id == user.tenant_id)

    if type_filter:
        query = query.where(Space.type == type_filter)
    if floor:
        query = query.where(Space.floor == floor)
    if parent_id is not None:
        query = query.where(Space.parent_id == parent_id)
    else:
        query = query.where(Space.parent_id == None)  # noqa: E711 — top-level spaces only

    query = query.options(selectinload(Space.children).selectinload(Space.children))
    result = await db.execute(query.order_by(Space.name))
    spaces = result.scalars().all()

    return ResponseWrapper(data=[_build_space_tree(s) for s in spaces])


@router.post("", response_model=ResponseWrapper[SpaceResponse], status_code=201)
async def create_space(
    body: SpaceCreate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("space:write")),
):
    if body.code:
        existing = await db.execute(
            select(Space).where(Space.tenant_id == user.tenant_id, Space.code == body.code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, detail={"code": "CONFLICT", "message": f"空间代码 {body.code} 已存在"})

    space = Space(tenant_id=user.tenant_id, **body.model_dump())
    db.add(space)
    await db.flush()
    return ResponseWrapper(data=_space_to_response(space))


@router.get("/{space_id}", response_model=ResponseWrapper[SpaceResponse])
async def get_space(
    space_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("space:read")),
):
    space = await db.get(Space, space_id)
    if not space or space.tenant_id != user.tenant_id:
        raise HTTPException(404)
    return ResponseWrapper(data=_space_to_response(space))


@router.put("/{space_id}", response_model=ResponseWrapper[SpaceResponse])
async def update_space(
    space_id: int,
    body: SpaceUpdate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("space:write")),
):
    space = await db.get(Space, space_id)
    if not space or space.tenant_id != user.tenant_id:
        raise HTTPException(404)

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(space, key, value)
    space.updated_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_space_to_response(space))


@router.delete("/{space_id}", status_code=204)
async def delete_space(
    space_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("space:write")),
):
    space = await db.get(Space, space_id)
    if not space or space.tenant_id != user.tenant_id:
        raise HTTPException(404)

    # Check for children
    if space.children:
        raise HTTPException(400, detail={"code": "HAS_CHILDREN", "message": "该空间有子空间，无法删除"})

    await db.delete(space)
