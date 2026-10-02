import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AuditLog, Person, Tenant, TenantKey


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    role: str
    key_id: str = "platform"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def authenticate(x_api_key: str | None = Header(default=None), db: Session = Depends(get_db),
                 x_tenant_id: str | None = Header(default=None)) -> Principal:
    if not x_api_key:
        raise HTTPException(401, "API key required")
    if hmac.compare_digest(x_api_key, get_settings().api_key):
        if x_tenant_id:
            tenant = db.get(Tenant, x_tenant_id)
            if tenant is None or not tenant.active:
                raise HTTPException(404, "Active company not found")
        return Principal(x_tenant_id or "demo", "platform")
    key = db.scalar(select(TenantKey).join(Tenant).where(
        TenantKey.digest == digest(x_api_key), TenantKey.active.is_(True), Tenant.active.is_(True),
    ))
    if key is None:
        raise HTTPException(401, "Invalid or revoked API key")
    if x_tenant_id and x_tenant_id != key.tenant_id:
        raise HTTPException(403, "Cannot access another company")
    return Principal(key.tenant_id, key.role, key.id)


def platform(principal: Principal = Depends(authenticate)) -> Principal:
    if principal.role != "platform":
        raise HTTPException(403, "Platform administrator required")
    return principal


def operator(principal: Principal = Depends(authenticate)) -> Principal:
    if principal.role not in {"platform", "operator"}:
        raise HTTPException(403, "Operator role required")
    return principal


def get_person(db: Session, person_id: str, principal: Principal) -> Person:
    person = db.scalar(select(Person).where(Person.id == person_id, Person.tenant_id == principal.tenant_id))
    if person is None or not person.active:
        raise HTTPException(404, "Person not found")
    return person


def audit(db: Session, principal: Principal, action: str, target: str, details: str | None = None) -> None:
    db.add(AuditLog(tenant_id=principal.tenant_id, actor=principal.key_id, action=action, target=target, details=details))
