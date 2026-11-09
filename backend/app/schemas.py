"""Request/response shapes (Pydantic). Money goes over the wire as integer paise;
the frontend formats it as ₹ with Indian digit grouping."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.faults import Fault


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
    # SIMULATION: ask the mock switch to misbehave for this one payment (demo / chaos testing).
    simulate_fault: Fault | None = None


class PaymentOut(BaseModel):
    id: uuid.UUID
    reference: str
    payer_vpa: str
    payer_name: str
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

    kind: str
    from_state: str | None
    to_state: str
    reason: str | None
    occurred_at: datetime


class PaymentDetailOut(PaymentOut):
    events: list[PaymentEventOut]


class ClockOut(BaseModel):
    now: datetime
    offset_seconds: int
    disputes_opened: int = 0  # set after a time-travel jump that breached deadlines


class ClockAdvance(BaseModel):
    # Up to a year per jump: plenty for any deadline in the demo.
    seconds: int = Field(gt=0, le=365 * 24 * 3600)


class DisputeStepOut(BaseModel):
    step: str
    title: str
    description: str
    completed_at: datetime | None
    available_at: datetime | None


class DisputeOut(BaseModel):
    id: int
    status: Literal["open", "resolved"]
    payment_id: uuid.UUID
    payment_reference: str
    amount_paise: int
    payee_name: str
    rule_code: str
    tat_days: int
    compensation_paise_per_day: int
    deadline_at: datetime
    opened_at: datetime
    resolved_at: datetime | None
    days_late: int
    compensation_owed_paise: int
    owed_by_bank: str
    headline: str
    who_owes: str
    steps: list[DisputeStepOut]


class StageOut(BaseModel):
    key: str
    label: str


class RuleOut(BaseModel):
    code: str
    title: str
    tat_days: int
    compensation_paise_per_day: int


class TrackerOut(BaseModel):
    payment: PaymentDetailOut
    stages: list[StageOut]
    position: Literal["payer_bank", "switch", "payee_bank", "returning"]
    health: Literal["ok", "delayed", "late", "failed"]
    headline: str
    detail: str
    rule: RuleOut | None
    deadline_at: datetime | None
    seconds_to_deadline: float | None
    breached: bool
    days_late: int
    dispute: DisputeOut | None
    sim_now: datetime


class BankChaosOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    profile: str
    is_down: bool
    fault: str | None
    response_delay_seconds: float


class BankChaosUpdate(BaseModel):
    """Only the fields you send are changed. Send "fault": null to clear a fault."""

    is_down: bool | None = None
    fault: Fault | None = None
    response_delay_seconds: float | None = Field(default=None, ge=0, le=60)


class ResolveRequest(BaseModel):
    outcome: Literal["credit", "reverse"]


class PayeeOut(BaseModel):
    """Someone you can pay: a contact or a shop (simulated UPI directory)."""

    vpa: str
    name: str
    kind: str
    bank_name: str
