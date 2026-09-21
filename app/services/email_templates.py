from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from urllib.parse import urlparse

from app.config import settings


@dataclass
class ReminderEmailContent:
    subject: str
    text_body: str
    html_body: str


@dataclass
class WelcomeEmailCardSummary:
    card_name: str
    card_type: str | None
    credit_limit_cents: int
    statement_day: int


def _language(subscriber_language: str | None) -> str:
    return "fr" if (subscriber_language or "").lower() == "fr" else "en"


def _is_additional_reminder(reminder_type: str | None) -> bool:
    return (reminder_type or "").upper() == "J20"


def _format_currency_en(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(int(cents))
    dollars = absolute // 100
    remainder = absolute % 100
    return f"{sign}${dollars:,}.{remainder:02d}"


def _format_currency_fr(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    absolute = abs(int(cents))
    dollars = absolute // 100
    remainder = absolute % 100
    grouped = f"{dollars:,}".replace(",", " ")
    return f"{sign}{grouped},{remainder:02d} $"


def _format_date_en(value: date) -> str:
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return f"{months[value.month - 1]} {value.day}, {value.year}"


def _format_date_fr(value: date) -> str:
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{value.day} {months[value.month - 1]} {value.year}"


def _format_statement_day_fr(statement_day: int) -> str:
    return f"le {statement_day} de chaque mois"


def _format_statement_day_en(statement_day: int) -> str:
    suffix = "th"
    if statement_day % 100 not in {11, 12, 13}:
        if statement_day % 10 == 1:
            suffix = "st"
        elif statement_day % 10 == 2:
            suffix = "nd"
        elif statement_day % 10 == 3:
            suffix = "rd"
    return f"{statement_day}{suffix} of each month"


def _fr_subject(card_name: str, reminder_type: str | None) -> str:
    if _is_additional_reminder(reminder_type):
        return f"Rappel à venir pour votre carte {card_name}"
    return f"Rappel pour votre carte {card_name}"


def _en_subject(card_name: str, reminder_type: str | None) -> str:
    if _is_additional_reminder(reminder_type):
        return f"Upcoming reminder for your {card_name} card"
    return f"Reminder for your {card_name} card"


def _welcome_subject(lang: str) -> str:
    if lang == "fr":
        return "Bienvenue dans vos rappels AvenaCredit"
    return "Welcome to your AvenaCredit reminders"


def _welcome_preheader(lang: str) -> str:
    if lang == "fr":
        return "Vos rappels de carte de crédit sont maintenant configurés."
    return "Your credit card reminders are now set up."


def _build_logo_url(app_base_url: str | None) -> str | None:
    base_url = (app_base_url or "").strip().rstrip("/")
    if not base_url:
        return None

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return f"{base_url}/static/email/logo.png"


def _brand_header_html(logo_url: str | None) -> str:
    if not logo_url:
        return (
            '<p style="margin:0;font-size:14px;letter-spacing:0.02em;color:#0f4f86;font-weight:700;">'
            "AvenaCredit"
            "</p>"
        )

    safe_logo_url = escape(logo_url)
    return (
        f'<img src="{safe_logo_url}" width="160" alt="AvenaCredit" '
        'style="display:block;border:0;outline:none;text-decoration:none;height:auto;max-width:160px;" />'
    )


def _safe_card_type(value: str | None) -> str | None:
    card_type = (value or "").strip()
    if not card_type:
        return None
    return card_type.title()


def _fr_text(
    *,
    first_name: str,
    card_name: str,
    statement_date: str,
    target_amount: str,
    credit_limit: str,
    preferences_url: str,
) -> str:
    hello = f"Bonjour {first_name}," if first_name else "Bonjour,"
    return (
        f"{hello}\n\n"
        f"Votre relevé pour la carte {card_name} approche.\n\n"
        f"Date de relevé : {statement_date}\n\n"
        f"Montant cible : {target_amount}\n"
        f"Ce montant représente environ 30 % de votre limite de crédit de {credit_limit}.\n\n"
        "Vous pouvez gérer vos rappels ou vous désabonner ici :\n"
        f"{preferences_url}\n\n"
        "AvenaCredit"
    )


def _en_text(
    *,
    first_name: str,
    card_name: str,
    statement_date: str,
    target_amount: str,
    credit_limit: str,
    preferences_url: str,
) -> str:
    hello = f"Hello {first_name}," if first_name else "Hello,"
    return (
        f"{hello}\n\n"
        f"Your statement date for {card_name} is coming up.\n\n"
        f"Statement date: {statement_date}\n\n"
        f"Target amount: {target_amount}\n"
        f"This amount represents about 30% of your credit limit of {credit_limit}.\n\n"
        "You can manage your reminders or unsubscribe here:\n"
        f"{preferences_url}\n\n"
        "AvenaCredit"
    )


def _fr_html(
    *,
    first_name: str,
    card_name: str,
    statement_date: str,
    target_amount: str,
    credit_limit: str,
    preferences_url: str,
) -> str:
    safe_name = escape(first_name)
    safe_card = escape(card_name)
    safe_statement = escape(statement_date)
    safe_target = escape(target_amount)
    safe_limit = escape(credit_limit)
    safe_url = escape(preferences_url)
    brand_header = _brand_header_html(_build_logo_url(settings.app_base_url))
    greeting = f"Bonjour {safe_name}," if safe_name else "Bonjour,"

    return f"""<!doctype html>
<html lang=\"fr\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>AvenaCredit</title>
  </head>
  <body style=\"margin:0;padding:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif;color:#1f2a37;\">
    <div style=\"display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;\">Un rappel pour vous aider à gérer l'utilisation de votre carte de crédit.</div>
    <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f3f6fa;padding:24px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
      <tr>
        <td align=\"center\">
          <table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"width:100%;max-width:600px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
            <tr>
              <td style=\"padding:24px 24px 10px 24px;\">{brand_header}<h1 style=\"margin:12px 0 0 0;font-size:24px;line-height:1.3;color:#0f172a;\">Rappel pour votre carte de crédit</h1></td>
            </tr>
            <tr>
              <td style=\"padding:8px 24px 0 24px;font-size:16px;line-height:1.6;\">
                <p style=\"margin:0 0 12px 0;\">{greeting}</p>
                <p style=\"margin:0 0 12px 0;\">Votre relevé pour la carte <strong>{safe_card}</strong> approche.</p>
                <p style=\"margin:0 0 8px 0;\">Pour favoriser une bonne gestion de votre dossier de crédit, essayez de garder le solde de cette carte sous :</p>
                <p style=\"margin:0 0 16px 0;font-size:28px;font-weight:700;color:#0f4f86;\">{safe_target}</p>
                <p style=\"margin:0 0 16px 0;\">Ce montant représente environ 30 % de votre limite de crédit de <strong>{safe_limit}</strong>.</p>
                <p style=\"margin:0 0 18px 0;\"><strong>Date de relevé :</strong> {safe_statement}</p>
                <table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0 0 14px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\"><tr><td align=\"center\" bgcolor=\"#175f95\" style=\"border-radius:10px;\"><a href=\"{safe_url}\" style=\"display:inline-block;padding:12px 20px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;\">Gérer mes rappels</a></td></tr></table>
                <p style=\"margin:0 0 16px 0;font-size:14px;color:#475569;\">Vous pouvez modifier vos préférences ou vous désabonner des rappels à tout moment.</p>
              </td>
            </tr>
            <tr>
              <td style=\"padding:18px 24px 24px 24px;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:#64748b;\">
                <p style=\"margin:0 0 8px 0;font-weight:700;color:#334155;\">AvenaCredit</p>
                <p style=\"margin:0 0 8px 0;\">Ce courriel vous est envoyé parce que vous avez activé les rappels de carte de crédit.</p>
                <p style=\"margin:0 0 4px 0;\">Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :</p>
                <p style=\"margin:0;word-break:break-all;\"><a href=\"{safe_url}\" style=\"color:#175f95;\">{safe_url}</a></p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _en_html(
    *,
    first_name: str,
    card_name: str,
    statement_date: str,
    target_amount: str,
    credit_limit: str,
    preferences_url: str,
) -> str:
    safe_name = escape(first_name)
    safe_card = escape(card_name)
    safe_statement = escape(statement_date)
    safe_target = escape(target_amount)
    safe_limit = escape(credit_limit)
    safe_url = escape(preferences_url)
    brand_header = _brand_header_html(_build_logo_url(settings.app_base_url))
    greeting = f"Hello {safe_name}," if safe_name else "Hello,"

    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>AvenaCredit</title>
  </head>
  <body style=\"margin:0;padding:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif;color:#1f2a37;\">
    <div style=\"display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;\">A reminder to help you manage your credit card utilization.</div>
    <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f3f6fa;padding:24px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
      <tr>
        <td align=\"center\">
          <table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"width:100%;max-width:600px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
            <tr>
              <td style=\"padding:24px 24px 10px 24px;\">{brand_header}<h1 style=\"margin:12px 0 0 0;font-size:24px;line-height:1.3;color:#0f172a;\">Credit card reminder</h1></td>
            </tr>
            <tr>
              <td style=\"padding:8px 24px 0 24px;font-size:16px;line-height:1.6;\">
                <p style=\"margin:0 0 12px 0;\">{greeting}</p>
                <p style=\"margin:0 0 12px 0;\">Your statement date for <strong>{safe_card}</strong> is coming up.</p>
                <p style=\"margin:0 0 8px 0;\">To help manage your credit profile, try to keep this card's balance under:</p>
                <p style=\"margin:0 0 16px 0;font-size:28px;font-weight:700;color:#0f4f86;\">{safe_target}</p>
                <p style=\"margin:0 0 16px 0;\">This amount represents about 30% of your credit limit of <strong>{safe_limit}</strong>.</p>
                <p style=\"margin:0 0 18px 0;\"><strong>Statement date:</strong> {safe_statement}</p>
                <table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0 0 14px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\"><tr><td align=\"center\" bgcolor=\"#175f95\" style=\"border-radius:10px;\"><a href=\"{safe_url}\" style=\"display:inline-block;padding:12px 20px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;\">Manage my reminders</a></td></tr></table>
                <p style=\"margin:0 0 16px 0;font-size:14px;color:#475569;\">You can update your preferences or unsubscribe at any time.</p>
              </td>
            </tr>
            <tr>
              <td style=\"padding:18px 24px 24px 24px;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:#64748b;\">
                <p style=\"margin:0 0 8px 0;font-weight:700;color:#334155;\">AvenaCredit</p>
                <p style=\"margin:0 0 8px 0;\">You are receiving this email because you enabled credit card reminders.</p>
                <p style=\"margin:0 0 4px 0;\">If the button does not work, copy this link into your browser:</p>
                <p style=\"margin:0;word-break:break-all;\"><a href=\"{safe_url}\" style=\"color:#175f95;\">{safe_url}</a></p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _welcome_cards_text_en(cards: list[WelcomeEmailCardSummary]) -> str:
    lines: list[str] = []
    for card in cards:
        target_amount = int(round(card.credit_limit_cents * 0.30))
        lines.append(f"- {card.card_name}")
        card_type = _safe_card_type(card.card_type)
        if card_type:
            lines.append(f"  Type: {card_type}")
        lines.append(f"  Credit limit: {_format_currency_en(card.credit_limit_cents)}")
        lines.append(f"  Recommended target amount: {_format_currency_en(target_amount)}")
        lines.append(f"  Statement day: {_format_statement_day_en(card.statement_day)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _welcome_cards_text_fr(cards: list[WelcomeEmailCardSummary]) -> str:
    lines: list[str] = []
    for card in cards:
        target_amount = int(round(card.credit_limit_cents * 0.30))
        lines.append(f"- {card.card_name}")
        card_type = _safe_card_type(card.card_type)
        if card_type:
            lines.append(f"  Type : {card_type}")
        lines.append(f"  Limite : {_format_currency_fr(card.credit_limit_cents)}")
        lines.append(f"  Montant cible recommandé : {_format_currency_fr(target_amount)}")
        lines.append(f"  Date de relevé : {_format_statement_day_fr(card.statement_day)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _welcome_cards_html_en(cards: list[WelcomeEmailCardSummary]) -> str:
    rows: list[str] = []
    for card in cards:
        target_amount = int(round(card.credit_limit_cents * 0.30))
        safe_name = escape(card.card_name)
        safe_type = escape(_safe_card_type(card.card_type) or "")
        type_line = f'<p style="margin:0 0 6px 0;font-size:14px;color:#334155;">Type: {safe_type}</p>' if safe_type else ""
        rows.append(
            "<tr><td style=\"padding:14px 16px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fbff;\">"
            f'<p style="margin:0 0 6px 0;font-size:16px;font-weight:700;color:#0f172a;">{safe_name}</p>'
            f"{type_line}"
            f'<p style="margin:0 0 6px 0;font-size:14px;color:#334155;">Credit limit: {_format_currency_en(card.credit_limit_cents)}</p>'
            f'<p style="margin:0 0 6px 0;font-size:14px;color:#334155;">Recommended target amount: {_format_currency_en(target_amount)}</p>'
            f'<p style="margin:0;font-size:14px;color:#334155;">Statement day: {_format_statement_day_en(card.statement_day)}</p>'
            "</td></tr>"
        )
    return "".join(rows)


def _welcome_cards_html_fr(cards: list[WelcomeEmailCardSummary]) -> str:
    rows: list[str] = []
    for card in cards:
        target_amount = int(round(card.credit_limit_cents * 0.30))
        safe_name = escape(card.card_name)
        safe_type = escape(_safe_card_type(card.card_type) or "")
        type_line = f'<p style="margin:0 0 6px 0;font-size:14px;color:#334155;">Type : {safe_type}</p>' if safe_type else ""
        rows.append(
            "<tr><td style=\"padding:14px 16px;border:1px solid #e2e8f0;border-radius:10px;background:#f8fbff;\">"
            f'<p style="margin:0 0 6px 0;font-size:16px;font-weight:700;color:#0f172a;">{safe_name}</p>'
            f"{type_line}"
            f'<p style="margin:0 0 6px 0;font-size:14px;color:#334155;">Limite : {_format_currency_fr(card.credit_limit_cents)}</p>'
            f'<p style="margin:0 0 6px 0;font-size:14px;color:#334155;">Montant cible recommandé : {_format_currency_fr(target_amount)}</p>'
            f'<p style="margin:0;font-size:14px;color:#334155;">Date de relevé : {_format_statement_day_fr(card.statement_day)}</p>'
            "</td></tr>"
        )
    return "".join(rows)


def _welcome_text_fr(*, first_name: str, cards_block: str, preferences_url: str) -> str:
    greeting = f"Bonjour {first_name}," if first_name else "Bonjour,"
    return (
        f"{greeting}\n\n"
        "Votre inscription aux rappels AvenaCredit est maintenant activée.\n\n"
        "Nous vous enverrons un rappel avant la date de relevé de vos cartes pour vous aider à suivre votre utilisation de crédit.\n\n"
        "Vos cartes inscrites :\n"
        f"{cards_block}\n\n"
        "Gérer mes rappels :\n"
        f"{preferences_url}\n\n"
        "Vous pouvez modifier vos préférences ou vous désabonner à tout moment.\n\n"
        "AvenaCredit"
    )


def _welcome_text_en(*, first_name: str, cards_block: str, preferences_url: str) -> str:
    greeting = f"Hello {first_name}," if first_name else "Hello,"
    return (
        f"{greeting}\n\n"
        "Your AvenaCredit reminders are now active.\n\n"
        "We will send you a reminder before each card's statement date to help you monitor your credit utilization.\n\n"
        "Your subscribed cards:\n"
        f"{cards_block}\n\n"
        "Manage my reminders:\n"
        f"{preferences_url}\n\n"
        "You can update your preferences or unsubscribe at any time.\n\n"
        "AvenaCredit"
    )


def _welcome_html_fr(*, first_name: str, cards_html: str, preferences_url: str) -> str:
    safe_name = escape(first_name)
    greeting = f"Bonjour {safe_name}," if safe_name else "Bonjour,"
    safe_url = escape(preferences_url)
    brand_header = _brand_header_html(_build_logo_url(settings.app_base_url))
    preheader = escape(_welcome_preheader("fr"))

    return f"""<!doctype html>
<html lang=\"fr\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>AvenaCredit</title>
  </head>
  <body style=\"margin:0;padding:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif;color:#1f2a37;\">
    <div style=\"display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;\">{preheader}</div>
    <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f3f6fa;padding:24px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
      <tr>
        <td align=\"center\">
          <table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"width:100%;max-width:600px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
            <tr>
              <td style=\"padding:24px 24px 10px 24px;\">{brand_header}<h1 style=\"margin:12px 0 0 0;font-size:24px;line-height:1.3;color:#0f172a;\">Bienvenue dans vos rappels AvenaCredit</h1></td>
            </tr>
            <tr>
              <td style=\"padding:8px 24px 0 24px;font-size:16px;line-height:1.6;\">
                <p style=\"margin:0 0 12px 0;\">{greeting}</p>
                <p style="margin:0 0 12px 0;">Votre inscription aux rappels AvenaCredit est maintenant activée.</p>
                <p style="margin:0 0 14px 0;">Nous vous enverrons un rappel avant la date de relevé de vos cartes pour vous aider à suivre votre utilisation de crédit.</p>
                <p style=\"margin:0 0 10px 0;font-weight:700;color:#0f172a;\">Vos cartes inscrites :</p>
                <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0 0 18px 0;border-collapse:separate;border-spacing:0 8px;mso-table-lspace:0pt;mso-table-rspace:0pt;\">{cards_html}</table>
                <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0 0 14px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;"><tr><td align="center" bgcolor="#175f95" style="border-radius:10px;"><a href="{safe_url}" style="display:inline-block;padding:12px 20px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;">Gérer mes rappels</a></td></tr></table>
                <p style="margin:0 0 16px 0;font-size:14px;color:#475569;">Vous pouvez modifier vos préférences ou vous désabonner à tout moment.</p>
              </td>
            </tr>
            <tr>
              <td style=\"padding:18px 24px 24px 24px;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:#64748b;\">
                <p style=\"margin:0 0 8px 0;font-weight:700;color:#334155;\">AvenaCredit</p>
                <p style=\"margin:0 0 4px 0;\">Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :</p>
                <p style=\"margin:0;word-break:break-all;\"><a href=\"{safe_url}\" style=\"color:#175f95;\">{safe_url}</a></p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _welcome_html_en(*, first_name: str, cards_html: str, preferences_url: str) -> str:
    safe_name = escape(first_name)
    greeting = f"Hello {safe_name}," if safe_name else "Hello,"
    safe_url = escape(preferences_url)
    brand_header = _brand_header_html(_build_logo_url(settings.app_base_url))
    preheader = escape(_welcome_preheader("en"))

    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>AvenaCredit</title>
  </head>
  <body style=\"margin:0;padding:0;background:#f3f6fa;font-family:Arial,Helvetica,sans-serif;color:#1f2a37;\">
    <div style=\"display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;\">{preheader}</div>
    <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"background:#f3f6fa;padding:24px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
      <tr>
        <td align=\"center\">
          <table role=\"presentation\" width=\"600\" cellspacing=\"0\" cellpadding=\"0\" style=\"width:100%;max-width:600px;background:#ffffff;border:1px solid #e5e7eb;border-radius:14px;overflow:hidden;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\">
            <tr>
              <td style=\"padding:24px 24px 10px 24px;\">{brand_header}<h1 style=\"margin:12px 0 0 0;font-size:24px;line-height:1.3;color:#0f172a;\">Welcome to your AvenaCredit reminders</h1></td>
            </tr>
            <tr>
              <td style=\"padding:8px 24px 0 24px;font-size:16px;line-height:1.6;\">
                <p style=\"margin:0 0 12px 0;\">{greeting}</p>
                <p style=\"margin:0 0 12px 0;\">Your AvenaCredit reminders are now active.</p>
                <p style=\"margin:0 0 14px 0;\">We will send you a reminder before each card's statement date to help you monitor your credit utilization.</p>
                <p style=\"margin:0 0 10px 0;font-weight:700;color:#0f172a;\">Your subscribed cards:</p>
                <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0 0 18px 0;border-collapse:separate;border-spacing:0 8px;mso-table-lspace:0pt;mso-table-rspace:0pt;\">{cards_html}</table>
                <table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin:0 0 14px 0;border-collapse:separate;mso-table-lspace:0pt;mso-table-rspace:0pt;\"><tr><td align=\"center\" bgcolor=\"#175f95\" style=\"border-radius:10px;\"><a href=\"{safe_url}\" style=\"display:inline-block;padding:12px 20px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;\">Manage my reminders</a></td></tr></table>
                <p style=\"margin:0 0 16px 0;font-size:14px;color:#475569;\">You can update your preferences or unsubscribe at any time.</p>
              </td>
            </tr>
            <tr>
              <td style=\"padding:18px 24px 24px 24px;border-top:1px solid #e5e7eb;font-size:12px;line-height:1.6;color:#64748b;\">
                <p style=\"margin:0 0 8px 0;font-weight:700;color:#334155;\">AvenaCredit</p>
                <p style=\"margin:0 0 4px 0;\">If the button does not work, copy this link into your browser:</p>
                <p style=\"margin:0;word-break:break-all;\"><a href=\"{safe_url}\" style=\"color:#175f95;\">{safe_url}</a></p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def build_reminder_email_content(
    *,
    subscriber_language: str | None,
    subscriber_first_name: str | None,
    card_name: str,
    card_credit_limit_cents: int,
    reminder_type: str | None,
    statement_date: date,
    preferences_url: str,
    target_balance_cents: int,
) -> ReminderEmailContent:
    lang = _language(subscriber_language)
    first_name = (subscriber_first_name or "").strip()

    if lang == "fr":
        statement_display = _format_date_fr(statement_date)
        target_display = _format_currency_fr(target_balance_cents)
        credit_limit_display = _format_currency_fr(card_credit_limit_cents)
        subject = _fr_subject(card_name, reminder_type)
        text_body = _fr_text(
            first_name=first_name,
            card_name=card_name,
            statement_date=statement_display,
            target_amount=target_display,
            credit_limit=credit_limit_display,
            preferences_url=preferences_url,
        )
        html_body = _fr_html(
            first_name=first_name,
            card_name=card_name,
            statement_date=statement_display,
            target_amount=target_display,
            credit_limit=credit_limit_display,
            preferences_url=preferences_url,
        )
    else:
        statement_display = _format_date_en(statement_date)
        target_display = _format_currency_en(target_balance_cents)
        credit_limit_display = _format_currency_en(card_credit_limit_cents)
        subject = _en_subject(card_name, reminder_type)
        text_body = _en_text(
            first_name=first_name,
            card_name=card_name,
            statement_date=statement_display,
            target_amount=target_display,
            credit_limit=credit_limit_display,
            preferences_url=preferences_url,
        )
        html_body = _en_html(
            first_name=first_name,
            card_name=card_name,
            statement_date=statement_display,
            target_amount=target_display,
            credit_limit=credit_limit_display,
            preferences_url=preferences_url,
        )

    return ReminderEmailContent(subject=subject, text_body=text_body, html_body=html_body)


def build_welcome_email_content(
    *,
    subscriber_language: str | None,
    subscriber_first_name: str | None,
    cards: list[WelcomeEmailCardSummary],
    preferences_url: str,
) -> ReminderEmailContent:
    lang = _language(subscriber_language)
    first_name = (subscriber_first_name or "").strip()

    normalized_cards = [
        WelcomeEmailCardSummary(
            card_name=(card.card_name or "").strip(),
            card_type=card.card_type,
            credit_limit_cents=int(card.credit_limit_cents),
            statement_day=int(card.statement_day),
        )
        for card in cards
        if (card.card_name or "").strip()
    ]

    if not normalized_cards:
        normalized_cards = [
            WelcomeEmailCardSummary(
                card_name="AvenaCredit Card",
                card_type="",
                credit_limit_cents=0,
                statement_day=1,
            )
        ]

    if lang == "fr":
        cards_text = _welcome_cards_text_fr(normalized_cards)
        cards_html = _welcome_cards_html_fr(normalized_cards)
        text_body = _welcome_text_fr(first_name=first_name, cards_block=cards_text, preferences_url=preferences_url)
        html_body = _welcome_html_fr(first_name=first_name, cards_html=cards_html, preferences_url=preferences_url)
    else:
        cards_text = _welcome_cards_text_en(normalized_cards)
        cards_html = _welcome_cards_html_en(normalized_cards)
        text_body = _welcome_text_en(first_name=first_name, cards_block=cards_text, preferences_url=preferences_url)
        html_body = _welcome_html_en(first_name=first_name, cards_html=cards_html, preferences_url=preferences_url)

    return ReminderEmailContent(
        subject=_welcome_subject(lang),
        text_body=text_body,
        html_body=html_body,
    )
