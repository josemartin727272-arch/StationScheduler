"""
Local JSON archive: saves/loads weekly schedules organized by year/month/week.
"""
import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

ARCHIVE_DIR = Path(__file__).parent / "archive"


def _path(week_start: date) -> Path:
    return ARCHIVE_DIR / str(week_start.year) / f"{week_start.month:02d}" / f"{week_start.isoformat()}.json"


def save_schedule(week_start: date, schedule: dict) -> Path:
    p = _path(week_start)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Convert date objects to strings for JSON serialisation
    serializable = {}
    for dk, day in schedule.items():
        serializable[dk] = {
            k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in day.items()
        }
    p.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_schedule(week_start: date) -> Optional[dict]:
    p = _path(week_start)
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    from datetime import date as _date
    result = {}
    for dk, day in raw.items():
        day = dict(day)
        if "date" in day and isinstance(day["date"], str):
            try:
                day["date"] = _date.fromisoformat(day["date"])
            except ValueError:
                pass
        result[dk] = day
    return result


def delete_schedule(week_start: date) -> bool:
    p = _path(week_start)
    if p.exists():
        p.unlink()
        # Remove empty parent dirs
        for parent in [p.parent, p.parent.parent]:
            try:
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except Exception:
                pass
        return True
    return False


def list_archive() -> dict:
    """Return nested dict: {year: {month: [week_start_str, ...]}}"""
    result = {}
    if not ARCHIVE_DIR.exists():
        return result
    for year_dir in sorted(ARCHIVE_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        yr = year_dir.name
        result[yr] = {}
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            mo = month_dir.name
            weeks = sorted([f.stem for f in month_dir.glob("*.json")])
            if weeks:
                result[yr][mo] = weeks
    return result
