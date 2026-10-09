"""Exercise the packaged container without AWS, using only localhost."""

import json
import time
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8001"


def call(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def main():
    for _ in range(30):
        try:
            call("/health")
            break
        except (URLError, ConnectionError, TimeoutError, HTTPException):
            time.sleep(1)
    else:
        raise RuntimeError("Container did not become healthy")
    jobs = call("/api/videos")
    if len([j for j in jobs if j.get("packaged_example")]) != 3:
        raise RuntimeError("Expected three preprocessed, attributed archival examples")
    for job in jobs:
        if job.get("packaged_example"):
            result = call("/api/videos/" + job["job_id"] + "/result")
            if result["quality_gate"]["coaching_allowed"]:
                raise RuntimeError("Low-resolution demo was incorrectly marked supported")
    session = call("/api/demo", {})
    run = call(
        "/api/sessions/" + session["session_id"] + "/reports",
        {
            "question": "Review my recovery time",
            "mode": "demo",
        },
    )
    if not run["citation_ids_valid"] or not run["citation_count"]:
        raise RuntimeError("Report did not pass its evidence checks")
    print("Container demo session and coaching report passed.")


if __name__ == "__main__":
    main()
