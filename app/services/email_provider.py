from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import hashlib

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings


@dataclass
class EmailSendResult:
    provider: str
    message_id: str
    accepted: bool


class EmailProviderInterface(ABC):
    provider_name: str

    @abstractmethod
    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> EmailSendResult:
        raise NotImplementedError


class MockEmailProvider(EmailProviderInterface):
    provider_name = "mock"

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> EmailSendResult:
        payload = f"{to_email}|{subject}|{body_text}|{body_html or ''}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return EmailSendResult(provider=self.provider_name, message_id=f"mock-{digest}", accepted=True)


class MailgunEmailProvider(EmailProviderInterface):
    provider_name = "mailgun"

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str | None,
        domain: str | None,
        from_email: str | None,
        timeout_seconds: float = 10.0,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.domain = domain
        self.from_email = from_email
        self.timeout_seconds = timeout_seconds

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> EmailSendResult:
        if not self.api_key or not self.domain or not self.from_email:
            return EmailSendResult(provider=self.provider_name, message_id="", accepted=False)

        payload = {
            "from": self.from_email,
            "to": to_email,
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            payload["html"] = body_html

        endpoint = f"{self.api_base}/{self.domain}/messages"

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    endpoint,
                    data=payload,
                    auth=("api", self.api_key),
                )
            if response.is_error:
                return EmailSendResult(provider=self.provider_name, message_id="", accepted=False)

            message_id = ""
            try:
                response_payload = response.json()
                if isinstance(response_payload, dict):
                    message_id = str(response_payload.get("id") or "")
            except ValueError:
                message_id = ""

            return EmailSendResult(provider=self.provider_name, message_id=message_id, accepted=True)
        except httpx.HTTPError:
            return EmailSendResult(provider=self.provider_name, message_id="", accepted=False)


class AmazonSesEmailProvider(EmailProviderInterface):
    provider_name = "ses"

    def __init__(
        self,
        *,
        region: str,
        from_email: str | None,
        configuration_set: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ):
        self.region = region
        self.from_email = from_email
        self.configuration_set = configuration_set
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            # Explicit keys are used on hosts that cannot expose AWS_* env vars (Vercel reserves those
            # names); with none set, boto3 falls back to its own credential chain (IAM role on Lambda).
            credentials = {}
            if self.access_key_id and self.secret_access_key:
                credentials = {
                    "aws_access_key_id": self.access_key_id,
                    "aws_secret_access_key": self.secret_access_key,
                }
            self._client = boto3.client("sesv2", region_name=self.region, **credentials)
        return self._client

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> EmailSendResult:
        if not self.from_email:
            return EmailSendResult(provider=self.provider_name, message_id="", accepted=False)

        body: dict[str, Any] = {"Text": {"Data": body_text}}
        if body_html:
            body["Html"] = {"Data": body_html}

        payload: dict[str, Any] = {
            "FromEmailAddress": self.from_email,
            "Destination": {"ToAddresses": [to_email]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": subject},
                    "Body": body,
                }
            },
        }

        if self.configuration_set:
            payload["ConfigurationSetName"] = self.configuration_set

        try:
            response = self._get_client().send_email(**payload)
            message_id = str(response.get("MessageId") or "")
            return EmailSendResult(provider=self.provider_name, message_id=message_id, accepted=True)
        except (BotoCoreError, ClientError):
            return EmailSendResult(provider=self.provider_name, message_id="", accepted=False)


class EmailProviderFactory:
    @staticmethod
    def get_provider(current_settings=settings) -> EmailProviderInterface:
        provider_name = (current_settings.email_provider or "mock").lower()

        if provider_name == "mock":
            return MockEmailProvider()
        if provider_name == "mailgun":
            from_email = current_settings.email_from or current_settings.mailgun_from_email
            return MailgunEmailProvider(
                api_base=current_settings.mailgun_api_base,
                api_key=current_settings.mailgun_api_key,
                domain=current_settings.mailgun_domain,
                from_email=from_email,
            )
        if provider_name == "ses":
            from_email = current_settings.email_from or current_settings.ses_from_email
            return AmazonSesEmailProvider(
                region=current_settings.ses_region,
                from_email=from_email,
                configuration_set=current_settings.ses_configuration_set,
                access_key_id=current_settings.ses_access_key_id,
                secret_access_key=current_settings.ses_secret_access_key,
            )

        raise ValueError(f"Unsupported email provider: {current_settings.email_provider}")


def get_email_provider(current_settings=settings) -> EmailProviderInterface:
    return EmailProviderFactory.get_provider(current_settings)


def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> EmailSendResult:
    provider = get_email_provider(settings)
    return provider.send_email(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
