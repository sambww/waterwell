#!/usr/bin/env python3
"""Pull the upcoming Workiz job schedule and write docs/data/queue.json.

Reads:
  - docs/data/rigs.json  (rig + supervisor + workizMatch config)
  - WORKIZ_API_TOKEN     (env var, required)

Writes:
  - docs/data/queue.json (per-rig position lists, no customer info)

Runs in CI on a 15-minute cron — see .github/workflows/sync-workiz.yml.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RIGS_JSON = REPO_ROOT / "docs" / "data" / "rigs.json"
QUEUE_JSON = REPO_ROOT / "docs" / "data" / "queue.json"

WORKIZ_BASE = "https://api.workiz.com/api/v1"
PAGE_SIZE = 100
HORIZON_DAYS = 90
ACTIVE_STATUSES = {"submitted", "scheduled", "pending", "in progress"}
DRILLING_STATUSES = {"in progress"}


def fetch_jobs(token: str, start: date) -> list[dict]:
    """Page through Workiz /job/all/ from `start` until we run out of results."""
    jobs: list[dict] = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "start_date": start.isoformat(),
            "offset": offset,
            "records": PAGE_SIZE,
        })
        url = f"{WORKIZ_BASE}/{token}/job/all/?{params}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.load(resp)
        page = payload.get("data") or []
        if not page:
            break
        jobs.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return jobs


def job_haystack(job: dict) -> str:
    """Build a lowercase blob of the fields we route on."""
    parts: list[str] = []
    for key in ("Team", "Assigned", "JobTeam", "SubStatus"):
        value = job.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
    tags = job.get("Tags") or job.get("JobTags") or []
    if isinstance(tags, list):
        parts.extend(str(t) for t in tags)
    elif isinstance(tags, str):
        parts.append(tags)
    return " | ".join(parts).lower()


def route(job: dict, rigs: list[dict]) -> str | None:
    """Return the first rig name whose workizMatch tokens appear in the job."""
    hay = job_haystack(job)
    if not hay:
        return None
    for rig in rigs:
        for needle in rig.get("workizMatch") or []:
            if needle and needle.lower() in hay:
                return rig["name"]
    return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def week_label(dt: datetime) -> str:
    """'Week of Jun 1, 2026' — Monday of that week, en-US."""
    monday = dt.date() - timedelta(days=dt.weekday())
    return f"Week of {monday.strftime('%b')} {monday.day}, {monday.year}"


def build_queue(rigs: list[dict], jobs: list[dict], horizon: date) -> dict[str, list[dict]]:
    by_rig: dict[str, list[tuple[datetime, str]]] = {r["name"]: [] for r in rigs}
    dropped = 0
    for job in jobs:
        status = (job.get("Status") or "").strip().lower()
        if status not in ACTIVE_STATUSES:
            continue
        dt = parse_dt(job.get("JobDateTime") or job.get("JobEndDateTime"))
        if dt is None or dt.date() > horizon:
            continue
        rig = route(job, rigs)
        if rig is None:
            dropped += 1
            sys.stderr.write(
                f"unrouted job {job.get('JobID')!r} "
                f"team={job.get('Team')!r} assigned={job.get('Assigned')!r}\n"
            )
            continue
        by_rig.setdefault(rig, []).append((dt, status))

    out: dict[str, list[dict]] = {}
    for rig_name, entries in by_rig.items():
        entries.sort(key=lambda x: x[0])
        out[rig_name] = [
            {
                "position": i + 1,
                "etaWeek": week_label(dt),
                "status": "drilling" if status in DRILLING_STATUSES and i == 0 else "scheduled",
            }
            for i, (dt, status) in enumerate(entries)
        ]
    if dropped:
        sys.stderr.write(f"{dropped} active job(s) had no matching rig — check workizMatch in rigs.json\n")
    return out


def main() -> int:
    token = os.environ.get("WORKIZ_API_TOKEN", "").strip()
    if not token:
        sys.stderr.write("WORKIZ_API_TOKEN is required\n")
        return 2

    config = json.loads(RIGS_JSON.read_text())
    rigs = config.get("rigs") or []
    if not rigs:
        sys.stderr.write("rigs.json has no rigs configured\n")
        return 2

    today = date.today()
    horizon = today + timedelta(days=HORIZON_DAYS)
    jobs = fetch_jobs(token, today)
    sys.stderr.write(f"fetched {len(jobs)} job(s) from Workiz\n")

    queue = build_queue(rigs, jobs, horizon)
    payload = {
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "workiz-api",
        "rigs": queue,
    }
    QUEUE_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    sys.stderr.write(f"wrote {QUEUE_JSON.relative_to(REPO_ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
