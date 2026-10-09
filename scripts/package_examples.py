"""Package three licensed archival clips as explicit unsupported QA demonstrations."""

import json
import shutil
from pathlib import Path

from fencecoach.evidence_cache import prepare_evidence
from fencecoach.quality import assess_quality


def main():
    project = Path(__file__).resolve().parents[1]
    target = project / "examples/video"
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "purpose": "Archival QA/overlay demonstrations, not validated coaching inputs.",
        "clips": [],
    }
    for name, title in (
        ("jumpe_lunge", "MIT / Jump lunge — archival QA example"),
        ("parry_4_repost", "MIT / Parry and riposte — archival QA example"),
        ("jump_forward_jump_back", "MIT / Forward and backward footwork — archival QA example"),
    ):
        source = project / "data/training/mit-ocw" / name
        metadata = json.loads((source / "source.json").read_text(encoding="utf-8"))
        prepared = source / "prepared"
        output = target / name
        output.mkdir(exist_ok=True)
        shutil.copy2(source / "source.mp4", output / "source.video")
        shutil.copy2(source / "source.json", output / "source.json")
        for filename in ("preview.mp4", "poster.jpg", "contact-sheet.jpg"):
            shutil.copy2(prepared / filename, output / filename)
        result = json.loads((prepared / "result.json").read_text(encoding="utf-8"))
        result["quality_gate"] = assess_quality(result)
        result["source"] = "mit_ocw"
        result["source_credit"] = metadata["attribution"]
        result["warnings"].insert(
            0,
            "Preprocessed low-resolution archival demonstration. Unsupported for personal coaching; inspect overlays and QA reasons only.",
        )
        (output / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (output / "evidence.json").write_text(
            json.dumps(prepare_evidence(result)), encoding="utf-8"
        )
        manifest["clips"].append(
            {
                "id": name,
                "title": title,
                "sha256": metadata["sha256"],
                "bytes": metadata["bytes"],
                "license": metadata["license"],
                "license_url": metadata["license_url"],
                "source_page": metadata["source_page"],
                "attribution": metadata["attribution"],
                "qa": result["quality_gate"]["verdict"],
            }
        )
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"clips": len(manifest["clips"]), "purpose": manifest["purpose"]}))


if __name__ == "__main__":
    main()
