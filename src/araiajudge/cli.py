from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Iterable

import click
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from araiajudge.artifacts import summarize_results_file, summarize_results_directory, write_summary
from araiajudge.constants import DEFAULT_BASE_URL, DEFAULT_MODEL, VALID_DECISIONS
from araiajudge.docs import (
    count_sectionized_doc_files,
    doc_input_sha256,
    iter_sectionized_docs,
    iter_sectionized_docs_stream,
)
from araiajudge.jobs import prepare_doc_jobs_stream
from araiajudge.runners import check_connection as check_provider_connection, run_requests
from araiajudge.util import load_json, sha256_text


# Service presets for ANL
_SERVICE_PRESETS = {
    "ARGO": {
        "style": "argo",
        "base_url": "https://apps.inside.anl.gov/argoapi/api/v1/resource/chat/",
        "default_model": "claudesonnet46",
    },
    "ALCF-SOPHIA": {
        "style": "openai",
        "base_url": "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1",
        "default_model": "openai/gpt-oss-120b",
    },
    "ALCF-METIS": {
        "style": "openai",
        "base_url": "https://inference-api.alcf.anl.gov/resource_server/metis/api/v1",
        "default_model": "openai/gpt-oss-120b",
    },
    "ALCF-MINERVA": {
        "style": "openai",
        "base_url": "https://inference-api.alcf.anl.gov/resource_server/minerva/api/v1",
        "default_model": "openai/gpt-oss-120b",
    },
    "ANL-ASKSAGE": {
        "style": "openai",
        "base_url": "https://api.asksage.anl.gov/server/openai/v1",
        "default_model": "gpt_5.4_nano",
    },
}


def parse_keep_decisions(value: str) -> set[str]:
    decisions = {item.strip().lower() for item in value.split(",") if item.strip()}
    invalid = decisions - VALID_DECISIONS
    if invalid:
        raise click.BadParameter(f"invalid decision(s): {', '.join(sorted(invalid))}")
    if not decisions:
        raise click.BadParameter("provide at least one decision")
    return decisions


def _write_judge_run_artifacts(
    *,
    stats: dict,
    docs: list[dict],
    source: Path,
    output_dir: Path,
    model: str,
    base_url: str,
    prompt_path: Path,
    prompt_sha256: str,
    keep_decisions: set[str],
    copy_kept: bool,
    current_run_attempted: int,
    malformed_files: int,
    resume_skipped: int,
    result_path: Path,
    summary_path: Path,
    failures_path: Path,
    api_key_provided: bool,
    aggregate_dir: Path | None = None,
) -> None:
    # Failures are written by run_requests; remove stale file on success
    if stats.get("failures"):
        failures_path.write_text(json.dumps(stats["failures"], indent=2), encoding="utf-8")
    elif failures_path.exists():
        failures_path.unlink()

    expected_input_hashes = {}
    total_discovered = 0
    for doc in docs:
        expected_input_hashes[doc["source_path"]] = doc_input_sha256(doc)
        total_discovered += 1

    if aggregate_dir is not None:
        cumulative = summarize_results_directory(
            aggregate_dir,
            model=model,
            prompt_sha256=prompt_sha256,
            expected_input_hashes=expected_input_hashes,
        )
    else:
        cumulative = summarize_results_file(
            result_path,
            model=model,
            base_url=base_url,
            prompt_sha256=prompt_sha256,
            expected_input_hashes=expected_input_hashes,
        )
    write_summary(
        summary_path,
        source=source,
        output_dir=output_dir,
        model=model,
        base_url=base_url,
        prompt_path=prompt_path,
        prompt_sha256=prompt_sha256,
        keep_decisions=keep_decisions,
        copy_kept=copy_kept,
        total_discovered=total_discovered,
        total_attempted=cumulative["succeeded"] + stats["failed"],
        total_succeeded=cumulative["succeeded"],
        total_failed=stats["failed"],
        decision_counts=cumulative["decision_counts"],
        parse_failures=cumulative["parse_failures"],
        current_run_attempted=current_run_attempted,
        current_run_succeeded=stats["succeeded"],
        current_run_failed=stats["failed"],
        current_run_decision_counts=stats["decision_counts"],
        current_run_parse_failures=stats["parse_failures"],
        retries=4,
        api_key_provided=api_key_provided,
        malformed_files=malformed_files,
        resume_skipped=resume_skipped,
        elapsed_seconds=stats.get("elapsed_seconds", 0.0),
        backends=stats.get("backends"),
    )


@click.command("araiajudge")
@click.argument(
    "source",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--anl-llm-service",
    type=click.Choice(list(_SERVICE_PRESETS.keys()), case_sensitive=False),
    multiple=True,
    default=("ARGO",),
    show_default=True,
    help=(
        "ANL inference service preset; repeat to distribute work across services. "
        "One of ARGO, ALCF-SOPHIA, ALCF-METIS, ALCF-MINERVA, or ANL-ASKSAGE."
    ),
)
@click.option(
    "--model",
    default=None,
    help="Chat model name. Defaults depend on --anl-llm-service.",
)
@click.option(
    "--base-url",
    default=None,
    help="API base URL. Overrides the URL derived from --anl-llm-service.",
)
@click.option(
    "--api-key",
    envvar=["API_KEY", "OPENAI_API_KEY"],
    help="API key/token for OpenAI-compatible endpoints (ALCF/ASKSAGE).",
)
@click.option(
    "--argo-user",
    envvar="ARGO_USER",
    help="Argo user/token (also used as Bearer token).",
)
@click.option(
    "--prompt",
    "prompt_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Rubric prompt file. Must emphasize a 0-3 score and corresponding relevance criteria."
    ),
)
@click.option(
    "--output-dir",
    "-o",
    "output_dir",
    type=click.Path(path_type=Path),
    help=(
        "Directory for araiajudge artifacts/work files (request results, checkpoints, summary). "
        "Defaults to SOURCE_judged."
    ),
)
@click.option("--concurrency", default=4, show_default=True, type=click.IntRange(1))
@click.option("--max-tokens", default=512, show_default=True, type=click.IntRange(1))
@click.option(
    "--timeout",
    default=120.0,
    show_default=True,
    type=click.FloatRange(1.0),
    help="Per-request timeout in seconds.",
)
@click.option("--limit", type=click.IntRange(1), help="Judge at most N documents. No limit by default.")
@click.option("--dry-run", is_flag=True, help="Build and print prompt samples without calling the model.")
@click.option(
    "--max-input-chars",
    default=50000,
    show_default=True,
    type=click.IntRange(100),
    help="Maximum document payload characters included in each prompt.",
)
@click.option("--copy-kept", is_flag=True, help="Copy documents with kept decisions into OUTPUT_DIR/kept.")
@click.option(
    "--keep-decisions",
    default="relevant",
    show_default=True,
    help="Comma-separated decisions copied by --copy-kept.",
)
@click.option(
    "--resume/--no-resume",
    default=True,
    show_default=True,
    help="Skip completed stable job keys from judge_checkpoint.json.",
)
@click.option(
    "--append-session",
    is_flag=True,
    help=(
        "Join an existing run; write per-session files and coordinate via per-doc locks. "
        "In this mode, summaries aggregate across all session result files. "
        "Session checkpoints are separate (judge_checkpoint.<session-id>.json)."
    ),
)
@click.option(
    "--session-id",
    default=None,
    help="Optional session label. Defaults to timestamp-pid-host.",
)
@click.option(
    "--lock-ttl",
    default=600,
    show_default=True,
    type=click.IntRange(1),
    help="Seconds after which a stale per-doc lock can be stolen.",
)
def agentic_judge_dataset(
    *,
    source: Path,
    anl_llm_service: tuple[str, ...],
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    argo_user: str | None,
    prompt_path: Path,
    output_dir: Path | None,
    concurrency: int,
    max_tokens: int,
    timeout: float,
    limit: int | None,
    dry_run: bool,
    max_input_chars: int,
    copy_kept: bool,
    keep_decisions: str,
    resume: bool,
    append_session: bool,
    session_id: str | None,
    lock_ttl: int,
) -> None:
    # Resolve service presets. Multiple services share one job stream and one model.
    service_keys = tuple(dict.fromkeys((service or "ARGO").upper() for service in anl_llm_service))
    if not service_keys:
        service_keys = ("ARGO",)
    if len(service_keys) > 1 and base_url:
        raise click.UsageError("--base-url cannot be used with multiple --anl-llm-service options.")

    resolved_model = model or _SERVICE_PRESETS[service_keys[0]].get("default_model") or DEFAULT_MODEL
    backends = []
    for service_key in service_keys:
        preset = _SERVICE_PRESETS[service_key]
        backend_model = model or preset.get("default_model") or DEFAULT_MODEL
        if backend_model != resolved_model:
            raise click.UsageError(
                "Multiple backends must use one model; provide a shared --model value."
            )
        backends.append({
            "service": service_key,
            "provider": preset["style"],
            "base_url": base_url or preset["base_url"] or DEFAULT_BASE_URL,
            "model": resolved_model,
            "api_key": api_key,
            "argo_user": argo_user,
        })
    resolved_base_url = backends[0]["base_url"]
    provider_style = backends[0]["provider"]

    # Output directory
    output_dir = output_dir or Path(str(source) + "_judged")
    source_resolved = source.resolve()
    output_resolved = output_dir.resolve(strict=False)
    if output_resolved == source_resolved or output_resolved.is_relative_to(source_resolved):
        raise click.UsageError(
            "--output-dir must be outside SOURCE so judging never mutates or rereads its input."
        )

    # Credentials validation
    if not dry_run:
        if any(backend["provider"] == "openai" for backend in backends) and not api_key:
            raise click.UsageError("Provide --api-key or set API_KEY/OPENAI_API_KEY.")
        if any(backend["provider"] == "argo" for backend in backends) and not argo_user:
            raise click.UsageError("Provide --argo-user or set ARGO_USER.")

    # Prepare documents and jobs
    parsed_keep_decisions = parse_keep_decisions(keep_decisions)
    rubric = prompt_path.read_text(encoding="utf-8")
    prompt_sha256 = sha256_text(rubric)

    discovered_count = count_sectionized_doc_files(source)
    click.echo(f"Scanning source: {discovered_count} candidate JSON files")

    discovery_stats: dict[str, int] = {}
    docs_iter: Iterable[dict] = iter_sectionized_docs_stream(source, discovery_stats)
    if limit is not None:
        docs_iter = itertools.islice(docs_iter, limit)

    # Determine session mode and id only when requested
    session_mode = bool(append_session or session_id)
    if session_mode and session_id is None:
        # ts-pid-host pattern without importing socket for minimal deps if not needed
        try:
            import os, socket, time as _t
            session_id = f"{int(_t.time())}-{os.getpid()}-{socket.gethostname().split('.')[0]}"
        except Exception:
            session_id = "session"

    # Shared-completed set across legacy and per-session result files
    shared_completed_keys: set[str] = set()

    checkpoint_path = output_dir / "judge_checkpoint.json"
    checkpoint = load_json(checkpoint_path, {"completed_keys": []}) if resume else {"completed_keys": []}
    completed_keys = set(checkpoint.get("completed_keys", []))

    # Validate/prepare append mode
    if append_session:
        if not output_dir.exists():
            raise click.UsageError("--append-session requires an existing output directory")
        # Validate model/prompt against summary if present
        summary_path = output_dir / "judge_summary.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if summary.get("prompt_sha256") != prompt_sha256 or summary.get("model") != resolved_model:
                    raise click.UsageError(
                        "--append-session requires matching model and prompt (prompt_sha256)."
                    )
            except Exception:
                pass

    # Build shared-completed by scanning all result files when in session mode
    if session_mode and output_dir.exists():
        expected_input_hashes = {}
        for doc in iter_sectionized_docs(source):
            expected_input_hashes[doc["source_path"]] = doc_input_sha256(doc)
        # Use summarize_results_directory logic to scan files but we need keys; implement inline here
        import gzip
        for path in sorted(output_dir.glob("judge_results*.jsonl.gz")):
            try:
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if row.get("model") != resolved_model or row.get("prompt_sha256") != prompt_sha256:
                            continue
                        sp = row.get("source_path"); ih = row.get("input_sha256")
                        if expected_input_hashes.get(sp) != ih:
                            continue
                        # For shared key, base_url is irrelevant; use docs.job_shared_key shape
                        from araiajudge.docs import job_shared_key
                        shared_completed_keys.add(
                            job_shared_key(
                                source_path=sp,
                                doc_id=row.get("doc_id", ""),
                                input_sha256=ih,
                                prompt_sha256=prompt_sha256,
                                model=resolved_model,
                            )
                        )
            except OSError:
                continue

    job_stats: dict[str, int] = {}
    jobs = prepare_doc_jobs_stream(
        docs=docs_iter,
        rubric=rubric,
        prompt_sha256=prompt_sha256,
        model=resolved_model,
        base_url=resolved_base_url,
        max_input_chars=max_input_chars,
        completed_keys=completed_keys,
        resume=resume,
        stats=job_stats,
        shared_completed_keys=shared_completed_keys,
    )

    if dry_run:
        samples: list[dict] = []
        would_judge = 0
        for job in jobs:
            would_judge += 1
            if len(samples) < 5:
                samples.append(job)
        click.echo(f"Discovered documents: {job_stats.get('discovered', 0)}")
        click.echo(f"Skipped completed documents: {job_stats.get('resume_skipped', 0)}")
        click.echo(f"Malformed JSON files skipped: {discovery_stats.get('malformed_files', 0)}")
        click.echo(f"Would judge documents: {would_judge}")
        for idx, job in enumerate(samples, start=1):
            click.echo(f"\n--- Prompt sample {idx}: {job['doc']['source_path']} ---")
            click.echo(job["prompt"])
        return

    for backend in backends:
        try:
            response = check_provider_connection(
                provider=backend["provider"],
                api_key=api_key,
                base_url=backend["base_url"],
                model=resolved_model,
                argo_user=argo_user,
                timeout=timeout,
            )
        except Exception as exc:
            raise click.UsageError(
                f"Connection check failed for {backend['service']}: {exc}"
            ) from exc
        if len(backends) == 1:
            click.echo(f"Connection check succeeded: {response.strip()[:80]}")
        else:
            click.echo(f"Connection check succeeded for {backend['service']}: {response.strip()[:80]}")

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "judge_summary.json"

    # Result/CSV/Checkpoint/Failures paths depend on sessionization mode
    if append_session or session_mode:
        result_path = output_dir / f"judge_results.{session_id}.jsonl.gz"
        decision_csv_path = output_dir / f"judge_decisions.{session_id}.csv"
        checkpoint_path = output_dir / f"judge_checkpoint.{session_id}.json"
        failures_path = output_dir / f"failures.{session_id}.json"
        lock_dir = output_dir / "locks"
    else:
        checkpoint_path = output_dir / "judge_checkpoint.json"
        result_path = output_dir / "judge_results.jsonl.gz"
        decision_csv_path = output_dir / "judge_decisions.csv"
        failures_path = output_dir / "failures.json"
        lock_dir = None

    with Progress(SpinnerColumn(), *Progress.get_default_columns(), TimeElapsedColumn()) as progress:
        stats = run_requests(
            jobs=jobs,
            source=source,
            output_dir=output_dir,
            provider="argo" if provider_style == "argo" else "openai",
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
            prompt_sha256=prompt_sha256,
            max_tokens=max_tokens,
            timeout=timeout,
            concurrency=concurrency,
            copy_kept=copy_kept,
            keep_decisions=parsed_keep_decisions,
            completed_keys=completed_keys,
            checkpoint_path=checkpoint_path,
            result_path=result_path,
            decision_csv_path=decision_csv_path,
            argo_user=argo_user,
            progress=progress,
            lock_dir=lock_dir,
            lock_ttl=lock_ttl,
            backends=backends,
        )

        _write_judge_run_artifacts(
            stats=stats,
            docs=list(iter_sectionized_docs(source)),
            source=source,
            output_dir=output_dir,
            model=resolved_model,
            base_url=resolved_base_url,
            prompt_path=prompt_path,
            prompt_sha256=prompt_sha256,
            keep_decisions=parsed_keep_decisions,
            copy_kept=copy_kept,
            current_run_attempted=stats["attempted"],
            malformed_files=discovery_stats.get("malformed_files", 0),
            resume_skipped=job_stats.get("resume_skipped", 0),
            result_path=result_path,
            summary_path=summary_path,
            failures_path=failures_path,
            api_key_provided=bool(api_key),
            aggregate_dir=output_dir if (append_session or session_mode) else None,
        )
        progress.log("\n* Agentic judging complete.")
        progress.log(f"* Output directory: {output_dir}")
        progress.log(f"* Documents attempted: {stats['attempted']}")
        progress.log(f"* Documents succeeded: {stats['succeeded']}")
        progress.log(f"* Documents failed: {stats['failed']}")
        progress.log(f"* Parse failures: {stats['parse_failures']}")
        progress.log(f"* Resume-skipped documents: {job_stats.get('resume_skipped', 0)}")
        progress.log(f"* Malformed JSON files skipped: {discovery_stats.get('malformed_files', 0)}")
        elapsed = stats.get("elapsed_seconds", 0.0)
        progress.log(f"* Throughput: {stats['attempted'] / elapsed if elapsed else 0.0:.2f} docs/s")
