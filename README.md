### ARAIAjudge

Judges a sectionized corpus produced by araiadoc's `section-dataset-s2orc` or `section-dataset-v2`.
Input documents are flat JSON files containing fields such as `title`, `abstract`, and body sections.

Documents are judged by the model as "relevant", "maybe", or "irrelevant" based on the prompt.

#### Examples

With ANL Argo access.

```bash
araiajudge data/all_weather_sectionized \
  --prompt prompts/climate/climate_resilience_relevance.md \
  --argo-user $ARGO_USER \
```

Run on ALCF's Sophia cluster. `gpt-oss-120b` is the default model.

```bash
araiajudge /path/to/sectionized/docs \
  --anl-llm-service ALCF-SOPHIA \
  --api-key $API_KEY \
  --output-dir results_v2
```

```bash
araiajudge /path/to/docs --model claudesonnet5 --concurrency 8
araiajudge /path/to/docs --dry-run --limit 5
araiajudge /path/to/docs --keep-decisions relevant,maybe --copy-kept
```

#### Usage

```bash
Usage: araiajudge [OPTIONS] SOURCE

Options:
  --anl-llm-service [ARGO|ALCF-SOPHIA|ALCF-METIS|ALCF-MINERVA|ANL-ASKSAGE]
                                  ANL inference service preset. Overrides defaults for base URL
                                  and model.  [default: ARGO]
  --model TEXT                    Chat model name. Defaults depend on --anl-llm-service.
  --base-url TEXT                 API base URL. Overrides the URL derived from --anl-llm-service.
  --api-key TEXT                  API key/token for OpenAI-compatible endpoints (ALCF/ASKSAGE).
                                  Also read from API_KEY or OPENAI_API_KEY.
  --argo-user TEXT                Argo user/token. Also read from ARGO_USER.
  --prompt FILE                   Rubric prompt file. Must emphasize a 0-3 score and corresponding
                                  relevance criteria.  [required]
  -o, --output-dir PATH
                                  Directory for araiajudge artifacts/work files (results,
                                  checkpoints, summary). Defaults to SOURCE_judged.
  --concurrency INTEGER           Concurrent requests.  [default: 4; x>=1]
  --max-tokens INTEGER            Maximum generated tokens.  [default: 512; x>=1]
  --timeout FLOAT                 Per-request timeout in seconds.  [default: 120.0; x>=1.0]
  --limit INTEGER                 Judge at most N documents. No limit by default.  [x>=1]
  --dry-run                       Build and print prompt samples without calling the model.
  --max-input-chars INTEGER       Maximum document payload characters included in each prompt.
                                  [default: 20000; x>=100]
  --copy-kept                     Copy documents with kept decisions into OUTPUT_DIR/kept.
  --keep-decisions TEXT           Comma-separated decisions copied by --copy-kept.  [default: relevant]
  --resume / --no-resume          Skip completed stable job keys from judge_checkpoint.json.
                                  [default: resume]
```

The command preserves source data and writes judgment artifacts outside the input directory:

```text
SOURCE_judged/
  judge_results.jsonl.gz
  judge_summary.json
  judge_checkpoint.json
  failures.json
  kept/
```

#### Service presets
- ARGO (default): base `https://apps.inside.anl.gov/argoapi/api/v1/resource/chat/`; default model `claudesonnet46`.
- ALCF-SOPHIA: base `https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1`; default model `openai/gpt-oss-120b`.
- ALCF-METIS: base `https://inference-api.alcf.anl.gov/resource_server/metis/api/v1`; default model `openai/gpt-oss-120b`.
- ALCF-MINERVA: base `https://inference-api.alcf.anl.gov/resource_server/minerva/api/v1`; default model `openai/gpt-oss-120b`.
- ANL-ASKSAGE: base `https://api.asksage.anl.gov/server/openai/v1`; default model `gpt_5.4_nano`. Use OpenAI-style models/options only when targeting AskSage (for now).

#### Result schema and resume
- Each result row in `judge_results.jsonl.gz` includes doc_id, source_path, title, model, base URL, prompt and input hashes, decision, score, rationale, raw response, parse status, and timestamp.
- Resume is enabled by default. Completed work is keyed by source path, document ID, input hash, prompt hash, model, and base URL, so changing any of these forces re-judgment.
- Summary artifacts include resume-skipped and malformed-file counts, elapsed time, and throughput.
- `--output-dir` must be outside `SOURCE` so the command cannot recurse into its own artifacts.

#### Copy-kept
- When `--copy-kept` is set, documents whose parsed decision is in `--keep-decisions` are copied to `OUTPUT_DIR/kept/`.
