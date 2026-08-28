"""Tests for CRUD endpoints."""

import pytest


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

SAMPLE = {
    "request_number": "REQ-001",
    "department": "IT",
    "status": "open",
    "data": {"priority": "high"},
}


async def _create(client, overrides=None):
    payload = {**SAMPLE, **(overrides or {})}
    return await client.post("/api/requests", json=payload)


# -----------------------------------------------------------------------
# Create
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_201(client):
    resp = await _create(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["request_number"] == "REQ-001"
    assert body["id"]
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_empty_number_422(client):
    resp = await _create(client, {"request_number": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_empty_department_422(client):
    resp = await _create(client, {"department": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_whitespace_only_fields_422(client):
    resp = await _create(client, {"department": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_duplicate_409(client):
    await _create(client)
    resp = await _create(client)
    assert resp.status_code == 409


# -----------------------------------------------------------------------
# List
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_empty(client):
    resp = await client.get("/api/requests")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_returns_items(client):
    await _create(client, {"request_number": "L-1"})
    await _create(client, {"request_number": "L-2"})
    resp = await client.get("/api/requests")
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_list_filter_department(client):
    await _create(client, {"request_number": "F1", "department": "HR"})
    await _create(client, {"request_number": "F2", "department": "IT"})
    resp = await client.get("/api/requests", params={"department": "HR"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["department"] == "HR"


@pytest.mark.asyncio
async def test_list_filter_status(client):
    await _create(client, {"request_number": "S1", "status": "open"})
    await _create(client, {"request_number": "S2", "status": "closed"})
    resp = await client.get("/api/requests", params={"status": "closed"})
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_list_search_q(client):
    await _create(client, {"request_number": "ABC-123"})
    await _create(client, {"request_number": "XYZ-789"})
    resp = await client.get("/api/requests", params={"q": "abc"})
    assert resp.json()["total"] == 1


# -----------------------------------------------------------------------
# Get by id
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_by_id(client):
    created = (await _create(client)).json()
    resp = await client.get(f"/api/requests/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["request_number"] == "REQ-001"


@pytest.mark.asyncio
async def test_get_not_found_404(client):
    resp = await client.get("/api/requests/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_invalid_uuid_422(client):
    resp = await client.get("/api/requests/not-a-uuid")
    assert resp.status_code == 422


# -----------------------------------------------------------------------
# Update (PATCH)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_updates_fields(client):
    created = (await _create(client)).json()
    resp = await client.patch(
        f"/api/requests/{created['id']}",
        json={"status": "closed", "data": {"resolution": "fixed"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "closed"
    assert body["data"]["resolution"] == "fixed"


@pytest.mark.asyncio
async def test_patch_not_found_404(client):
    resp = await client.patch(
        "/api/requests/00000000-0000-0000-0000-000000000000",
        json={"status": "closed"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_duplicate_number_409(client):
    r1 = (await _create(client, {"request_number": "DUP-A"})).json()
    await _create(client, {"request_number": "DUP-B"})
    resp = await client.patch(
        f"/api/requests/{r1['id']}", json={"request_number": "DUP-B"}
    )
    assert resp.status_code == 409


# -----------------------------------------------------------------------
# Audit
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_writes_audit(client, db_session):
    created = (await _create(client)).json()
    from backend.models import AuditLog
    from sqlalchemy import select

    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "create"
    assert str(rows[0].request_id) == created["id"]


@pytest.mark.asyncio
async def test_update_writes_audit(client, db_session):
    created = (await _create(client)).json()
    await client.patch(f"/api/requests/{created['id']}", json={"status": "wip"})

    from backend.models import AuditLog
    from sqlalchemy import select
    from uuid import UUID

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.request_id == UUID(created["id"]))
        )
    ).scalars().all()
    assert len(rows) == 2
    actions = sorted(r.action for r in rows)
    assert actions == ["create", "update"]
    # update row should have old_data
    update_row = next(r for r in rows if r.action == "update")
    assert update_row.old_data is not None
    assert update_row.old_data["status"] == "open"
