from __future__ import annotations

import concurrent.futures
import random
import time
from pathlib import Path
from typing import Any, Iterable

from rich.progress import Progress

from araiajudge.artifacts import (
    append_decision_csv,
    append_result,
    copy_kept_doc,
    make_result_row,
    write_checkpoint,
)
from araiajudge.constants import TRANSIENT_STATUS_CODES
from araiajudge.parsing import parse_judge_response
from araiajudge.util import now_iso


def chat_completion_with_retries(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
    retries: int = 4,
) -> str:
    import requests

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            # Treat transient HTTP errors as retryable
            if response.status_code in TRANSIENT_STATUS_CODES and attempt < retries:
                time.sleep((2**attempt) + random.uniform(0, 0.5))
                continue
            if response.status_code >= 400:
                raise RuntimeError(f"OpenAI-compatible {response.status_code}: {response.text[:200]}")
            data = response.json()
            # Prefer OpenAI-compatible schema; tolerate simple {"response": ...}
            if isinstance(data, dict):
                if "choices" in data:
                    return str(data["choices"][0]["message"]["content"])
                if "response" in data:
                    return str(data["response"])
            raise RuntimeError("Unrecognized OpenAI-compatible response shape")
        except requests.exceptions.RequestException:
            if attempt >= retries:
                raise
            time.sleep((2**attempt) + random.uniform(0, 0.5))
    raise RuntimeError("unreachable retry loop")


def argo_completion_with_retries(
    *,
    base_url: str,
    model: str,
    prompt: str,
    argo_user: str,
    max_tokens: int,
    timeout: float,
    retries: int = 4,
) -> str:
    import requests

    payload = {
        "user": argo_user,
        "model": model,
        "system": "You are judging scientific document relevance. Return only valid JSON.",
        "prompt": [prompt],
        "stop": [],
        "temperature": 0.0,
        "max_completion_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {argo_user}"}
    for attempt in range(retries + 1):
        try:
            response = requests.post(base_url, json=payload, headers=headers, timeout=timeout)
            if response.status_code in TRANSIENT_STATUS_CODES and attempt < retries:
                time.sleep((2**attempt) + random.uniform(0, 0.5))
                continue
            if response.status_code != 200:
                raise RuntimeError(f"Argo {response.status_code}: {response.text[:200]}")
            data = response.json()
            if "response" in data:
                return str(data["response"])
            if "choices" in data:
                return str(data["choices"][0]["message"]["content"])
            raise RuntimeError(f"Unrecognized Argo response keys: {list(data.keys())}")
        except requests.exceptions.RequestException:
            if attempt >= retries:
                raise
            time.sleep((2**attempt) + random.uniform(0, 0.5))
    raise RuntimeError("unreachable retry loop")


def check_connection(
    *,
    provider: str,
    api_key: str | None,
    base_url: str,
    model: str,
    argo_user: str | None,
    timeout: float,
) -> str:
    """Make a small request to validate provider connectivity and credentials."""
    if provider == "argo":
        return argo_completion_with_retries(
            base_url=base_url,
            model=model,
            prompt="Reply with OK.",
            argo_user=argo_user or "",
            max_tokens=10,
            timeout=timeout,
        )
    return chat_completion_with_retries(
        api_key=api_key or "",
        base_url=base_url,
        model=model,
        prompt="Reply with OK.",
        max_tokens=10,
        timeout=timeout,
    )


def run_requests(
    *,
    jobs: Iterable[dict[str, Any]],
    source: Path,
    output_dir: Path,
    provider: str,
    api_key: str | None,
    base_url: str,
    model: str,
    prompt_sha256: str,
    max_tokens: int,
    timeout: float,
    concurrency: int,
    copy_kept: bool,
    keep_decisions: set[str],
    completed_keys: set[str],
    checkpoint_path: Path,
    result_path: Path,
    decision_csv_path: Path,
    argo_user: str | None,
    progress: Progress,
) -> dict[str, Any]:
    stats = {
        "succeeded": 0,
        "failed": 0,
        "parse_failures": 0,
        "decision_counts": {},
        "failures": [],
        "attempted": 0,
        "elapsed_seconds": 0.0,
    }
    task = progress.add_task("[green]Judging documents", total=None)
    started_at = time.perf_counter()

    def call(job: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if provider == "argo":
            raw = argo_completion_with_retries(
                base_url=base_url,
                model=model,
                prompt=job["prompt"],
                argo_user=argo_user or "",
                max_tokens=max_tokens,
                timeout=timeout,
            )
        else:
            raw = chat_completion_with_retries(
                api_key=api_key or "",
                base_url=base_url,
                model=model,
                prompt=job["prompt"],
                max_tokens=max_tokens,
                timeout=timeout,
            )
        return job, raw

    def drain_one(pending: dict[concurrent.futures.Future, dict[str, Any]]) -> None:
        done, _ = concurrent.futures.wait(
            pending,
            return_when=concurrent.futures.FIRST_COMPLETED,
        )
        for future in done:
            job = pending.pop(future)
            try:
                job, raw_response = future.result()
                parsed_response = parse_judge_response(raw_response)
                row = make_result_row(
                    doc=job["doc"],
                    model=model,
                    base_url=base_url,
                    prompt_sha256=prompt_sha256,
                    input_sha256=job["input_sha256"],
                    raw_response=raw_response,
                    parsed_response=parsed_response,
                )
                append_result(result_path, row)
                append_decision_csv(decision_csv_path, row)
                completed_keys.add(job["key"])
                write_checkpoint(
                    checkpoint_path,
                    completed_keys=completed_keys,
                    model=model,
                    base_url=base_url,
                    prompt_sha256=prompt_sha256,
                )
                stats["succeeded"] += 1
                if not row["parsed"]:
                    stats["parse_failures"] += 1
                decision = row.get("decision")
                if decision:
                    stats["decision_counts"][decision] = stats["decision_counts"].get(decision, 0) + 1
                if copy_kept and row["parsed"] and decision in keep_decisions:
                    copy_kept_doc(job["doc"], source, output_dir)
            except Exception as e:
                stats["failed"] += 1
                stats["failures"].append(
                    {
                        "doc_id": job["doc"]["doc_id"],
                        "source_path": job["doc"]["source_path"],
                        "error": str(e),
                        "created_at": now_iso(),
                    }
                )
                progress.log(f"* Error judging {job['doc']['source_path']}: {e}")
            stats["attempted"] += 1
            elapsed = time.perf_counter() - started_at
            stats["elapsed_seconds"] = elapsed
            rate = stats["attempted"] / elapsed if elapsed else 0.0
            progress.update(task, advance=1, description=(
                f"[green]Judging documents ({stats['attempted']} done, {rate:.2f}/s)"
            ))
            progress.log(
                f"* Progress: {stats['attempted']} done at {rate:.2f}/s; "
                f"decisions={dict(sorted(stats['decision_counts'].items()))}"
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        pending: dict[concurrent.futures.Future, dict[str, Any]] = {}
        job_iter = iter(jobs)
        exhausted = False
        max_inflight = concurrency * 2
        while not exhausted or pending:
            while not exhausted and len(pending) < max_inflight:
                try:
                    job = next(job_iter)
                except StopIteration:
                    exhausted = True
                    break
                pending[executor.submit(call, job)] = job
            if pending:
                drain_one(pending)
    return stats
