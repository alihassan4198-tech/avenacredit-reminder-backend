# Webhook V2 Examples

Endpoint:

- `POST /v1/webhooks/subscriber-onboarded`

Required headers:

- `X-Signature`: lowercase hex HMAC-SHA256 over raw JSON body using `WEBHOOK_SECRET`
- `X-Timestamp`: unix epoch seconds
- `X-Idempotency-Key`: caller-generated unique key
- `Content-Type: application/json`

Validation notes:

- Clock skew window is controlled by `ALLOWED_CLOCK_SKEW_SECONDS`.
- `cards` must contain at least one card.
- `statementDay` must be between 1 and 31.
- `subscriber.timezone` must be a valid IANA timezone.

## 1. Popular Card Example

```json
{
  "event": "subscriber_onboarded",
  "occurredAt": "2026-05-10T14:30:00Z",
  "source": "avena_form_v2",
  "subscriber": {
    "firstName": "Alex",
    "lastName": "Martin",
    "email": "alex.martin@example.com",
    "phone": "+15145550001",
    "language": "fr",
    "timezone": "America/Toronto",
    "consentEmail": true,
    "consentSms": false
  },
  "cards": [
    {
      "selectionType": "popular",
      "popularCardKey": "rbc_visa_platinum",
      "cardType": "visa",
      "creditLimit": 2500,
      "statementDay": 14
    }
  ]
}
```



## 2. Other Card Example

```json
{
  "event": "subscriber_onboarded",
  "occurredAt": "2026-05-10T14:35:00Z",
  "source": "avena_form_v2",
  "subscriber": {
    "firstName": "Sam",
    "lastName": "Lee",
    "email": "sam.lee@example.com",
    "phone": "+15145550002",
    "language": "en",
    "timezone": "America/Toronto",
    "consentEmail": true,
    "consentSms": false
  },
  "cards": [
    {
      "selectionType": "other",
      "customCardName": "My Credit Union Card",
      "cardType": "mastercard",
      "creditLimit": 1800,
      "statementDay": 8
    }
  ]
}
```



## 3. Multi-Card Example

```json
{
  "event": "subscriber_onboarded",
  "occurredAt": "2026-05-10T14:40:00Z",
  "source": "avena_form_v2",
  "subscriber": {
    "firstName": "Taylor",
    "lastName": "Nguyen",
    "email": "taylor.nguyen@example.com",
    "phone": "+15145550003",
    "language": "en",
    "timezone": "America/Toronto",
    "consentEmail": true,
    "consentSms": false
  },
  "cards": [
    {
      "selectionType": "popular",
      "popularCardKey": "td_rewards_visa",
      "cardType": "visa",
      "creditLimit": 3000,
      "statementDay": 12
    },
    {
      "selectionType": "other",
      "customCardName": "Secondary Other Card",
      "cardType": "mastercard",
      "creditLimit": 2100,
      "statementDay": 21
    }
  ]
}
```



## 4. Curl Example (Signed Request)

```bash
WEBHOOK_URL="https://your-api.example.com/v1/webhooks/subscriber-onboarded"
WEBHOOK_SECRET="replace-webhook-secret"
IDEMPOTENCY_KEY="onboard-$(date +%s)-001"
TIMESTAMP="$(date +%s)"

read -r -d '' BODY <<'JSON'
{
  "event": "subscriber_onboarded",
  "occurredAt": "2026-05-10T14:30:00Z",
  "source": "avena_form_v2",
  "subscriber": {
    "firstName": "Alex",
    "lastName": "Martin",
    "email": "alex.martin@example.com",
    "phone": "+15145550001",
    "language": "fr",
    "timezone": "America/Toronto",
    "consentEmail": true,
    "consentSms": false
  },
  "cards": [
    {
      "selectionType": "popular",
      "popularCardKey": "rbc_visa_platinum",
      "cardType": "visa",
      "creditLimit": 2500,
      "statementDay": 14
    }
  ]
}
JSON

SIGNATURE="$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $2}')"

curl -sS -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -H "X-Timestamp: $TIMESTAMP" \
  -H "X-Idempotency-Key: $IDEMPOTENCY_KEY" \
  --data "$BODY"
```

Expected success response:

```json
{
  "ok": true,
  "duplicate": false,
  "idempotent": false
}
```

If the same `X-Idempotency-Key` is reused, expected response:

```json
{
  "ok": true,
  "duplicate": true,
  "idempotent": true
}
```

