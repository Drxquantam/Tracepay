"""Request/response shapes (Pydantic). Money goes over the wire as integer paise;
the frontend formats it as ₹ with Indian digit grouping."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vpa: str
    display_name: str
    kind: str
    bank_code: str
    bank_name: str
    balance_paise: int
    is_frozen: bool


class MeOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    senior_mode: bool
    accounts: list[AccountOut]


class PaymentCreate(BaseModel):
    payee_vpa: str = Field(min_length=3, max_length=100)
    amount_paise: int = Field(gt=0, description="Amount in paise (₹1 = 100)")
    note: str | None = Field(default=None, max_length=200)


class PaymentOut(BaseModel):
    id: uuid.UUID
    reference: str
    payer_vpa: str
    payee_vpa: str
    payee_name: str
    amount_paise: int
    state: str
    failure_reason: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class PaymentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_state: str | None
    to_state: str
    reason: str | None
    occurred_at: datetime


class PaymentDetailOut(PaymentOut):
    events: list[PaymentEventOut]


class ClockOut(BaseModel):
    now: datetime
    offset_seconds: int


class ClockAdvance(BaseModel):
    # Up to a year per jump: plenty for any deadline in the demo.
    seconds: int = Field(gt=0, le=365 * 24 * 3600)
