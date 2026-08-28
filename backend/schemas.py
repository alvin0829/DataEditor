"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class _StripNonEmptyStrings(BaseModel):
    @field_validator("request_number", "department", "status", mode="before", check_fields=False)
    @classmethod
    def strip_non_empty_strings(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RequestCreate(_StripNonEmptyStrings):
    request_number: str = Field(..., min_length=1, max_length=64)
    department: str = Field(..., min_length=1, max_length=128)
    status: str = Field(default="open", min_length=1, max_length=64)
    data: dict[str, Any] | None = None


class RequestUpdate(_StripNonEmptyStrings):
    request_number: str | None = Field(default=None, min_length=1, max_length=64)
    department: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = Field(default=None, min_length=1, max_length=64)
    data: dict[str, Any] | None = None


class RequestResponse(BaseModel):
    id: UUID
    request_number: str
    department: str
    status: str
    data: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str


class ListResponse(BaseModel):
    items: list[RequestResponse]
    total: int
    limit: int
    offset: int

# ---------------------------------------------------------------------------
# UserSetting schemas
# ---------------------------------------------------------------------------

class UserSettingCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=254)
    display_name: str = Field(..., min_length=1, max_length=128)
    role: Literal["user", "admin", "editor", "viewer"] = "user"
    theme: Literal["light", "dark", "auto"] = "light"
    density: Literal["default", "compact", "comfortable"] = "default"
    sidebar: Literal["visible", "hidden"] = "visible"
    notifications: Literal["on", "off"] = "on"
    active: bool = True

    @field_validator(
        "email", "display_name", "role", "theme", "density", "sidebar", "notifications",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("must not be blank")
        return v


class UserSettingUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=254)
    display_name: str | None = Field(default=None, max_length=128)
    role: Literal["user", "admin", "editor", "viewer"] | None = None
    theme: Literal["light", "dark", "auto"] | None = None
    density: Literal["default", "compact", "comfortable"] | None = None
    sidebar: Literal["visible", "hidden"] | None = None
    notifications: Literal["on", "off"] | None = None
    active: bool | None = None

    @field_validator(
        "email", "display_name", "role", "theme", "density", "sidebar", "notifications",
        mode="before",
    )
    @classmethod
    def strip_whitespace(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("must not be blank")
        return v


class UserSettingResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    theme: str
    density: str
    sidebar: str
    notifications: str
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSettingListResponse(BaseModel):
    items: list[UserSettingResponse]
    total: int


# These are the canonical keys stored in ContractService.fields. Contract No.
# is stored separately so multiple service rows can share a contract. The
# second Venue heading is disambiguated as Venue RBQ in stored data.
CONTRACT_SERVICE_HEADERS = (
    "Schedule Type", "Status", "Quotation Ref. No.", "Quotation Date",
    "Quotation Amount", "EMSD Group", "Department", "Venue", "Description",
    "Remark", "P.O. no.", "P.O. Date", "P.O. Amount", "Invoice No.",
    "Invoice Date", "Invoice Amount", "EMSD Assessed Amount", "Payment",
    "Payment Amount", "RBQ No.", "Venue RBQ", "維修樓層 / 房號 / 故障詳情",
    "開工三色紙 日期", "開工三色紙", "完工三色紙 日期", "完工三色紙", "最新情況",
    "過往紀錄", "EMSD Person In Charge", "Follow Up Personel", "Status Summary",
    "Follow Up Date", "PC Remarks", "EMSD 報價編號", "EMSD PO Status", "Phase 1",
    "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6", "Phase 7",
    "<- Lock", "PW",
)

RBQ_NO_HEADER = "RBQ No."
RBQ_FIELD = RBQ_NO_HEADER

CONTRACT_SERVICE_FIELD_ALIASES = {
    # Preserve requests from the older frontend while keeping the canonical
    # stored key aligned with the normalized second-Venue key.
    "Venue (RBQ)": "Venue RBQ",
}

# Raw headings must match XXX!A6:AR6 exactly for CSV uploads. The field map
# uses a normalized key for the second duplicated "Venue" heading.
CONTRACT_SERVICE_CSV_HEADERS = (
    "Schedule Type", "Status", "Quotation Ref. No.", "Quotation Date",
    "Quotation Amount", "EMSD Group", "Department", "Venue", "Description",
    "Remark", "P.O. no.", "P.O. Date", "P.O. Amount", "Invoice No.",
    "Invoice Date", "Invoice Amount", "EMSD Assessed Amount", "Payment",
    "Payment Amount", "RBQ No.", "Venue", "維修樓層 / 房號 / 故障詳情",
    "開工三色紙\n日期", "開工三色紙", "完工三色紙\n日期", "完工三色紙", "最新情況",
    "過往紀錄", "EMSD \nPerson In Charge", "Follow Up Personel", "Status\nSummary",
    "Follow Up\nDate", "PC\nRemarks", "EMSD\n報價編號", "EMSD PO\nStatus", "Phase 1",
    "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6", "Phase 7",
    "<- Lock", "PW",
)

CONTRACT_SERVICE_CSV_FIELD_KEYS = CONTRACT_SERVICE_HEADERS


class _ContractServiceFields(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fields", mode="before")
    @classmethod
    def normalize_field_aliases(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        for alias, canonical in CONTRACT_SERVICE_FIELD_ALIASES.items():
            if alias in normalized:
                normalized.setdefault(canonical, normalized[alias])
                del normalized[alias]
        return normalized

    @model_validator(mode="after")
    def ensure_known_headers(self):
        if self.fields is None:
            return self
        unknown = set(self.fields) - set(CONTRACT_SERVICE_HEADERS)
        if unknown:
            raise ValueError(f"Unsupported XXX columns: {', '.join(sorted(unknown))}")
        rbq_no = self.fields.get(RBQ_NO_HEADER)
        if not isinstance(rbq_no, str) or not rbq_no.strip():
            raise ValueError("RBQ No. is required")
        self.fields[RBQ_NO_HEADER] = rbq_no.strip()
        return self


class ContractServiceCreate(_ContractServiceFields):
    contract_no: str = Field(..., min_length=1, max_length=128)

    @field_validator("contract_no", mode="before")
    @classmethod
    def strip_contract_no(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class ContractServiceUpdate(_ContractServiceFields):
    contract_no: str | None = Field(default=None, min_length=1, max_length=128)
    fields: dict[str, Any] | None = None

    @field_validator("contract_no", mode="before")
    @classmethod
    def strip_contract_no(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value

class ContractServiceResponse(BaseModel):
    id: UUID
    contract_no: str
    rbq_no: str | None = None
    fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContractServiceListResponse(BaseModel):
    items: list[ContractServiceResponse]
    total: int
    limit: int
    offset: int


class ContractServiceImportResponse(BaseModel):
    imported: int
    items: list[ContractServiceResponse]


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=256)
    password: str = Field(..., min_length=1, max_length=1024)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value):
        return value.strip() if isinstance(value, str) else value


class IdentityResponse(BaseModel):
    username: str
    display_name: str
    email: str
    is_admin: bool
    groups: list[str] = []
    departments: list[str] = []
    editable_sheets: list[str] = []

