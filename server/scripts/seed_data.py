#!/usr/bin/env python3
"""Comprehensive mock data seeder for VelaMesh (枢络).

Run with:
    cd server && PYTHONPATH=. python scripts/seed_data.py [--force]

Seeds:
- 1 tenant + 6 users (admin/hr/it/security/reception/employee)
- 20 persons with face embeddings and BLE MACs
- 3 ESP32 devices (door-01, corridor-01, meeting-01)
- 8 spaces (2 floors → 5 rooms + 1 entrance + 2 areas)
- 150+ recognition events over past 7 days
- 8 visitors in various states
- 5 automation rules
- 360 energy log entries (72h @ 5min intervals)
- Device status history
"""

import asyncio
import json
import math
import random
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, "..")  # so script works from scripts/ or server/

from app.models.database import async_session_factory, init_db
from app.models.models import (
    Alert, AuditLog, Device, EnergyLog, Event, Face, Person, Permission,
    Role, RolePermission, Rule, Space, Tenant, User, UserRole, Visitor,
)
from app.services.auth_service import hash_password


# ═══════════════════════════════════════════════════════════════════════════
# Faker helpers
# ═══════════════════════════════════════════════════════════════════════════

NAMES_ZH = [
    ("张伟", "研发部"), ("王芳", "市场部"), ("李娜", "财务部"),
    ("刘洋", "人事部"), ("陈静", "行政部"), ("杨磊", "研发部"),
    ("赵敏", "研发部"), ("黄强", "运维部"), ("周杰", "安保部"),
    ("吴红", "市场部"), ("徐明", "财务部"), ("孙丽", "人事部"),
    ("马超", "研发部"), ("朱婷", "行政部"), ("胡亮", "运维部"),
    ("郭晶", "研发部"), ("林峰", "安保部"), ("何云", "市场部"),
    ("高峰", "财务部"), ("罗琳", "人事部"),
]

BLE_MACS = [
    "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03",
    "AA:BB:CC:DD:EE:04", "AA:BB:CC:DD:EE:05", "AA:BB:CC:DD:EE:06",
    "AA:BB:CC:DD:EE:07", "AA:BB:CC:DD:EE:08", "AA:BB:CC:DD:EE:09",
    "AA:BB:CC:DD:EE:10", "AA:BB:CC:DD:EE:11", "AA:BB:CC:DD:EE:12",
    "AA:BB:CC:DD:EE:13", "AA:BB:CC:DD:EE:14", "AA:BB:CC:DD:EE:15",
    "AA:BB:CC:DD:EE:16", "AA:BB:CC:DD:EE:17", "AA:BB:CC:DD:EE:18",
    "AA:BB:CC:DD:EE:19", "AA:BB:CC:DD:EE:20",
]

FLOORS = ["1F", "2F"]
SPACES_DEF = [
    # (name, type, parent_name_or_None, floor, access_level, capacity, area)
    ("A栋", "area", None, None, 1, 0, 2000.0),
    ("A栋一楼", "floor", "A栋", "1F", 1, 0, 1000.0),
    ("A栋二楼", "floor", "A栋", "2F", 1, 0, 1000.0),
    ("大门入口", "entrance", "A栋一楼", "1F", 1, 0, 20.0),
    ("101会议室", "room", "A栋一楼", "1F", 2, 10, 50.0),
    ("102会议室", "room", "A栋一楼", "1F", 2, 20, 80.0),
    ("大厅", "area", "A栋一楼", "1F", 1, 0, 200.0),
    ("201会议室", "room", "A栋二楼", "2F", 2, 15, 60.0),
    ("202多功能厅", "room", "A栋二楼", "2F", 2, 30, 120.0),
    ("财务部", "area", "A栋二楼", "2F", 3, 0, 100.0),
]


DEVICES = [
    {"node_id": "door-01", "name": "大门门禁", "location": "A栋一楼大门入口",
     "device_type": "camera", "space_name": "大门入口"},
    {"node_id": "corridor-01", "name": "走廊节点", "location": "A栋一楼走廊天花",
     "device_type": "camera", "space_name": "大厅"},
    {"node_id": "meeting-01", "name": "101会议室节点", "location": "101会议室入口",
     "device_type": "camera", "space_name": "101会议室"},
]


def make_embedding(seed: int) -> list[float]:
    """Generate a deterministic 128-d fake embedding for a person."""
    rng = random.Random(seed)
    vec = [rng.gauss(0, 0.1) for _ in range(128)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [round(x / norm, 6) for x in vec]


def random_event_time(days_ago: int, hour_bias: int = 9) -> datetime:
    """Generate a random event timestamp within business hours."""
    d = datetime.utcnow() - timedelta(days=random.uniform(0, days_ago))
    hour = (hour_bias + random.gauss(0, 3)) % 24
    d = d.replace(hour=int(hour), minute=random.randint(0, 59),
                   second=random.randint(0, 59), microsecond=0)
    return d


def random_rssi() -> int:
    return random.randint(-85, -30)


# ═══════════════════════════════════════════════════════════════════════════


async def seed(force: bool = False):
    """Main seed function — idempotent unless --force."""
    async with async_session_factory() as db:
        # Check if already seeded
        existing = await db.execute(
            __import__("sqlalchemy").select(Person).limit(1)
        )
        if existing.scalar_one_or_none() and not force:
            print("Database already seeded. Use --force to re-seed.")
            return

        if force:
            print("Force mode: clearing existing data...")
            for table in [EnergyLog, Alert, AuditLog, Event, Rule, Visitor,
                          Face, Person, Device, Space, UserRole, RolePermission,
                          Role, Permission, User, Tenant]:
                await db.execute(table.__table__.delete())
            await db.commit()

        now = datetime.utcnow()

        # ── 1. Tenant ─────────────────────────────────────────────────
        tenant = Tenant(name="默认组织", code="default", tier="enterprise",
                        max_devices=50, max_persons=500)
        db.add(tenant)
        await db.flush()
        print(f"[1/9] Tenant created: {tenant.name}")

        # ── 2. Permissions ───────────────────────────────────────────
        perm_defs = [
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
        perm_objects = {}
        for code, name, resource, action in perm_defs:
            p = Permission(code=code, name=name, resource=resource, action=action,
                           description=name)
            db.add(p)
            perm_objects[code] = p
        await db.flush()
        print(f"[2/9] {len(perm_defs)} permissions created")

        # ── 3. Roles ──────────────────────────────────────────────────
        role_defs = {
            "admin": "超级管理员，系统全部权限",
            "hr": "人事管理员，负责人事管理",
            "it": "IT运维，负责设备和系统配置",
            "security": "安保人员，查看监控/识别/告警",
            "reception": "前台接待，负责访客",
            "employee": "普通员工，仅查看大屏",
        }
        role_perms = {
            "admin": [p[0] for p in perm_defs],
            "hr": ["person:read", "person:write", "dashboard:view"],
            "it": ["device:read", "device:write", "space:read", "space:write",
                   "rule:read", "rule:write", "energy:read", "dashboard:view"],
            "security": ["person:read", "visitor:read", "visitor:approve",
                          "device:read", "event:read", "dashboard:view"],
            "reception": ["visitor:read", "visitor:write", "dashboard:view"],
            "employee": ["dashboard:view"],
        }
        role_objects = {}
        for name, desc in role_defs.items():
            role = Role(tenant_id=tenant.id, name=name, description=desc, is_system=True)
            db.add(role)
            await db.flush()
            for pc in role_perms[name]:
                db.add(RolePermission(role_id=role.id, permission_id=perm_objects[pc].id))
            role_objects[name] = role
        await db.flush()
        print(f"[3/9] {len(role_defs)} roles created")

        # ── 4. Users ──────────────────────────────────────────────────
        user_defs = [
            ("admin", "admin123", "超级管理", ["admin"], True),
            ("hr_wang", "hr123", "王人事", ["hr"], False),
            ("it_li", "it123", "李运维", ["it"], False),
            ("sec_zhang", "sec123", "张保安", ["security"], False),
            ("rec_zhao", "rec123", "赵前台", ["reception"], False),
            ("emp_liu", "emp123", "刘员工", ["employee"], False),
        ]
        users = {}
        for uname, pw, dname, roles, is_sa in user_defs:
            u = User(tenant_id=tenant.id, username=uname,
                     password_hash=hash_password(pw),
                     display_name=dname, is_superadmin=is_sa)
            db.add(u)
            await db.flush()
            for rname in roles:
                db.add(UserRole(user_id=u.id, role_id=role_objects[rname].id))
            users[uname] = u
        await db.flush()
        print(f"[4/9] {len(user_defs)} users created")

        # ── 5. Spaces ─────────────────────────────────────────────────
        space_objects = {}
        for sname, stype, parent_name, sfloor, slevel, scap, sarea in SPACES_DEF:
            parent_id = space_objects[parent_name].id if parent_name else None
            s = Space(tenant_id=tenant.id, name=sname, type=stype,
                      parent_id=parent_id, floor=sfloor or "",
                      area=sarea, capacity=scap,
                      occupancy=random.randint(0, max(1, scap // 2)),
                      access_level=slevel)
            db.add(s)
            await db.flush()
            space_objects[sname] = s
        await db.flush()
        print(f"[5/9] {len(SPACES_DEF)} spaces created")

        # ── 6. Devices ────────────────────────────────────────────────
        device_objects = {}
        for dd in DEVICES:
            space = space_objects.get(dd["space_name"])
            dev = Device(
                tenant_id=tenant.id, node_id=dd["node_id"], name=dd["name"],
                location=dd["location"], device_type=dd["device_type"],
                is_online=True, last_seen=now - timedelta(seconds=random.randint(0, 60)),
                config_json={"face_threshold": 0.55, "led_brightness": 80},
            )
            db.add(dev)
            await db.flush()
            device_objects[dd["node_id"]] = dev
        await db.flush()
        print(f"[6/9] {len(DEVICES)} devices created")

        # ── 7. Persons + Faces ────────────────────────────────────────
        persons = []
        for idx, (pname, dept) in enumerate(NAMES_ZH):
            person = Person(
                tenant_id=tenant.id, name=pname,
                employee_id=f"EMP{idx+1:03d}", department=dept,
                person_type=random.choices(
                    ["employee", "vip", "contractor"],
                    weights=[80, 10, 10]
                )[0],
                phone=f"138{random.randint(10000000, 99999999)}",
                email=f"{pname.lower()}@company.com",
                ble_mac=BLE_MACS[idx] if idx < len(BLE_MACS) else "",
                access_level=random.randint(1, 3),
                is_active=True,
            )
            db.add(person)
            await db.flush()

            # Register a face for each person
            embedding = make_embedding(idx)
            face = Face(person_id=person.id, embedding=embedding,
                        image_url=f"/data/faces/{person.id}_{0}.jpg",
                        quality_score=round(random.uniform(0.75, 0.98), 2))
            db.add(face)

            persons.append(person)
        await db.flush()
        print(f"[7/9] {len(persons)} persons with faces created")

        # ── 8. Events (150+ recognition events) ───────────────────────
        decisions = ["granted", "granted", "granted", "granted",  # 80% granted
                     "denied", "unknown"]
        events_created = 0
        for i in range(180):
            person = random.choice(persons)
            device_id = random.choice(list(device_objects.values())).id
            node_id = random.choice(list(device_objects.keys()))
            face_c = round(random.uniform(0.3, 0.95), 4)
            gait_c = round(random.uniform(0.0, 0.6), 4)
            ble_c = round(random.uniform(0.0, 0.7), 4)
            dec = random.choice(decisions)
            mod_count = random.randint(1, 3)
            fusion_c = round((face_c * 0.6 + gait_c * 0.2 + ble_c * 0.2), 4)

            evt = Event(
                tenant_id=tenant.id,
                person_id=person.id if dec != "unknown" else None,
                person_name=person.name if dec != "unknown" else "未知",
                device_id=device_id, node_id=node_id,
                face_conf=face_c, gait_conf=gait_c, ble_conf=ble_c,
                fusion_conf=fusion_c, modality_count=mod_count,
                light_level=round(random.uniform(0.3, 1.0), 2),
                decision=dec,
                explain_text=(
                    f"多模态融合确认 {person.name}（置信度 {fusion_c:.2f}）"
                    if dec == "granted" else
                    f"未识别到匹配人员（置信度 {fusion_c:.2f}）"
                ),
                created_at=random_event_time(7),
            )
            db.add(evt)
            events_created += 1

            # Every 20 events, add an alert
            if i % 20 == 0 and i > 0:
                alert = Alert(
                    tenant_id=tenant.id,
                    level=random.choice(["info", "warning", "critical"]),
                    type="unauthorized_access" if random.random() > 0.5 else "device_offline",
                    title="未授权通行检测" if random.random() > 0.5 else "设备离线告警",
                    message=f"检测到异常通行事件 (conf={fusion_c:.2f})",
                    related_event_id=i,
                    related_person_id=person.id if dec == "denied" else None,
                    created_at=evt.created_at,
                )
                db.add(alert)
        await db.flush()
        print(f"[8/9] {events_created} events + alerts created")

        # ── 9a. Visitors ──────────────────────────────────────────────
        visitor_states = [
            ("赵访客", "13900000001", 1, "商务洽谈",
             now - timedelta(hours=2), now - timedelta(hours=2),
             now + timedelta(hours=4), "checked_in", None, now - timedelta(hours=1)),
            ("钱访客", "13900000002", 2, "面试",
             now + timedelta(hours=24), now + timedelta(hours=24),
             now + timedelta(hours=28), "approved", 1, None),
            ("孙访客", "13900000003", 3, "拜访",
             now + timedelta(hours=48), now + timedelta(hours=48),
             now + timedelta(hours=52), "pending", None, None),
            ("李访客", "13900000004", 1, "设备检修",
             now - timedelta(days=1), now - timedelta(days=1),
             now - timedelta(hours=2), "checked_out", 1,
             now - timedelta(hours=3)),
            ("周访客", "13900000005", 4, "项目对接",
             now - timedelta(hours=3), now - timedelta(hours=3),
             now + timedelta(hours=1), "approved", 1, None),
            ("吴访客", "13900000006", 5, "送货",
             now + timedelta(hours=72), now + timedelta(hours=72),
             now + timedelta(hours=76), "pending", None, None),
            ("郑访客", "13900000007", 2, "客户会议",
             now + timedelta(hours=4), now + timedelta(hours=4),
             now + timedelta(hours=6), "approved", 1, None),
            ("王访客", "13900000008", 3, "面试",
             now - timedelta(days=3), now - timedelta(days=3),
             now - timedelta(days=2), "denied", 1, None),
        ]
        for vname, vphone, host_id, purpose, expected, vfrom, vuntil, status, approver, checkin in visitor_states:
            v = Visitor(
                tenant_id=tenant.id, name=vname, phone=vphone,
                host_person_id=host_id, purpose=purpose,
                expected_at=expected, valid_from=vfrom, valid_until=vuntil,
                status=status, approved_by=approver,
                approved_at=now if approver else None,
                checked_in_at=checkin,
            )
            if status == "denied":
                v.denied_reason = "受访人暂时不便接待"
            db.add(v)
        await db.flush()
        print(f"[9/9] Visitors, rules, energy logs, audit logs...")

        # ── 9b. Rules ─────────────────────────────────────────────────
        rules_data = [
            {"name": "非工作时间敏感区告警", "trigger_type": "recognition",
             "trigger_config": {"time_range": ["20:00", "08:00"], "space_ids": [10]},
             "action_type": "create_alert",
             "action_config": {"level": "critical", "title": "非工作时间敏感区域通行"}},
            {"name": "会议室无人关灯", "trigger_type": "recognition",
             "trigger_config": {"space_ids": [5, 6], "decision": "denied", "timeout_seconds": 600},
             "action_type": "mqtt_publish",
             "action_config": {"topic": "vela/server/command/light-ctrl",
                               "payload": {"cmd": "off"}}},
            {"name": "连续失败身份验证", "trigger_type": "recognition",
             "trigger_config": {"max_failures": 3, "window_minutes": 5},
             "action_type": "create_alert",
             "action_config": {"level": "warning", "title": "连续身份验证失败"}},
            {"name": "访客到达通知", "trigger_type": "recognition",
             "trigger_config": {"person_types": ["visitor"]},
             "action_type": "webhook",
             "action_config": {"url": "http://notify.internal/visitor-arrived"}},
            {"name": "设备离线告警", "trigger_type": "device_offline",
             "trigger_config": {"timeout_seconds": 30},
             "action_type": "create_alert",
             "action_config": {"level": "warning", "title": "设备离线"}},
        ]
        for r in rules_data:
            db.add(Rule(tenant_id=tenant.id, **r, priority=1, is_enabled=True))
        await db.flush()

        # ── 9c. Energy Logs (72h, 360 entries, distributed by area) ─────
        base_time = now - timedelta(hours=72)
        area_spaces = [s for s in SPACES_DEF if s[1] in ("area", "room", "floor")]
        area_space_objects = [space_objects[s[0]] for s in area_spaces]
        for i in range(360):
            t = base_time + timedelta(minutes=i * 12)  # ~12 min intervals
            hour_factor = 1.0 + 0.5 * math.sin(2 * math.pi * t.hour / 24)
            space = random.choice(area_space_objects)
            # Different spaces have different base power consumption
            base_power = {"room": 10, "floor": 50, "area": 100}.get(space.type, 20)
            power = round(random.uniform(base_power * 0.5, base_power * 1.5) * hour_factor, 2)
            db.add(EnergyLog(
                tenant_id=tenant.id, device_id=device_objects["door-01"].id,
                space_id=space.id,
                metric="power", value=power, unit="W",
                source="device", recorded_at=t,
            ))
        await db.flush()

        # ── 9d. Audit Logs ────────────────────────────────────────────
        actions = [
            "person.create", "person.update", "person.delete",
            "device.create", "visitor.approve", "rule.create",
            "user.login", "user.login", "user.login",
        ]
        for i in range(30):
            db.add(AuditLog(
                tenant_id=tenant.id, user_id=random.choice(list(users.values())).id,
                action=random.choice(actions),
                resource_type=random.choice(["person", "device", "visitor", "rule"]),
                resource_id=str(random.randint(1, 20)),
                ip_address=random.choice(["192.168.1.100", "192.168.1.101", "10.0.0.1"]),
                created_at=random_event_time(3),
            ))
        await db.commit()
        print(f"[DONE] All seed data inserted successfully!")

        # Summary
        from sqlalchemy import func, select
        counts = {
            "Tenants": (await db.execute(select(func.count()).select_from(Tenant))).scalar(),
            "Users": (await db.execute(select(func.count()).select_from(User))).scalar(),
            "Persons": (await db.execute(select(func.count()).select_from(Person))).scalar(),
            "Faces": (await db.execute(select(func.count()).select_from(Face))).scalar(),
            "Devices": (await db.execute(select(func.count()).select_from(Device))).scalar(),
            "Spaces": (await db.execute(select(func.count()).select_from(Space))).scalar(),
            "Events": (await db.execute(select(func.count()).select_from(Event))).scalar(),
            "Alerts": (await db.execute(select(func.count()).select_from(Alert))).scalar(),
            "Visitors": (await db.execute(select(func.count()).select_from(Visitor))).scalar(),
            "Rules": (await db.execute(select(func.count()).select_from(Rule))).scalar(),
            "EnergyLogs": (await db.execute(select(func.count()).select_from(EnergyLog))).scalar(),
            "AuditLogs": (await db.execute(select(func.count()).select_from(AuditLog))).scalar(),
        }
        print("\n📊 Seed Summary:")
        for k, v in counts.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    asyncio.run(seed(force=force))
