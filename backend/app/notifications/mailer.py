import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape
from typing import Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.notifications.models import OutboxJob


class TransientMailError(Exception):
    pass


class PermanentMailError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RenderedMail:
    recipient: str
    subject: str
    text: str
    html: str


class MailSender(Protocol):
    async def send(self, job: OutboxJob, secret_payload: dict[str, object]) -> None: ...


def render_mail(
    job: OutboxJob,
    secret_payload: dict[str, object],
    *,
    app_base_url: str,
) -> RenderedMail:
    recipient = str(job.payload["recipient"])
    full_name = str(job.payload.get("full_name") or "同学")
    safe_name = escape(full_name)
    base_url = app_base_url.rstrip("/")

    if job.job_type in {"email_verification", "password_reset"}:
        token = secret_payload.get("token")
        if not isinstance(token, str) or not token:
            raise PermanentMailError("MISSING_TOKEN")
        path = "verify-email" if job.job_type == "email_verification" else "reset-password"
        link = f"{base_url}/{path}?token={quote(token, safe='')}"
        if job.job_type == "email_verification":
            subject = "验证你的 PNX Training Hub 学校邮箱"
            action = "验证邮箱"
            expiry = "24 小时"
        else:
            subject = "重置你的 PNX Training Hub 密码"
            action = "重置密码"
            expiry = "30 分钟"
        text = (
            f"{full_name}，你好：\n\n请在 {expiry}内打开以下链接完成{action}：\n"
            f"{link}\n\n如果这不是你的操作，请忽略本邮件。"
        )
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p>请在 {expiry}内打开以下链接完成{action}：</p>"
            f'<p><a href="{escape(link)}">{action}</a></p>'
            "<p>如果这不是你的操作，请忽略本邮件。</p>"
        )
        return RenderedMail(recipient=recipient, subject=subject, text=text, html=html)

    if job.job_type in {"announcement_email", "announcement_update_email"}:
        title = str(job.payload["title"])
        summary = str(job.payload["summary"])
        target_url = str(job.payload["target_url"])
        if not target_url.startswith("/announcements/") or "://" in target_url:
            raise PermanentMailError("INVALID_TARGET_URL")
        link = f"{base_url}{target_url}"
        subject_title = " ".join(title.splitlines()).strip()
        if not subject_title:
            raise PermanentMailError("MISSING_TITLE")
        prefix = "通知更新" if job.job_type == "announcement_update_email" else "新通知"
        subject = f"PNX Training Hub {prefix}：{subject_title}"
        text = (
            f"{full_name}，你好：\n\n{prefix}：{title}\n{summary}\n\n"
            f"请登录平台查看完整内容与附件：\n{link}"
        )
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p><strong>{escape(prefix)}：{escape(title)}</strong></p>"
            f"<p>{escape(summary)}</p>"
            f'<p><a href="{escape(link)}">登录平台查看完整内容与附件</a></p>'
        )
        return RenderedMail(recipient=recipient, subject=subject, text=text, html=html)

    if job.job_type == "assignment_extension_email":
        title = str(job.payload["title"])
        target_url = str(job.payload["target_url"])
        deadline_raw = str(job.payload["extended_deadline"])
        if not target_url.startswith("/assignments/") or "://" in target_url:
            raise PermanentMailError("INVALID_TARGET_URL")
        try:
            deadline = datetime.fromisoformat(deadline_raw)
        except ValueError as exc:
            raise PermanentMailError("INVALID_DEADLINE") from exc
        if deadline.tzinfo is None:
            raise PermanentMailError("INVALID_DEADLINE")
        deadline_text = deadline.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
        link = f"{base_url}{target_url}"
        subject_title = " ".join(title.splitlines()).strip()
        if not subject_title:
            raise PermanentMailError("MISSING_TITLE")
        subject = f"PNX Training Hub 作业延期：{subject_title}"
        text = (
            f"{full_name}，你好：\n\n作业《{title}》的个人截止时间已延长至 "
            f"{deadline_text}（Asia/Shanghai）。\n\n请登录平台查看作业详情：\n{link}"
        )
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p>作业《{escape(title)}》的个人截止时间已延长至 "
            f"<strong>{escape(deadline_text)}（Asia/Shanghai）</strong>。</p>"
            f'<p><a href="{escape(link)}">登录平台查看作业详情</a></p>'
        )
        return RenderedMail(recipient=recipient, subject=subject, text=text, html=html)

    if job.job_type == "security_alert":
        event = str(job.payload.get("event") or "account_changed")
        event_text = {
            "password_changed": "密码已更改",
            "email_changed": "学校邮箱已更改，账号需要重新验证",
        }.get(event, "账号安全设置已更改")
        subject = "PNX Training Hub 账号安全提醒"
        text = f"{full_name}，你好：\n\n你的账号{event_text}。如非本人操作，请联系管理员。"
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p>你的账号{escape(event_text)}。如非本人操作，请联系管理员。</p>"
        )
        return RenderedMail(recipient=recipient, subject=subject, text=text, html=html)

    raise PermanentMailError("UNSUPPORTED_JOB_TYPE")


class SMTPMailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, job: OutboxJob, secret_payload: dict[str, object]) -> None:
        mail = render_mail(
            job,
            secret_payload,
            app_base_url=str(self._settings.app_base_url),
        )
        await asyncio.to_thread(self._send_sync, mail)

    def _send_sync(self, mail: RenderedMail) -> None:
        message = EmailMessage()
        message["Subject"] = mail.subject
        message["From"] = self._settings.mail_from
        message["To"] = mail.recipient
        message["Reply-To"] = self._settings.mail_reply_to
        message["Message-ID"] = f"<{id(message)}@pnx-training.local>"
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")

        try:
            with smtplib.SMTP(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=20,
            ) as client:
                client.ehlo()
                if self._settings.smtp_starttls:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                if self._settings.smtp_username:
                    client.login(
                        self._settings.smtp_username,
                        self._settings.smtp_password.get_secret_value(),
                    )
                client.send_message(message)
        except smtplib.SMTPRecipientsRefused as exc:
            response_codes = [
                detail[0]
                for detail in exc.recipients.values()
                if isinstance(detail, tuple) and isinstance(detail[0], int)
            ]
            if response_codes and all(code >= 500 for code in response_codes):
                raise PermanentMailError("RECIPIENT_REJECTED") from exc
            raise TransientMailError("RECIPIENT_TEMPORARILY_REJECTED") from exc
        except smtplib.SMTPResponseException as exc:
            if exc.smtp_code >= 500:
                raise PermanentMailError(f"SMTP_{exc.smtp_code}") from exc
            raise TransientMailError(f"SMTP_{exc.smtp_code}") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise TransientMailError("SMTP_UNAVAILABLE") from exc
