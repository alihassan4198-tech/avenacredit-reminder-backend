from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Avena Credit Reminder API"
    app_env: str = "development"

    database_url: str = "postgresql+psycopg2://app:app@postgres:5432/credit_reminder"
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    preferences_token_secret: str = "change-preferences-secret"
    preferences_token_expire_days: int = 365

    webhook_secret: str = "replace-webhook-secret"
    allowed_clock_skew_seconds: int = 300

    reminder_send_hour_local: int = 10
    scheduler_horizon_months: int = 3
    reminder_max_attempts: int = 3
    reminder_processing_timeout_minutes: int = 30
    worker_poll_seconds: int = 20

    email_provider: str = "mock"
    email_from: str | None = None
    sms_feature_enabled: bool = False

    mailgun_api_base: str = "https://api.mailgun.net/v3"
    mailgun_api_key: str | None = None
    mailgun_domain: str | None = None
    mailgun_from_email: str | None = None

    ses_region: str = "ca-central-1"
    ses_from_email: str = "no-reply@example.com"
    ses_configuration_set: str | None = None

    # Optional one-time bootstrap: creates the first owner only when admin_users is empty.
    # Logins always use the admin_users table; leave these unset once an admin exists.
    admin_bootstrap_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADMIN_EMAIL", "ADMIN_BOOTSTRAP_EMAIL"),
    )
    admin_bootstrap_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADMIN_PASSWORD", "ADMIN_BOOTSTRAP_PASSWORD"),
    )
    # Vercel Cron sends Authorization: Bearer <CRON_SECRET> to /v1/cron/run-due.
    cron_secret: str | None = None

    # SES bounce/complaint notifications arrive from SNS at /v1/webhooks/ses-events?token=<SES_EVENTS_TOKEN>.
    ses_events_token: str | None = None
    ses_events_topic_arn: str | None = None

    default_timezone: str = "America/Toronto"
    app_base_url: str = "http://localhost:4321"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
