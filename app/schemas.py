from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AdminUserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    role: str
    status: str
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class CardBase(BaseModel):
    card_name: str
    card_type: str
    credit_limit_cents: int = Field(gt=0)
    statement_day: int = Field(ge=1, le=31)


class CardCreate(CardBase):
    email_enabled: bool = True

    model_config = {"extra": "forbid"}


class CardUpdate(BaseModel):
    card_name: str | None = None
    card_type: str | None = None
    credit_limit_cents: int | None = Field(default=None, gt=0)
    statement_day: int | None = Field(default=None, ge=1, le=31)
    is_active: bool | None = None
    email_enabled: bool | None = None

    model_config = {"extra": "forbid"}


class CardStatusUpdate(BaseModel):
    is_active: bool


class CardOut(CardBase):
    id: str
    is_active: bool
    email_enabled: bool
    sms_enabled: bool

    model_config = {"from_attributes": True}


class SubscriberBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr
    phone: str | None = None
    signup_source: str | None = None
    language: str = Field(default="en", pattern="^(fr|en)$")
    timezone: str = "America/Toronto"
    email_enabled: bool = True


class SubscriberCreate(SubscriberBase):
    status: str = Field(default="active", pattern="^(active|paused|unsubscribed|inactive)$")

    model_config = {"extra": "forbid"}


class SubscriberUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    signup_source: str | None = None
    language: str | None = Field(default=None, pattern="^(fr|en)$")
    timezone: str | None = None
    status: str | None = Field(default=None, pattern="^(active|paused|unsubscribed|inactive)$")
    email_enabled: bool | None = None

    model_config = {"extra": "forbid"}


class SubscriberStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|paused|unsubscribed|inactive)$")


class SubscriberOut(BaseModel):
    id: str
    first_name: str | None
    last_name: str | None
    email: EmailStr
    phone: str | None
    signup_source: str | None
    language: str
    status: str
    email_enabled: bool
    sms_enabled: bool
    timezone: str
    cards: list[CardOut] = []

    model_config = {"from_attributes": True}


class ReminderRuleOut(BaseModel):
    id: str
    j20_enabled: bool
    j20_offset_days: int
    j5_enabled: bool
    j5_offset_days: int
    timezone: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReminderRulePatch(BaseModel):
    j20_enabled: bool | None = None
    j20_offset_days: int | None = Field(default=None, ge=1, le=60)
    j5_enabled: bool | None = None
    j5_offset_days: int | None = Field(default=None, ge=1, le=60)
    timezone: str | None = None


class WebhookCardV1(BaseModel):
    cardName: str
    cardType: str
    creditLimit: int = Field(gt=0)
    statementDay: int = Field(ge=1, le=31)


class WebhookSubscriber(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    email: EmailStr
    phone: str | None = None
    language: str = Field(default="en", pattern="^(fr|en)$")
    timezone: str = "America/Toronto"
    consentEmail: bool = True
    consentSms: bool = False


class WebhookPayloadV1(BaseModel):
    event: str
    occurredAt: datetime
    subscriber: WebhookSubscriber
    cards: list[WebhookCardV1] = Field(min_length=1)


class WebhookCardV2(BaseModel):
    selectionType: Literal["popular", "other"]
    popularCardKey: str | None = None
    customCardName: str | None = None
    cardType: str
    creditLimit: int = Field(gt=0)
    statementDay: int = Field(ge=1, le=31)

    @model_validator(mode="after")
    def validate_selection_fields(self):
        if self.selectionType == "popular" and not self.popularCardKey:
            raise ValueError("popularCardKey is required when selectionType=popular")
        if self.selectionType == "other" and not (self.customCardName and self.customCardName.strip()):
            raise ValueError("customCardName is required when selectionType=other")
        return self


class WebhookPayloadV2(BaseModel):
    event: str
    occurredAt: datetime
    source: str
    subscriber: WebhookSubscriber
    cards: list[WebhookCardV2] = Field(min_length=1)


# Backward-compatible aliases for existing imports.
WebhookCard = WebhookCardV1
WebhookPayload = WebhookPayloadV1


class PreferenceItemIn(BaseModel):
    scope: str = Field(pattern="^(global|card)$")
    reminder_type: str = Field(pattern="^(all|J20|J5)$")
    enabled: bool
    card_id: str | None = None


class PreferenceItemOut(BaseModel):
    id: str
    scope: str
    reminder_type: str
    enabled: bool
    card_id: str | None
    updated_by: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class PreferencesViewOut(BaseModel):
    subscriber_id: str
    email: EmailStr
    status: str
    cards: list[CardOut]
    preferences: list[PreferenceItemOut]


class PreferenceCardEmailUpdateIn(BaseModel):
    card_id: str
    email_enabled: bool


class PreferencesUpdateRequest(BaseModel):
    global_email_enabled: bool | None = None
    card_email_updates: list[PreferenceCardEmailUpdateIn] = []

    model_config = {"extra": "forbid"}


class PreferenceCardPublicOut(BaseModel):
    id: str
    card_name: str
    card_type: str
    statement_day: int
    is_active: bool
    email_enabled: bool


class PreferencesContextOut(BaseModel):
    subscriber_email_masked: str
    language: str
    subscriber_status: str
    global_email_enabled: bool
    focused_card_id: str | None
    cards: list[PreferenceCardPublicOut]


class ReminderOverrideCreate(BaseModel):
    reminder_type: str = Field(pattern="^(J20|J5)$")
    offset_days: int = Field(ge=1, le=60)
    enabled: bool = True
    card_id: str | None = None


class ReminderOverridePatch(BaseModel):
    offset_days: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None


class ReminderOverrideOut(BaseModel):
    id: str
    subscriber_id: str
    card_id: str | None
    reminder_type: str
    offset_days: int
    enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScheduledReminderOut(BaseModel):
    id: str
    subscriber_id: str
    card_id: str
    reminder_type: str
    channel: str
    target_statement_date: date
    planned_send_at: datetime
    status: str

    model_config = {"from_attributes": True}


class EmailEventOut(BaseModel):
    id: str
    scheduled_reminder_id: str
    provider: str
    provider_message_id: str | None
    event_type: str
    payload_json: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogOut(BaseModel):
    id: str
    actor_type: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    diff_json: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RunDueResponse(BaseModel):
    processed: int
    sent: int
    failed: int
    cancelled: int


class PreferenceLinkResponse(BaseModel):
    url: str


class DashboardSummaryOut(BaseModel):
    total_subscribers: int
    active_subscribers: int
    paused_subscribers: int
    unsubscribed_subscribers: int
    total_cards: int
    active_cards: int
    queued_reminders: int
    due_reminders: int
    sent_last_24h: int
    failed_last_24h: int
    cancelled_last_24h: int
