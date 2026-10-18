"""Recover only two historical source files from this task's patch journal.

No historical shell commands are executed. All patch hunks must match; the
result is subsequently checked against all 56 recorded pre-call packets.
"""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = (
    Path.home()
    / ".codex/sessions/2026/10/14/rollout-2026-10-14T00-43-55-01a138b9-5e3f-75f3-8512-f968ba7825ec.jsonl"
)
OUT = ROOT / "evals/next_phase/baseline_source"
NAMES = {"turn_packet.py", "core_packet.py"}


def replace_hunk(source, old, new):
    before, after = "\n".join(old) + "\n", "\n".join(new) + "\n"
    if before in source:
        return source.replace(before, after, 1)
    # Ruff changed whitespace/line wrapping between some recorded patches.
    positions = [i for i, char in enumerate(source) if not char.isspace()]
    compact = "".join(source[i] for i in positions)
    wanted = re.sub(r"\s+", "", before)
    assert compact.count(wanted) == 1, "Historical hunk does not match uniquely."
    start = compact.index(wanted)
    a, b = positions[start], positions[start + len(wanted) - 1] + 1
    left, right = source.rfind("\n", 0, a) + 1, source.find("\n", b)
    right = len(source) if right < 0 else right + 1
    assert not source[left:a].strip() and not source[b:right].strip()
    return source[:left] + after + source[right:]


def main():
    files, provenance = {}, []
    for line in JOURNAL.open(encoding="utf-8"):
        event = json.loads(line)
        if event.get("timestamp", "") > "2026-10-14T22:13:00":
            continue
        payload = event.get("payload", {})
        code = payload.get("input", "")
        if payload.get("type") != "custom_tool_call" or "tools.apply_patch(" not in code:
            continue
        for found in re.finditer(r'tools\.apply_patch\(("(?:\\.|[^"\\])*")\)', code):
            patch = json.loads(found[1]).splitlines()
            index = 0
            while index < len(patch):
                header = re.match(r"\*\*\* (Add|Update) File: (.*)", patch[index])
                if not header:
                    index += 1
                    continue
                action, path = header.groups()
                name = path.replace("\\", "/").split("/")[-1]
                index += 1
                end = index
                while end < len(patch) and not patch[end].startswith("*** "):
                    end += 1
                block = patch[index:end]
                index = end
                if name not in NAMES:
                    continue
                if action == "Add":
                    assert name not in files
                    files[name] = "\n".join(row[1:] for row in block if row.startswith("+")) + "\n"
                else:
                    assert name in files
                    formatted = subprocess.run(
                        [sys.executable, "-m", "ruff", "format", "--stdin-filename", name, "-"],
                        input=files[name],
                        text=True,
                        encoding="utf-8",
                        capture_output=True,
                    )
                    assert formatted.returncode == 0, formatted.stderr
                    files[name] = formatted.stdout
                    hunks, current = [], []
                    for row in block:
                        if row.startswith("@@"):
                            if current:
                                hunks.append(current)
                            current = []
                        elif row.startswith((" ", "+", "-")):
                            current.append(row)
                    if current:
                        hunks.append(current)
                    for hunk in hunks:
                        try:
                            files[name] = replace_hunk(
                                files[name],
                                [r[1:] for r in hunk if r[0] in " -"],
                                [r[1:] for r in hunk if r[0] in " +"],
                            )
                        except AssertionError:
                            print("Unmatched patch", event["timestamp"], name, hunk[:5])
                            if "for feature" in str(hunk):
                                pos = files[name].find("for feature")
                                print(repr(files[name][pos : pos + 220]))
                            raise
                ast.parse(files[name])
                provenance.append(
                    {
                        "file": name,
                        "timestamp": event["timestamp"],
                        "call_id": payload["call_id"],
                        "operation": action,
                    }
                )
    assert set(files) == NAMES
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8")
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print("Recovered:", {name: len(text) for name, text in files.items()})


if __name__ == "__main__":
    main()
