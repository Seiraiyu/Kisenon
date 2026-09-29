import json

import httpx
import pytest

from rag_complex.meili import Meili, MeiliError, index_name


def test_index_name_is_per_branch_and_sanitized():
    assert index_name("main") == "chunks_main"
    assert index_name("rag-exp-ab12cd") == "chunks_rag-exp-ab12cd"
    assert index_name("feat/x.y") == "chunks_feat_x_y"


def mock_meili(task_status="succeeded", task_error=None):
    requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        if req.url.path.startswith("/tasks/"):
            return httpx.Response(200, json={"status": task_status, "error": task_error})
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"hits": [{"id": "d-0"}]})
        return httpx.Response(202, json={"taskUid": len(requests)})

    client = httpx.Client(base_url="http://meili", transport=httpx.MockTransport(handler))
    return Meili("http://meili", "k", client=client), requests


def test_replace_document_deletes_by_filter_then_adds():
    meili, reqs = mock_meili()
    meili.replace_document("chunks_main", "abc", [{"id": "abc-0", "text": "t"}])
    calls = [(r.method, r.url.path) for r in reqs if not r.url.path.startswith("/tasks/")]
    assert calls == [
        ("POST", "/indexes/chunks_main/documents/delete"),
        ("POST", "/indexes/chunks_main/documents"),
    ]
    assert json.loads(reqs[0].content) == {"filter": "document_id = 'abc'"}
    assert reqs[2].url.params["primaryKey"] == "id"


def test_ensure_index_sets_searchable_and_filterable():
    meili, reqs = mock_meili()
    meili.ensure_index("chunks_x")
    assert (reqs[0].method, reqs[0].url.path) == ("PATCH", "/indexes/chunks_x/settings")
    assert json.loads(reqs[0].content)["filterableAttributes"] == ["document_id", "page_start"]


def test_delete_index_ignores_missing_index():
    meili, reqs = mock_meili("failed", {"code": "index_not_found", "message": "nope"})
    meili.delete_index("chunks_rag-exp-1")
    assert (reqs[0].method, reqs[0].url.path) == ("DELETE", "/indexes/chunks_rag-exp-1")


def test_failed_task_raises():
    meili, _ = mock_meili("failed", {"code": "invalid_document_id", "message": "bad id"})
    with pytest.raises(MeiliError, match="bad id"):
        meili.ensure_index("chunks_x")


def test_search_returns_hits():
    meili, reqs = mock_meili()
    assert meili.search("chunks_main", "q", 20) == [{"id": "d-0"}]
    assert json.loads(reqs[0].content) == {"q": "q", "limit": 20}
