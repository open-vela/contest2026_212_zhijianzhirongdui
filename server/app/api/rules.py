"""Rules API router: policy rule CRUD + toggle."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Rule
from app.models.models import User as UserModel
from app.schemas.schemas import (
    PaginatedResponse,
    Pagination,
    ResponseWrapper,
    RuleCreate,
    RuleResponse,
    RuleToggle,
    RuleUpdate,
)

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _rule_response(r: Rule) -> RuleResponse:
    return RuleResponse(
        id=r.id, name=r.name, description=r.description or "",
        trigger_type=r.trigger_type, trigger_config=r.trigger_config or {},
        condition_expr=r.condition_expr or "",
        action_type=r.action_type, action_config=r.action_config or {},
        priority=r.priority or 2, is_enabled=r.is_enabled,
        created_at=r.created_at,
    )


@router.get("", response_model=PaginatedResponse[RuleResponse])
async def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    trigger_type: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rule:read")),
):
    query = select(Rule).where(Rule.tenant_id == user.tenant_id)

    if trigger_type:
        query = query.where(Rule.trigger_type == trigger_type)
    if is_enabled is not None:
        query = query.where(Rule.is_enabled == is_enabled)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_col = getattr(Rule, sort_by, Rule.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    rules = result.scalars().all()

    return PaginatedResponse(
        data=[_rule_response(r) for r in rules],
        pagination=Pagination(page=page, page_size=page_size, total=total,
                               total_pages=(total + page_size - 1) // page_size),
    )


@router.post("", response_model=ResponseWrapper[RuleResponse], status_code=201)
async def create_rule(
    body: RuleCreate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rule:write")),
):
    rule = Rule(tenant_id=user.tenant_id, **body.model_dump())
    db.add(rule)
    await db.flush()
    return ResponseWrapper(data=_rule_response(rule))


@router.put("/{rule_id}", response_model=ResponseWrapper[RuleResponse])
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rule:write")),
):
    rule = await db.get(Rule, rule_id)
    if not rule or rule.tenant_id != user.tenant_id:
        raise HTTPException(404)

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    rule.updated_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_rule_response(rule))


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rule:write")),
):
    rule = await db.get(Rule, rule_id)
    if not rule or rule.tenant_id != user.tenant_id:
        raise HTTPException(404)
    await db.delete(rule)


@router.put("/{rule_id}/toggle", response_model=ResponseWrapper[RuleResponse])
async def toggle_rule(
    rule_id: int,
    body: RuleToggle,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rule:write")),
):
    rule = await db.get(Rule, rule_id)
    if not rule or rule.tenant_id != user.tenant_id:
        raise HTTPException(404)

    rule.is_enabled = body.is_enabled
    rule.updated_at = datetime.utcnow()
    await db.flush()
    return ResponseWrapper(data=_rule_response(rule))
