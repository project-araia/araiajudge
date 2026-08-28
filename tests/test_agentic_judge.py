from __future__ import annotations

import gzip
import json
from pathlib import Path

from click.testing import CliRunner

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
        assert summary["backends"]["ALCF-METIS"]["attempted"] == 2
        assert summary["backends"]["ALCF-METIS"]["succeeded"] == 2
        assert summary["backends"]["ALCF-MINERVA"]["attempted"] == 2
        assert summary["backends"]["ALCF-MINERVA"]["succeeded"] == 2
        assert summary["backends"]["ALCF-SOPHIA"]["attempted"] == 2
        assert summary["backends"]["ALCF-SOPHIA"]["succeeded"] == 2

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
        assert calls[0]["prompt"] == "Reply with OK."
        assert calls[1]["argo_user"] == "user1"
        assert calls[1]["model"] == "claudesonnet46"
        with gzip.open(output / "judge_results.jsonl.gz", "rt", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        assert rows[0]["decision"] == "relevant"
