"""Copy kept documents from judge_decisions.csv into output/kept/.

Reads source/output_dir from judge_summary.json, so it can be run with no
arguments against an existing run output dir:

    python copy_kept.py [OUTPUT_DIR] [--keep-decisions relevant,maybe]
"""

import argparse
import csv
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path, nargs="?",
                        help="Run output dir (defaults to judge_summary.json in cwd or .)")
    parser.add_argument("--keep-decisions", default="relevant,maybe")
    args = parser.parse_args()

    out_dir = args.output_dir or Path(".")
    summary_path = out_dir / "judge_summary.json"
    if summary_path.exists():
        import json
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        source = Path(summary["source"])
    else:
        summary = None
        source = None

    csv_path = out_dir / "judge_decisions.csv"
    if not csv_path.exists():
        raise SystemExit(f"Not found: {csv_path}")

    keep = {d.strip().lower() for d in args.keep_decisions.split(",")}
    kept_dir = out_dir / "kept"

    copied = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("decision") not in keep:
                continue
            rel = row["source_path"]
            if source is None:
                src = Path(rel)
            else:
                src = source / rel
            if not src.is_file():
                print(f"missing source: {src}")
                continue
            dest = kept_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1

    print(f"Copied {copied} kept files to {kept_dir}")


if __name__ == "__main__":
    main()
