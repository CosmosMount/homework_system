from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID

_BLOCK_FIELDS = {
    2: ("paragraph", "text"),
    3: ("heading", "heading1"),
    4: ("heading", "heading2"),
    5: ("heading", "heading3"),
    6: ("heading", "heading4"),
    7: ("heading", "heading5"),
    8: ("heading", "heading6"),
    9: ("heading", "heading7"),
    10: ("heading", "heading8"),
    11: ("heading", "heading9"),
    12: ("bullet", "bullet"),
    13: ("ordered", "ordered"),
    14: ("code", "code"),
    15: ("quote", "quote"),
    16: ("equation", "equation"),
    17: ("todo", "todo"),
    19: ("callout", "callout"),
    22: ("divider", "divider"),
    23: ("attachment", "file"),
    27: ("image", "image"),
    31: ("table", "table"),
    32: ("container", "table_cell"),
    34: ("quote", "quote_container"),
    43: ("whiteboard", "whiteboard"),
}
_CODE_LANGUAGES = {
    1: "Plain Text",
    7: "Bash",
    9: "C++",
    10: "C",
    12: "CSS",
    13: "CoffeeScript",
    18: "Dockerfile",
    22: "Go",
    24: "HTML",
    28: "JSON",
    29: "Java",
    30: "JavaScript",
    32: "Kotlin",
    39: "Markdown",
    43: "PHP",
    46: "PowerShell",
    49: "Python",
    53: "Rust",
    56: "SQL",
    61: "Swift",
    63: "TypeScript",
    66: "XML",
    67: "YAML",
    68: "CMake",
    69: "Diff",
    75: "TOML",
}
_FEISHU_DOCUMENT_PATH_MARKERS = {"wiki", "docx", "document", "docs"}


@dataclass(frozen=True, slots=True)
class AssetReference:
    token: str
    kind: str
    file_name: str
    width: int | None = None
    height: int | None = None


def safe_href(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    decoded = unquote(value).strip()
    parts = urlsplit(decoded)
    if parts.scheme != "https" or parts.hostname is None:
        return None
    return decoded[:2000]


def _document_token_from_href(href: str | None) -> str | None:
    if href is None:
        return None
    parts = urlsplit(href)
    hostname = (parts.hostname or "").lower()
    if not (
        hostname == "feishu.cn"
        or hostname.endswith(".feishu.cn")
        or hostname == "larksuite.com"
        or hostname.endswith(".larksuite.com")
    ):
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    marker_index = next(
        (
            index
            for index, segment in enumerate(segments)
            if segment.lower() in _FEISHU_DOCUMENT_PATH_MARKERS
        ),
        -1,
    )
    if marker_index < 0 or marker_index + 1 >= len(segments):
        return None
    token = unquote(segments[marker_index + 1]).strip()
    if not token or token.lower() == "space":
        return None
    return token[:500]


def _clean_text(value: object, *, limit: int = 200_000) -> str:
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "")[:limit]


def _rich_text(
    container: object,
    *,
    assets: dict[tuple[str, str], UUID],
    asset_names: dict[tuple[str, str], str],
    fallback_url: str,
) -> list[dict[str, object]]:
    if not isinstance(container, dict):
        return []
    elements = container.get("elements")
    if not isinstance(elements, list):
        return []
    result: list[dict[str, object]] = []
    for raw in elements:
        if not isinstance(raw, dict):
            continue
        text = ""
        href: str | None = None
        document_token: str | None = None
        is_equation = False
        style_source: object = {}
        text_run = raw.get("text_run")
        mention_doc = raw.get("mention_doc")
        mention_user = raw.get("mention_user")
        equation = raw.get("equation")
        inline_file = raw.get("file")
        if isinstance(text_run, dict):
            text = _clean_text(text_run.get("content"))
            style_source = text_run.get("text_element_style")
            if isinstance(style_source, dict):
                link = style_source.get("link")
                if isinstance(link, dict):
                    href = safe_href(link.get("url"))
                    document_token = _document_token_from_href(href)
        elif isinstance(mention_doc, dict):
            text = _clean_text(mention_doc.get("title")) or "飞书文档"
            token = mention_doc.get("token")
            document_token = token if isinstance(token, str) and token else None
            href = safe_href(mention_doc.get("url"))
            document_token = document_token or _document_token_from_href(href)
        elif isinstance(mention_user, dict):
            text = "@" + (_clean_text(mention_user.get("name")) or "成员")
        elif isinstance(equation, dict):
            text = _clean_text(equation.get("content"), limit=20_000)
            is_equation = True
        elif isinstance(inline_file, dict):
            token = inline_file.get("file_token")
            if isinstance(token, str) and token:
                key = (token, "attachment")
                text = asset_names.get(key, "附件")
                asset_id = assets.get(key)
                href = (
                    f"/api/v1/knowledge/assets/{asset_id}/content"
                    if asset_id is not None
                    else fallback_url
                )
        if not text:
            continue
        style = style_source if isinstance(style_source, dict) else {}
        segment: dict[str, object] = {
            "text": text,
            "bold": style.get("bold") is True,
            "italic": style.get("italic") is True,
            "underline": style.get("underline") is True,
            "strikethrough": style.get("strikethrough") is True,
            "inline_code": style.get("inline_code") is True,
        }
        if href is not None:
            segment["href"] = href
        if document_token is not None:
            segment["document_token"] = document_token
        if is_equation:
            segment["equation"] = True
        result.append(segment)
    return result


def _block_elements(block: dict[str, Any]) -> list[dict[str, Any]]:
    block_type = block.get("block_type")
    field = _BLOCK_FIELDS.get(block_type, ("", ""))[1] if isinstance(block_type, int) else ""
    preferred = block.get(field) if field else None
    candidates = [preferred, *block.values()]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        elements = candidate.get("elements")
        if isinstance(elements, list):
            return [item for item in elements if isinstance(item, dict)]
    return []


def discover_asset_references(blocks: list[dict[str, Any]]) -> list[AssetReference]:
    references: list[AssetReference] = []
    seen: set[tuple[str, str]] = set()
    by_id = {
        str(block["block_id"]): block for block in blocks if isinstance(block.get("block_id"), str)
    }

    def add_reference(
        token: object,
        kind: str,
        *,
        file_name: str,
        width: object = None,
        height: object = None,
    ) -> None:
        if not isinstance(token, str) or not token or (token, kind) in seen:
            return
        seen.add((token, kind))
        references.append(
            AssetReference(
                token=token,
                kind=kind,
                file_name=file_name,
                width=width if isinstance(width, int) and width > 0 else None,
                height=height if isinstance(height, int) and height > 0 else None,
            )
        )

    for block in blocks:
        image = block.get("image")
        if isinstance(image, dict):
            add_reference(
                image.get("token"),
                "image",
                file_name="知识库图片",
                width=image.get("width"),
                height=image.get("height"),
            )
        attachment = block.get("file")
        if isinstance(attachment, dict):
            raw_name = attachment.get("name")
            add_reference(
                attachment.get("token"),
                "attachment",
                file_name=(
                    _clean_text(raw_name, limit=255) if isinstance(raw_name, str) else "附件"
                ),
            )
        board = block.get("board")
        if not isinstance(board, dict):
            board = block.get("whiteboard")
        if isinstance(board, dict):
            add_reference(
                board.get("token") or board.get("whiteboard_id") or block.get("token"),
                "whiteboard",
                file_name="白板.png",
                width=board.get("width"),
                height=board.get("height"),
            )
        for element in _block_elements(block):
            inline_file = element.get("file")
            if not isinstance(inline_file, dict):
                continue
            source_id = inline_file.get("source_block_id")
            source = by_id.get(source_id) if isinstance(source_id, str) else None
            source_file = source.get("file") if isinstance(source, dict) else None
            raw_name = source_file.get("name") if isinstance(source_file, dict) else None
            add_reference(
                inline_file.get("file_token"),
                "attachment",
                file_name=(
                    _clean_text(raw_name, limit=255) if isinstance(raw_name, str) else "附件"
                ),
            )
    return references


def normalize_document(
    raw_blocks: list[dict[str, Any]],
    *,
    assets: dict[tuple[str, str], UUID],
    asset_names: dict[tuple[str, str], str],
    fallback_url: str,
    asset_sizes: dict[tuple[str, str], int] | None = None,
    asset_media_types: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    resolved_asset_sizes = asset_sizes or {}
    resolved_asset_media_types = asset_media_types or {}
    by_id = {
        str(block["block_id"]): block
        for block in raw_blocks
        if isinstance(block.get("block_id"), str)
    }
    referenced_children: set[str] = set()
    for block in raw_blocks:
        children = block.get("children")
        if isinstance(children, list):
            referenced_children.update(str(child) for child in children if isinstance(child, str))

    def children_of(block: dict[str, Any], trail: set[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        raw_children = block.get("children")
        if not isinstance(raw_children, list):
            return result
        for child_id in raw_children:
            if not isinstance(child_id, str) or child_id in trail:
                continue
            child = by_id.get(child_id)
            if child is not None:
                normalized = normalize_block(child, trail | {child_id})
                if normalized is not None:
                    result.append(normalized)
        return result

    def normalize_block(block: dict[str, Any], trail: set[str]) -> dict[str, Any] | None:
        block_id = str(block.get("block_id", ""))
        block_type = block.get("block_type")
        numeric_type = block_type if isinstance(block_type, int) else 0
        normalized_type, field = _BLOCK_FIELDS.get(numeric_type, ("container", ""))
        detail = block.get(field) if field else None
        result: dict[str, Any] = {"id": block_id, "type": normalized_type}

        if normalized_type in {
            "paragraph",
            "heading",
            "bullet",
            "ordered",
            "code",
            "quote",
            "equation",
            "todo",
        }:
            result["segments"] = _rich_text(
                detail,
                assets=assets,
                asset_names=asset_names,
                fallback_url=fallback_url,
            )
        if normalized_type == "heading":
            result["level"] = max(1, min(numeric_type - 2, 6))
        if normalized_type == "todo" and isinstance(detail, dict):
            result["done"] = detail.get("done") is True
        if normalized_type == "code" and isinstance(detail, dict):
            style = detail.get("style")
            language = style.get("language") if isinstance(style, dict) else None
            result["language"] = (
                _CODE_LANGUAGES.get(language, str(language))
                if isinstance(language, int)
                else "Plain Text"
            )
            result["wrap"] = isinstance(style, dict) and style.get("wrap") is True
        if normalized_type == "callout":
            callout = detail if isinstance(detail, dict) else {}
            for source_field, target_field in (
                ("background_color", "background_color"),
                ("border_color", "border_color"),
                ("text_color", "text_color"),
                ("emoji_id", "emoji_id"),
            ):
                value = callout.get(source_field)
                if isinstance(value, int) and not isinstance(value, bool):
                    result[target_field] = value
                elif isinstance(value, str) and value:
                    result[target_field] = _clean_text(value, limit=64)
            result["tone"] = result.get("background_color", "")
        if normalized_type in {"image", "attachment", "whiteboard"}:
            kind = normalized_type
            asset_kind = "attachment" if kind == "attachment" else kind
            if normalized_type == "whiteboard":
                detail = block.get("board") or block.get("whiteboard") or detail
            token = detail.get("token") if isinstance(detail, dict) else None
            if normalized_type == "whiteboard" and isinstance(detail, dict):
                token = token or detail.get("whiteboard_id") or block.get("token")
            key = (token, asset_kind) if isinstance(token, str) else ("", asset_kind)
            asset_id = assets.get(key)
            if asset_id is None and normalized_type in {"image", "whiteboard"}:
                return None
            result["asset_id"] = str(asset_id) if asset_id is not None else None
            result["file_name"] = asset_names.get(key, "知识库附件")
            result["fallback_url"] = fallback_url
            if normalized_type == "attachment" and asset_id is not None:
                file_size = resolved_asset_sizes.get(key)
                media_type = resolved_asset_media_types.get(key)
                if isinstance(file_size, int) and file_size >= 0:
                    result["file_size"] = file_size
                if isinstance(media_type, str) and media_type:
                    result["mime_type"] = media_type
            if isinstance(detail, dict):
                width = detail.get("width")
                height = detail.get("height")
                result["width"] = width if isinstance(width, int) and width > 0 else None
                result["height"] = height if isinstance(height, int) and height > 0 else None
        if normalized_type == "table" and isinstance(detail, dict):
            raw_cells = detail.get("cells") or block.get("children")
            properties = detail.get("property")
            row_size = properties.get("row_size") if isinstance(properties, dict) else None
            column_size = properties.get("column_size") if isinstance(properties, dict) else None
            raw_merge_info = properties.get("merge_info") if isinstance(properties, dict) else None
            cells = (
                [item for item in raw_cells if isinstance(item, str)]
                if isinstance(raw_cells, list)
                else []
            )
            if not isinstance(column_size, int) or column_size <= 0:
                column_size = len(cells) or 1
            expected_rows = (
                row_size
                if isinstance(row_size, int) and row_size > 0
                else max(1, (len(cells) + column_size - 1) // column_size)
            )
            merge_info = raw_merge_info if isinstance(raw_merge_info, list) else []
            occupied = [[False for _ in range(column_size)] for _ in range(expected_rows)]
            normalized_rows: list[list[dict[str, Any]]] = []
            cell_index = 0
            for row_index in range(expected_rows):
                row: list[dict[str, Any]] = []
                for column_index in range(column_size):
                    if occupied[row_index][column_index] or cell_index >= len(cells):
                        continue
                    cell_id = cells[cell_index]
                    merge = merge_info[cell_index] if cell_index < len(merge_info) else {}
                    row_span_value = merge.get("row_span") if isinstance(merge, dict) else None
                    col_span_value = merge.get("col_span") if isinstance(merge, dict) else None
                    row_span = (
                        row_span_value
                        if isinstance(row_span_value, int) and row_span_value > 0
                        else 1
                    )
                    col_span = (
                        col_span_value
                        if isinstance(col_span_value, int) and col_span_value > 0
                        else 1
                    )
                    for span_row in range(row_index, min(row_index + row_span, expected_rows)):
                        for span_column in range(
                            column_index,
                            min(column_index + col_span, column_size),
                        ):
                            occupied[span_row][span_column] = True
                    cell = by_id.get(cell_id)
                    normalized_cell: dict[str, Any] = {
                        "id": cell_id,
                        "blocks": (
                            children_of(cell, trail | {cell_id}) if cell is not None else []
                        ),
                    }
                    if row_span > 1:
                        normalized_cell["row_span"] = row_span
                    if col_span > 1:
                        normalized_cell["col_span"] = col_span
                    row.append(normalized_cell)
                    cell_index += 1
                normalized_rows.append(row)
            result["rows"] = normalized_rows
        nested = children_of(block, trail | {block_id})
        if nested and normalized_type != "table":
            result["children"] = nested
        if normalized_type == "divider":
            return result
        if normalized_type == "container" and not nested:
            return None
        return result

    page = next((block for block in raw_blocks if block.get("block_type") == 1), None)
    if page is not None:
        return children_of(page, {str(page.get("block_id", ""))})
    roots: list[dict[str, Any]] = []
    for block in raw_blocks:
        block_id = block.get("block_id")
        if not isinstance(block_id, str) or block_id in referenced_children:
            continue
        normalized = normalize_block(block, {block_id})
        if normalized is not None:
            roots.append(normalized)
    return roots
