DEFAULT_MODEL = "claudesonnet46"
DEFAULT_BASE_URL = "https://apps.inside.anl.gov/argoapi/api/v1/resource/chat/"
VALID_DECISIONS = {"relevant", "maybe", "irrelevant"}
SKIP_JSON_FILENAMES = {
    "batch_checkpoint.json",
    "duckdb_checkpoint.json",
    "failures.json",
    "filter_report.json",
    "judge_checkpoint.json",
    "judge_summary.json",
    "sectionization_report.json",
}
PRIORITY_SECTION_MARKERS = (
    "introduction",
    "abstract",
    "results",
    "results and discussion",
    "materials and methods",
    "methodology",
    "background",
    "overview",
    "summary",
    "conclusion",
    "discussion",
)
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
