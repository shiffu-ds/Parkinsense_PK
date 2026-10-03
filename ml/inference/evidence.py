"""Opt-in, versioned approved-document retrieval. Empty by default."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ApprovedKnowledgeBase:
    def __init__(self, path: str | Path | None = None):
        self.documents: list[dict[str, Any]] = []
        if path is None:
            return
        source = Path(path)
        if not source.is_file() or source.stat().st_size > 1_000_000:
            raise ValueError("Approved knowledge-base JSON must exist and be under 1 MB.")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("documents"), list):
            raise ValueError("Unsupported approved knowledge-base schema.")
        required = {"id", "title", "version", "approved_by", "approval_date", "source_url", "content"}
        for document in payload["documents"]:
            if document.get("approved") is not True:
                continue
            if not required <= set(document) or any(not isinstance(document[key], str) or not document[key].strip() for key in required):
                raise ValueError("Approved documents require identity, version, source, content and approval metadata.")
            if urlparse(document["source_url"]).scheme != "https":
                raise ValueError("Approved evidence source URLs must use HTTPS.")
            if len(document["content"]) > 100_000:
                raise ValueError("Approved evidence document is too long.")
            self.documents.append(document)

    def retrieve(self, query: str, limit: int = 3) -> list[dict[str, str]]:
        if not isinstance(query, str) or len(query) > 5000 or not 1 <= limit <= 5:
            raise ValueError("Evidence queries require text under 5,000 characters and a limit from 1 to 5.")
        tokens = set(re.findall(r"\w+", query.lower()))
        ranked = []
        for document in self.documents:
            terms = set(re.findall(r"\w+", (document["title"] + " " + document["content"]).lower()))
            overlap = len(tokens & terms)
            if overlap:
                ranked.append((overlap, document))
        ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return [{key: document[key] for key in ["id", "title", "version", "approved_by", "approval_date", "source_url"]}
                | {"excerpt": document["content"][:600], "retrieval_method": "keyword_overlap_1.0"}
                for _, document in ranked[:limit]]
