import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.config import Settings

logger = logging.getLogger(__name__)
_FEISHU_API_ORIGIN = "https://open.feishu.cn"
_MAX_JSON_BYTES = 12 * 1024 * 1024
_MAX_PAGES = 200


class KnowledgeSyncError(Exception):
    def __init__(self, code: str, *, permanent: bool) -> None:
        super().__init__(code)
        self.code = code
        self.permanent = permanent


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class _WikiTarget:
    is_space: bool
    token: str


class HttpTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        max_bytes: int,
    ) -> HttpResponse: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> Request | None:
        return None


class UrllibHttpTransport:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirectHandler())

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        max_bytes: int,
    ) -> HttpResponse:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != "open.feishu.cn":
            raise KnowledgeSyncError("FEISHU_ENDPOINT_REJECTED", permanent=True)
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                payload = response.read(max_bytes + 1)
                if len(payload) > max_bytes:
                    raise KnowledgeSyncError("FEISHU_RESPONSE_TOO_LARGE", permanent=True)
                return HttpResponse(
                    status=int(response.status),
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=payload,
                )
        except HTTPError as exc:
            status = int(exc.code)
            raise KnowledgeSyncError(
                "FEISHU_RATE_LIMITED"
                if status == 429
                else "FEISHU_SERVICE_UNAVAILABLE"
                if status >= 500
                else "FEISHU_REQUEST_REJECTED",
                permanent=status not in {408, 425, 429} and status < 500,
            ) from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise KnowledgeSyncError("FEISHU_NETWORK_UNAVAILABLE", permanent=False) from exc


class FeishuClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        if not settings.feishu_knowledge_configured:
            raise KnowledgeSyncError("KNOWLEDGE_SYNC_NOT_CONFIGURED", permanent=True)
        self._settings = settings
        self._transport = transport or UrllibHttpTransport()
        self._tenant_token: str | None = None

    async def _request(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, str | int] | None = None,
        body: dict[str, object] | None = None,
        authenticated: bool = True,
        max_bytes: int = _MAX_JSON_BYTES,
        accept: str | None = "application/json",
    ) -> HttpResponse:
        url = _FEISHU_API_ORIGIN + path
        if query:
            url += "?" + urlencode(query)
        headers: dict[str, str] = {}
        if accept is not None:
            headers["accept"] = accept
        payload: bytes | None = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["content-type"] = "application/json; charset=utf-8"
        if authenticated:
            headers["authorization"] = "Bearer " + await self.tenant_token()
        return await asyncio.to_thread(
            self._transport.request,
            method=method,
            url=url,
            headers=headers,
            body=payload,
            max_bytes=max_bytes,
        )

    @staticmethod
    def _decode_json(response: HttpResponse) -> dict[str, Any]:
        if response.status < 200 or response.status >= 300:
            code = (
                "FEISHU_SERVICE_UNAVAILABLE"
                if response.status >= 500
                else "FEISHU_REQUEST_REJECTED"
            )
            raise KnowledgeSyncError(code, permanent=response.status < 500)
        try:
            decoded = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeSyncError("FEISHU_INVALID_RESPONSE", permanent=False) from exc
        if not isinstance(decoded, dict):
            raise KnowledgeSyncError("FEISHU_INVALID_RESPONSE", permanent=False)
        return {str(key): value for key, value in decoded.items()}

    @classmethod
    def _data(cls, response: HttpResponse) -> dict[str, Any]:
        payload = cls._decode_json(response)
        code = payload.get("code", 0)
        if code != 0:
            raise KnowledgeSyncError("FEISHU_API_REJECTED", permanent=True)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise KnowledgeSyncError("FEISHU_INVALID_RESPONSE", permanent=False)
        return {str(key): value for key, value in data.items()}

    async def tenant_token(self) -> str:
        if self._tenant_token is not None:
            return self._tenant_token
        response = await self._request(
            method="POST",
            path="/open-apis/auth/v3/tenant_access_token/internal",
            body={
                "app_id": self._settings.feishu_app_id,
                "app_secret": self._settings.feishu_app_secret.get_secret_value(),
            },
            authenticated=False,
        )
        payload = self._decode_json(response)
        token = payload.get("tenant_access_token")
        if payload.get("code", 0) != 0 or not isinstance(token, str) or not token:
            raise KnowledgeSyncError("FEISHU_AUTHENTICATION_FAILED", permanent=True)
        self._tenant_token = token
        return token

    async def _paged_items(
        self,
        *,
        path: str,
        query: dict[str, str | int],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        for _ in range(_MAX_PAGES):
            parameters = dict(query)
            if page_token:
                parameters["page_token"] = page_token
            data = self._data(await self._request(method="GET", path=path, query=parameters))
            raw_items = data.get("items")
            if isinstance(raw_items, list):
                items.extend(
                    {str(key): value for key, value in item.items()}
                    for item in raw_items
                    if isinstance(item, dict)
                )
            next_token = data.get("page_token")
            if not isinstance(next_token, str) or not next_token:
                if data.get("has_more") is True:
                    raise KnowledgeSyncError("FEISHU_INVALID_PAGINATION", permanent=False)
                return items
            if next_token == page_token:
                raise KnowledgeSyncError("FEISHU_INVALID_PAGINATION", permanent=False)
            page_token = next_token
        raise KnowledgeSyncError("FEISHU_PAGE_LIMIT_EXCEEDED", permanent=True)

    def _wiki_target(self) -> _WikiTarget:
        configured = self._settings.feishu_wiki_url
        if configured is None:
            raise KnowledgeSyncError("KNOWLEDGE_SYNC_NOT_CONFIGURED", permanent=True)
        parts = urlsplit(str(configured))
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) == 3 and segments[:2] == ["wiki", "space"]:
            return _WikiTarget(is_space=True, token=segments[2])
        if len(segments) == 2 and segments[0] == "wiki":
            return _WikiTarget(is_space=False, token=segments[1])
        raise KnowledgeSyncError("FEISHU_WIKI_URL_INVALID", permanent=True)

    async def _resolve_node(self, token: str) -> dict[str, Any]:
        data = self._data(
            await self._request(
                method="GET",
                path="/open-apis/wiki/v2/spaces/get_node",
                query={"token": token},
            )
        )
        raw_node = data.get("node")
        if not isinstance(raw_node, dict):
            raise KnowledgeSyncError("FEISHU_INVALID_RESPONSE", permanent=False)
        node = {str(key): value for key, value in raw_node.items()}
        node_token = node.get("node_token")
        object_token = node.get("obj_token")
        if node.get("obj_type") != "docx" or not isinstance(object_token, str) or not object_token:
            raise KnowledgeSyncError(
                "FEISHU_WIKI_NODE_UNSUPPORTED",
                permanent=True,
            )
        if not isinstance(node_token, str) or not node_token:
            node_token = token
        node["node_token"] = node_token
        node["_depth"] = 0
        node["_parent_node_token"] = None
        return node

    async def list_nodes(self) -> list[dict[str, Any]]:
        target = self._wiki_target()
        if not target.is_space:
            return [await self._resolve_node(target.token)]
        space_id = quote(target.token, safe="")
        path = f"/open-apis/wiki/v2/spaces/{space_id}/nodes"
        visited_parents: set[str] = set()
        seen_nodes: set[str] = set()
        result: list[dict[str, Any]] = []

        async def visit(parent_token: str | None, depth: int) -> None:
            if parent_token is not None:
                if parent_token in visited_parents:
                    return
                visited_parents.add(parent_token)
            query: dict[str, str | int] = {"page_size": 50}
            if parent_token is not None:
                query["parent_node_token"] = parent_token
            children = await self._paged_items(path=path, query=query)
            for child in children:
                node_token = child.get("node_token")
                if not isinstance(node_token, str) or not node_token or node_token in seen_nodes:
                    continue
                seen_nodes.add(node_token)
                normalized = dict(child)
                normalized["_depth"] = depth
                normalized["_parent_node_token"] = parent_token
                result.append(normalized)
                if len(result) > self._settings.feishu_knowledge_max_documents * 20:
                    raise KnowledgeSyncError("KNOWLEDGE_NODE_LIMIT_EXCEEDED", permanent=True)
                if child.get("has_child") is True:
                    await visit(node_token, depth + 1)

        await visit(None, 0)
        return result

    async def document_blocks(self, document_id: str) -> list[dict[str, Any]]:
        token = quote(document_id, safe="")
        return await self._paged_items(
            path=f"/open-apis/docx/v1/documents/{token}/blocks",
            query={"page_size": 500},
        )

    async def document_title(self, document_id: str) -> str:
        token = quote(document_id, safe="")
        data = self._data(
            await self._request(
                method="GET",
                path=f"/open-apis/docx/v1/documents/{token}",
            )
        )
        raw_document = data.get("document")
        if not isinstance(raw_document, dict):
            raise KnowledgeSyncError("FEISHU_INVALID_RESPONSE", permanent=False)
        title = raw_document.get("title")
        return title if isinstance(title, str) and title else "未命名文档"

    async def download_asset(self, token: str, kind: str) -> tuple[bytes, str | None]:
        safe_token = quote(token, safe="")
        path = (
            f"/open-apis/board/v1/whiteboards/{safe_token}/download_as_image"
            if kind == "whiteboard"
            else f"/open-apis/drive/v1/medias/{safe_token}/download"
        )
        response = await self._request(
            method="GET",
            path=path,
            max_bytes=self._settings.feishu_knowledge_max_asset_bytes,
            accept="image/png" if kind == "whiteboard" else None,
        )
        if response.status < 200 or response.status >= 300:
            raise KnowledgeSyncError("FEISHU_ASSET_UNAVAILABLE", permanent=response.status < 500)
        if not response.body:
            raise KnowledgeSyncError("FEISHU_ASSET_EMPTY", permanent=True)
        return response.body, response.headers.get("content-type")

    def source_url(self, node_token: str) -> str:
        configured = self._settings.feishu_wiki_url
        if configured is None:
            raise KnowledgeSyncError("KNOWLEDGE_SYNC_NOT_CONFIGURED", permanent=True)
        parts = urlsplit(str(configured))
        base = f"{parts.scheme}://{parts.netloc}/wiki/"
        return base + quote(node_token, safe="")
