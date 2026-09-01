from __future__ import annotations

import concurrent.futures
import random
import time
from collections import deque
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


BACKEND_RETRY_SECONDS = 60 * 60
MAX_TRANSIENT_JOB_ATTEMPTS = 24


class ProviderError(RuntimeError):
    def __init__(self, provider: str, response) -> None:
        self.status_code = response.status_code
        self.cloudflare_blocked = (
            response.status_code == 403
            and "cloudflare" in response.text.lower()
            and "text/html" in response.headers.get("Content-Type", "").lower()
        )
        diagnostics = []
        for header in ("Retry-After", "cf-ray"):
            if value := response.headers.get(header):
                diagnostics.append(f"{header}={value}")
        detail = response.text[:200]
        suffix = f" [{' '.join(diagnostics)}]" if diagnostics else ""
        super().__init__(f"{provider} {response.status_code}: {detail}{suffix}")


def is_transient_error(error: Exception) -> bool:
    """Return whether a request failure indicates temporary backend unavailability."""
    import requests

    if isinstance(error, requests.exceptions.RequestException):
        return True
    if isinstance(error, ProviderError):
        return error.cloudflare_blocked or error.status_code in TRANSIENT_STATUS_CODES
    return any(f" {status_code}:" in str(error) for status_code in TRANSIENT_STATUS_CODES)


def response_content(data: dict[str, Any]) -> str:
    if "choices" in data:
        content = data["choices"][0]["message"].get("content")
    else:
        content = data.get("response")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Provider returned an empty completion")
    return content


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
                raise ProviderError("OpenAI-compatible", response)
            data = response.json()
            # Prefer OpenAI-compatible schema; tolerate simple {"response": ...}
            if isinstance(data, dict) and ("choices" in data or "response" in data):
                return response_content(data)
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
                raise ProviderError("Argo", response)
            data = response.json()
            if isinstance(data, dict) and ("response" in data or "choices" in data):
                return response_content(data)
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
    max_tokens: int = 512,
) -> str:
    """Make a small request to validate provider connectivity and credentials."""
    probe_prompt = 'Return exactly this JSON: {"decision":"relevant","score":3,"rationale":"probe"}.'
    if provider == "argo":
        return argo_completion_with_retries(
            base_url=base_url,
            model=model,
            prompt=probe_prompt,
            argo_user=argo_user or "",
            max_tokens=max_tokens,
            timeout=timeout,
        )
    return chat_completion_with_retries(
        api_key=api_key or "",
        base_url=base_url,
        model=model,
        prompt=probe_prompt,
        max_tokens=max_tokens,
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
    backends: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    backend_configs = backends or [{
        "service": provider.upper(),
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "argo_user": argo_user,
    }]
    stats = {
        "succeeded": 0,
        "failed": 0,
        "parse_failures": 0,
        "decision_counts": {},
        "failures": [],
        "attempted": 0,
        "elapsed_seconds": 0.0,
        "backends": {
            backend["service"]: {
                "service": backend["service"],
                "base_url": backend["base_url"],
                "model": backend["model"],
                "attempted": 0,
                "succeeded": 0,
                "failed": 0,
            }
            for backend in backend_configs
        },
    }
    task = progress.add_task("[green]Judging documents", total=None)
    started_at = time.perf_counter()

    def call(job: dict[str, Any], backend: dict[str, Any]) -> tuple[dict[str, Any], str, dict[str, Any]]:
        if backend["provider"] == "argo":
            raw = argo_completion_with_retries(
                base_url=backend["base_url"],
                model=backend["model"],
                prompt=job["prompt"],
                argo_user=backend.get("argo_user") or "",
                max_tokens=max_tokens,
                timeout=timeout,
            )
        else:
            raw = chat_completion_with_retries(
                api_key=backend.get("api_key") or "",
                base_url=backend["base_url"],
                model=backend["model"],
                prompt=job["prompt"],
                max_tokens=max_tokens,
                timeout=timeout,
            )
        return job, raw, backend

    retry_jobs: deque[dict[str, Any]] = deque()
    transient_attempts: dict[str, int] = {}
    job_iter = iter(jobs)
    exhausted = False
    unavailable_until: dict[str, float] = {}
    backend_slots = [backend for backend in backend_configs for _ in range(concurrency)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(backend_slots)) as executor:
        pending: dict[concurrent.futures.Future, tuple[dict[str, Any], dict[str, Any]]] = {}
        available_slots = list(backend_slots)
        while retry_jobs or not exhausted or pending:
            now = time.monotonic()
            for service, retry_at in list(unavailable_until.items()):
                if now < retry_at:
                    continue
                backend = next(backend for backend in backend_configs if backend["service"] == service)
                try:
                    check_connection(
                        provider=backend["provider"],
                        api_key=backend.get("api_key"),
                        base_url=backend["base_url"],
                        model=backend["model"],
                        argo_user=backend.get("argo_user"),
                        timeout=timeout,
                        max_tokens=max_tokens,
                    )
                except Exception as error:
                    if is_transient_error(error):
                        unavailable_until[service] = now + BACKEND_RETRY_SECONDS
                        continue
                    raise RuntimeError(f"Backend {service} health check failed: {error}") from error
                del unavailable_until[service]
                progress.log(f"* Backend {service} recovered and returned to service.")

            while available_slots and (retry_jobs or not exhausted):
                backend = available_slots.pop()
                if backend["service"] in unavailable_until:
                    available_slots.insert(0, backend)
                    if all(slot["service"] in unavailable_until for slot in available_slots):
                        break
                    continue
                if retry_jobs:
                    job = retry_jobs.popleft()
                else:
                    try:
                        job = next(job_iter)
                    except StopIteration:
                        exhausted = True
                        available_slots.append(backend)
                        break
                pending[executor.submit(call, job, backend)] = (job, backend)

            if not pending:
                if retry_jobs or not exhausted:
                    next_retry = min(unavailable_until.values())
                    time.sleep(max(0.0, next_retry - time.monotonic()))
                continue

            done, _ = concurrent.futures.wait(
                pending,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                job, backend = pending.pop(future)
                backend_stats = stats["backends"][backend["service"]]
                backend_stats["attempted"] += 1
                try:
                    job, raw_response, backend = future.result()
                    parsed_response = parse_judge_response(raw_response)
                    row = make_result_row(
                        doc=job["doc"],
                        model=backend["model"],
                        base_url=backend["base_url"],
                        service=backend["service"],
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
                    backend_stats["succeeded"] += 1
                    if not row["parsed"]:
                        stats["parse_failures"] += 1
                    decision = row.get("decision")
                    if decision:
                        stats["decision_counts"][decision] = stats["decision_counts"].get(decision, 0) + 1
                    if copy_kept and row["parsed"] and decision in keep_decisions:
                        copy_kept_doc(job["doc"], source, output_dir)
                except Exception as error:
                    backend_stats["failed"] += 1
                    if is_transient_error(error):
                        unavailable_until[backend["service"]] = time.monotonic() + BACKEND_RETRY_SECONDS
                        transient_attempts[job["key"]] = transient_attempts.get(job["key"], 0) + 1
                        if transient_attempts[job["key"]] < MAX_TRANSIENT_JOB_ATTEMPTS:
                            retry_jobs.appendleft(job)
                            progress.log(
                                f"* Backend {backend['service']} is unavailable; retrying its work in one hour. Error: {error}"
                            )
                        else:
                            stats["failed"] += 1
                            stats["failures"].append(
                                {
                                    "doc_id": job["doc"]["doc_id"],
                                    "source_path": job["doc"]["source_path"],
                                    "service": backend["service"],
                                    "base_url": backend["base_url"],
                                    "error": f"{error} (transient attempts exhausted)",
                                    "created_at": now_iso(),
                                }
                            )
                    else:
                        stats["failed"] += 1
                        stats["failures"].append(
                            {
                                "doc_id": job["doc"]["doc_id"],
                                "source_path": job["doc"]["source_path"],
                                "service": backend["service"],
                                "base_url": backend["base_url"],
                                "error": str(error),
                                "created_at": now_iso(),
                            }
                        )
                        progress.log(f"* Error judging {job['doc']['source_path']} via {backend['service']}: {error}")
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
                available_slots.append(backend)

    return stats
