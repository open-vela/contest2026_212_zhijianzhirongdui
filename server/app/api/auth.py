"""Auth API router: login, refresh, me."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.database import get_db
from app.models.models import Tenant, User
from app.schemas.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    UserInfo,
)
from app.services.auth_service import (
    authenticate_user,
    build_token_data,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_permissions,
    get_user_roles,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, req.tenant_code, req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_FAILED", "message": "用户名或密码错误"},
        )

    token_data = await build_token_data(db, user)
    roles = await get_user_roles(db, user)
    permissions = await get_user_permissions(db, user)

    # Get tenant code
    tenant = await db.get(Tenant, user.tenant_id)
    tenant_code = tenant.code if tenant else req.tenant_code

    access_token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "tenant_code": tenant_code,
        "username": user.username,
        "roles": roles,
        "permissions": permissions,
        "is_superadmin": user.is_superadmin,
    })
    refresh_token = create_refresh_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
    })

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email or "",
            roles=roles,
            permissions=permissions,
            tenant_id=user.tenant_id,
            tenant_code=tenant_code,
            is_superadmin=user.is_superadmin,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("wrong type")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_REFRESH", "message": "刷新令牌无效或已过期"},
        )

    user_id = int(payload.get("sub", 0))
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail={"code": "USER_DISABLED", "message": "用户已禁用"})

    permissions = await get_user_permissions(db, user)
    roles = await get_user_roles(db, user)

    access_token = create_access_token({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "tenant_code": payload.get("tenant_code", ""),
        "username": user.username,
        "roles": roles,
        "permissions": permissions,
        "is_superadmin": user.is_superadmin,
    })

    return RefreshResponse(access_token=access_token)


@router.get("/me", response_model=UserInfo)
async def get_me(request: Request, user: User = Depends(get_current_user)):
    payload = request.state.token_data
    return UserInfo(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email or "",
        roles=payload.get("roles", []),
        permissions=payload.get("permissions", []),
        tenant_id=user.tenant_id,
        tenant_code=payload.get("tenant_code", ""),
        is_superadmin=user.is_superadmin,
    )
