"""Authentication service: JWT, password hashing, seed data."""

from datetime import datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import (
    Permission,
    Role,
    RolePermission,
    Tenant,
    User,
    UserRole,
)
from app.schemas.schemas import TokenData

# ── Password hashing ──────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["iat"] = datetime.utcnow()
    payload["type"] = "access"
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload["iat"] = datetime.utcnow()
    payload["type"] = "refresh"
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ── DB helpers ────────────────────────────────────────────────────────


async def get_user_by_username(db: AsyncSession, tenant_code: str, username: str) -> User | None:
    result = await db.execute(
        select(User).join(Tenant).where(Tenant.code == tenant_code, User.username == username)
    )
    return result.scalar_one_or_none()


async def get_user_permissions(db: AsyncSession, user: User) -> list[str]:
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
    )
    return [row[0] for row in result.fetchall()]


async def get_user_roles(db: AsyncSession, user: User) -> list[str]:
    result = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    return [row[0] for row in result.fetchall()]


async def build_token_data(db: AsyncSession, user: User) -> TokenData:
    permissions = await get_user_permissions(db, user)
    return TokenData(
        user_id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        permissions=permissions,
    )


async def authenticate_user(db: AsyncSession, tenant_code: str, username: str, password: str) -> User | None:
    user = await get_user_by_username(db, tenant_code, username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login = datetime.utcnow()
    return user


# ── Permission definitions ────────────────────────────────────────────
PERMISSION_DEFS = [
    ("person:read", "查看人员", "person", "read"),
    ("person:write", "管理人员", "person", "manage"),
    ("visitor:read", "查看访客", "visitor", "read"),
    ("visitor:write", "管理访客", "visitor", "manage"),
    ("visitor:approve", "审批访客", "visitor", "approve"),
    ("device:read", "查看设备", "device", "read"),
    ("device:write", "管理设备", "device", "manage"),
    ("space:read", "查看空间", "space", "read"),
    ("space:write", "管理空间", "space", "manage"),
    ("event:read", "查看事件", "event", "read"),
    ("audit:read", "查看审计", "audit", "read"),
    ("rule:read", "查看规则", "rule", "read"),
    ("rule:write", "管理规则", "rule", "manage"),
    ("energy:read", "查看能耗", "energy", "read"),
    ("tenant:admin", "租户管理", "tenant", "manage"),
    ("dashboard:view", "查看大屏", "dashboard", "read"),
    ("system:admin", "系统管理", "system", "super"),
]

# Role → permission mapping
ROLE_PERMISSIONS = {
    "admin": [p[0] for p in PERMISSION_DEFS],
    "hr": ["person:read", "person:write", "dashboard:view"],
    "it": ["device:read", "device:write", "space:read", "space:write",
           "rule:read", "rule:write", "energy:read", "dashboard:view"],
    "security": ["person:read", "visitor:read", "visitor:approve",
                  "device:read", "event:read", "dashboard:view"],
    "reception": ["visitor:read", "visitor:write", "dashboard:view"],
    "employee": ["dashboard:view"],
}

ROLE_DESCRIPTIONS = {
    "admin": "超级管理员，拥有系统全部权限",
    "hr": "人事管理员，负责人事信息和人员管理",
    "it": "IT运维，负责设备和系统配置",
    "security": "安保人员，可查看监控/识别记录/告警",
    "reception": "前台接待，负责访客管理",
    "employee": "普通员工，仅可查看大屏",
}


# ── Seed default data ─────────────────────────────────────────────────


async def seed_default_data(db: AsyncSession):
    """Create default tenant, permissions, roles, and admin user if they don't exist."""

    # Check if already seeded
    existing = await db.execute(select(Tenant).where(Tenant.code == "default"))
    if existing.scalar_one_or_none():
        return

    # Tenant
    tenant = Tenant(
        name=settings.SEED_DEFAULT_TENANT,
        code="default",
        tier="enterprise",
        max_devices=50,
        max_persons=500,
    )
    db.add(tenant)
    await db.flush()

    # Permissions
    perm_objects = {}
    for code, name, resource, action in PERMISSION_DEFS:
        perm = Permission(code=code, name=name, resource=resource, action=action)
        db.add(perm)
        perm_objects[code] = perm
    await db.flush()

    # Roles
    role_objects = {}
    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        role = Role(
            tenant_id=tenant.id,
            name=role_name,
            description=ROLE_DESCRIPTIONS.get(role_name, ""),
            is_system=True,
        )
        db.add(role)
        await db.flush()
        for pc in perm_codes:
            db.add(RolePermission(role_id=role.id, permission_id=perm_objects[pc].id))
        role_objects[role_name] = role

    # Admin user
    admin = User(
        tenant_id=tenant.id,
        username=settings.SEED_ADMIN_USERNAME,
        password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
        display_name="超级管理员",
        is_superadmin=True,
    )
    db.add(admin)
    await db.flush()
    db.add(UserRole(user_id=admin.id, role_id=role_objects["admin"].id))

    # Some sample persons
    sample_persons = [
        {"name": "张三", "employee_id": "EMP001", "department": "研发部",
         "person_type": "employee", "phone": "13800138001", "access_level": 3},
        {"name": "李四", "employee_id": "EMP002", "department": "安保部",
         "person_type": "employee", "phone": "13800138002", "access_level": 2},
        {"name": "王五", "employee_id": "EMP003", "department": "市场部",
         "person_type": "employee", "phone": "13800138003", "access_level": 1},
    ]
    from app.models.models import Person  # local import to avoid circular
    for sp in sample_persons:
        db.add(Person(tenant_id=tenant.id, **sp))
