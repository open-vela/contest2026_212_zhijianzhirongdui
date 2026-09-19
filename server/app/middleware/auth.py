"""FastAPI dependency-based auth middleware for JWT + RBAC."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.models import User
from app.services.auth_service import build_token_data, decode_token, get_user_permissions

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "缺少认证令牌"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "无效的令牌类型"})
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "令牌无效或已过期"},
        )

    user_id = int(payload.get("sub", 0))
    result = await db.get(User, user_id)
    if not result or not result.is_active:
        raise HTTPException(status_code=401, detail={"code": "USER_DISABLED", "message": "用户已禁用"})

    # Enrich request.state for use in endpoints
    request.state.user = result
    request.state.token_data = payload
    request.state.permissions = await get_user_permissions(db, result)
    return result


async def optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of 401."""
    if credentials is None:
        return None
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


def require_permission(permission: str):
    """Factory: returns a dependency that checks for a specific permission."""
    async def permission_checker(
        request: Request,
        user: User = Depends(get_current_user),
    ) -> bool:
        # Superadmin bypasses all permission checks
        if user.is_superadmin:
            return True
        perms: list[str] = getattr(request.state, "permissions", [])
        if permission not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"需要权限: {permission}",
                },
            )
        return True

    return permission_checker
