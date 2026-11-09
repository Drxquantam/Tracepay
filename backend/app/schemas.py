"""Request/response shapes (Pydantic). Money goes over the wire as integer paise;
the frontend formats it as ₹ with Indian digit grouping."""

from pydantic import BaseModel, ConfigDict


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
