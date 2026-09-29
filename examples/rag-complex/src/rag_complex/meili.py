"""Minimal Meilisearch REST client (httpx). One index per branch: `chunks_<branch>`."""
from __future__ import annotations

import re
import time

import httpx

SETTINGS = {
    "searchableAttributes": ["text", "heading_context"],
    "filterableAttributes": ["document_id", "page_start"],
}


class MeiliError(RuntimeError):
    def __init__(self, error: dict | None):
        error = error or {}
        super().__init__(error.get("message", "meilisearch task failed"))
        self.code = error.get("code")


def index_name(branch: str) -> str:
    return "chunks_" + re.sub(r"[^A-Za-z0-9_-]", "_", branch)


class Meili:
    def __init__(self, url: str, key: str, *, client: httpx.Client | None = None):
        self.http = client or httpx.Client(
            base_url=url, headers={"Authorization": f"Bearer {key}"}, timeout=60
        )

    def healthy(self) -> bool:
        try:
            return self.http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False

    def _wait(self, resp: httpx.Response) -> None:
        resp.raise_for_status()
        uid = resp.json()["taskUid"]
        while True:
            task = self.http.get(f"/tasks/{uid}").json()
            if task["status"] == "succeeded":
                return
            if task["status"] in ("failed", "canceled"):
                raise MeiliError(task.get("error"))
            time.sleep(0.05)

    def ensure_index(self, index: str) -> None:
        self._wait(self.http.patch(f"/indexes/{index}/settings", json=SETTINGS))

    def replace_document(self, index: str, document_id: str, docs: list[dict]) -> None:
        self._wait(self.http.post(f"/indexes/{index}/documents/delete",
                                  json={"filter": f"document_id = '{document_id}'"}))
        if docs:
            self._wait(self.http.post(f"/indexes/{index}/documents",
                                      params={"primaryKey": "id"}, json=docs))

    def search(self, index: str, q: str, limit: int) -> list[dict]:
        resp = self.http.post(f"/indexes/{index}/search", json={"q": q, "limit": limit})
        resp.raise_for_status()
        return resp.json()["hits"]

    def delete_index(self, index: str) -> None:
        try:
            self._wait(self.http.delete(f"/indexes/{index}"))
        except MeiliError as e:
            if e.code != "index_not_found":
                raise
