"""Run golden video regression and write BENCHMARKS.md. Optionally refresh poses."""

import argparse
import json
from pathlib import Path

from fencecoach.benchmarks import render_report, video_regression


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--no-sheets", action="store_true")
    parser.add_argument(
        "--set-baseline",
        action="store_true",
        help="Explicitly save this error-free engineering run as the regression baseline; does not validate technique.",
    )
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    manifest = json.loads((project / "evals/golden.json").read_text())
    directory = project / "data/evals"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "benchmark.json"
    data = json.loads(destination.read_text()) if destination.exists() else {}
    data["integration"] = {
        name: json.loads((directory / filename).read_text(encoding="utf-8"))
        for name, filename in (
            ("browser", "browser-smoke.json"),
            ("mcp", "mcp-smoke.json"),
            ("phoenix", "tracing-smoke.json"),
            ("packaging", "packaging.json"),
        )
        if (directory / filename).is_file()
    }
    baseline_path = project / "evals/video-baseline.json"
    previous = json.loads(baseline_path.read_text()) if baseline_path.exists() else []
    data["video"] = video_regression(project, manifest, args.reprocess, not args.no_sheets)
    data["video_diff"] = [
        {
            "clip": c["clip"],
            "before": p["quality"]["measurements"]["tracking_coverage"],
            "after": c["quality"]["measurements"]["tracking_coverage"],
        }
        for c in data["video"]
        for p in previous
        if c["clip"] == p["clip"] and "quality" in c and "quality" in p
    ]
    failures = [row["clip"] for row in data["video"] if "error" in row]
    failures += [row["clip"] for row in data["video_diff"] if row["after"] + 0.05 < row["before"]]
    data["video_regression_pass"] = not failures
    data["video_regression_failures"] = failures
    if args.set_baseline:
        if failures:
            raise SystemExit("Refusing to replace the baseline with a failing regression run.")
        baseline_path.write_text(json.dumps(data["video"], indent=2), encoding="utf-8")
    destination.write_text(json.dumps(data, indent=2), encoding="utf-8")
    (project / "BENCHMARKS.md").write_text(render_report(data), encoding="utf-8")
    print(
        json.dumps(
            {
                "clips": len(data["video"]),
                "supported": sum(
                    c.get("quality", {}).get("coaching_allowed", False) for c in data["video"]
                ),
                "report": "BENCHMARKS.md",
            }
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
