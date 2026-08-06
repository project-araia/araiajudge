from __future__ import annotations

from araiajudge.docs import doc_input_sha256, job_key, job_shared_key
from araiajudge.prompting import build_judge_prompt


def prepare_doc_jobs_stream(
    *,
    docs,
    rubric: str,
    prompt_sha256: str,
    model: str,
    base_url: str,
    max_input_chars: int,
    completed_keys: set[str],
    resume: bool,
    stats: dict[str, int] | None = None,
    shared_completed_keys: set[str] | None = None,
):
    """Yield prepared jobs without retaining the corpus or prompts.

    Supports cross-session resume using shared_completed_keys (provider-agnostic).
    """
    for doc in docs:
        if stats is not None:
            stats["discovered"] = stats.get("discovered", 0) + 1
        input_sha256 = doc_input_sha256(doc)
        key = job_key(
            source_path=doc["source_path"],
            doc_id=doc["doc_id"],
            input_sha256=input_sha256,
            prompt_sha256=prompt_sha256,
            model=model,
            base_url=base_url,
        )
        shared_key = job_shared_key(
            source_path=doc["source_path"],
            doc_id=doc["doc_id"],
            input_sha256=input_sha256,
            prompt_sha256=prompt_sha256,
            model=model,
        )
        if resume and (key in completed_keys or (shared_completed_keys is not None and shared_key in shared_completed_keys)):
            if stats is not None:
                stats["resume_skipped"] = stats.get("resume_skipped", 0) + 1
            continue
        if stats is not None:
            stats["prepared"] = stats.get("prepared", 0) + 1
        yield {
            "key": key,
            "shared_key": shared_key,
            "doc": doc,
            "input_sha256": input_sha256,
            "prompt": build_judge_prompt(rubric, doc, max_input_chars),
        }
