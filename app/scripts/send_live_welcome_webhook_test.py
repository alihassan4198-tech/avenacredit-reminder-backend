from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import httpx

from app.config import settings


ALLOWED_REAL_TEST_RECIPIENT = "info+avenacredit@nanukweb.ca"


def assert_allowed_real_test_recipient(*, to_email: str) -> None:
    provider = (settings.email_provider or "mock").lower()
    if provider in {"mailgun", "ses"} and to_email != ALLOWED_REAL_TEST_RECIPIENT:
        raise RuntimeError(
            "Real email tests may only be sent to info+avenacredit@nanukweb.ca"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Trigger live welcome email webhook test safely")
    parser.add_argument(
        "--to-email",
        default=ALLOWED_REAL_TEST_RECIPIENT,
        help="Target recipient for live welcome email test",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL where /v1/webhooks/subscriber-onboarded is reachable",
    )
    args = parser.parse_args()

    to_email = args.to_email.strip().lower()
    assert_allowed_real_test_recipient(to_email=to_email)

    payload = {
        "event": "subscriber_onboarded",
        "occurredAt": datetime.now(timezone.utc).isoformat(),
        "source": "live_mailgun_welcome_test",
        "subscriber": {
            "firstName": "Test",
            "lastName": "AvenaCredit",
            "email": to_email,
            "phone": "+15145559999",
            "language": "fr",
            "timezone": "America/Toronto",
            "consentEmail": True,
            "consentSms": False,
        },
        "cards": [
            {
                "selectionType": "other",
                "customCardName": "Triangle Canadian Tire",
                "cardType": "mastercard",
                "creditLimit": 8000,
                "statementDay": 27,
            },
            {
                "selectionType": "other",
                "customCardName": "RBC Visa",
                "cardType": "visa",
                "creditLimit": 5000,
                "statementDay": 14,
            },
        ],
    }

    idempotency_key = f"live-welcome-{int(time.time())}"
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(settings.webhook_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    response = httpx.post(
        f"{args.base_url.rstrip('/')}/v1/webhooks/subscriber-onboarded",
        content=raw,
        headers={
            "X-Signature": signature,
            "X-Timestamp": str(int(time.time())),
            "X-Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )

    print(f"IDEMPOTENCY_KEY={idempotency_key}")
    print(f"WEBHOOK_STATUS={response.status_code}")
    print(f"WEBHOOK_BODY={response.text}")


if __name__ == "__main__":
    main()