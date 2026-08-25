"""统一的服务端 Markdown 渲染与清洗。"""

import re

import nh3
from markdown_it import MarkdownIt

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
