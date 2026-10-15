"""Mock users service (contains PII, to show redaction)."""

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="users")


class User(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    tier: str = Field(description="Loyalty tier: basic | gold")


USERS = {
    1: User(id=1, name="Ada Lovelace", email="ada@example.com", phone="415-555-0101", tier="gold"),
    2: User(id=2, name="Alan Turing", email="alan@example.com", phone="(212) 555-0199", tier="basic"),
}


def audit_caller(x_agentifyapi_caller: str | None = Header(default=None)) -> str | None:
    return x_agentifyapi_caller


@app.get("/users/{user_id}", response_model=User, tags=["users"])
def get_user(user_id: int, caller: str | None = Depends(audit_caller)) -> User:
    """Fetch one customer profile by numeric id, including contact details and loyalty tier."""
    if user_id not in USERS:
        raise HTTPException(404, "user not found")
    return USERS[user_id]


@app.get("/users", response_model=list[User], tags=["users"])
def search_users(tier: str | None = None) -> list[User]:
    """List customers, optionally filtered by loyalty tier."""
    return [u for u in USERS.values() if tier is None or u.tier == tier]
