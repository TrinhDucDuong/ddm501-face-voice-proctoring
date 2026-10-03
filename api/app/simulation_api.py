"""Platform authentication boundary; fixed proxy targets, no production mutations."""
from typing import Literal

import requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import platform

router = APIRouter(prefix='/v1/admin/simulation', dependencies=[Depends(platform)])


def proxy(method, path, body=None):
    from .main import settings
    if not settings.simulation_service_url or not settings.simulation_service_key:
        raise HTTPException(503, 'Isolated simulation service is not configured')
    try:
        response = requests.request(method, settings.simulation_service_url.rstrip('/') + path,
            headers={'X-Simulation-Key': settings.simulation_service_key}, json=body, timeout=240)
    except requests.RequestException as exc:
        raise HTTPException(503, 'Simulation service unavailable; production lifecycle unchanged') from exc
    if not response.ok:
        raise HTTPException(response.status_code, response.json().get('detail', 'Simulation failed'))
    return response.json()


class StartRequest(BaseModel):
    scenario: Literal['promotion', 'rollback']
    modality: Literal['face', 'voice'] = 'voice'
    seed: int = Field(default=501, ge=0, le=1000000)


@router.get('/state')
def state():
    return proxy('GET', '/state')


@router.post('/runs', status_code=202)
def start(body: StartRequest):
    return proxy('POST', '/runs', body.model_dump())


@router.post('/reset')
def reset():
    return proxy('POST', '/reset')


@router.get('/evidence/{run_id}')
def evidence(run_id: str):
    from uuid import UUID
    try:
        normalized = str(UUID(run_id))
    except ValueError as exc:
        raise HTTPException(422, 'Invalid simulation ID') from exc
    return proxy('GET', '/evidence/' + normalized)
