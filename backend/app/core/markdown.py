"""统一的服务端 Markdown 渲染与清洗。"""

import re
from collections.abc import Callable
from uuid import UUID

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token

_MARKDOWN = MarkdownIt(
    "commonmark",
    {
        "html": False,
        "linkify": False,
        "typographer": False,
    },
).enable("table")

_ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "code": {"class"},
}
_HEADING_PATTERN = re.compile(r"<(\/?)h([1-5])>")
ANNOUNCEMENT_IMAGE_PREFIX = "announcement-image:"
ANNOUNCEMENT_INLINE_IMAGE_MAX_COUNT = 10
ANNOUNCEMENT_INLINE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
ANNOUNCEMENT_INLINE_IMAGES_MAX_TOTAL_BYTES = 20 * 1024 * 1024
ANNOUNCEMENT_IMAGE_MEDIA_TYPES = {
    "gif": "image/gif",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def _demote_headings(html: str) -> str:
    """为页面标题保留 h1，把正文标题整体下移一级。"""

    def replace(match: re.Match[str]) -> str:
        return f"<{match.group(1)}h{int(match.group(2)) + 1}>"

    return _HEADING_PATTERN.sub(replace, html)


def render_markdown(markdown: str) -> str:
    """把用户 Markdown 转换为允许列表 HTML。"""

    rendered = _MARKDOWN.render(markdown)
    cleaned = nh3.clean(
        rendered,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https"},
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )
    return _demote_headings(cleaned)


def _image_tokens(tokens: list[Token]) -> list[Token]:
    images: list[Token] = []
    for token in tokens:
        if token.type == "image":
            images.append(token)
        if token.children:
            images.extend(_image_tokens(token.children))
    return images


def announcement_image_ids(markdown: str) -> list[UUID]:
    """按正文出现顺序提取通知专用图片 UUID；错误专用 URI 直接拒绝。"""

    image_ids: list[UUID] = []
    for token in _image_tokens(_MARKDOWN.parse(markdown)):
        source_value = token.attrGet("src")
        source = source_value if isinstance(source_value, str) else ""
        if not source.startswith(ANNOUNCEMENT_IMAGE_PREFIX):
            continue
        raw_file_id = source.removeprefix(ANNOUNCEMENT_IMAGE_PREFIX)
        try:
            file_id = UUID(raw_file_id)
        except ValueError as exc:
            raise ValueError("INVALID_ANNOUNCEMENT_IMAGE_REFERENCE") from exc
        if str(file_id) != raw_file_id.lower():
            raise ValueError("INVALID_ANNOUNCEMENT_IMAGE_REFERENCE")
        image_ids.append(file_id)
    return image_ids


def render_announcement_markdown(
    markdown: str,
    *,
    image_source: Callable[[UUID], str | None] | None = None,
) -> str:
    """渲染通知 Markdown；只允许服务端可解析的通知附件图片。"""

    tokens = _MARKDOWN.parse(markdown)
    resolver = image_source or (lambda file_id: f"{ANNOUNCEMENT_IMAGE_PREFIX}{file_id}")
    for token in _image_tokens(tokens):
        source_value = token.attrGet("src")
        source = source_value if isinstance(source_value, str) else ""
        replacement: str | None = None
        if source.startswith(ANNOUNCEMENT_IMAGE_PREFIX):
            raw_file_id = source.removeprefix(ANNOUNCEMENT_IMAGE_PREFIX)
            try:
                file_id = UUID(raw_file_id)
            except ValueError:
                file_id = None
            if file_id is not None and str(file_id) == raw_file_id.lower():
                replacement = resolver(file_id)
        if replacement is None:
            token.type = "text"
            token.tag = ""
            token.nesting = 0
            token.attrs = {}
            token.children = None
            token.content = token.content or "图片"
        else:
            token.attrSet("src", replacement)

    rendered = _MARKDOWN.renderer.render(tokens, _MARKDOWN.options, {})
    cleaned = nh3.clean(
        rendered,
        tags=_ALLOWED_TAGS | {"img"},
        attributes={
            **_ALLOWED_ATTRIBUTES,
            "img": {"src", "alt", "title"},
        },
        url_schemes={"http", "https", "cid", "announcement-image"},
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )
    return _demote_headings(cleaned)
