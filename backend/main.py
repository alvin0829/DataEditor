"""FastAPI application entry point."""

import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db, init_db
from .auth import (
    COOKIE_NAME,
    AuthIdentity,
    AuthUnavailable,
    AccessDenied,
    InvalidCredentials,
    authenticate_ldap,
    create_session_token,
    disabled_identity,
    load_auth_config,
    validate_ldap_config,
    verify_session_token,
)
from .models import AuditLog, ContractService, ServiceRequest, UserSetting
from .schemas import (
    HealthResponse,
    IdentityResponse,
    ListResponse,
    LoginRequest,
    RequestCreate,
    RequestResponse,
    RequestUpdate,
    ContractServiceCreate,
    ContractServiceImportResponse,
    ContractServiceListResponse,
    ContractServiceResponse,
    ContractServiceUpdate,
    CONTRACT_SERVICE_HEADERS,
    CONTRACT_SERVICE_CSV_HEADERS,
    RBQ_NO_HEADER,
    UserSettingCreate,
    UserSettingListResponse,
    UserSettingResponse,
    UserSettingUpdate,
)


async def require_authenticated(request: Request) -> AuthIdentity:
    """Verify session and return identity. Any authenticated user passes."""
    try:
        config = load_auth_config()
        if config.mode == "disabled":
            return disabled_identity()
        validate_ldap_config(config)
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        return verify_session_token(token, config)
    except AuthUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

async def require_admin(identity: AuthIdentity = Depends(require_authenticated)) -> AuthIdentity:
    """Require global admin membership."""
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return identity


def require_sheet_access(sheet_key: str):
    """Return a dependency that requires the user to have access to *sheet_key*."""
    async def _check(identity: AuthIdentity = Depends(require_authenticated)) -> AuthIdentity:
        if not identity.is_admin and sheet_key not in identity.editable_sheets:
            raise HTTPException(status_code=403, detail=f"Access denied: {sheet_key} sheet")
        return identity
    return _check


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Service Request API",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(select(func.count()).select_from(ServiceRequest))
    return HealthResponse(status="ok")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit_snapshot(sr: ServiceRequest) -> dict:
    return {
        "request_number": sr.request_number,
        "department": sr.department,
        "status": sr.status,
        "data": sr.data,
    }


async def _write_audit(
    db: AsyncSession, action: str, sr: ServiceRequest, old: dict | None = None
):
    audit = AuditLog(
        action=action,
        request_id=sr.id,
        old_data=old,
        new_data=_audit_snapshot(sr),
    )
    db.add(audit)


def _extract_rbq_no(fields: dict) -> str:
    value = fields.get(RBQ_NO_HEADER)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail="RBQ No. must not be blank")
    return value.strip()


async def _ensure_rbq_available(
    db: AsyncSession, rbq_no: str, exclude_id: UUID | None = None
) -> None:
    rbq_json_value = ContractService.fields[RBQ_NO_HEADER].as_string()
    stmt = select(ContractService.id).where(
        or_(ContractService.rbq_no == rbq_no, rbq_json_value == rbq_no)
    )
    if exclude_id is not None:
        stmt = stmt.where(ContractService.id != exclude_id)
    if await db.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail="Duplicate RBQ No.")


def _validate_csv_upload_type(file: UploadFile) -> None:
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if not filename.endswith(".csv") and content_type not in {"text/csv", "application/csv"}:
        raise HTTPException(status_code=415, detail="Only CSV files are accepted")


async def _parse_contract_service_csv(file: UploadFile) -> list[dict[str, str]]:
    try:
        content = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV must be UTF-8 encoded") from exc

    try:
        rows = list(csv.reader(io.StringIO(content, newline=""), strict=True))
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail="Malformed CSV") from exc

    if not rows:
        raise HTTPException(status_code=422, detail="CSV is empty")

    expected_headers = list(CONTRACT_SERVICE_CSV_HEADERS)
    heading_index = next(
        (index for index, row in enumerate(rows) if row == expected_headers),
        None,
    )
    if heading_index is None:
        raise HTTPException(
            status_code=422,
            detail="CSV must contain the exact XXX row 6 headings in their original order",
        )

    parsed: list[dict[str, str]] = []
    expected_width = len(CONTRACT_SERVICE_HEADERS)
    rbq_column_index = CONTRACT_SERVICE_HEADERS.index(RBQ_NO_HEADER)
    for row_number, values in enumerate(rows[heading_index + 1:], start=heading_index + 2):
        if not values or all(not value.strip() for value in values):
            continue
        # Reports often carry titles, notes, or totals around the real table.
        # A row without an RBQ value is not a service record and is ignored.
        if len(values) <= rbq_column_index or not values[rbq_column_index].strip():
            continue
        if len(values) != expected_width:
            raise HTTPException(
                status_code=422,
                detail=f"CSV row {row_number} has {len(values)} columns; expected {expected_width}",
            )
        fields = dict(zip(CONTRACT_SERVICE_HEADERS, values, strict=True))
        _extract_rbq_no(fields)
        parsed.append(fields)

    if not parsed:
        raise HTTPException(status_code=422, detail="CSV contains no data rows")
    return parsed


# ---------------------------------------------------------------------------
# CRUD - Service Requests
# ---------------------------------------------------------------------------

@app.post("/api/requests", response_model=RequestResponse, status_code=201)
async def create_request(body: RequestCreate, db: AsyncSession = Depends(get_db)):
    sr = ServiceRequest(
        request_number=body.request_number.strip(),
        department=body.department.strip(),
        status=body.status.strip(),
        data=body.data or {},
    )
    db.add(sr)
    try:
        await db.flush()
        await _write_audit(db, "create", sr)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate request_number")
    await db.refresh(sr)
    return sr


@app.get("/api/requests", response_model=ListResponse)
async def list_requests(
    department: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ServiceRequest)
    count_stmt = select(func.count()).select_from(ServiceRequest)

    if department:
        stmt = stmt.where(ServiceRequest.department == department)
        count_stmt = count_stmt.where(ServiceRequest.department == department)
    if status:
        stmt = stmt.where(ServiceRequest.status == status)
        count_stmt = count_stmt.where(ServiceRequest.status == status)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(ServiceRequest.request_number.ilike(pattern))
        count_stmt = count_stmt.where(ServiceRequest.request_number.ilike(pattern))

    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(ServiceRequest.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    return ListResponse(
        items=[RequestResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/api/requests/{request_id}", response_model=RequestResponse)
async def get_request(request_id: str, db: AsyncSession = Depends(get_db)):
    from uuid import UUID

    try:
        uid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    sr = await db.get(ServiceRequest, uid)
    if sr is None:
        raise HTTPException(status_code=404, detail="Not found")
    return sr


@app.patch("/api/requests/{request_id}", response_model=RequestResponse)
async def update_request(
    request_id: str, body: RequestUpdate, db: AsyncSession = Depends(get_db)
):
    from uuid import UUID

    try:
        uid = UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    sr = await db.get(ServiceRequest, uid)
    if sr is None:
        raise HTTPException(status_code=404, detail="Not found")

    old = _audit_snapshot(sr)

    if body.request_number is not None:
        sr.request_number = body.request_number.strip()
    if body.department is not None:
        sr.department = body.department.strip()
    if body.status is not None:
        sr.status = body.status.strip()
    if body.data is not None:
        sr.data = body.data

    sr.updated_at = datetime.now(timezone.utc)
    try:
        await db.flush()
        await _write_audit(db, "update", sr, old=old)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate request_number")
    await db.refresh(sr)
    return sr


# ---------------------------------------------------------------------------
# CRUD - Contract services (XXX workbook sheet)
# ---------------------------------------------------------------------------

@app.post(
    "/api/contract-services",
    response_model=ContractServiceResponse,
    status_code=201,
)
async def create_contract_service(
    body: ContractServiceCreate,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("xxx")),
):
    rbq_no = _extract_rbq_no(body.fields)
    await _ensure_rbq_available(db, rbq_no)
    record = ContractService(
        contract_no=body.contract_no,
        rbq_no=rbq_no,
        fields=body.fields,
    )
    db.add(record)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate RBQ No.")
    await db.refresh(record)
    return record


@app.get("/api/contract-services", response_model=ContractServiceListResponse)
async def list_contract_services(
    contract_no: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("xxx")),
):
    stmt = select(ContractService)
    count_stmt = select(func.count()).select_from(ContractService)
    if contract_no:
        stmt = stmt.where(ContractService.contract_no == contract_no)
        count_stmt = count_stmt.where(ContractService.contract_no == contract_no)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(ContractService.contract_no.ilike(pattern))
        count_stmt = count_stmt.where(ContractService.contract_no.ilike(pattern))

    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (
        (await db.execute(stmt.order_by(ContractService.updated_at.desc()).offset(offset).limit(limit)))
        .scalars()
        .all()
    )
    return ContractServiceListResponse(
        items=[ContractServiceResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.patch("/api/contract-services/{record_id}", response_model=ContractServiceResponse)
async def update_contract_service(
    record_id: UUID,
    body: ContractServiceUpdate,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("xxx")),
):
    record = await db.get(ContractService, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    new_fields = body.fields if body.fields is not None else record.fields
    rbq_no = _extract_rbq_no(new_fields)
    await _ensure_rbq_available(db, rbq_no, exclude_id=record.id)
    if body.contract_no is not None:
        record.contract_no = body.contract_no
    if body.fields is not None:
        record.fields = new_fields
    record.rbq_no = rbq_no
    record.updated_at = datetime.now(timezone.utc)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate RBQ No.")
    await db.refresh(record)
    return record


@app.delete("/api/contract-services/{record_id}", status_code=204)
async def delete_contract_service(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("xxx")),
):
    record = await db.get(ContractService, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(record)
    await db.commit()


@app.post(
    "/api/contract-services/import",
    response_model=ContractServiceImportResponse,
    status_code=201,
)
async def import_contract_services_csv(
    contract_no: str = Form(..., min_length=1, max_length=128),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("xxx")),
):
    """Atomically import rows whose headings match the XXX workbook exactly."""
    normalized_contract_no = contract_no.strip()
    if not normalized_contract_no:
        raise HTTPException(status_code=422, detail="Contract No. is required")
    _validate_csv_upload_type(file)
    fields_rows = await _parse_contract_service_csv(file)

    records: list[ContractService] = []
    seen_rbq: set[str] = set()
    for fields in fields_rows:
        rbq_no = _extract_rbq_no(fields)
        if rbq_no in seen_rbq:
            raise HTTPException(status_code=409, detail=f"Duplicate RBQ No. in CSV: {rbq_no}")
        seen_rbq.add(rbq_no)
        await _ensure_rbq_available(db, rbq_no)
        records.append(ContractService(contract_no=normalized_contract_no, rbq_no=rbq_no, fields=fields))
    if not records:
        raise HTTPException(status_code=422, detail="CSV contains no data rows")
    db.add_all(records)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A CSV RBQ No. already exists")
    for record in records:
        await db.refresh(record)
    return ContractServiceImportResponse(
        imported=len(records),
        items=[ContractServiceResponse.model_validate(record) for record in records],
    )


# ---------------------------------------------------------------------------
# Static files and admin page
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return await admin_page(request)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    login_path = Path(__file__).parent / "static" / "login.html"
    return HTMLResponse(content=login_path.read_text(encoding="utf-8"))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    try:
        identity = await require_authenticated(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise
    index_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/admin-console", response_class=HTMLResponse)
async def admin_console_page(request: Request):
    identity = await require_authenticated(request)
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    console_path = Path(__file__).parent / "static" / "admin-console.html"
    return HTMLResponse(content=console_path.read_text(encoding="utf-8"))


@app.post("/api/auth/login", response_model=IdentityResponse)
async def login(body: LoginRequest, response: Response):
    try:
        config = load_auth_config()
        if config.mode == "disabled":
            identity = disabled_identity()
            return identity.as_dict()
        identity = await run_in_threadpool(
            authenticate_ldap, body.username, body.password, config
        )
        # authenticate_ldap raises InvalidCredentials for users with no permitted sheets.
        token = create_session_token(identity, config)
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=config.session_ttl_seconds,
            httponly=True,
            secure=config.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        return identity.as_dict()
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="Invalid username or password") from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
@app.post("/api/auth/logout", status_code=204)
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@app.get("/api/auth/me", response_model=IdentityResponse)
async def auth_me(identity: AuthIdentity = Depends(require_authenticated)):
    return identity.as_dict()


# ---------------------------------------------------------------------------
# User Settings CRUD
# ---------------------------------------------------------------------------

@app.post("/api/user-settings", response_model=UserSettingResponse, status_code=201)
async def create_user_setting(
    body: UserSettingCreate,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("settings")),
):
    us = UserSetting(
        email=body.email.strip().lower(),
        display_name=body.display_name.strip(),
        role=body.role.strip(),
        theme=body.theme.strip(),
        density=body.density.strip(),
        sidebar=body.sidebar.strip(),
        notifications=body.notifications.strip(),
        active=body.active,
    )
    db.add(us)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate email")
    await db.refresh(us)
    return us


@app.get("/api/user-settings", response_model=UserSettingListResponse)
async def list_user_settings(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("settings")),
):
    stmt = select(UserSetting)
    count_stmt = select(func.count()).select_from(UserSetting)

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(UserSetting.email.ilike(pattern) | UserSetting.display_name.ilike(pattern))
        count_stmt = count_stmt.where(UserSetting.email.ilike(pattern) | UserSetting.display_name.ilike(pattern))

    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = stmt.order_by(UserSetting.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()

    return UserSettingListResponse(
        items=[UserSettingResponse.model_validate(r) for r in rows],
        total=total,
    )


@app.get("/api/user-settings/{setting_id}", response_model=UserSettingResponse)
async def get_user_setting(
    setting_id: str,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("settings")),
):
    try:
        uid = UUID(setting_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    us = await db.get(UserSetting, uid)
    if us is None:
        raise HTTPException(status_code=404, detail="Not found")
    return us


@app.patch("/api/user-settings/{setting_id}", response_model=UserSettingResponse)
async def update_user_setting(
    setting_id: str,
    body: UserSettingUpdate,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("settings")),
):
    try:
        uid = UUID(setting_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    us = await db.get(UserSetting, uid)
    if us is None:
        raise HTTPException(status_code=404, detail="Not found")

    update_data = body.model_dump(exclude_unset=True)
    if "email" in update_data:
        us.email = update_data["email"].strip().lower()
    if "display_name" in update_data:
        us.display_name = update_data["display_name"].strip()
    if "role" in update_data:
        us.role = update_data["role"].strip()
    if "theme" in update_data:
        us.theme = update_data["theme"].strip()
    if "density" in update_data:
        us.density = update_data["density"].strip()
    if "sidebar" in update_data:
        us.sidebar = update_data["sidebar"].strip()
    if "notifications" in update_data:
        us.notifications = update_data["notifications"].strip()
    if "active" in update_data:
        us.active = update_data["active"]

    us.updated_at = datetime.now(timezone.utc)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate email")
    await db.refresh(us)
    return us


@app.delete("/api/user-settings/{setting_id}", status_code=204)
async def delete_user_setting(
    setting_id: str,
    db: AsyncSession = Depends(get_db),
    _identity: AuthIdentity = Depends(require_sheet_access("settings")),
):
    try:
        uid = UUID(setting_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid UUID")
    us = await db.get(UserSetting, uid)
    if us is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(us)
    await db.commit()



