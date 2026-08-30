### ARAIAjudge

Judges a sectionized corpus produced by araiadoc's `section-dataset-s2orc` or `section-dataset-v2`.
Input documents are flat JSON files containing fields such as `title`, `abstract`, and body sections.

Documents are judged by the model as "relevant", "maybe", or "irrelevant" based on the prompt.

#### Examples

Primary run with ANL Argo access.

```bash
araiajudge data/all_weather_sectionized \
  --prompt prompts/electric_utility/araia_electric_utility_relevance.md \
  --argo-user $ARGO_USER
```

Run on ALCF's Sophia cluster. `gpt-oss-120b` is the default model.

```bash
araiajudge /path/to/sectionized/docs \
  --anl-llm-service ALCF-SOPHIA \
  --api-key $API_KEY \
  --output-dir results_v2
```

Distribute one run across multiple ALCF clusters. Repeat `--anl-llm-service`; `--concurrency`
is applied independently to each service. All services must use the same model.

```bash
araiajudge /path/to/sectionized/docs \
  --anl-llm-service ALCF-SOPHIA \
  --anl-llm-service ALCF-METIS \
  --anl-llm-service ALCF-MINERVA \
  --api-key $API_KEY \
  --concurrency 4 \
  --output-dir results_distributed
```

```bash
araiajudge /path/to/docs --model claudesonnet5 --concurrency 8
araiajudge /path/to/docs --dry-run --limit 5
araiajudge /path/to/docs --keep-decisions relevant,maybe --copy-kept
```

#### Full Usage

```bash
Usage: araiajudge [OPTIONS] SOURCE

Options:
  --anl-llm-service [ARGO|ALCF-SOPHIA|ALCF-METIS|ALCF-MINERVA|ANL-ASKSAGE]
                                   ANL inference service preset; repeat to distribute work across
                                   services.  [default: ARGO]
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
  --concurrency INTEGER           Concurrent requests per backend. [default: 4; x>=1]
  --max-tokens INTEGER            Maximum generated tokens.  [default: 512; x>=1]
  --timeout FLOAT                 Per-request timeout in seconds.  [default: 120.0; x>=1.0]
  --limit INTEGER                 Judge at most N documents. No limit by default.  [x>=1]
  --dry-run                       Build and print prompt samples without calling the model.
  --max-input-chars INTEGER       Maximum document payload characters included in each prompt.
                                  [default: 50000; x>=100]
  --copy-kept                     Copy documents with kept decisions into OUTPUT_DIR/kept.
  --keep-decisions TEXT           Comma-separated decisions copied by --copy-kept.  [default: relevant]
  --resume / --no-resume          Skip completed stable job keys from judge_checkpoint.json.
                                  [default: resume]
```

The command preserves source data and writes judgment artifacts outside the input directory:

```text
SOURCE_judged/
  judge_results.jsonl.gz                 # results for a regular run
  judge_decisions.csv                    # decisions for a regular run
  judge_summary.json                     # run summary, including backend counts
  judge_checkpoint.json                  # checkpoint for a regular run
  failures.json                          # failures for a regular run
  kept/
```

#### Service Presets
- ARGO (default): base `https://apps.inside.anl.gov/argoapi/api/v1/resource/chat/`; default model `claudesonnet46`.
- ALCF-SOPHIA: base `https://inference-api.alcf.anl.gov/resource_server/sophia/vllm/v1`; default model `openai/gpt-oss-120b`.
- ALCF-METIS: base `https://inference-api.alcf.anl.gov/resource_server/metis/api/v1`; default model `gpt-oss-120b`.
- ALCF-MINERVA: base `https://inference-api.alcf.anl.gov/resource_server/minerva/api/v1`; default model `gpt-oss-120b`.
- ANL-ASKSAGE: base `https://api.asksage.anl.gov/server/openai/v1`; default model `gpt_5.4_nano`. Use OpenAI-style models/options only when targeting AskSage (for now).

#### Result Schema and Resume
- Each result row includes doc_id, source_path, title, service, model, base URL, prompt and input hashes, decision, score, rationale, raw response, parse status, and timestamp.
- With multiple services, rows share one result stream and record the service that handled each document. Summaries include per-service attempted, succeeded, and failed counts.
- If a backend has an exhausted transient request failure, including a Cloudflare HTML block page, it is removed from scheduling and its work is reassigned to healthy backends. The backend is probed once per hour and automatically restored after a successful probe. If all backends are unavailable, the run waits for the next hourly probe. A job is retried at most 24 times across transient backend failures before being written to `failures.json`.
- JSON `401`/`403` responses remain permanent credential or authorization failures. Cloudflare block diagnostics include `Retry-After` and `cf-ray` headers when supplied.
- Resume is enabled by default. Completed keys include source path, document ID, input hash, prompt hash, model, and base URL.
- `--output-dir` must be outside `SOURCE` so the command cannot recurse into its own artifacts.

#### Copy-kept
- When `--copy-kept` is set, documents whose parsed decision is in `--keep-decisions` are copied to `OUTPUT_DIR/kept/`.
