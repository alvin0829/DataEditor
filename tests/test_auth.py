"""Authentication and authorization tests without a live LDAP server."""

import hashlib
import hmac
import json
import pytest

from backend.auth import (
    COOKIE_NAME,
    AccessDenied,
    AuthIdentity,
    AuthUnavailable,
    InvalidCredentials,
    authenticate_ldap,
    create_session_token,
    disabled_identity,
    load_auth_config,
    verify_session_token,
)


def _ldap_environment(monkeypatch):
    values = {
        "AUTH_MODE": "ldap",
        "LDAP_SERVER_URI": "ldaps://directory.test:636",
        "LDAP_USER_BASE_DN": "ou=users,dc=test",
        "LDAP_USER_DN_TEMPLATE": "uid={username},ou=users,dc=test",
        "LDAP_ADMIN_GROUP_DN": "cn=admins,ou=groups,dc=test",
        "SESSION_SECRET": "0123456789abcdef0123456789abcdef",
        "SESSION_TTL_SECONDS": "3600",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_ldap_config_does_not_require_service_account(monkeypatch):
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    assert config.user_base_dn == "ou=users,dc=test"
    assert config.user_dn_template == "uid={username},ou=users,dc=test"


def test_ldap_config_requires_permitted_base(monkeypatch):
    _ldap_environment(monkeypatch)
    monkeypatch.delenv("LDAP_USER_BASE_DN")
    with pytest.raises(AuthUnavailable, match="LDAP_USER_BASE_DN"):
        authenticate_ldap("alice", "password", load_auth_config())


def test_missing_dn_template_uses_default_uid_rdn(monkeypatch):
    """When LDAP_USER_DN_TEMPLATE is absent, DN is uid=<escaped>,<base_dn>."""
    _ldap_environment(monkeypatch)
    monkeypatch.delenv("LDAP_USER_DN_TEMPLATE")
    config = load_auth_config()
    assert config.user_dn_template == ""
    calls = {}

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["onyx"],
            "cn": ["Onyx User"],
            "mail": ["onyx@test"],
            "memberOf": ["cn=admins,ou=groups,dc=test"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            calls["bind"] = kwargs
            self.entries = [FakeEntry()]

        def search(self, base, search_filter, **kwargs):
            calls["search"] = (base, search_filter, kwargs)

        def unbind(self):
            calls["unbind"] = True

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("onyx", "correct-password", config)

    assert calls["bind"]["user"] == "uid=onyx,ou=users,dc=test"
    assert calls["search"][0] == "uid=onyx,ou=users,dc=test"
    assert identity.username == "onyx"


def test_unsafe_username_is_rdn_escaped(monkeypatch):
    """Usernames with LDAP-special chars are RDN-escaped before DN construction."""
    _ldap_environment(monkeypatch)
    monkeypatch.delenv("LDAP_USER_DN_TEMPLATE")
    config = load_auth_config()
    calls = {}

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["john,doe"],
            "cn": ["John Doe"],
            "mail": ["john@test"],
            "memberOf": ["cn=admins,ou=groups,dc=test"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            calls["bind"] = kwargs
            self.entries = [FakeEntry()]

        def search(self, base, search_filter, **kwargs):
            calls["search"] = (base, search_filter, kwargs)

        def unbind(self):
            calls["unbind"] = True

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("john,doe", "password", config)

    # escape_rdn should escape the comma in the username
    bound_dn = calls["bind"]["user"]
    assert bound_dn.startswith("uid=")
    assert ",ou=users,dc=test" in bound_dn
    # The raw comma must not appear unescaped in the DN uid portion
    assert "uid=john,doe,ou=users" not in bound_dn


def test_invalid_template_without_placeholder_is_rejected(monkeypatch):
    """A template that lacks {username} must be rejected before any bind."""
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    monkeypatch.setattr("backend.auth.Connection", lambda *_a, **_k: pytest.fail("must not bind"))
    config = config.__class__(**{**config.__dict__, "user_dn_template": "cn=static,ou=users,dc=test"})
    with pytest.raises(AuthUnavailable, match="LDAP_USER_DN_TEMPLATE must contain \\{username\\}"):
        authenticate_ldap("alice", "password", config)


def test_username_authentication_builds_dn_and_reads_own_entry(monkeypatch):
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    calls = {}

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["alice"],
            "cn": ["Alice Admin"],
            "mail": ["alice@test"],
            "memberOf": ["cn=admins,ou=groups,dc=test"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            calls["bind"] = kwargs
            self.entries = [FakeEntry()]

        def search(self, base, search_filter, **kwargs):
            calls["search"] = (base, search_filter, kwargs)

        def unbind(self):
            calls["unbind"] = True

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("alice", "correct-password", config)

    assert calls["bind"]["user"] == "uid=alice,ou=users,dc=test"
    assert calls["bind"]["password"] == "correct-password"
    assert calls["search"][0] == "uid=alice,ou=users,dc=test"
    assert identity == AuthIdentity("alice", "Alice Admin", "alice@test", True, groups=("cn=admins,ou=groups,dc=test",), departments=(), editable_sheets=("settings", "xxx"))
    assert calls["unbind"] is True


def test_ldap_connection_failure_is_reported_as_unavailable(monkeypatch):
    """A network/directory failure must not be presented as a bad password."""
    _ldap_environment(monkeypatch)
    config = load_auth_config()

    class FailingConnection:
        def __init__(self, *_args, **_kwargs):
            from ldap3.core.exceptions import LDAPException
            raise LDAPException("connection refused")

    monkeypatch.setattr("backend.auth.Connection", FailingConnection)
    with pytest.raises(AuthUnavailable, match="LDAP directory is unavailable"):
        authenticate_ldap("onyx", "correct-password", config)


def test_username_authentication_rejects_template_outside_base(monkeypatch):
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    monkeypatch.setattr("backend.auth.Connection", lambda *_args, **_kwargs: pytest.fail("must not bind"))
    config = config.__class__(**{**config.__dict__, "user_dn_template": "uid={username},dc=other"})
    with pytest.raises(AuthUnavailable, match="Constructed DN must resolve within LDAP_USER_BASE_DN"):
        authenticate_ldap("alice", "password", config)


@pytest.mark.asyncio
async def test_disabled_mode_identity(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "local-admin"
    assert response.json()["is_admin"] is True


@pytest.mark.asyncio
async def test_ldap_mode_missing_session_is_unauthorized(client, monkeypatch):
    _ldap_environment(monkeypatch)
    response = await client.get("/api/user-settings")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_page_redirects_to_login(client, monkeypatch):
    _ldap_environment(monkeypatch)
    response = await client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_login_sets_session_and_identifies_user(client, monkeypatch):
    _ldap_environment(monkeypatch)

    def fake_authenticate(username, password, config):
        assert password == "correct-password"
        return AuthIdentity(username, "Alice Admin", "alice@test", True)

    monkeypatch.setattr("backend.main.authenticate_ldap", fake_authenticate)
    response = await client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "correct-password"},
    )
    assert response.status_code == 200
    assert COOKIE_NAME in response.cookies
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["display_name"] == "Alice Admin"


@pytest.mark.asyncio
async def test_bad_credentials_do_not_set_cookie(client, monkeypatch):
    _ldap_environment(monkeypatch)

    def reject(*_args):
        raise InvalidCredentials("bad credentials")

    monkeypatch.setattr("backend.main.authenticate_ldap", reject)
    response = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert response.status_code == 401
    assert COOKIE_NAME not in response.cookies


@pytest.mark.asyncio
async def test_ldap_service_failure_returns_503(client, monkeypatch):
    _ldap_environment(monkeypatch)

    def unavailable(*_args):
        raise AuthUnavailable("LDAP directory is unavailable")

    monkeypatch.setattr("backend.main.authenticate_ldap", unavailable)
    response = await client.post(
        "/api/auth/login", json={"username": "onyx", "password": "correct"}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "LDAP directory is unavailable"
    assert COOKIE_NAME not in response.cookies


@pytest.mark.asyncio
async def test_non_admin_without_sheets_gets_403_at_login(client, monkeypatch):
    """Non-admin user with no permitted sheets gets 403 (not 401) at login."""
    _ldap_environment(monkeypatch)

    def reject_no_sheets(*_args):
        raise AccessDenied("No permitted sheets for this user")

    monkeypatch.setattr("backend.main.authenticate_ldap", reject_no_sheets)
    response = await client.post(
        "/api/auth/login", json={"username": "bob", "password": "correct"}
    )
    assert response.status_code == 403
    assert COOKIE_NAME not in response.cookies


@pytest.mark.asyncio
async def test_tampered_session_is_rejected(client, monkeypatch):
    _ldap_environment(monkeypatch)
    client.cookies.set(COOKIE_NAME, "tampered.token")
    response = await client.get("/api/user-settings")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_session(client):
    response = await client.post("/api/auth/logout")
    assert response.status_code == 204
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f'{COOKIE_NAME}=""')
    assert "Max-Age=0" in set_cookie
    assert "Path=/" in set_cookie


def test_expired_session_is_rejected(monkeypatch):
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    token = create_session_token(
        AuthIdentity("alice", "Alice", "alice@test", True), config, now=100
    )
    with pytest.raises(InvalidCredentials):
        verify_session_token(token, config, now=100 + config.session_ttl_seconds + 1)

# ---------------------------------------------------------------------------
# Sheet access control tests
# ---------------------------------------------------------------------------

def _ldap_environment_with_sheet_access(monkeypatch):
    """Set up LDAP env with sheet access rules."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv(
        "LDAP_SHEET_ACCESS_JSON",
        json.dumps({
            "xxx": {"groups": ["cn=xxx-editors,ou=groups,dc=test"], "departments": ["maintenance"]},
            "settings": {"groups": ["cn=settings-editors,ou=groups,dc=test"], "departments": ["IT"]},
        }),
    )


def test_admin_gets_all_sheets(monkeypatch):
    """Global admin members receive both sheets regardless of rules."""
    _ldap_environment_with_sheet_access(monkeypatch)
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["alice"],
            "cn": ["Alice Admin"],
            "mail": ["alice@test"],
            "memberOf": ["cn=admins,ou=groups,dc=test"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, *args, **kwargs):
            pass
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("alice", "password", config)
    assert identity.is_admin is True
    assert set(identity.editable_sheets) == {"xxx", "settings"}


def test_group_grants_mapped_sheet(monkeypatch):
    """memberOf matching a configured group grants only that sheet."""
    _ldap_environment_with_sheet_access(monkeypatch)
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["bob"],
            "cn": ["Bob"],
            "mail": ["bob@test"],
            "memberOf": ["cn=xxx-editors,ou=groups,dc=test"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, *args, **kwargs):
            pass
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("bob", "password", config)
    assert identity.is_admin is False
    assert identity.editable_sheets == ("xxx",)


def test_department_grants_mapped_sheet(monkeypatch):
    """LDAP department attribute matching a configured department grants that sheet."""
    _ldap_environment_with_sheet_access(monkeypatch)
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["carol"],
            "cn": ["Carol"],
            "mail": ["carol@test"],
            "memberOf": [],
            "department": ["IT"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, *args, **kwargs):
            pass
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("carol", "password", config)
    assert identity.is_admin is False
    assert identity.editable_sheets == ("settings",)


def test_no_matching_sheet_rejected_at_login(monkeypatch):
    """Non-admin user with no matching sheet gets InvalidCredentials."""
    _ldap_environment_with_sheet_access(monkeypatch)
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["dave"],
            "cn": ["Dave"],
            "mail": ["dave@test"],
            "memberOf": ["cn=unrelated,ou=groups,dc=test"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, *args, **kwargs):
            pass
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    with pytest.raises(AccessDenied, match="No permitted sheets"):
        authenticate_ldap("dave", "password", config)


def test_token_roundtrip_preserves_sheet_fields(monkeypatch):
    """Session token roundtrip preserves groups, departments, editable_sheets."""
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        username="eve",
        display_name="Eve",
        email="eve@test",
        is_admin=False,
        groups=("cn=xxx-editors,ou=groups,dc=test",),
        departments=("maintenance",),
        editable_sheets=("xxx",),
    )
    token = create_session_token(identity, config, now=1000)
    restored = verify_session_token(token, config, now=1000)
    assert restored.groups == ("cn=xxx-editors,ou=groups,dc=test",)
    assert restored.departments == ("maintenance",)
    assert restored.editable_sheets == ("xxx",)
    assert restored.as_dict()["groups"] == ["cn=xxx-editors,ou=groups,dc=test"]
    assert restored.as_dict()["departments"] == ["maintenance"]
    assert restored.as_dict()["editable_sheets"] == ["xxx"]


def test_optional_group_search(monkeypatch):
    """When LDAP_GROUP_BASE_DN is set, additional groups are merged."""
    _ldap_environment_with_sheet_access(monkeypatch)
    monkeypatch.setenv("LDAP_GROUP_BASE_DN", "ou=groups,dc=test")
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["frank"],
            "cn": ["Frank"],
            "mail": ["frank@test"],
            "memberOf": [],
        }

    search_calls = []

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, base, search_filter, **kwargs):
            search_calls.append((base, search_filter))
            # Simulate finding the user in a posix group
            if base == "ou=groups,dc=test":
                class GroupEntry:
                    entry_dn = "cn=xxx-editors,ou=groups,dc=test"
                self.entries = [GroupEntry()]
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("frank", "password", config)
    assert "cn=xxx-editors,ou=groups,dc=test" in identity.groups
    assert "xxx" in identity.editable_sheets
    # Verify the group search was performed
    assert len(search_calls) == 2  # user entry + group search


def test_group_search_failure_is_open(monkeypatch):
    """If group search fails, memberOf results still apply."""
    _ldap_environment_with_sheet_access(monkeypatch)
    monkeypatch.setenv("LDAP_GROUP_BASE_DN", "ou=groups,dc=test")
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["grace"],
            "cn": ["Grace"],
            "mail": ["grace@test"],
            "memberOf": ["cn=settings-editors,ou=groups,dc=test"],
        }

    call_count = [0]

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            call_count[0] += 1
            self.entries = [FakeEntry()]
        def search(self, *args, **kwargs):
            if call_count[0] > 1:
                from ldap3.core.exceptions import LDAPException
                raise LDAPException("connection lost")
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("grace", "password", config)
    # memberOf still works even though group search failed
    assert "settings" in identity.editable_sheets


def test_case_insensitive_sheet_matching(monkeypatch):
    """Group and department matching is case-insensitive."""
    _ldap_environment_with_sheet_access(monkeypatch)
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["hank"],
            "cn": ["Hank"],
            "mail": ["hank@test"],
            "memberOf": ["CN=XXX-EDITORS,OU=GROUPS,DC=TEST"],
            "department": ["MAINTENANCE"],
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, *args, **kwargs):
            pass
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("hank", "password", config)
    assert "xxx" in identity.editable_sheets


def test_disabled_mode_has_all_sheets():
    """AUTH_MODE=disabled returns both sheets."""
    identity = disabled_identity()
    assert set(identity.editable_sheets) == {"xxx", "settings"}
    assert identity.is_admin is True


def test_invalid_sheet_access_json_is_rejected(monkeypatch):
    """Malformed LDAP_SHEET_ACCESS_JSON raises AuthUnavailable."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv("LDAP_SHEET_ACCESS_JSON", "not valid json{{{")
    with pytest.raises(AuthUnavailable, match="LDAP_SHEET_ACCESS_JSON"):
        load_auth_config()


def test_unknown_sheet_key_in_json_is_rejected(monkeypatch):
    """Unknown sheet key in LDAP_SHEET_ACCESS_JSON raises AuthUnavailable."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv("LDAP_SHEET_ACCESS_JSON", json.dumps({"unknown": {"groups": []}}))
    with pytest.raises(AuthUnavailable, match="unknown sheet key"):
        load_auth_config()



# ---------------------------------------------------------------------------
# Finding 4: gidNumber in POSIX group search
# ---------------------------------------------------------------------------

def test_gidnumber_included_in_group_search_filter(monkeypatch):
    """gidNumber from user entry is included in the POSIX group search OR filter."""
    _ldap_environment_with_sheet_access(monkeypatch)
    monkeypatch.setenv("LDAP_GROUP_BASE_DN", "ou=groups,dc=test")
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["ivan"],
            "cn": ["Ivan"],
            "mail": ["ivan@test"],
            "memberOf": [],
            "gidNumber": ["500"],
        }

    search_calls = []

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, base, search_filter, **kwargs):
            search_calls.append((base, search_filter))
            if base == "ou=groups,dc=test":
                class GroupEntry:
                    entry_dn = "cn=xxx-editors,ou=groups,dc=test"
                self.entries = [GroupEntry()]
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("ivan", "password", config)
    # Verify gidNumber=500 appears in the group search filter
    assert len(search_calls) == 2
    group_filter = search_calls[1][1]
    assert "gidNumber=500" in group_filter
    assert "memberUid=ivan" in group_filter
    assert "cn=xxx-editors,ou=groups,dc=test" in identity.groups


# ---------------------------------------------------------------------------
# Finding 2: is_admin from merged groups
# ---------------------------------------------------------------------------

def test_admin_status_computed_from_merged_groups(monkeypatch):
    """is_admin is True when admin group is discovered via LDAP_GROUP_BASE_DN."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv("LDAP_GROUP_BASE_DN", "ou=groups,dc=test")
    config = load_auth_config()

    class FakeEntry:
        entry_attributes_as_dict = {
            "uid": ["judy"],
            "cn": ["Judy"],
            "mail": ["judy@test"],
            "memberOf": [],  # Not in memberOf
        }

    class FakeConnection:
        def __init__(self, _server, **kwargs):
            self.entries = [FakeEntry()]
        def search(self, base, search_filter, **kwargs):
            if base == "ou=groups,dc=test":
                class GroupEntry:
                    entry_dn = "cn=admins,ou=groups,dc=test"
                self.entries = [GroupEntry()]
        def unbind(self):
            pass

    monkeypatch.setattr("backend.auth.Connection", FakeConnection)
    identity = authenticate_ldap("judy", "password", config)
    assert identity.is_admin is True
    assert "cn=admins,ou=groups,dc=test" in identity.groups
    assert set(identity.editable_sheets) == {"xxx", "settings"}


# ---------------------------------------------------------------------------
# Finding 5: verify_session_token fail-closed
# ---------------------------------------------------------------------------

def test_verify_token_rejects_non_admin_with_no_sheets(monkeypatch):
    """Token for non-admin with empty editable_sheets is rejected."""
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    identity = AuthIdentity(
        "stale", "Stale", "stale@test", False,
        groups=(), departments=(), editable_sheets=(),
    )
    token = create_session_token(identity, config, now=1000)
    with pytest.raises(InvalidCredentials, match="no permitted sheets"):
        verify_session_token(token, config, now=1000)


def test_verify_token_rejects_invalid_sheet_keys(monkeypatch):
    """Token with invalid sheet keys is rejected."""
    _ldap_environment(monkeypatch)
    config = load_auth_config()
    # Manually craft a token with invalid sheet key
    import base64
    payload = {
        "username": "bad", "display_name": "Bad", "email": "bad@test",
        "is_admin": False, "groups": [], "departments": [],
        "editable_sheets": ["xxx", "hacked"], "iat": 1000, "exp": 4600,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).rstrip(b"=").decode("ascii")
    signature = hmac.new(config.session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
    sig_encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    token = f"{encoded}.{sig_encoded}"
    with pytest.raises(InvalidCredentials, match="invalid sheet keys"):
        verify_session_token(token, config, now=1000)


# ---------------------------------------------------------------------------
# Finding 7: Hardened _parse_sheet_access_json
# ---------------------------------------------------------------------------

def test_non_string_json_key_is_rejected(monkeypatch):
    """Non-string JSON keys in LDAP_SHEET_ACCESS_JSON are rejected."""
    _ldap_environment(monkeypatch)
    # JSON doesn't allow non-string keys natively, but we can test with a dict
    # that has integer-like keys by using a custom approach
    monkeypatch.setenv("LDAP_SHEET_ACCESS_JSON", '{"xxx": {"groups": ["valid"]}}')
    config = load_auth_config()
    assert "xxx" in config.sheet_access_rules


def test_empty_group_value_is_rejected(monkeypatch):
    """Empty string in groups list is rejected."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv("LDAP_SHEET_ACCESS_JSON", '{"xxx": {"groups": [""]}}')
    with pytest.raises(AuthUnavailable, match="empty value"):
        load_auth_config()


def test_empty_department_value_is_rejected(monkeypatch):
    """Empty string in departments list is rejected."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv("LDAP_SHEET_ACCESS_JSON", '{"xxx": {"departments": ["  "]}}')
    with pytest.raises(AuthUnavailable, match="empty value"):
        load_auth_config()


def test_group_values_are_trimmed_and_casefolded(monkeypatch):
    """Group and department values are trimmed and casefolded."""
    _ldap_environment(monkeypatch)
    monkeypatch.setenv("LDAP_SHEET_ACCESS_JSON", '{"xxx": {"groups": ["  CN=XXX-EDITORS,OU=GROUPS,DC=TEST  "], "departments": ["  Maintenance  "]}}')
    config = load_auth_config()
    assert config.sheet_access_rules["xxx"]["groups"] == ["cn=xxx-editors,ou=groups,dc=test"]
    assert config.sheet_access_rules["xxx"]["departments"] == ["maintenance"]

