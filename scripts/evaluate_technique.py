"""Audit every saved clip with cached poses, phase medians, and evidence frames.

Source analyses and saved reviews are unchanged. Human technique text is excluded;
submitted timing bookmarks may supply reviewed phase anchors.
"""

import argparse
import hashlib
import html
import json
from datetime import UTC, datetime
from pathlib import Path

from fencecoach.feedback_learning import corrected_windows
from fencecoach.repository import Repository
from fencecoach.settings import settings
from fencecoach.technique import evaluate_lunges
from fencecoach.video_jobs import VideoJobs
from fencecoach.video_pipeline import refresh_cached_proposals


def evidence_sheet(directory, evaluation, destination):
    import av
    from PIL import Image, ImageDraw

    targets = sorted(
        {r["selected_frame_ms"] for r in evaluation["reps"] if "selected_frame_ms" in r}
    )
    if not targets or not (directory / "preview.mp4").is_file():
        return None
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    poses = {f["time_ms"]: f for f in result.get("frames", [])}
    snapshots, index = {}, 0
    with av.open(str(directory / "preview.mp4")) as container:
        for frame in container.decode(video=0):
            if frame.pts is None:
                continue
            t = round(float(frame.pts * frame.time_base) * 1000)
            if index < len(targets) and t >= targets[index]:
                snapshots[targets[index]] = frame.to_image()
                index += 1
                if index == len(targets):
                    break
    reps = [r for r in evaluation["reps"] if r.get("selected_frame_ms") in snapshots]
    if not reps:
        return None
    sheet = Image.new("RGB", (1440, ((len(reps) + 2) // 3) * 320), "#151719")
    draw = ImageDraw.Draw(sheet)
    bones = (
        (11, 12),
        (11, 23),
        (12, 24),
        (23, 24),
        (11, 13),
        (13, 15),
        (12, 14),
        (14, 16),
        (23, 25),
        (25, 27),
        (24, 26),
        (26, 28),
    )
    for number, rep in enumerate(reps):
        time = rep["selected_frame_ms"]
        pixels = snapshots[time].copy()
        pixels.thumbnail((480, 270))
        x, y = (
            number % 3 * 480 + (480 - pixels.width) // 2,
            number // 3 * 320 + (270 - pixels.height) // 2,
        )
        sheet.paste(pixels, (x, y))
        landmarks = poses[time].get("landmarks", [])
        if len(landmarks) == 33:
            for a, b in bones:
                if min(*landmarks[a][3:5], *landmarks[b][3:5]) >= 0.7:
                    pa = x + landmarks[a][0] * pixels.width, y + landmarks[a][1] * pixels.height
                    pb = x + landmarks[b][0] * pixels.width, y + landmarks[b][1] * pixels.height
                    draw.line((pa, pb), fill="#78ecba", width=2)
        origin = number % 3 * 480 + 8, number // 3 * 320 + 277
        draw.text(
            origin,
            f"Rep {rep['rep_number']} | pose {time / 1000:.3f}s | {rep['status']}",
            fill="white",
        )
        draw.text(
            (origin[0], origin[1] + 17),
            "Phase evidence; 2D pose accuracy is not independently verified",
            fill="#d2d5da",
        )
    sheet.save(destination, quality=90)
    return destination.name


def write_reports(rows, destination):
    lines = [
        "# Cross-clip analysis audit",
        "",
        f"Generated {datetime.now(UTC).isoformat()}",
        "",
        "Counts are movement proposals, not independently verified gesture accuracy. Related uploads and trimmed versions are not independent validation recordings. Human technique text was excluded.",
        "",
        "| Recording | Stored / refreshed cycles | Intervals / geometry available | Flags / suppressed | Status |",
        "|---|---:|---:|---:|---|",
    ]
    sections = []
    for row in rows:
        if "error" in row:
            lines.append(f"| {row['title']} | — | — | — | Error: {row['error']} |")
            continue
        lines.append(
            f"| {row['title']} | {row['stored_automatic_count']} / {row['refreshed_automatic_count']} | {row['reps']} / {row['geometry_reps']} | {row['flags']} / {row['suppressed_flags']} | {row['status']} |"
        )
        escape = html.escape
        details = []
        for rep in row["evaluation"]["reps"]:
            phases = []
            for name, phase in rep.get("phases", {}).items():
                measurements = "".join(
                    f"<tr><td>{escape(key.replace('_', ' '))}</td><td>{m['value']} {m['unit']}</td><td>{m['sample_count']}</td></tr>"
                    for key, m in phase["measurements"].items()
                    if key != "signed_torso_tilt"
                )
                phases.append(
                    f"<details><summary>{escape(name.replace('_', ' '))} · {phase['start_ms'] / 1000:.3f}–{phase['end_ms'] / 1000:.3f}s</summary><button data-seek='{phase['representative_ms'] / 1000}'>Jump to phase</button><p>{escape(phase['method'])}</p><table><tr><th>Measurement</th><th>Phase median</th><th>Samples</th></tr>{measurements}</table></details>"
                )
            observations = "".join(
                f"<p><b>{escape(f['observation'])}</b> {escape(f['cue'])}</p>"
                for f in rep["findings"]
            )
            gaps = "".join(f"<li>{escape(note)}</li>" for note in rep["unavailable"])
            details.append(
                f"<details><summary>Rep {rep['rep_number']} · {escape(rep['status'].replace('_', ' '))}</summary>{observations}{''.join(phases)}<ul>{gaps}</ul></details>"
            )
        sheet = (
            f"<img src='/api/videos/technique-audit/assets/{row['contact_sheet']}' alt='Actual per-rep evidence frames and pose overlays'>"
            if row.get("contact_sheet")
            else ""
        )
        sections.append(
            f"<section><h2>{escape(row['title'])}</h2><p>{escape(row['status'].replace('_', ' '))} · cycles {row['stored_automatic_count']} → {row['refreshed_automatic_count']}</p><p>{escape(row.get('reason') or '')}</p><video controls preload='metadata' src='/api/videos/{row['job_id']}/preview'></video>{sheet}{''.join(details)}</section>"
        )
    lines += [
        "",
        "Each measurement is summarized inside its rep phase. A lunge hold must be observed; otherwise the finish neighborhood is explicitly labeled. Recovery peak refers to the deepest sampled rear-knee bend, not a validated optimal position.",
        "",
        "Saved review bookmarks remain unchanged. Refreshed proposals use the new guard calibration without pose inference. Missing geometry is unavailable even when timing bookmarks exist. Low-resolution/multiple-person rejection gates remain in effect. No technique accuracy or event F1 is claimed.",
        "",
    ]
    (destination / "report.md").write_text("\n".join(lines), encoding="utf-8")
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Flèche analysis audit</title><style>body{background:#111315;color:#f1f2f4;font:16px/1.5 system-ui;margin:0 auto;padding:24px;max-width:1100px}section{border:1px solid #3c4047;padding:20px;border-radius:12px;margin:24px 0}video{display:block;width:100%;max-height:520px;object-fit:contain;background:#000}img{width:100%;margin:16px 0}details{border-top:1px solid #3c4047;padding:12px 0}summary{cursor:pointer}button{background:#b82636;color:white;border:0;padding:10px 14px;border-radius:6px;margin:10px 0;cursor:pointer}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px;border-bottom:1px solid #333}h1,h2{line-height:1.2}</style><h1>Cross-clip analysis audit</h1><p>Per-phase medians, automatic movement proposals, and actual evidence frames. These are provisional geometry checks. Related uploads are not independent validation data.</p>"""
    page += "".join(sections)
    page += """<script>document.addEventListener('click',e=>{const b=e.target.closest('button[data-seek]');if(b){const v=b.closest('section').querySelector('video');v.pause();v.currentTime=Number(b.dataset.seek)}})</script></html>"""
    (destination / "report.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=settings.fencecoach_video_dir.parent / "technique-evaluations",
    )
    parser.add_argument("--contact-sheets", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = VideoJobs(settings.fencecoach_db_path, settings.fencecoach_video_dir)
    repo = Repository(settings.fencecoach_db_path)
    summary = []
    for job in jobs.list(limit=None):
        directory = jobs.directory / job["job_id"]
        path = directory / "result.json"
        if not path.is_file() or job["status"] not in {"completed", "review_ready"}:
            continue
        row = {"job_id": job["job_id"], "title": job["title"]}
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            refreshed = refresh_cached_proposals(result, job.get("capture_profile", {}))
            windows = job.get("reviewed_windows") or refreshed["candidates"]
            basis = (
                "saved_review" if job.get("reviewed_windows") else "refreshed_automatic_proposals"
            )
            if job.get("session_id"):
                feedback = repo.coaching_context(job["session_id"])["reviewed_feedback"]
                if feedback:
                    windows = corrected_windows(feedback, windows)
                    basis = "submitted_timing_bookmarks"
            evaluation = evaluate_lunges(refreshed, windows, job.get("capture_profile", {}))
            with (directory / "source.video").open("rb") as file:
                source_hash = hashlib.file_digest(file, "sha256").hexdigest()
            row.update(
                source_sha256=source_hash,
                analysis_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                status=evaluation["status"],
                window_basis=basis,
                stored_automatic_count=len(result.get("candidates", [])),
                refreshed_automatic_count=len(refreshed["candidates"]),
                guard_calibration=refreshed["guard_calibration"],
                reps=len(evaluation["reps"]),
                geometry_reps=sum(r.get("geometry_available", False) for r in evaluation["reps"]),
                flags=len(evaluation["findings"]),
                suppressed_flags=len(evaluation["suppressed_findings"]),
                reason=evaluation.get("reason"),
                human_technique_feedback_used=False,
                evaluation=evaluation,
            )
            if args.contact_sheets:
                row["contact_sheet"] = evidence_sheet(
                    directory, evaluation, args.output / f"{job['job_id']}.jpg"
                )
            (args.output / f"{job['job_id']}.json").write_text(
                json.dumps(row, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            row["error"] = str(exc)
        summary.append(row)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_reports(summary, args.output)
    print(
        json.dumps(
            {
                "recordings": len(summary),
                "unique_source_files": len(
                    {r["source_sha256"] for r in summary if "source_sha256" in r}
                ),
                "errors": sum("error" in r for r in summary),
                "report": str(args.output / "report.md"),
            },
            indent=2,
        )
    )
    for row in summary:
        print(
            json.dumps(
                {
                    k: v
                    for k, v in row.items()
                    if k
                    in {
                        "job_id",
                        "title",
                        "status",
                        "stored_automatic_count",
                        "refreshed_automatic_count",
                        "geometry_reps",
                        "reps",
                        "flags",
                        "suppressed_flags",
                        "error",
                    }
                }
            )
        )


if __name__ == "__main__":
    main()
