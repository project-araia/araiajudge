from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from araiajudge.constants import SKIP_JSON_FILENAMES
from araiajudge.util import normalize_ws, sha256_text


def count_sectionized_doc_files(source: Path) -> int:
    """Count candidate JSON files without opening their contents."""
    return sum(1 for path in source.rglob("*.json") if path.is_file() and path.name not in SKIP_JSON_FILENAMES)


def iter_sectionized_docs_stream(source: Path, stats: dict[str, int] | None = None):
    """Yield normalized sectionized docs one at a time from *source*."""
    for path in sorted(source.rglob("*.json")):
        if not path.is_file() or path.name in SKIP_JSON_FILENAMES:
            continue
        if stats is not None:
            stats["candidate_files"] = stats.get("candidate_files", 0) + 1
        rel_path = path.relative_to(source).as_posix()
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            if stats is not None:
                stats["malformed_files"] = stats.get("malformed_files", 0) + 1
            continue
        if not isinstance(data, dict):
            if stats is not None:
                stats["malformed_files"] = stats.get("malformed_files", 0) + 1
            continue

        title = normalize_ws(data.get("title"))
        abstract = normalize_ws(data.get("abstract"))
        sections: list[dict[str, str]] = []
        for key, value in data.items():
            if key in {"title", "abstract"} or key.startswith("_araiadoc_"):
                continue
            text = normalize_ws(value)
            if text:
                sections.append({"header": str(key), "text": text})

        if title or abstract or sections:
            yield {
                "doc_id": path.stem,
                "source_path": rel_path,
                "source_file": path,
                "title": title,
                "abstract": abstract,
                "sections": sections,
            }


def iter_sectionized_docs(source: Path) -> list[dict[str, Any]]:
    """Return normalized sectionized docs from nested JSON files under source."""
    return list(iter_sectionized_docs_stream(source))


def doc_input_sha256(doc: dict[str, Any]) -> str:
    stable = {
        "doc_id": doc["doc_id"],
        "source_path": doc["source_path"],
        "title": doc.get("title", ""),
        "abstract": doc.get("abstract", ""),
        "sections": doc.get("sections", []),
    }
    return sha256_text(json.dumps(stable, ensure_ascii=False, sort_keys=True))


def job_key(
    *,
    source_path: str,
    doc_id: str,
    input_sha256: str,
    prompt_sha256: str,
    model: str,
    base_url: str,
) -> str:
    raw = "\n".join([source_path, doc_id, input_sha256, prompt_sha256, model, base_url])
    return sha256_text(raw)


def job_shared_key(
    *,
    source_path: str,
    doc_id: str,
    input_sha256: str,
    prompt_sha256: str,
    model: str,
) -> str:
    """Provider-agnostic job key (excludes base_url) for cross-session dedup/locking."""
    raw = "\n".join([source_path, doc_id, input_sha256, prompt_sha256, model])
    return sha256_text(raw)
