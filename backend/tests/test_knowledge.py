import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.knowledge.feishu_client import FeishuClient, HttpResponse, KnowledgeSyncError
from app.knowledge.normalizer import (
    discover_asset_references,
    normalize_document,
    safe_href,
)
from app.notifications.models import OutboxJob
from app.notifications.service import OutboxProcessor


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str], bytes | None]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        max_bytes: int,
    ) -> HttpResponse:
        self.requests.append((url, headers, body))
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            return HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"code": 0, "tenant_access_token": "tenant-token"}).encode(),
            )
        if "/wiki/v2/spaces/get_node?token=document-node" in url:
            node = {
                "node_token": "document-node",
                "obj_token": "document-id",
                "obj_type": "docx",
                "title": "单篇文档",
                "has_child": False,
            }
            return HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"code": 0, "data": {"node": node}}).encode(),
            )
        if "/wiki/v2/spaces/7666438057763015890/nodes" in url:
            if "parent_node_token=folder-node" in url:
                items = [
                    {
                        "node_token": "child-node",
                        "obj_token": "child-doc",
                        "obj_type": "docx",
                        "title": "子文档",
                        "has_child": False,
                    }
                ]
            else:
                items = [
                    {
                        "node_token": "root-doc-node",
                        "obj_token": "root-doc",
                        "obj_type": "docx",
                        "title": "入门",
                        "has_child": False,
                    },
                    {
                        "node_token": "folder-node",
                        "obj_type": "wiki",
                        "title": "进阶",
                        "has_child": True,
                    },
                    {
                        "node_token": "tail-node",
                        "obj_type": "wiki",
                        "title": "末尾节点",
                        "has_child": False,
                    },
                ]
            return HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"code": 0, "data": {"items": items, "has_more": False}}).encode(),
            )
        if "/docx/v1/documents/root-doc/blocks" in url:
            items = [{"block_id": "page", "block_type": 1, "children": []}]
            return HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"code": 0, "data": {"items": items, "has_more": False}}).encode(),
            )
        if url.endswith("/docx/v1/documents/root-doc"):
            return HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"code": 0, "data": {"document": {"title": "接口中的标题"}}}).encode(),
            )
        raise AssertionError("unexpected Feishu URL: " + url)


def configured_settings() -> Settings:
    return Settings(
        app_env="test",
        feishu_app_id="app-id",
        feishu_app_secret="app-secret-value",
        feishu_wiki_url="https://pnx.feishu.cn/wiki/space/7666438057763015890",
    )


@pytest.mark.asyncio
async def test_feishu_client_uses_fixed_host_bearer_auth_and_recursive_nodes() -> None:
    transport = RecordingTransport()
    client = FeishuClient(configured_settings(), transport=transport)

    nodes = await client.list_nodes()
    blocks = await client.document_blocks("root-doc")
    title = await client.document_title("root-doc")

    assert [node["node_token"] for node in nodes] == [
        "root-doc-node",
        "folder-node",
        "child-node",
        "tail-node",
    ]
    assert nodes[2]["_parent_node_token"] == "folder-node"
    assert nodes[2]["_depth"] == 1
    assert blocks[0]["block_type"] == 1
    assert title == "接口中的标题"
    assert all(
        url.startswith("https://open.feishu.cn/open-apis/") for url, _, _ in transport.requests
    )
    block_url = next(
        url for url, _, _ in transport.requests if "/docx/v1/documents/root-doc/blocks" in url
    )
    assert "document_revision_id" not in block_url
    authenticated = [headers for _, headers, _ in transport.requests[1:]]
    assert all(headers["authorization"] == "Bearer tenant-token" for headers in authenticated)
    assert all("app-secret-value" not in url for url, _, _ in transport.requests)


class RejectedSubtreeTransport(RecordingTransport):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        max_bytes: int,
    ) -> HttpResponse:
        if "parent_node_token=folder-node" in url:
            return HttpResponse(403, {"content-type": "application/json"}, b"{}")
        return super().request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            max_bytes=max_bytes,
        )


@pytest.mark.asyncio
async def test_feishu_client_fails_when_nonroot_subtree_is_rejected() -> None:
    client = FeishuClient(configured_settings(), transport=RejectedSubtreeTransport())

    with pytest.raises(KnowledgeSyncError) as exc_info:
        await client.list_nodes()

    assert exc_info.value.code == "FEISHU_REQUEST_REJECTED"


class PageTokenTransport(RecordingTransport):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        max_bytes: int,
    ) -> HttpResponse:
        if "/wiki/v2/spaces/7666438057763015890/nodes" in url:
            self.requests.append((url, headers, body))
            if "page_token=next-page" in url:
                items = [
                    {
                        "node_token": "second-node",
                        "obj_type": "wiki",
                        "title": "第二页",
                        "has_child": False,
                    }
                ]
                data = {"items": items, "has_more": False}
            else:
                items = [
                    {
                        "node_token": "first-node",
                        "obj_type": "wiki",
                        "title": "第一页",
                        "has_child": False,
                    }
                ]
                data = {"items": items, "has_more": False, "page_token": "next-page"}
            return HttpResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"code": 0, "data": data}).encode(),
            )
        return super().request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            max_bytes=max_bytes,
        )


@pytest.mark.asyncio
async def test_feishu_client_paginates_until_page_token_is_empty() -> None:
    client = FeishuClient(configured_settings(), transport=PageTokenTransport())

    nodes = await client.list_nodes()

    assert [node["node_token"] for node in nodes] == ["first-node", "second-node"]


class AssetHeaderTransport(RecordingTransport):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        max_bytes: int,
    ) -> HttpResponse:
        if "/board/v1/whiteboards/board-token/download_as_image" in url:
            self.requests.append((url, headers, body))
            return HttpResponse(200, {"content-type": "image/png"}, b"board")
        if "/drive/v1/medias/image-token/download" in url:
            self.requests.append((url, headers, body))
            return HttpResponse(200, {"content-type": "image/png"}, b"image")
        return super().request(
            method=method,
            url=url,
            headers=headers,
            body=body,
            max_bytes=max_bytes,
        )


@pytest.mark.asyncio
async def test_feishu_client_requests_whiteboard_as_png_only() -> None:
    transport = AssetHeaderTransport()
    client = FeishuClient(configured_settings(), transport=transport)

    await client.download_asset("board-token", "whiteboard")
    await client.download_asset("image-token", "image")

    board_headers = next(
        headers for url, headers, _ in transport.requests if "/whiteboards/" in url
    )
    image_headers = next(headers for url, headers, _ in transport.requests if "/medias/" in url)
    assert board_headers["accept"] == "image/png"
    assert "accept" not in image_headers


@pytest.mark.asyncio
async def test_feishu_client_resolves_document_wiki_url_without_space_id() -> None:
    transport = RecordingTransport()
    settings = Settings(
        app_env="test",
        feishu_app_id="app-id",
        feishu_app_secret="app-secret-value",
        feishu_wiki_url="https://pnx.feishu.cn/wiki/document-node",
    )
    client = FeishuClient(settings, transport=transport)

    nodes = await client.list_nodes()

    assert [node["node_token"] for node in nodes] == ["document-node"]
    assert nodes[0]["obj_token"] == "document-id"
    assert client.source_url("document-node") == "https://pnx.feishu.cn/wiki/document-node"


def test_normalizer_rejects_unsafe_links_and_localizes_known_assets() -> None:
    image_id = uuid4()
    attachment_id = uuid4()
    board_id = uuid4()
    blocks = [
        {
            "block_id": "page",
            "block_type": 1,
            "children": ["heading", "text", "image", "board"],
        },
        {
            "block_id": "heading",
            "block_type": 4,
            "heading2": {
                "elements": [{"text_run": {"content": "准备工作", "text_element_style": {}}}]
            },
        },
        {
            "block_id": "text",
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "text_run": {
                            "content": "安全链接",
                            "text_element_style": {"link": {"url": "https://example.edu/guide"}},
                        }
                    },
                    {
                        "text_run": {
                            "content": "危险链接",
                            "text_element_style": {"link": {"url": "javascript:alert(1)"}},
                        }
                    },
                    {
                        "mention_doc": {
                            "title": "下一篇",
                            "token": "next-doc",
                            "url": "https://pnx.feishu.cn/docx/next-doc",
                        }
                    },
                    {
                        "file": {
                            "file_token": "inline-file-token",
                            "source_block_id": "inline-file-source",
                        }
                    },
                ]
            },
        },
        {
            "block_id": "image",
            "block_type": 27,
            "image": {"token": "image-token", "width": 800, "height": 600},
        },
        {
            "block_id": "board",
            "block_type": 43,
            "board": {"whiteboard_id": "board-token"},
        },
        {
            "block_id": "inline-file-source",
            "block_type": 23,
            "file": {"token": "inline-file-token", "name": "说明.pdf"},
        },
    ]

    references = discover_asset_references(blocks)
    normalized = normalize_document(
        blocks,
        assets={
            ("image-token", "image"): image_id,
            ("inline-file-token", "attachment"): attachment_id,
            ("board-token", "whiteboard"): board_id,
        },
        asset_names={
            ("image-token", "image"): "知识库图片.png",
            ("inline-file-token", "attachment"): "说明.pdf",
            ("board-token", "whiteboard"): "白板.png",
        },
        fallback_url="https://pnx.feishu.cn/wiki/source",
    )

    assert {(reference.token, reference.kind) for reference in references} == {
        ("image-token", "image"),
        ("inline-file-token", "attachment"),
        ("board-token", "whiteboard"),
    }
    assert normalized[0]["type"] == "heading"
    segments = normalized[1]["segments"]
    assert isinstance(segments, list)
    assert segments[0]["href"] == "https://example.edu/guide"
    assert "href" not in segments[1]
    assert segments[2]["document_token"] == "next-doc"
    assert segments[3]["text"] == "说明.pdf"
    assert segments[3]["href"] == (f"/api/v1/knowledge/assets/{attachment_id}/content")
    assert normalized[2]["asset_id"] == str(image_id)
    assert normalized[3]["asset_id"] == str(board_id)
    assert safe_href("http://example.edu") is None
    assert safe_href("javascript:alert(1)") is None


def test_normalizer_preserves_inline_and_display_equations() -> None:
    inline_latex = r"e^{i\pi}+1=0"
    display_latex = r"\int_0^\infty e^{-x^2}\,dx=\frac{\sqrt{\pi}}{2}"
    oversized_latex = "x" * 20_001
    blocks = [
        {
            "block_id": "page",
            "block_type": 1,
            "children": ["paragraph", "display-equation", "oversized-equation"],
        },
        {
            "block_id": "paragraph",
            "block_type": 2,
            "text": {
                "elements": [
                    {"text_run": {"content": "欧拉公式："}},
                    {"equation": {"content": inline_latex}},
                ]
            },
        },
        {
            "block_id": "display-equation",
            "block_type": 16,
            "equation": {
                "elements": [{"equation": {"content": display_latex}}],
            },
        },
        {
            "block_id": "oversized-equation",
            "block_type": 16,
            "equation": {
                "elements": [{"equation": {"content": oversized_latex}}],
            },
        },
    ]

    normalized = normalize_document(
        blocks,
        assets={},
        asset_names={},
        fallback_url="https://pnx.feishu.cn/wiki/source",
    )

    assert normalized[0]["type"] == "paragraph"
    assert normalized[0]["segments"] == [
        {
            "text": "欧拉公式：",
            "bold": False,
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "inline_code": False,
        },
        {
            "text": inline_latex,
            "bold": False,
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "inline_code": False,
            "equation": True,
        },
    ]
    assert normalized[1]["type"] == "equation"
    assert normalized[1]["segments"] == [
        {
            "text": display_latex,
            "bold": False,
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "inline_code": False,
            "equation": True,
        }
    ]
    assert normalized[2]["type"] == "equation"
    assert len(normalized[2]["segments"][0]["text"]) == 20_000


def test_normalizer_preserves_reference_metadata_and_merged_tables() -> None:
    attachment_id = uuid4()
    blocks = [
        {
            "block_id": "page",
            "block_type": 1,
            "children": ["text-link", "code", "callout", "file", "table"],
        },
        {
            "block_id": "text-link",
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "text_run": {
                            "content": "本地文档",
                            "text_element_style": {
                                "link": {"url": "https://pnx.feishu.cn/wiki/node-target"}
                            },
                        }
                    }
                ]
            },
        },
        {
            "block_id": "code",
            "block_type": 14,
            "code": {
                "elements": [{"text_run": {"content": "const pnx = true;"}}],
                "style": {"language": 63, "wrap": True},
            },
        },
        {
            "block_id": "callout",
            "block_type": 19,
            "callout": {
                "background_color": 12,
                "border_color": 5,
                "text_color": 6,
                "emoji_id": "bulb",
            },
            "children": ["callout-text"],
        },
        {
            "block_id": "callout-text",
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": "提示"}}]},
        },
        {
            "block_id": "file",
            "block_type": 23,
            "file": {"token": "file-token", "name": "资料.pdf"},
        },
        {
            "block_id": "table",
            "block_type": 31,
            "table": {
                "cells": ["cell-a", "cell-b", "cell-c"],
                "property": {
                    "row_size": 2,
                    "column_size": 2,
                    "merge_info": [{"row_span": 2}, {}, {}],
                },
            },
        },
        {
            "block_id": "cell-a",
            "block_type": 32,
            "children": ["cell-a-text"],
        },
        {
            "block_id": "cell-a-text",
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": "合并"}}]},
        },
        {
            "block_id": "cell-b",
            "block_type": 32,
            "children": ["cell-b-text"],
        },
        {
            "block_id": "cell-b-text",
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": "上"}}]},
        },
        {
            "block_id": "cell-c",
            "block_type": 32,
            "children": ["cell-c-text"],
        },
        {
            "block_id": "cell-c-text",
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": "下"}}]},
        },
    ]

    normalized = normalize_document(
        blocks,
        assets={("file-token", "attachment"): attachment_id},
        asset_names={("file-token", "attachment"): "资料.pdf"},
        fallback_url="https://pnx.feishu.cn/wiki/source",
        asset_sizes={("file-token", "attachment"): 4096},
        asset_media_types={("file-token", "attachment"): "application/pdf"},
    )

    link_segments = normalized[0]["segments"]
    assert isinstance(link_segments, list)
    assert link_segments[0]["document_token"] == "node-target"
    assert normalized[1]["language"] == "TypeScript"
    assert normalized[1]["wrap"] is True
    assert normalized[2]["background_color"] == 12
    assert normalized[2]["border_color"] == 5
    assert normalized[2]["text_color"] == 6
    assert normalized[2]["emoji_id"] == "bulb"
    assert normalized[3]["file_size"] == 4096
    assert normalized[3]["mime_type"] == "application/pdf"
    rows = normalized[4]["rows"]
    assert isinstance(rows, list)
    assert rows[0][0]["row_span"] == 2
    assert rows[0][0]["blocks"][0]["segments"][0]["text"] == "合并"
    assert len(rows[1]) == 1
    assert rows[1][0]["blocks"][0]["segments"][0]["text"] == "下"


def test_normalizer_skips_unlocalized_visuals_but_keeps_attachment_fallbacks() -> None:
    fallback_url = "https://pnx.feishu.cn/wiki/source"
    blocks = [
        {
            "block_id": "page",
            "block_type": 1,
            "children": ["image", "board", "file", "text"],
        },
        {
            "block_id": "image",
            "block_type": 27,
            "image": {"token": "missing-image"},
        },
        {
            "block_id": "board",
            "block_type": 43,
            "board": {"whiteboard_id": "missing-board"},
        },
        {
            "block_id": "file",
            "block_type": 23,
            "file": {"token": "missing-file", "name": "资料.pdf"},
        },
        {
            "block_id": "text",
            "block_type": 2,
            "text": {
                "elements": [
                    {
                        "file": {
                            "file_token": "missing-file",
                            "source_block_id": "file",
                        }
                    }
                ]
            },
        },
    ]

    normalized = normalize_document(
        blocks,
        assets={},
        asset_names={},
        fallback_url=fallback_url,
    )

    assert [block["type"] for block in normalized] == ["attachment", "paragraph"]
    assert normalized[0]["asset_id"] is None
    assert normalized[0]["fallback_url"] == fallback_url
    assert normalized[1]["segments"][0]["href"] == fallback_url


class RecordingKnowledgeSync:
    def __init__(self) -> None:
        self.run_ids: list[UUID] = []
        self.failed_run_ids: list[UUID] = []

    async def synchronize(self, run_id: UUID) -> None:
        self.run_ids.append(run_id)

    async def mark_failed(self, run_id: UUID, error: Exception) -> None:
        self.failed_run_ids.append(run_id)


class KnowledgeProcessorHarness(OutboxProcessor):
    def __init__(self, job: OutboxJob) -> None:
        self._job = job
        self.recording_sync = RecordingKnowledgeSync()
        self._knowledge_sync = self.recording_sync
        self.sent_ids: list[UUID] = []
        self.failed_ids: list[UUID] = []

    async def _claim(self, now: datetime) -> list[OutboxJob]:
        return [self._job]

    async def _mark_sent(self, job_id: UUID, now: datetime) -> None:
        self.sent_ids.append(job_id)

    async def _mark_failed(
        self,
        job_id: UUID,
        *,
        now: datetime,
        code: str,
        permanent: bool,
    ) -> None:
        self.failed_ids.append(job_id)


@pytest.mark.asyncio
async def test_outbox_dispatches_knowledge_sync_to_dedicated_processor() -> None:
    now = datetime.now(UTC)
    run_id = uuid4()
    job = OutboxJob(
        id=uuid4(),
        job_type="sync_knowledge",
        event_key=f"knowledge_sync:{run_id}",
        payload={"run_id": str(run_id)},
        secret_payload_ciphertext=None,
        status="processing",
        available_at=now,
        attempt_count=0,
        max_attempts=3,
        locked_by="worker",
        locked_at=now,
        last_error_code=None,
        last_error_summary=None,
        created_at=now,
        sent_at=None,
    )
    processor = KnowledgeProcessorHarness(job)

    assert await processor.run_once() == 1
    assert processor.recording_sync.run_ids == [run_id]
    assert processor.sent_ids == [job.id]
    assert processor.failed_ids == []
