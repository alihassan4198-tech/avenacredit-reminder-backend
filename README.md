# AvenaCredit Reminder Backend (API + admin backend)

FastAPI backend for the credit card reminder system. It receives reminder form submissions, stores subscribers and cards, schedules J20/J5 reminders, sends them by email (AWS SES), and exposes the admin APIs.

The form, admin page and unsubscribe page are served by `avenacredit-reminder-form` on Vercel. That app forwards `/v1/*` calls here.

## Production layout (AWS + Supabase)

| Piece | Where |
|---|---|
| API (`lambda_handler.handler`) | AWS Lambda (container image from `Dockerfile.lambda`) behind API Gateway |
| Reminder sending (`reminder_job.handler`) | Same image, second Lambda, triggered by an EventBridge schedule (every 5 min) |
| Database | Supabase Postgres (pooler connection string) |
| Email | AWS SES; bounces and complaints come back via SNS to `/v1/webhooks/ses-events?token=...` |

## Interim hosting on Vercel (until AWS is available)

The same code runs on Vercel's Python runtime. Vercel detects the FastAPI app in `app/main.py` and routes every path to it (no rewrites needed; `vercel.json` only defines the cron).

- Database: Supabase **transaction pooler** URL (port 6543) in `DATABASE_URL`
- Reminder sending: Vercel Cron calls `/v1/cron/run-due` daily at 18:00 UTC (Hobby plan limit: once a day; 18:00 covers 10:00 local in every Canadian timezone), authenticated with `CRON_SECRET`
- Email: `EMAIL_PROVIDER=mock` until SES (or Mailgun) is configured
- Env vars: everything from `.env.example` except the `POSTGRES_*` and `SES_EVENTS_*` lines, plus `CRON_SECRET`

## Key endpoints

- `POST /v1/webhooks/subscriber-onboarded`: reminder form submissions (HMAC-signed with `WEBHOOK_SECRET`)
- `POST /v1/webhooks/ses-events?token=<SES_EVENTS_TOKEN>`: SNS notifications for SES bounces and complaints. A permanent bounce or complaint turns off email for that subscriber.
- `/v1/admin/*`: admin APIs (JWT login)
- `/v1/preferences/*`: unsubscribe / preferences
- `/health`, `/readyz`: health checks

## Run locally

Needs Docker Desktop.

```bash
cp .env.example .env    # set APP_ENV=development, EMAIL_PROVIDER=mock, DATABASE_URL=<Supabase session pooler URL>
docker compose -f docker-compose.local.yml -p avenacredit-reminder-backend up -d --build
```

- API: http://localhost:18020 (docs: http://localhost:18020/docs)
- Run the frontend (`avenacredit-reminder-form`) with `BACKEND_API_URL=http://localhost:18020` to use the admin at http://localhost:4321/admin

Stop: `docker compose -f docker-compose.local.yml -p avenacredit-reminder-backend down`

## Database migrations

```bash
DATABASE_URL="<supabase pooler url>" alembic upgrade head
```

Admin logins are stored in the `admin_users` table (Argon2 password hashes). `ADMIN_EMAIL` / `ADMIN_PASSWORD` are only an optional one-time bootstrap for an empty table; leave them unset afterwards. Add admins with:

```bash
python -m app.scripts.create_admin_user --email "client@example.com" --name "Client" --role admin
```

## Test the Lambda image locally

```bash
docker build -f Dockerfile.lambda -t avenacredit-reminder-lambda .
docker run --rm -p 9010:8080 --env-file .env avenacredit-reminder-lambda                        # API
docker run --rm -p 9010:8080 --env-file .env avenacredit-reminder-lambda reminder_job.handler   # reminder job
curl -X POST http://localhost:9010/2015-03-31/functions/function/invocations -d '{}'
```
