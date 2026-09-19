"""Persons API router: CRUD + face registration."""

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.middleware.auth import get_current_user, require_permission
from app.models.database import get_db
from app.models.models import Face, Person, User as UserModel
from app.schemas.schemas import (
    EnrollFromNodeRequest,
    EnrollResult,
    FaceInfo,
    PaginatedResponse,
    Pagination,
    PersonCreate,
    PersonListResponse,
    PersonResponse,
    PersonUpdate,
    ResponseWrapper,
)

router = APIRouter(prefix="/api/persons", tags=["persons"])


async def _person_to_response(p: Person) -> PersonResponse:
    return PersonResponse(
        id=p.id,
        name=p.name,
        employee_id=p.employee_id,
        department=p.department,
        person_type=p.person_type,
        phone=p.phone,
        email=p.email,
        ble_mac=p.ble_mac or "",
        avatar_url=p.avatar_url or "",
        access_level=p.access_level,
        is_active=p.is_active,
        face_count=len(p.faces) if p.faces else 0,
        faces=[FaceInfo(id=f.id, quality_score=f.quality_score, image_url=f.image_url or "",
                        created_at=f.created_at) for f in (p.faces or [])],
        valid_from=p.valid_from,
        valid_until=p.valid_until,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _person_to_list(p: Person) -> PersonListResponse:
    return PersonListResponse(
        id=p.id,
        name=p.name,
        employee_id=p.employee_id,
        department=p.department,
        person_type=p.person_type,
        phone=p.phone,
        email=p.email,
        access_level=p.access_level,
        is_active=p.is_active,
        face_count=len(p.faces) if p.faces else 0,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("", response_model=PaginatedResponse[PersonListResponse])
async def list_persons(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    person_type: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:read")),
):
    query = select(Person).where(Person.tenant_id == user.tenant_id)

    if search:
        like = f"%{search}%"
        query = query.where(
            Person.name.like(like) | Person.employee_id.like(like) | Person.phone.like(like)
        )
    if person_type:
        query = query.where(Person.person_type == person_type)
    if department:
        query = query.where(Person.department == department)
    if is_active is not None:
        query = query.where(Person.is_active == is_active)

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    sort_col = getattr(Person, sort_by, Person.created_at)
    query = query.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query.options(selectinload(Person.faces)))
    persons = result.scalars().all()

    return PaginatedResponse(
        data=[_person_to_list(p) for p in persons],
        pagination=Pagination(
            page=page, page_size=page_size, total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@router.post("", response_model=ResponseWrapper[PersonResponse], status_code=201)
async def create_person(
    body: PersonCreate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:write")),
):
    # Check employee_id uniqueness
    if body.employee_id:
        existing = await db.execute(
            select(Person).where(
                Person.tenant_id == user.tenant_id,
                Person.employee_id == body.employee_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, detail={"code": "CONFLICT", "message": f"工号 {body.employee_id} 已存在"})

    person = Person(tenant_id=user.tenant_id, **body.model_dump())
    db.add(person)
    await db.flush()
    await db.refresh(person, ["faces"])
    return ResponseWrapper(data=await _person_to_response(person))


@router.get("/{person_id}", response_model=ResponseWrapper[PersonResponse])
async def get_person(
    person_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:read")),
):
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "人员不存在"})
    await db.refresh(person, ["faces"])
    return ResponseWrapper(data=await _person_to_response(person))


@router.put("/{person_id}", response_model=ResponseWrapper[PersonResponse])
async def update_person(
    person_id: int,
    body: PersonUpdate,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:write")),
):
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "人员不存在"})

    update_data = body.model_dump(exclude_unset=True)
    if "employee_id" in update_data and update_data["employee_id"]:
        existing = await db.execute(
            select(Person).where(
                Person.tenant_id == user.tenant_id,
                Person.employee_id == update_data["employee_id"],
                Person.id != person_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, detail={"code": "CONFLICT", "message": f"工号 {update_data['employee_id']} 已存在"})

    for key, value in update_data.items():
        setattr(person, key, value)
    person.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(person, ["faces"])
    return ResponseWrapper(data=await _person_to_response(person))


@router.delete("/{person_id}", status_code=204)
async def delete_person(
    person_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:write")),
):
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "人员不存在"})
    await db.delete(person)


@router.post("/{person_id}/faces", response_model=ResponseWrapper[FaceInfo], status_code=201)
async def register_face(
    person_id: int,
    file: UploadFile = File(...),
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:write")),
):
    """Register a face image for a person. Stores image and creates a dummy embedding."""
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "人员不存在"})

    # Read image file and create face record
    image_data = await file.read()
    image_url = f"/data/faces/{person_id}_{len(person.faces) + 1}.jpg"

    # In Phase 2, we store the image and extract embedding via MobileFaceNet later
    face = Face(
        person_id=person_id,
        embedding=[0.0] * 128,  # placeholder — real embedding from ML pipeline
        image_url=image_url,
        quality_score=0.9,
    )
    db.add(face)
    await db.flush()

    return ResponseWrapper(data=FaceInfo(
        id=face.id,
        quality_score=face.quality_score,
        image_url=face.image_url or "",
        created_at=face.created_at,
    ))


@router.post("/{person_id}/enroll-from-node", response_model=ResponseWrapper[EnrollResult])
async def enroll_from_node(
    person_id: int,
    body: EnrollFromNodeRequest,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:write")),
):
    """Camera-based face enrollment — no server-side model required.

    The ESP32 node extracts the embedding and publishes it over MQTT.
    This endpoint registers a pending capture: the next face embedding
    arriving from `body.node_id` is stored as this person's reference
    embedding. The call blocks until the embedding is captured or the
    timeout expires.

    Demo flow: create person → call this endpoint → subject looks at the
    camera → embedding captured → subsequent recognitions match against it.
    """
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "人员不存在"})

    from app.services.identity_engine import identity_engine

    future = identity_engine.request_enrollment(
        node_id=body.node_id,
        person_id=person_id,
        person_name=person.name,
        tenant_id=user.tenant_id,
    )
    try:
        result = await asyncio.wait_for(future, timeout=body.timeout_seconds)
    except asyncio.TimeoutError:
        identity_engine.cancel_enrollment(body.node_id)
        raise HTTPException(
            408,
            detail={
                "code": "ENROLL_TIMEOUT",
                "message": (f"{body.timeout_seconds:.0f}秒内未收到节点 {body.node_id} 的人脸数据，"
                           "请确认设备在线、摄像头对准人脸且固件正在发布 embedding"),
            },
        )
    except asyncio.CancelledError:
        raise HTTPException(500, detail={"code": "ENROLL_CANCELLED", "message": "注册被取消"})

    return ResponseWrapper(data=EnrollResult(
        person_id=person_id,
        person_name=person.name,
        node_id=result["node_id"],
        face_id=result["face_id"],
        embedding_len=result["embedding_len"],
        status=result["status"],
    ))


@router.get("/{person_id}/faces", response_model=ResponseWrapper[list[FaceInfo]])
async def list_faces(
    person_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:read")),
):
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404)
    await db.refresh(person, ["faces"])
    return ResponseWrapper(data=[
        FaceInfo(id=f.id, quality_score=f.quality_score, image_url=f.image_url or "",
                 created_at=f.created_at)
        for f in person.faces
    ])


@router.delete("/{person_id}/faces/{face_id}", status_code=204)
async def delete_face(
    person_id: int,
    face_id: int,
    user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("person:write")),
):
    face = await db.get(Face, face_id)
    if not face or face.person_id != person_id:
        raise HTTPException(404)
    # Verify person ownership
    person = await db.get(Person, person_id)
    if not person or person.tenant_id != user.tenant_id:
        raise HTTPException(404)
    await db.delete(face)
