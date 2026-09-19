"""Users, roles, and permissions management API router."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.schemas.schemas import (
    PaginatedResponse,
    Pagination,
    PermissionResponse,
    ResponseWrapper,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import (
    get_user_permissions,
    get_user_roles,
    hash_password,
)

router = APIRouter(tags=["users"])
user_router = APIRouter(prefix="/api/users", tags=["users"])
role_router = APIRouter(prefix="/api/roles", tags=["users"])
perm_router = APIRouter(prefix="/api/permissions", tags=["users"])


# ── Users ─────────────────────────────────────────────────────────────

@user_router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    query = select(User).where(User.tenant_id == current_user.tenant_id)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query.options(selectinload(User.roles)))
    users = result.scalars().all()

    data = []
    for u in users:
        roles = await get_user_roles(db, u) if u.roles else []
        data.append(UserResponse(
            id=u.id, username=u.username, display_name=u.display_name or "",
            email=u.email or "", is_active=u.is_active,
            roles=roles, last_login=u.last_login, created_at=u.created_at,
        ))

    return PaginatedResponse(
        data=data,
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@user_router.post("", response_model=ResponseWrapper[UserResponse], status_code=201)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    existing = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id, User.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail={"code": "CONFLICT", "message": f"用户名 {body.username} 已存在"})

    user = User(
        tenant_id=current_user.tenant_id,
        username=body.username,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        email=body.email,
    )
    db.add(user)
    await db.flush()

    for rid in body.role_ids:
        db.add(UserRole(user_id=user.id, role_id=rid))

    return ResponseWrapper(data=UserResponse(
        id=user.id, username=user.username, display_name=user.display_name or "",
        email=user.email or "", is_active=user.is_active,
        roles=[], created_at=user.created_at,
    ))


@user_router.put("/{user_id}", response_model=ResponseWrapper[UserResponse])
async def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(404)

    update_data = body.model_dump(exclude_unset=True)
    role_ids = update_data.pop("role_ids", None)

    for key, value in update_data.items():
        setattr(user, key, value)

    if role_ids is not None:
        # Remove existing roles
        await db.execute(UserRole.__table__.delete().where(UserRole.user_id == user_id))
        for rid in role_ids:
            db.add(UserRole(user_id=user_id, role_id=rid))

    await db.flush()
    roles = await get_user_roles(db, user)
    return ResponseWrapper(data=UserResponse(
        id=user.id, username=user.username, display_name=user.display_name or "",
        email=user.email or "", is_active=user.is_active,
        roles=roles, last_login=user.last_login, created_at=user.created_at,
    ))


@user_router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    user = await db.get(User, user_id)
    if not user or user.tenant_id != current_user.tenant_id:
        raise HTTPException(404)
    await db.delete(user)


# ── Roles ─────────────────────────────────────────────────────────────

@role_router.get("", response_model=ResponseWrapper[list[RoleResponse]])
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    result = await db.execute(
        select(Role).where(Role.tenant_id == current_user.tenant_id)
    )
    roles = result.scalars().all()
    data = []
    for r in roles:
        perms = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == r.id)
        )
        perm_codes = [row[0] for row in perms.fetchall()]
        data.append(RoleResponse(
            id=r.id, name=r.name, description=r.description or "",
            is_system=r.is_system, permissions=perm_codes, created_at=r.created_at,
        ))
    return ResponseWrapper(data=data)


@role_router.post("", response_model=ResponseWrapper[RoleResponse], status_code=201)
async def create_role(
    body: RoleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    role = Role(tenant_id=current_user.tenant_id, name=body.name, description=body.description)
    db.add(role)
    await db.flush()

    for pid in body.permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=pid))

    return ResponseWrapper(data=RoleResponse(
        id=role.id, name=role.name, description=role.description or "",
        is_system=role.is_system, permissions=[], created_at=role.created_at,
    ))


@role_router.put("/{role_id}", response_model=ResponseWrapper[RoleResponse])
async def update_role(
    role_id: int,
    body: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    role = await db.get(Role, role_id)
    if not role or role.tenant_id != current_user.tenant_id:
        raise HTTPException(404)
    if role.is_system:
        raise HTTPException(400, detail={"code": "SYSTEM_ROLE", "message": "系统内置角色不可修改"})

    update_data = body.model_dump(exclude_unset=True)
    permission_ids = update_data.pop("permission_ids", None)

    for key, value in update_data.items():
        setattr(role, key, value)

    if permission_ids is not None:
        await db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role_id))
        for pid in permission_ids:
            db.add(RolePermission(role_id=role_id, permission_id=pid))

    await db.flush()
    return ResponseWrapper(data=RoleResponse(
        id=role.id, name=role.name, description=role.description or "",
        is_system=role.is_system, permissions=[], created_at=role.created_at,
    ))


@role_router.delete("/{role_id}", status_code=204)
async def delete_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("tenant:admin")),
):
    role = await db.get(Role, role_id)
    if not role or role.tenant_id != current_user.tenant_id:
        raise HTTPException(404)
    if role.is_system:
        raise HTTPException(400, detail={"code": "SYSTEM_ROLE", "message": "系统内置角色不可删除"})
    await db.delete(role)


# ── Permissions (read-only) ──────────────────────────────────────────

@perm_router.get("", response_model=ResponseWrapper[list[PermissionResponse]])
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Permission).order_by(Permission.id))
    perms = result.scalars().all()
    return ResponseWrapper(data=[
        PermissionResponse(id=p.id, code=p.code, name=p.name,
                           resource=p.resource, action=p.action,
                           description=p.description or "")
        for p in perms
    ])
