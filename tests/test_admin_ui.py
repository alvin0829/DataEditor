"""Tests for admin UI page and user-settings CRUD API."""

import time
import pytest


# ---------------------------------------------------------------------------
# Admin page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_page_returns_200_html(client):
    resp = await client.get("/admin")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "User Settings" in resp.text


@pytest.mark.asyncio
async def test_root_serves_admin_on_api_port(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert "User Settings" in resp.text


@pytest.mark.asyncio
async def test_root_follows_to_admin(client):
    resp = await client.get("/", follow_redirects=True)
    assert resp.status_code == 200
    assert "User Settings" in resp.text


# ---------------------------------------------------------------------------
# User Settings CRUD
# ---------------------------------------------------------------------------

SAMPLE_SETTING = {
    "email": "alice@example.com",
    "display_name": "Alice Smith",
    "role": "admin",
    "theme": "dark",
    "density": "compact",
    "sidebar": "visible",
    "notifications": "on",
    "active": True,
}


async def _create_setting(client, overrides=None):
    payload = {**SAMPLE_SETTING, **(overrides or {})}
    return await client.post("/api/user-settings", json=payload)


# Create


@pytest.mark.asyncio
async def test_create_user_setting_201(client):
    resp = await _create_setting(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["display_name"] == "Alice Smith"
    assert body["id"]
    assert "created_at" in body


@pytest.mark.asyncio
async def test_create_user_setting_duplicate_409(client):
    await _create_setting(client)
    resp = await _create_setting(client)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_user_setting_empty_email_422(client):
    resp = await _create_setting(client, {"email": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_user_setting_whitespace_email_422(client):
    resp = await _create_setting(client, {"email": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_user_setting_whitespace_display_name_422(client):
    resp = await _create_setting(client, {"display_name": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_user_setting_strips_whitespace(client):
    resp = await _create_setting(client, {
        "email": "  bob@example.com  ",
        "display_name": "  Bob Jones  ",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "bob@example.com"
    assert body["display_name"] == "Bob Jones"


@pytest.mark.asyncio
async def test_create_user_setting_normalizes_email_lowercase(client):
    resp = await _create_setting(client, {"email": "CHARLIE@Example.COM"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "charlie@example.com"


# List


@pytest.mark.asyncio
async def test_list_user_settings_empty(client):
    resp = await client.get("/api/user-settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_user_settings_returns_items(client):
    await _create_setting(client, {"email": "list1@test.com"})
    await _create_setting(client, {"email": "list2@test.com"})
    resp = await client.get("/api/user-settings")
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_list_user_settings_search_q(client):
    await _create_setting(client, {"email": "search-abc@test.com", "display_name": "Alpha"})
    await _create_setting(client, {"email": "search-xyz@test.com", "display_name": "Zeta"})
    resp = await client.get("/api/user-settings", params={"q": "abc"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "search-abc@test.com"


@pytest.mark.asyncio
async def test_list_user_settings_search_by_name(client):
    await _create_setting(client, {"email": "n1@test.com", "display_name": "FooBar"})
    await _create_setting(client, {"email": "n2@test.com", "display_name": "BazQux"})
    resp = await client.get("/api/user-settings", params={"q": "Foo"})
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "FooBar"


# Get by id


@pytest.mark.asyncio
async def test_get_user_setting_by_id(client):
    created = (await _create_setting(client)).json()
    resp = await client.get(f"/api/user-settings/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_get_user_setting_not_found_404(client):
    resp = await client.get("/api/user-settings/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_user_setting_invalid_uuid_422(client):
    resp = await client.get("/api/user-settings/not-a-uuid")
    assert resp.status_code == 422


# Update (PATCH)


@pytest.mark.asyncio
async def test_patch_user_setting_updates_fields(client):
    created = (await _create_setting(client)).json()
    resp = await client.patch(
        f"/api/user-settings/{created['id']}",
        json={"theme": "light", "role": "viewer"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["theme"] == "light"
    assert body["role"] == "viewer"
    assert body["email"] == "alice@example.com"  # unchanged


@pytest.mark.asyncio
async def test_patch_user_setting_not_found_404(client):
    resp = await client.patch(
        "/api/user-settings/00000000-0000-0000-0000-000000000000",
        json={"theme": "dark"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_user_setting_duplicate_email_409(client):
    r1 = (await _create_setting(client, {"email": "dup-a@test.com"})).json()
    await _create_setting(client, {"email": "dup-b@test.com"})
    resp = await client.patch(
        f"/api/user-settings/{r1['id']}", json={"email": "dup-b@test.com"}
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_patch_user_setting_invalid_uuid_422(client):
    resp = await client.patch(
        "/api/user-settings/not-a-uuid",
        json={"theme": "dark"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_user_setting_whitespace_email_422(client):
    created = (await _create_setting(client)).json()
    resp = await client.patch(
        f"/api/user-settings/{created['id']}",
        json={"email": "   "},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_user_setting_strips_whitespace(client):
    created = (await _create_setting(client, {"email": "strip@test.com"})).json()
    resp = await client.patch(
        f"/api/user-settings/{created['id']}",
        json={"display_name": "  Stripped  "},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Stripped"


# Delete


@pytest.mark.asyncio
async def test_delete_user_setting_204(client):
    created = (await _create_setting(client)).json()
    resp = await client.delete(f"/api/user-settings/{created['id']}")
    assert resp.status_code == 204

    # Confirm it's gone
    resp = await client.get(f"/api/user-settings/{created['id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_setting_not_found_404(client):
    resp = await client.delete("/api/user-settings/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_user_setting_invalid_uuid_422(client):
    resp = await client.delete("/api/user-settings/not-a-uuid")
    assert resp.status_code == 422


# Defaults


@pytest.mark.asyncio
async def test_create_user_setting_uses_defaults(client):
    resp = await client.post(
        "/api/user-settings",
        json={"email": "defaults@test.com", "display_name": "Defaults"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["display_name"] == "Defaults"
    assert body["role"] == "user"
    assert body["theme"] == "light"
    assert body["density"] == "default"
    assert body["sidebar"] == "visible"
    assert body["notifications"] == "on"
    assert body["active"] is True


@pytest.mark.asyncio
async def test_create_user_setting_requires_display_name(client):
    resp = await client.post("/api/user-settings", json={"email": "nameless@test.com"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_user_setting_rejects_invalid_enum(client):
    resp = await _create_setting(client, {"theme": "neon"})
    assert resp.status_code == 422

# ---------------------------------------------------------------------------
# Sheet access control API tests
# ---------------------------------------------------------------------------


def _ldap_env_with_sheet_access(monkeypatch):
    """Configure LDAP mode with sheet access rules."""
    import json
    monkeypatch.setenv("AUTH_MODE", "ldap")
    monkeypatch.setenv("LDAP_SERVER_URI", "ldaps://directory.test:636")
    monkeypatch.setenv("LDAP_USER_BASE_DN", "ou=users,dc=test")
    monkeypatch.setenv("LDAP_ADMIN_GROUP_DN", "cn=admins,ou=groups,dc=test")
    monkeypatch.setenv("SESSION_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv(
        "LDAP_SHEET_ACCESS_JSON",
        json.dumps({
            "xxx": {"groups": ["cn=xxx-editors,ou=groups,dc=test"], "departments": []},
            "settings": {"groups": ["cn=settings-editors,ou=groups,dc=test"], "departments": []},
        }),
    )


@pytest.mark.asyncio
async def test_contract_services_denied_without_xxx_sheet(client, monkeypatch):
    """User without xxx sheet gets 403 on contract-services endpoints."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "bob", "Bob", "bob@test", False,
        groups=("cn=settings-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("settings",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.get("/api/contract-services")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_settings_denied_without_settings_sheet(client, monkeypatch):
    """User without settings sheet gets 403 on user-settings endpoints."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "carol", "Carol", "carol@test", False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.get("/api/user-settings")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contract_services_allowed_with_xxx_sheet(client, monkeypatch):
    """User with xxx sheet can access contract-services."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "dave", "Dave", "dave@test", False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.get("/api/contract-services")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_user_settings_allowed_with_settings_sheet(client, monkeypatch):
    """User with settings sheet can access user-settings."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "eve", "Eve", "eve@test", False,
        groups=("cn=settings-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("settings",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.get("/api/user-settings")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_console_requires_global_admin(client, monkeypatch):
    """Non-admin user cannot access admin-console even with sheet access."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "frank", "Frank", "frank@test", False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.get("/admin-console")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_auth_me_returns_editable_sheets(client, monkeypatch):
    """/api/auth/me returns editable_sheets for authenticated user."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "grace", "Grace", "grace@test", False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=("maintenance",), editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["editable_sheets"] == ["xxx"]
    assert body["groups"] == ["cn=xxx-editors,ou=groups,dc=test"]
    assert body["departments"] == ["maintenance"]


@pytest.mark.asyncio
async def test_disabled_mode_identity_has_all_sheets(client):
    """Disabled mode identity returns both sheets."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["editable_sheets"]) == {"xxx", "settings"}
    assert body["is_admin"] is True



# ---------------------------------------------------------------------------
# Finding 1: Contract-service update/delete/import authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_service_update_denied_without_xxx_sheet(client, monkeypatch):
    """Non-admin user without xxx sheet gets 403 on PATCH /api/contract-services/{id}."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    # Create record in disabled mode first
    created = (await client.post("/api/contract-services", json={
        "contract_no": "TEST-001",
        "fields": {"RBQ No.": "RBQ-UPD-001", "Status": "Open"},
    })).json()
    assert "id" in created, f"Setup failed: {created}"
    # Switch to LDAP mode with non-xxx user
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "noxxx", "NoXxx", "noxxx@test", False,
        groups=("cn=settings-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("settings",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.patch(
        f"/api/contract-services/{created['id']}",
        json={"fields": {"RBQ No.": "RBQ-UPD-001", "Status": "Closed"}},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contract_service_delete_denied_without_xxx_sheet(client, monkeypatch):
    """Non-admin user without xxx sheet gets 403 on DELETE /api/contract-services/{id}."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    # Create record in disabled mode first
    created = (await client.post("/api/contract-services", json={
        "contract_no": "TEST-002",
        "fields": {"RBQ No.": "RBQ-DEL-001", "Status": "Open"},
    })).json()
    assert "id" in created, f"Setup failed: {created}"
    # Switch to LDAP mode with non-xxx user
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "noxxx2", "NoXxx2", "noxxx2@test", False,
        groups=("cn=settings-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("settings",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.delete(f"/api/contract-services/{created['id']}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contract_service_import_denied_without_xxx_sheet(client, monkeypatch):
    """Non-admin user without xxx sheet gets 403 on POST /api/contract-services/import."""
    import csv, io
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    from backend.schemas import CONTRACT_SERVICE_CSV_HEADERS
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "noxxx3", "NoXxx3", "noxxx3@test", False,
        groups=("cn=settings-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("settings",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(CONTRACT_SERVICE_CSV_HEADERS)
    values = [""] * len(CONTRACT_SERVICE_CSV_HEADERS)
    values[0] = "Schedule B3"
    values[19] = "RBQ-IMP-001"
    writer.writerow(values)
    csv_bytes = content.getvalue().encode("utf-8")
    resp = await client.post(
        "/api/contract-services/import",
        data={"contract_no": "TEST-IMP"},
        files={"file": ("xxx.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_contract_service_update_allowed_with_xxx_sheet(client, monkeypatch):
    """Non-admin user with xxx sheet can PATCH /api/contract-services/{id}."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    # Create record in disabled mode first
    created = (await client.post("/api/contract-services", json={
        "contract_no": "TEST-003",
        "fields": {"RBQ No.": "RBQ-UPD-OK", "Status": "Open"},
    })).json()
    assert "id" in created, f"Setup failed: {created}"
    # Switch to LDAP mode with xxx user
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "xxxuser", "XxxUser", "xxx@test", False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.patch(
        f"/api/contract-services/{created['id']}",
        json={"fields": {"RBQ No.": "RBQ-UPD-OK", "Status": "Closed"}},
    )
    assert resp.status_code == 200
    assert resp.json()["fields"]["Status"] == "Closed"


@pytest.mark.asyncio
async def test_contract_service_delete_allowed_with_xxx_sheet(client, monkeypatch):
    """Non-admin user with xxx sheet can DELETE /api/contract-services/{id}."""
    from backend.auth import AuthIdentity, COOKIE_NAME, load_auth_config, create_session_token
    # Create record in disabled mode first
    created = (await client.post("/api/contract-services", json={
        "contract_no": "TEST-004",
        "fields": {"RBQ No.": "RBQ-DEL-OK", "Status": "Open"},
    })).json()
    assert "id" in created, f"Setup failed: {created}"
    # Switch to LDAP mode with xxx user
    _ldap_env_with_sheet_access(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "xxxuser2", "XxxUser2", "xxx2@test", False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=(), editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=int(time.time()))
    client.cookies.set(COOKIE_NAME, token)
    resp = await client.delete(f"/api/contract-services/{created['id']}")
    assert resp.status_code == 204

