"""Durable, at-least-once webhook delivery. Run independently of the API process."""
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

import requests
from prometheus_client import Counter, Gauge, start_http_server
from sqlalchemy import func, select

from .config import get_settings
from .db import SessionLocal
from .models import Tenant, WebhookDelivery, utcnow
from .saas import derived_secret, validate_destination

ATTEMPTS = Counter("biometric_webhook_attempts_total", "Webhook attempts", ["outcome"])
BACKLOG = Gauge("biometric_webhook_backlog", "Webhook deliveries", ["status"])
LAST_CYCLE = Gauge("biometric_webhook_last_cycle_unixtime", "Last successful outbox polling cycle")
LOGGER = logging.getLogger(__name__)


def signature(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def deliver_one(db, post=requests.post) -> bool:
    row = db.scalar(select(WebhookDelivery).where(WebhookDelivery.status == "pending",
                                                  WebhookDelivery.next_attempt_at <= utcnow())
                     .order_by(WebhookDelivery.created_at).with_for_update(skip_locked=True).limit(1))
    if row is None:
        return False
    tenant = db.get(Tenant, row.tenant_id)
    row.attempts += 1
    body = json.dumps({"id": row.id, **row.payload}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    try:
        if not tenant.active or not tenant.webhook_url:
            raise ValueError("Tenant webhook disabled")
        destination = validate_destination(tenant.webhook_url)
        response = post(destination, data=body, timeout=10, allow_redirects=False, headers={
            "Content-Type": "application/json", "X-Webhook-Id": row.id, "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": signature(derived_secret("webhook", tenant.id), timestamp, body),
        })
        row.last_status_code = response.status_code
        successful = 200 <= response.status_code < 300
    except Exception:
        successful = False
        row.last_status_code = None
        LOGGER.warning("Webhook delivery failed id=%s attempt=%d", row.id, row.attempts)
    row.status = "delivered" if successful else "failed" if row.attempts >= get_settings().webhook_max_attempts else "pending"
    row.next_attempt_at = utcnow() + timedelta(seconds=min(2 ** row.attempts, 60))
    ATTEMPTS.labels(outcome="success" if successful else "failure").inc()
    db.commit()
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    start_http_server(8002)
    while True:
        try:
            with SessionLocal() as db:
                for _ in range(20):
                    if not deliver_one(db):
                        break
                for status in ("pending", "delivered", "failed"):
                    BACKLOG.labels(status=status).set(db.scalar(select(func.count()).select_from(WebhookDelivery)
                                                                .where(WebhookDelivery.status == status)))
            LAST_CYCLE.set_to_current_time()
        except Exception:
            LOGGER.exception("Outbox poll failed")
        time.sleep(2)


if __name__ == "__main__":
    main()
