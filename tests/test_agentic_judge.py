from __future__ import annotations

import gzip
import json
from pathlib import Path

from click.testing import CliRunner
import pytest

import araiajudge.docs
import araiajudge.runners as runners
from araiajudge import agentic_judge_dataset
from araiajudge.cli import parse_keep_decisions
from araiajudge.docs import doc_input_sha256, iter_sectionized_docs
from araiajudge.parsing import parse_judge_response
from araiajudge.prompting import build_judge_prompt, truncate_document_text


def _write_sectionized_doc(path: Path, **fields: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields), encoding="utf-8")


def _make_job(doc_id: str, prompt: str) -> dict:
    return {
        "key": doc_id,
        "doc": {
            "doc_id": doc_id,
            "source_path": f"00/{doc_id}.json",
            "title": f"title-{doc_id}",
        },
        "input_sha256": "x",
        "prompt": prompt,
    }


class _Progress:
    def add_task(self, *args, **kwargs):
        return 0

    def update(self, *args, **kwargs):
        pass

    def log(self, *args, **kwargs):
        pass


class TestIterSectionizedDocs:
    def test_skips_malformed_json(self, tmp_path):
        source = tmp_path / "sectionized"
        source.mkdir()
        (source / "bad.json").write_text("{not json", encoding="utf-8")
        _write_sectionized_doc(source / "good.json", title="Grid")

        stats = {}
        docs = list(araiajudge.docs.iter_sectionized_docs_stream(source, stats))

        assert [doc["doc_id"] for doc in docs] == ["good"]
        assert stats["malformed_files"] == 1

    def test_walks_nested_json_and_skips_reports(self, tmp_path):
        source = tmp_path / "sectionized"
        _write_sectionized_doc(
            source / "00" / "123.json",
            title=" Grid resilience ",
            abstract="\nStorm impacts\n",
            introduction=" Utilities prepare for storms. ",
            empty="   ",
        )
        (source / "sectionization_report.json").write_text("{}", encoding="utf-8")
        (source / "failures.json").write_text("[]", encoding="utf-8")

        docs = iter_sectionized_docs(source)

        assert len(docs) == 1
        assert docs[0]["doc_id"] == "123"
        assert docs[0]["source_path"] == "00/123.json"
        assert docs[0]["title"] == "Grid resilience"
        assert docs[0]["abstract"] == "Storm impacts"
        assert docs[0]["sections"] == [{"header": "introduction", "text": "Utilities prepare for storms."}]


class TestPromptConstruction:
    def test_prompt_preserves_section_boundaries(self):
        doc = {
            "title": "Grid report",
            "abstract": "About outage recovery.",
            "sections": [{"header": "methods", "text": "We model restoration."}],
        }

        prompt = build_judge_prompt("Judge utility relevance.", doc, 1000)

        assert "Return ONLY valid JSON" in prompt
        assert "Title: Grid report" in prompt
        assert "Abstract:\nAbout outage recovery." in prompt
        assert "## methods\nWe model restoration." in prompt

    def test_truncation_prioritizes_intro_before_other_sections(self):
        doc = {
            "title": "T",
            "abstract": "A",
            "sections": [
                {"header": "methods", "text": "M" * 300},
                {"header": "introduction", "text": "I" * 50},
            ],
        }

        text = truncate_document_text(doc, 120)

        assert "## introduction" in text
        assert "## methods" not in text
        assert len(text) <= 120


class TestParseJudgeResponse:
    def test_parses_plain_json(self):
        parsed = parse_judge_response('{"decision":"relevant","score":3,"rationale":"Matches."}')

        assert parsed["parsed"] is True
        assert parsed["decision"] == "relevant"
        assert parsed["score"] == 3

    def test_parses_json_inside_fence(self):
        parsed = parse_judge_response('```json\n{"decision":"maybe","score":1,"rationale":"Partial."}\n```')

        assert parsed["parsed"] is True
        assert parsed["decision"] == "maybe"

    def test_invalid_json_is_parse_failure(self):
        parsed = parse_judge_response("not json")

        assert parsed["parsed"] is False
        assert parsed["decision"] is None
        assert parsed["error"]

    def test_invalid_decision_is_parse_failure(self):
        parsed = parse_judge_response('{"decision":"yes","score":3,"rationale":"No."}')

        assert parsed["parsed"] is False
        assert parsed["decision"] is None
        assert "invalid decision" in parsed["error"]

    def test_fractional_score_is_parse_failure(self):
        parsed = parse_judge_response('{"decision":"maybe","score":1.5,"rationale":"Partial."}')

        assert parsed["parsed"] is False
        assert parsed["score"] is None
        assert "invalid score" in parsed["error"]


class TestKeepDecisionsValidation:
    def test_keep_decisions_validation(self):
        assert parse_keep_decisions("relevant, maybe") == {"relevant", "maybe"}


class TestProviderResponses:
    def test_cloudflare_html_403_is_transient(self):
        class Response:
            status_code = 403
            text = "<html><title>Cloudflare Block Page</title></html>"
            headers = {"Content-Type": "text/html", "cf-ray": "abc123"}

        error = runners.ProviderError("OpenAI-compatible", Response())

        assert runners.is_transient_error(error)
        assert "cf-ray=abc123" in str(error)

    def test_json_403_is_not_transient(self):
        class Response:
            status_code = 403
            text = '{"error":"forbidden"}'
            headers = {"Content-Type": "application/json"}

        assert not runners.is_transient_error(runners.ProviderError("OpenAI-compatible", Response()))

    def test_rejects_empty_completion(self):
        with pytest.raises(RuntimeError, match="empty completion"):
            runners.response_content({"choices": [{"message": {"content": None}}]})

    def test_connection_probe_uses_configured_token_budget(self, monkeypatch):
        calls = []

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return "probe"

        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)

        assert runners.check_connection(
            provider="openai",
            api_key="secret",
            base_url="https://example.test/v1",
            model="model",
            argo_user=None,
            timeout=1,
            max_tokens=512,
        ) == "probe"
        assert calls[0]["max_tokens"] == 512


class TestBackendFailover:
    def test_reassigns_transient_backend_failures(self, tmp_path, monkeypatch):
        calls = []

        def fake_completion(**kwargs):
            calls.append(kwargs["base_url"])
            if kwargs["base_url"] == "https://down.test/v1":
                raise RuntimeError("OpenAI-compatible 503: unavailable")
            return '{"decision":"relevant","score":3,"rationale":"Matches."}'

        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)
        stats = runners.run_requests(
            jobs=[_make_job(str(index), "judge") for index in range(3)],
            source=tmp_path,
            output_dir=tmp_path / "output",
            provider="openai",
            api_key="secret",
            base_url="https://healthy.test/v1",
            model="model",
            prompt_sha256="prompt",
            max_tokens=10,
            timeout=1,
            concurrency=1,
            copy_kept=False,
            keep_decisions={"relevant"},
            completed_keys=set(),
            checkpoint_path=tmp_path / "output" / "checkpoint.json",
            result_path=tmp_path / "output" / "results.jsonl.gz",
            decision_csv_path=tmp_path / "output" / "decisions.csv",
            argo_user=None,
            progress=_Progress(),
            backends=[
                {
                    "service": "healthy",
                    "provider": "openai",
                    "api_key": "secret",
                    "base_url": "https://healthy.test/v1",
                    "model": "model",
                    "argo_user": None,
                },
                {
                    "service": "down",
                    "provider": "openai",
                    "api_key": "secret",
                    "base_url": "https://down.test/v1",
                    "model": "model",
                    "argo_user": None,
                },
            ],
        )

        assert stats["succeeded"] == 3
        assert stats["failed"] == 0
        assert stats["backends"]["down"]["failed"] == 1
        assert calls.count("https://down.test/v1") == 1
        assert calls.count("https://healthy.test/v1") == 3

    def test_restores_backend_after_successful_health_probe(self, tmp_path, monkeypatch):
        attempts = 0

        def fake_completion(**kwargs):
            nonlocal attempts
            if kwargs["prompt"].startswith("Return exactly this JSON:"):
                return "OK"
            attempts += 1
            if attempts == 1:
                raise RuntimeError("OpenAI-compatible 503: unavailable")
            return '{"decision":"relevant","score":3,"rationale":"Matches."}'

        monkeypatch.setattr(runners, "BACKEND_RETRY_SECONDS", 0)
        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)
        stats = runners.run_requests(
            jobs=[_make_job("1", "judge")],
            source=tmp_path,
            output_dir=tmp_path / "output",
            provider="openai",
            api_key="secret",
            base_url="https://backend.test/v1",
            model="model",
            prompt_sha256="prompt",
            max_tokens=10,
            timeout=1,
            concurrency=1,
            copy_kept=False,
            keep_decisions={"relevant"},
            completed_keys=set(),
            checkpoint_path=tmp_path / "output" / "checkpoint.json",
            result_path=tmp_path / "output" / "results.jsonl.gz",
            decision_csv_path=tmp_path / "output" / "decisions.csv",
            argo_user=None,
            progress=_Progress(),
        )

        assert attempts == 2
        assert stats["succeeded"] == 1
        assert stats["failed"] == 0


class TestAgenticJudgeCli:
    def test_connection_check_runs_before_requests(self, tmp_path, monkeypatch):
        source = tmp_path / "sectionized"
        output = tmp_path / "judged"
        prompt = tmp_path / "rubric.md"
        prompt.write_text("Judge utility relevance.", encoding="utf-8")
        _write_sectionized_doc(source / "00" / "1.json", title="Grid", abstract="Storms")
        checks = []
        responses = iter(['{"decision":"relevant","score":3,"rationale":"Matches."}'])

        def fake_check(**kwargs):
            checks.append(kwargs)
            return "OK"

        def fake_completion(**kwargs):
            return next(responses)

        monkeypatch.setattr("araiajudge.cli.check_provider_connection", fake_check)
        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(output),
                "--api-key",
                "secret",
                "--anl-llm-service",
                "ALCF-SOPHIA",
                "--concurrency",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        assert len(checks) == 1
        assert "Request configuration: 1 concurrent requests across 1 backend(s); up to 50000 document characters per request" in result.output
        assert "Connection check succeeded: OK" in result.output

    def test_dry_run_prints_prompts_without_api_key(self, tmp_path):
        source = tmp_path / "sectionized"
        prompt = tmp_path / "rubric.md"
        prompt.write_text("Judge utility relevance.", encoding="utf-8")
        _write_sectionized_doc(
            source / "00" / "1.json",
            title="Grid",
            abstract="Storms",
            intro="Utility text",
        )

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--dry-run",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Would judge documents: 1" in result.output
        assert "Title: Grid" in result.output
        assert "## intro" in result.output

    def test_rejects_output_inside_source(self, tmp_path):
        source = tmp_path / "sectionized"
        source.mkdir()
        prompt = tmp_path / "rubric.md"
        prompt.write_text("rubric", encoding="utf-8")

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(source / "judged"),
                "--dry-run",
            ],
        )

        assert result.exit_code != 0
        assert "--output-dir must be outside SOURCE" in result.output

    def test_request_mode_writes_results_and_copies_relevant(self, tmp_path, monkeypatch):
        source = tmp_path / "sectionized"
        output = tmp_path / "judged"
        prompt = tmp_path / "rubric.md"
        prompt.write_text("Judge utility relevance.", encoding="utf-8")
        _write_sectionized_doc(
            source / "00" / "1.json",
            title="Grid",
            abstract="Storms",
            intro="Utility text",
        )
        _write_sectionized_doc(source / "00" / "2.json", title="Other", abstract="None", intro="Other text")
        responses = iter(
            [
                "OK",
                '{"decision":"relevant","score":3,"rationale":"Matches."}',
                '{"decision":"irrelevant","score":0,"rationale":"No match."}',
            ]
        )

        def fake_completion(**kwargs):
            return next(responses)

        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(output),
                "--api-key",
                "secret",
                "--anl-llm-service",
                "ALCF-SOPHIA",
                "--concurrency",
                "1",
                "--copy-kept",
            ],
        )

        assert result.exit_code == 0, result.output
        with gzip.open(output / "judge_results.jsonl.gz", "rt", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        assert len(rows) == 2
        assert {row["decision"] for row in rows} == {"relevant", "irrelevant"}
        csv_text = (output / "judge_decisions.csv").read_text(encoding="utf-8")
        assert "doc_id,source_path,title,decision,score,rationale" in csv_text
        assert "relevant" in csv_text
        assert "irrelevant" in csv_text
        assert (output / "kept" / "00" / "1.json").exists()
        assert not (output / "kept" / "00" / "2.json").exists()
        summary = json.loads((output / "judge_summary.json").read_text(encoding="utf-8"))
        assert summary["api_key_provided"] is True
        assert summary["malformed_files"] == 0
        assert summary["resume_skipped"] == 0
        assert summary["throughput_docs_per_second"] > 0
        assert "secret" not in (output / "judge_summary.json").read_text(encoding="utf-8")
        checkpoint = json.loads((output / "judge_checkpoint.json").read_text(encoding="utf-8"))
        assert len(checkpoint["completed_keys"]) == 2

    def test_resume_summary_counts_prior_result_rows(self, tmp_path, monkeypatch):
        source = tmp_path / "sectionized"
        output = tmp_path / "judged"
        prompt = tmp_path / "rubric.md"
        prompt.write_text("Judge utility relevance.", encoding="utf-8")
        _write_sectionized_doc(
            source / "00" / "1.json",
            title="Grid",
            abstract="Storms",
            intro="Utility text",
        )
        _write_sectionized_doc(source / "00" / "2.json", title="Other", abstract="None", intro="Other text")

        responses = iter(
            [
                "OK",
                '{"decision":"relevant","score":3,"rationale":"Matches."}',
                "OK",
                '{"decision":"irrelevant","score":0,"rationale":"No match."}',
            ]
        )

        def fake_completion(**kwargs):
            return next(responses)

        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)
        first = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(output),
                "--api-key",
                "secret",
                "--anl-llm-service",
                "ALCF-SOPHIA",
                "--concurrency",
                "1",
                "--limit",
                "1",
            ],
        )
        assert first.exit_code == 0, first.output

        second = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(output),
                "--api-key",
                "secret",
                "--anl-llm-service",
                "ALCF-SOPHIA",
                "--concurrency",
                "1",
            ],
        )
        assert second.exit_code == 0, second.output

        summary = json.loads((output / "judge_summary.json").read_text(encoding="utf-8"))
        assert summary["total_discovered"] == 2
        assert summary["total_attempted"] == 2
        assert summary["total_succeeded"] == 2
        assert summary["decision_counts"] == {"irrelevant": 1, "relevant": 1}
        assert summary["current_run_attempted"] == 1
        assert summary["current_run_succeeded"] == 1

    def test_distributes_work_across_multiple_services(self, tmp_path, monkeypatch):
        source = tmp_path / "sectionized"
        output = tmp_path / "judged"
        prompt = tmp_path / "rubric.md"
        prompt.write_text("Judge utility relevance.", encoding="utf-8")
        for doc_id in range(1, 7):
            _write_sectionized_doc(
                source / "00" / f"{doc_id}.json",
                title=f"Grid {doc_id}",
                abstract="Storms",
            )

        checks = []
        calls = []

        def fake_check(**kwargs):
            checks.append(kwargs)
            return "OK"

        def fake_completion(**kwargs):
            calls.append(kwargs)
            return '{"decision":"relevant","score":3,"rationale":"Matches."}'

        monkeypatch.setattr("araiajudge.cli.check_provider_connection", fake_check)
        monkeypatch.setattr(runners, "chat_completion_with_retries", fake_completion)

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(output),
                "--api-key",
                "secret",
                "--anl-llm-service",
                "ALCF-SOPHIA",
                "--anl-llm-service",
                "ALCF-METIS",
                "--anl-llm-service",
                "ALCF-MINERVA",
                "--concurrency",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        assert {check["base_url"] for check in checks} == {
            "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1",
            "https://inference-api.alcf.anl.gov/resource_server/metis/api/v1",
            "https://inference-api.alcf.anl.gov/resource_server/minerva/api/v1",
        }
        assert {check["model"] for check in checks} == {
            "openai/gpt-oss-120b",
            "gpt-oss-120b",
        }
        assert len(calls) == 6
        assert {call["base_url"] for call in calls} == {
            "https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1",
            "https://inference-api.alcf.anl.gov/resource_server/metis/api/v1",
            "https://inference-api.alcf.anl.gov/resource_server/minerva/api/v1",
        }
        assert {call["model"] for call in calls} == {
            "openai/gpt-oss-120b",
            "gpt-oss-120b",
        }

        with gzip.open(output / "judge_results.jsonl.gz", "rt", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        assert len(rows) == 6
        assert {row["service"] for row in rows} == {
            "ALCF-SOPHIA",
            "ALCF-METIS",
            "ALCF-MINERVA",
        }
        summary = json.loads((output / "judge_summary.json").read_text(encoding="utf-8"))
        assert sum(backend["attempted"] for backend in summary["backends"].values()) == 6
        assert sum(backend["succeeded"] for backend in summary["backends"].values()) == 6
        assert all(backend["succeeded"] > 0 for backend in summary["backends"].values())

    def test_rejects_custom_url_with_multiple_services(self, tmp_path):
        source = tmp_path / "sectionized"
        source.mkdir()
        prompt = tmp_path / "rubric.md"
        prompt.write_text("rubric", encoding="utf-8")

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--dry-run",
                "--anl-llm-service",
                "ALCF-SOPHIA",
                "--anl-llm-service",
                "ALCF-METIS",
                "--base-url",
                "https://example.test/v1",
            ],
        )

        assert result.exit_code != 0
        assert "--base-url cannot be used with multiple" in result.output

    def test_request_mode_supports_argo_service(self, tmp_path, monkeypatch):
        source = tmp_path / "sectionized"
        output = tmp_path / "judged"
        prompt = tmp_path / "rubric.md"
        prompt.write_text("Judge utility relevance.", encoding="utf-8")
        _write_sectionized_doc(
            source / "00" / "1.json",
            title="Grid",
            abstract="Storms",
            intro="Utility text",
        )
        calls: list[dict] = []

        def fake_argo(**kwargs):
            calls.append(kwargs)
            return '{"decision":"relevant","score":3,"rationale":"Matches."}'

        monkeypatch.setattr(runners, "argo_completion_with_retries", fake_argo)

        result = CliRunner().invoke(
            agentic_judge_dataset,
            [
                str(source),
                "--prompt",
                str(prompt),
                "--output-dir",
                str(output),
                "--anl-llm-service",
                "ARGO",
                "--base-url",
                "https://apps.inside.anl.gov/argoapi/api/v1/resource/chat/",
                "--model",
                "claudesonnet46",
                "--argo-user",
                "user1",
                "--concurrency",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        assert len(calls) == 2
        assert calls[0]["prompt"].startswith("Return exactly this JSON:")
        assert calls[1]["argo_user"] == "user1"
        assert calls[1]["model"] == "claudesonnet46"
        with gzip.open(output / "judge_results.jsonl.gz", "rt", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        assert rows[0]["decision"] == "relevant"
