"""Validate browser module syntax with Node without executing application code."""

import shutil
import subprocess
from pathlib import Path


def main():
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node is required for browser module syntax checks.")
    project = Path(__file__).resolve().parents[1]
    paths = sorted((project / "src/fencecoach/web").glob("*.js"))
    for path in paths:
        result = subprocess.run(
            [node, "--input-type=module", "--check"], input=path.read_bytes(), capture_output=True
        )
        if result.returncode:
            raise SystemExit(f"{path.name}: {result.stderr.decode()}")
    print(f"{len(paths)} browser modules passed syntax checks.")


if __name__ == "__main__":
    main()
