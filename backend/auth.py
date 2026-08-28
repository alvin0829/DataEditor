"""LDAP authentication and signed admin-session helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

try:
    from ldap3 import ALL, BASE, SUBTREE, Connection, Server
    from ldap3.core.exceptions import LDAPBindError, LDAPException
    from ldap3.utils.dn import escape_rdn
    from ldap3.utils.conv import escape_filter_chars
except ImportError:  # LDAP mode reports a configuration error; tests can use disabled mode.
    ALL = BASE = SUBTREE = Connection = Server = None
    LDAPBindError = LDAPException = Exception
    escape_rdn = None
    escape_filter_chars = None


COOKIE_NAME = "admin_session"

VALID_SHEET_KEYS = frozenset({"xxx", "settings"})


class AuthUnavailable(RuntimeError):
    pass


class InvalidCredentials(RuntimeError):
    pass


class AccessDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthIdentity:
    username: str
    display_name: str
    email: str
    is_admin: bool
    groups: tuple[str, ...] = ()
    departments: tuple[str, ...] = ()
    editable_sheets: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "is_admin": self.is_admin,
            "groups": list(self.groups),
            "departments": list(self.departments),
            "editable_sheets": list(self.editable_sheets),
        }


@dataclass(frozen=True)
class AuthConfig:
    mode: str
    server_uri: str
    user_base_dn: str
    user_dn_template: str
    admin_group_dn: str
    session_secret: str
    session_ttl_seconds: int
    session_cookie_secure: bool
    connect_timeout_seconds: int
    group_base_dn: str = ""
    sheet_access_rules: dict[str, dict[str, list[str]]] = field(default_factory=dict)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError as exc:
        raise AuthUnavailable(f"{name} must be an integer") from exc


def _parse_sheet_access_json(raw: str) -> dict[str, dict[str, list[str]]]:
    """Parse and validate LDAP_SHEET_ACCESS_JSON. Fail-closed on any error."""
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AuthUnavailable("LDAP_SHEET_ACCESS_JSON must be a JSON object")
    result: dict[str, dict[str, list[str]]] = {}
    for key, rules in parsed.items():
        if not isinstance(key, str):
            raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON key must be a string, got {type(key).__name__}")
        key_lower = key.strip().lower()
        if key_lower not in VALID_SHEET_KEYS:
            raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON contains unknown sheet key: {key!r}")
        if not isinstance(rules, dict):
            raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON rules for {key!r} must be an object")
        groups = rules.get("groups", [])
        departments = rules.get("departments", [])
        if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
            raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON groups for {key!r} must be a list of strings")
        if not isinstance(departments, list) or not all(isinstance(d, str) for d in departments):
            raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON departments for {key!r} must be a list of strings")
        clean_groups: list[str] = []
        for g in groups:
            g_stripped = g.strip().casefold()
            if not g_stripped:
                raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON groups for {key!r} contains empty value")
            clean_groups.append(g_stripped)
        clean_departments: list[str] = []
        for d in departments:
            d_stripped = d.strip().casefold()
            if not d_stripped:
                raise AuthUnavailable(f"LDAP_SHEET_ACCESS_JSON departments for {key!r} contains empty value")
            clean_departments.append(d_stripped)
        result[key_lower] = {
            "groups": clean_groups,
            "departments": clean_departments,
        }
    return result


def load_auth_config() -> AuthConfig:
    mode = os.environ.get("AUTH_MODE", "ldap").strip().lower()
    if mode not in {"ldap", "disabled"}:
        raise AuthUnavailable("AUTH_MODE must be ldap or disabled")
    return AuthConfig(
        mode=mode,
        server_uri=os.environ.get("LDAP_SERVER_URI", "").strip(),
        user_base_dn=os.environ.get("LDAP_USER_BASE_DN", "").strip(),
        user_dn_template=os.environ.get("LDAP_USER_DN_TEMPLATE", "").strip(),
        admin_group_dn=os.environ.get("LDAP_ADMIN_GROUP_DN", "").strip(),
        session_secret=os.environ.get("SESSION_SECRET", ""),
        session_ttl_seconds=_env_int("SESSION_TTL_SECONDS", 3600, 60),
        session_cookie_secure=_env_bool("SESSION_COOKIE_SECURE"),
        connect_timeout_seconds=_env_int("LDAP_CONNECT_TIMEOUT_SECONDS", 5, 1),
        group_base_dn=os.environ.get("LDAP_GROUP_BASE_DN", "").strip(),
        sheet_access_rules=_parse_sheet_access_json(os.environ.get("LDAP_SHEET_ACCESS_JSON", "")),
    )


def validate_ldap_config(config: AuthConfig) -> None:
    if config.mode == "disabled":
        return
    required = {
        "LDAP_SERVER_URI": config.server_uri,
        "LDAP_USER_BASE_DN": config.user_base_dn,
        "LDAP_ADMIN_GROUP_DN": config.admin_group_dn,
        "SESSION_SECRET": config.session_secret,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise AuthUnavailable("Missing authentication configuration: " + ", ".join(missing))
    if len(config.session_secret) < 32:
        raise AuthUnavailable("SESSION_SECRET must contain at least 32 characters")
    if config.user_dn_template and "{username}" not in config.user_dn_template:
        raise AuthUnavailable("LDAP_USER_DN_TEMPLATE must contain {username}")
    if Connection is None:
        raise AuthUnavailable("LDAP support is not installed")


def disabled_identity() -> AuthIdentity:
    return AuthIdentity(
        "local-admin", "Local Admin", "local-admin@localhost", True,
        groups=(), departments=(), editable_sheets=("xxx", "settings"),
    )


def _dn_within_base(dn: str, base_dn: str) -> bool:
    """Return True when *dn* is equal to or a child of *base_dn* (case-insensitive)."""
    dn_lower = dn.casefold().strip().rstrip(",")
    base_lower = base_dn.casefold().strip().rstrip(",")
    return dn_lower == base_lower or dn_lower.endswith("," + base_lower)


def _collect_strings(value: Any) -> list[str]:
    """Normalize an LDAP attribute value to a flat list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _search_additional_groups(
    connection: Connection,
    user_dn: str,
    uid: str,
    group_base_dn: str,
    gid_number: str = "",
) -> list[str]:
    """Search group_base_dn read-only for groups containing the user."""
    escaped_uid = escape_filter_chars(uid) if escape_filter_chars else uid
    escaped_dn = escape_filter_chars(user_dn) if escape_filter_chars else user_dn
    or_parts = [
        f"memberUid={escaped_uid}",
        f"member={escaped_dn}",
        f"uniqueMember={escaped_dn}",
    ]
    if gid_number:
        escaped_gid = escape_filter_chars(gid_number) if escape_filter_chars else gid_number
        or_parts.append(f"gidNumber={escaped_gid}")
    search_filter = "(|" + "".join(f"({p})" for p in or_parts) + ")"
    try:
        connection.search(
            group_base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=["cn", "gidNumber"],
        )
        return [str(entry.entry_dn) for entry in connection.entries]
    except LDAPException:
        # Fail open on group search — memberOf results still apply.
        return []


def _resolve_editable_sheets(
    is_admin: bool,
    groups: list[str],
    departments: list[str],
    sheet_access_rules: dict[str, dict[str, list[str]]],
) -> tuple[str, ...]:
    """Determine which sheets the user may edit."""
    if is_admin:
        return tuple(sorted(VALID_SHEET_KEYS))
    if not sheet_access_rules:
        return ()
    groups_lower = {g.lower() for g in groups}
    departments_lower = {d.lower() for d in departments}
    editable: list[str] = []
    for sheet_key, rules in sheet_access_rules.items():
        allowed_groups = set(rules.get("groups", []))
        allowed_departments = set(rules.get("departments", []))
        if allowed_groups & groups_lower or allowed_departments & departments_lower:
            editable.append(sheet_key)
    return tuple(sorted(editable))


def authenticate_ldap(username: str, password: str, config: AuthConfig) -> AuthIdentity:
    """Bind as the configured DN for a short username and read identity attributes."""
    validate_ldap_config(config)
    username = username.strip()
    if not username or not password:
        raise InvalidCredentials("Invalid username or password")

    if config.user_dn_template:
        dn = config.user_dn_template.replace("{username}", escape_rdn(username))
    else:
        dn = f"uid={escape_rdn(username)},{config.user_base_dn}"

    if not _dn_within_base(dn, config.user_base_dn):
        raise AuthUnavailable("Constructed DN must resolve within LDAP_USER_BASE_DN")

    parsed = urlparse(config.server_uri)
    if parsed.scheme not in {"ldap", "ldaps"} or not parsed.hostname:
        raise AuthUnavailable("LDAP_SERVER_URI must use ldap:// or ldaps://")
    server = Server(
        parsed.hostname,
        port=parsed.port,
        use_ssl=parsed.scheme == "ldaps",
        connect_timeout=config.connect_timeout_seconds,
        get_info=ALL,
    )

    connection = None
    try:
        connection = Connection(
            server,
            user=dn,
            password=password,
            auto_bind=True,
            raise_exceptions=True,
        )
        # Read only the authenticated user's own entry (BASE scope, read-only).
        connection.search(
            dn,
            "(objectClass=*)",
            search_scope=BASE,
            attributes=[
                "uid", "cn", "displayName", "mail", "memberOf",
                "departmentNumber", "department", "ou", "gidNumber",
            ],
        )
        if len(connection.entries) != 1:
            raise InvalidCredentials("Could not read user entry")
        entry = connection.entries[0]
        attributes = entry.entry_attributes_as_dict
    # A bind rejection means the supplied credentials are wrong. Connection,
    # TLS, timeout, and directory errors are service failures, not bad passwords.
    except LDAPBindError as exc:
        raise InvalidCredentials("Invalid username or password") from exc
    except LDAPException as exc:
        raise AuthUnavailable("LDAP directory is unavailable") from exc
    except InvalidCredentials:
        raise
    finally:
        if connection is not None:
            connection.unbind()

    def first(name: str, fallback: str = "") -> str:
        value = attributes.get(name, fallback)
        if isinstance(value, list):
            value = value[0] if value else fallback
        return str(value or fallback)

    # uid first, then displayName / cn fallbacks; extract from DN as last resort.
    resolved_username = first("uid") or first("displayName") or first("cn")
    if not resolved_username:
        first_rdn = dn.split(",")[0]
        resolved_username = first_rdn.split("=", 1)[1] if "=" in first_rdn else dn
    display_name = first("displayName") or first("cn") or resolved_username

    # Collect group memberships from memberOf.
    raw_memberof = _collect_strings(attributes.get("memberOf", []))
    groups = list(raw_memberof)

    # Extract gidNumber for POSIX primary group resolution.
    gid_number = first("gidNumber")

    # Optionally search LDAP_GROUP_BASE_DN for additional posix/group membership.
    if config.group_base_dn and connection is not None:
        # Re-open a read-only connection as the authenticated user for the group search.
        try:
            group_conn = Connection(
                server,
                user=dn,
                password=password,
                auto_bind=True,
                raise_exceptions=True,
            )
            try:
                additional = _search_additional_groups(
                    group_conn,
                    dn,
                    resolved_username,
                    config.group_base_dn,
                    gid_number,
                )
                seen = {g.lower() for g in groups}
                for grp in additional:
                    if grp.lower() not in seen:
                        groups.append(grp)
                        seen.add(grp.lower())
            finally:
                group_conn.unbind()
        except (LDAPBindError, LDAPException):
            pass  # Fail open — memberOf results still apply.

    # Collect departments from departmentNumber, department, ou.
    departments: list[str] = []
    for attr_name in ("departmentNumber", "department", "ou"):
        for val in _collect_strings(attributes.get(attr_name, [])):
            val_stripped = val.strip()
            if val_stripped and val_stripped.lower() not in {d.lower() for d in departments}:
                departments.append(val_stripped)

    # FIX 2: Compute is_admin from merged groups (including LDAP_GROUP_BASE_DN results).
    is_admin = config.admin_group_dn.casefold() in {
        str(group).casefold() for group in groups
    }

    editable_sheets = _resolve_editable_sheets(
        is_admin, groups, departments, config.sheet_access_rules,
    )

    # FIX 3: Non-admin users with no permitted sheets get AccessDenied (403), not InvalidCredentials (401).
    if not is_admin and not editable_sheets:
        raise AccessDenied("No permitted sheets for this user")

    return AuthIdentity(
        username=resolved_username,
        display_name=display_name,
        email=first("mail"),
        is_admin=is_admin,
        groups=tuple(groups),
        departments=tuple(departments),
        editable_sheets=editable_sheets,
    )


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token(identity: AuthIdentity, config: AuthConfig, now: int | None = None) -> str:
    validate_ldap_config(config)
    issued_at = int(time.time() if now is None else now)
    payload = {
        **identity.as_dict(),
        "iat": issued_at,
        "exp": issued_at + config.session_ttl_seconds,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(config.session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return encoded + "." + _b64encode(signature)


def verify_session_token(token: str, config: AuthConfig, now: int | None = None) -> AuthIdentity:
    validate_ldap_config(config)
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            config.session_secret.encode(), encoded.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64decode(supplied_signature)):
            raise ValueError
        payload = json.loads(_b64decode(encoded))
        current = int(time.time() if now is None else now)
        if int(payload["exp"]) < current or int(payload["iat"]) > current + 60:
            raise ValueError
        # FIX 5: Fail closed for non-admin with no editable sheets or invalid sheet keys.
        _sheets = tuple(payload.get("editable_sheets", []))
        _admin = payload["is_admin"] is True
        if not _admin and not _sheets:
            raise InvalidCredentials("Session has no permitted sheets")
        if any(s not in VALID_SHEET_KEYS for s in _sheets):
            raise InvalidCredentials("Session contains invalid sheet keys")
        return AuthIdentity(
            username=str(payload["username"]),
            display_name=str(payload["display_name"]),
            email=str(payload["email"]),
            is_admin=_admin,
            groups=tuple(payload.get("groups", [])),
            departments=tuple(payload.get("departments", [])),
            editable_sheets=_sheets,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidCredentials("Invalid or expired session") from exc
