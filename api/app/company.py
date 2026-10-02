"""Simulated subscriptions and customer-owned API configuration."""
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Principal, audit, digest, get_person, operator, platform
from .config import get_settings
from .db import get_db
from .models import EnrollmentInvitation, Tenant, TenantKey, utcnow
from .saas import derived_secret, validate_destination

router = APIRouter()


@router.post('/v1/people/{person_id}/enrollment-invitations', status_code=201)
def invite_employee(person_id: str, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    person = get_person(db, person_id, principal)
    if not db.get(Tenant, principal.tenant_id).active:
        raise HTTPException(403, 'Company subscription is inactive')
    token = 'en_' + secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(hours=24)
    db.add(EnrollmentInvitation(tenant_id=principal.tenant_id, person_id=person.id,
                                digest=digest(token), expires_at=expires_at))
    audit(db, principal, 'enrollment.invited', person.id)
    db.commit()
    return {'token': token, 'expires_at': expires_at.isoformat(), 'person_id': person.id,
            'display_name': person.display_name}


class Registration(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class CompanyConfiguration(BaseModel):
    webhook_url: str | None = Field(default=None, max_length=2048)


class Subscription(BaseModel):
    active: bool


def issue_key(db, tenant_id, role):
    token = 'fv_' + secrets.token_urlsafe(32)
    key = TenantKey(tenant_id=tenant_id, role=role, digest=digest(token))
    db.add(key)
    db.flush()
    return key, token


@router.post('/v1/registrations', status_code=201)
def register(body: Registration, db: Session = Depends(get_db)):
    if not get_settings().enable_demo_registration:
        raise HTTPException(403, 'Self-registration disabled; contact platform administrator')
    if db.scalar(select(func.count()).select_from(Tenant)) >= 1000:
        raise HTTPException(429, 'Demo registration capacity reached')
    row = Tenant(name=body.name.strip())
    if len(row.name) < 2:
        raise HTTPException(422, 'Company name is too short')
    db.add(row)
    try:
        db.flush()
        _, token = issue_key(db, row.id, 'operator')
        audit(db, Principal(row.id, 'operator', 'registration'), 'company.registered', row.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Company name already registered') from exc
    return {'tenant_id': row.id, 'name': row.name, 'operator_key': token, 'subscription': 'demo_active'}


@router.get('/v1/company')
def configuration(db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    row = db.get(Tenant, principal.tenant_id)
    return {'id': row.id, 'name': row.name, 'active': row.active, 'subscription': 'demo_active',
            'webhook_url': row.webhook_url, 'webhook_secret': derived_secret('webhook', row.id)}


@router.patch('/v1/company')
def configure(body: CompanyConfiguration, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    row = db.get(Tenant, principal.tenant_id)
    row.webhook_url = validate_destination(body.webhook_url)
    audit(db, principal, 'webhook.configured', row.id)
    db.commit()
    return {'webhook_url': row.webhook_url}


@router.get('/v1/company/keys')
def keys(db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    return [{'id': key.id, 'role': key.role, 'active': key.active} for key in db.scalars(
        select(TenantKey).where(TenantKey.tenant_id == principal.tenant_id, TenantKey.role == 'integration'))]


@router.post('/v1/company/keys', status_code=201)
def create_integration_key(db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    key, token = issue_key(db, principal.tenant_id, 'integration')
    audit(db, principal, 'key.created', key.id)
    db.commit()
    return {'id': key.id, 'role': key.role, 'api_key': token}


@router.delete('/v1/company/keys/{key_id}')
def revoke(key_id: str, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    key = db.scalar(select(TenantKey).where(TenantKey.id == key_id, TenantKey.tenant_id == principal.tenant_id,
                                           TenantKey.role == 'integration'))
    if key is None:
        raise HTTPException(404, 'Integration key not found')
    key.active = False
    audit(db, principal, 'key.revoked', key.id)
    db.commit()
    return {'revoked': key.id}


@router.patch('/v1/admin/tenants/{tenant_id}/subscription')
def subscription(tenant_id: str, body: Subscription, db: Session = Depends(get_db), principal: Principal = Depends(platform)):
    row = db.get(Tenant, tenant_id)
    if row is None:
        raise HTTPException(404, 'Company not found')
    row.active = body.active
    audit(db, principal, 'subscription.changed', tenant_id, str(body.active))
    db.commit()
    return {'tenant_id': tenant_id, 'active': row.active, 'data_retained': True}
