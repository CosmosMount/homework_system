import asyncio
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from typing import Protocol, cast
from urllib.parse import quote
from uuid import UUID

from app.core.config import Settings
from app.core.markdown import render_announcement_markdown
from app.notifications.models import OutboxJob


class TransientMailError(Exception):
    pass


class PermanentMailError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class InlineMailImage:
    file_id: UUID
    content_id: str
    content: bytes
    media_type: str
    file_name: str


@dataclass(frozen=True, slots=True)
class RenderedMail:
    recipient: str
    subject: str
    text: str
    html: str
    inline_images: tuple[InlineMailImage, ...] = ()


_KNOWLEDGE_REFERENCE_HREF = re.compile(r'href="(/knowledge(?:\?[^" ]*)?)"')


def _absolute_knowledge_links(rendered_html: str, base_url: str) -> str:
    """把站内知识库引用补成邮件客户端可直接打开的平台链接。"""

    normalized_base = base_url.rstrip("/")
    return _KNOWLEDGE_REFERENCE_HREF.sub(
        lambda match: f'href="{normalized_base}{match.group(1)}"',
        rendered_html,
    )


class MailSender(Protocol):
    async def send(self, job: OutboxJob, secret_payload: dict[str, object]) -> None: ...


_INLINE_IMAGE_MARKDOWN = re.compile(r"!\[([^\]\r\n]*)\]\(announcement-image:[0-9a-fA-F-]{36}\)")


def _plain_announcement_markdown(markdown: str) -> str:
    return _INLINE_IMAGE_MARKDOWN.sub(
        lambda match: f"[图片：{match.group(1) or '通知图片'}]",
        markdown,
    )


def _inline_images(secret_payload: dict[str, object]) -> tuple[InlineMailImage, ...]:
    value = secret_payload.get("inline_images")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, InlineMailImage) for item in value
    ):
        raise PermanentMailError("INVALID_INLINE_IMAGES")
    return tuple(value)


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

    if job.job_type in {
        "announcement_email",
        "announcement_update_email",
        "announcement_reminder_email",
    }:
        title = str(job.payload["title"])
        summary = str(job.payload["summary"])
        target_url = str(job.payload["target_url"])
        if not target_url.startswith("/announcements/") or "://" in target_url:
            raise PermanentMailError("INVALID_TARGET_URL")
        link = f"{base_url}{target_url}"
        subject_title = " ".join(title.splitlines()).strip()
        if not subject_title:
            raise PermanentMailError("MISSING_TITLE")
        prefix = (
            "通知提醒"
            if job.job_type == "announcement_reminder_email"
            else ("通知更新" if job.job_type == "announcement_update_email" else "新通知")
        )
        subject = f"PNX Training Hub {prefix}：{subject_title}"
        body_markdown = job.payload.get("body_markdown")
        inline_images = _inline_images(secret_payload)
        images_by_id = {image.file_id: image for image in inline_images}
        if isinstance(body_markdown, str) and body_markdown.strip():
            normalized_body = body_markdown.strip()
            rendered_body = render_announcement_markdown(
                normalized_body,
                image_source=lambda file_id: (
                    f"cid:{images_by_id[file_id].content_id}" if file_id in images_by_id else None
                ),
            )
            rendered_body = _absolute_knowledge_links(rendered_body, base_url)
            text = (
                f"{full_name}，你好：\n\n{prefix}：{title}\n{summary}\n\n"
                f"{_plain_announcement_markdown(normalized_body)}"
                f"\n\n请登录平台查看附件与原通知：\n{link}"
            )
            html = (
                f"<p>{safe_name}，你好：</p>"
                f"<p><strong>{escape(prefix)}：{escape(title)}</strong></p>"
                f"<p>{escape(summary)}</p>"
                f"<div>{rendered_body}</div>"
                f'<p><a href="{escape(link)}">登录平台查看附件与原通知</a></p>'
            )
        else:
            # 兼容部署前已经入队、尚未携带正文快照的通知邮件。
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
        return RenderedMail(
            recipient=recipient,
            subject=subject,
            text=text,
            html=html,
            inline_images=inline_images,
        )

    if job.job_type == "assignment_reminder_email":
        title = str(job.payload["title"])
        target_url = str(job.payload["target_url"])
        if not target_url.startswith("/assignments/") or "://" in target_url:
            raise PermanentMailError("INVALID_TARGET_URL")
        subject_title = " ".join(title.splitlines()).strip()
        if not subject_title:
            raise PermanentMailError("MISSING_TITLE")
        link = f"{base_url}{target_url}"
        subject = f"PNX Training Hub 作业提醒：{subject_title}"
        text = f"{full_name}，你好：\n\n作业《{title}》有新的提醒。\n\n请登录平台查看作业：\n{link}"
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p>作业《{escape(title)}》有新的提醒。</p>"
            f'<p><a href="{escape(link)}">登录平台查看作业</a></p>'
        )
        return RenderedMail(recipient=recipient, subject=subject, text=text, html=html)

    if job.job_type == "intention_open_email":
        title = str(job.payload["title"])
        target_url = str(job.payload["target_url"])
        if not target_url.startswith("/intentions/") or "://" in target_url:
            raise PermanentMailError("INVALID_TARGET_URL")
        subject_title = " ".join(title.splitlines()).strip()
        if not subject_title:
            raise PermanentMailError("MISSING_TITLE")
        link = f"{base_url}{target_url}"
        subject = f"PNX Training Hub 问卷填写提醒：{subject_title}"
        text = (
            f"{full_name}，你好：\n\n问卷《{title}》现已开放填写。\n\n请登录平台填写问卷：\n{link}"
        )
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p>问卷《{escape(title)}》现已开放填写。</p>"
            f'<p><a href="{escape(link)}">登录平台填写问卷</a></p>'
        )
        return RenderedMail(recipient=recipient, subject=subject, text=text, html=html)

    if job.job_type == "submission_feedback_email":
        title = str(job.payload["title"])
        target_url = str(job.payload["target_url"])
        if (
            not target_url.startswith("/assignments/")
            or "/submissions/" not in target_url
            or "://" in target_url
        ):
            raise PermanentMailError("INVALID_TARGET_URL")
        subject_title = " ".join(title.splitlines()).strip()
        if not subject_title:
            raise PermanentMailError("MISSING_TITLE")
        link = f"{base_url}{target_url}"
        subject = f"PNX Training Hub 作业评语更新：{subject_title}"
        text = f"{full_name}，你好：\n\n作业《{title}》有新的评语。\n\n请登录平台查看：\n{link}"
        html = (
            f"<p>{safe_name}，你好：</p>"
            f"<p>作业《{escape(title)}》有新的评语。</p>"
            f'<p><a href="{escape(link)}">登录平台查看评语</a></p>'
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
        payload = message.get_payload()
        if not isinstance(payload, list):
            raise PermanentMailError("INVALID_MIME_STRUCTURE")
        html_part = cast(EmailMessage, payload[-1])
        for inline_image in mail.inline_images:
            maintype, subtype = inline_image.media_type.split("/", 1)
            html_part.add_related(
                inline_image.content,
                maintype=maintype,
                subtype=subtype,
                cid=f"<{inline_image.content_id}>",
                filename=inline_image.file_name,
                disposition="inline",
            )

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
