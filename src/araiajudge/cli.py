from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Iterable

import click
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from araiajudge.artifacts import summarize_results_file, write_summary
from araiajudge.constants import DEFAULT_BASE_URL, DEFAULT_MODEL, VALID_DECISIONS
from araiajudge.docs import (
    count_sectionized_doc_files,
    doc_input_sha256,
    iter_sectionized_docs,
    iter_sectionized_docs_stream,
)
from araiajudge.jobs import prepare_doc_jobs, prepare_doc_jobs_stream
from araiajudge.runners import run_requests_mode
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
    result_path: Path,
    summary_path: Path,
    failures_path: Path,
    api_key_provided: bool,
) -> None:
    # Failures are written by run_requests_mode; remove stale file on success
    if stats.get("failures"):
        failures_path.write_text(json.dumps(stats["failures"], indent=2), encoding="utf-8")
    elif failures_path.exists():
        failures_path.unlink()

    expected_input_hashes = {}
    total_discovered = 0
    for doc in docs:
        expected_input_hashes[doc["source_path"]] = doc_input_sha256(doc)
        total_discovered += 1

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
    default="ARGO",
    show_default=True,
    help=(
        "ANL inference service preset. One of ARGO, ALCF-SOPHIA, ALCF-METIS, "
        "ALCF-MINERVA, or ANL-ASKSAGE. Overrides defaults for base URL and model."
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
    default=20000,
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
def agentic_judge_dataset(
    *,
    source: Path,
    anl_llm_service: str,
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
) -> None:
    # Resolve service preset
    service_key = (anl_llm_service or "ALCF-SOPHIA").upper()
    preset = _SERVICE_PRESETS.get(service_key, _SERVICE_PRESETS["ALCF-SOPHIA"])  # safe default

    resolved_base_url = base_url or preset["base_url"] or DEFAULT_BASE_URL
    resolved_model = model or preset.get("default_model") or DEFAULT_MODEL
    provider_style = preset["style"]  # "openai" or "argo"

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
        if provider_style == "openai" and not api_key:
            raise click.UsageError("Provide --api-key or set API_KEY/OPENAI_API_KEY.")
        if provider_style == "argo" and not argo_user:
            raise click.UsageError("Provide --argo-user or set ARGO_USER.")

    # Prepare documents and jobs
    parsed_keep_decisions = parse_keep_decisions(keep_decisions)
    rubric = prompt_path.read_text(encoding="utf-8")
    prompt_sha256 = sha256_text(rubric)

    discovered_count = count_sectionized_doc_files(source)
    click.echo(f"Scanning source: {discovered_count} candidate JSON files")

    docs_iter: Iterable[dict]
    docs_iter = iter_sectionized_docs_stream(source)
    if limit is not None:
        docs_iter = itertools.islice(docs_iter, limit)

    checkpoint_path = output_dir / "judge_checkpoint.json"
    checkpoint = load_json(checkpoint_path, {"completed_keys": []}) if resume else {"completed_keys": []}
    completed_keys = set(checkpoint.get("completed_keys", []))

    # Materialize the jobs list for requests
    docs_list = iter_sectionized_docs(source)
    if limit is not None:
        docs_list = docs_list[:limit]
    jobs = prepare_doc_jobs(
        docs=docs_list,
        rubric=rubric,
        prompt_sha256=prompt_sha256,
        model=resolved_model,
        base_url=resolved_base_url,
        max_input_chars=max_input_chars,
        completed_keys=completed_keys,
        resume=resume,
    )

    if dry_run:
        click.echo(f"Discovered documents: {discovered_count}")
        click.echo(f"Would judge documents: {len(jobs)}")
        for idx, job in enumerate(jobs[: min(5, len(jobs))], start=1):
            click.echo(f"\n--- Prompt sample {idx}: {job['doc']['source_path']} ---")
            click.echo(job["prompt"])
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "judge_checkpoint.json"
    result_path = output_dir / "judge_results.jsonl.gz"
    decision_csv_path = output_dir / "judge_decisions.csv"
    summary_path = output_dir / "judge_summary.json"
    failures_path = output_dir / "failures.json"

    with Progress(SpinnerColumn(), *Progress.get_default_columns(), TimeElapsedColumn()) as progress:
        stats = run_requests_mode(
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
            current_run_attempted=len(jobs),
            result_path=result_path,
            summary_path=summary_path,
            failures_path=failures_path,
            api_key_provided=bool(api_key),
        )
        progress.log("\n* Agentic judging complete.")
        progress.log(f"* Output directory: {output_dir}")
        progress.log(f"* Documents attempted: {len(jobs)}")
        progress.log(f"* Documents succeeded: {stats['succeeded']}")
        progress.log(f"* Documents failed: {stats['failed']}")
        progress.log(f"* Parse failures: {stats['parse_failures']}")
