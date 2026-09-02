"""
Central configuration layer: everything the Settings page can edit lives in
config.json next to this file. Any key missing from config.json falls back to
DEFAULTS, so a partial or old config file keeps the app working unchanged.
"""
import json
from copy import deepcopy
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

# Base rows in display order. "dates"/"days" are header rows; "vacation" maps
# to the vacation_il/vacation_pe pair. Custom rows are appended after these.
BASE_ROW_KEYS = [
    "dates", "days", "work_hours",
    "entry", "exit",
    "escort_morning", "school", "escort_noon",
    "emb_il", "emb_pe", "other_empl",
    "arrival_point", "theater", "udex",
    "apt_il", "apt_pe",
    "vehicle_morning", "axis_morning", "wait_morning",
    "taxi_apt", "taxi_arrival",
    "vehicle_noon", "axis_noon", "wait_noon",
    "taxi_emb", "taxi_arrival_noon",
    "vacation",
]

# Option lists are stored WITHOUT the leading blank; use options_with_blank().
DEFAULTS = {
    "schema_version": 1,
    "employees": {
        "il": ["LEON", "TORO"],
        "pe": ["HALCON", "CHCHORRO", "BUHO"],
    },
    "vacation_budget": {
        "LEON": 14, "TORO": 14,
        "HALCON": 30, "CHCHORRO": 30, "BUHO": 30,
    },
    "options": {
        "work_hours_weekday": ["7:30-16:00", "8:00-16:30", "8:30-17:00"],
        "work_hours_friday":  ["7:30-13:30", "8:00-14:00", "8:30-14:30",
                               "7:30-13:00", "8:00-13:30"],
        "entry":         ["10", "13", "10-T", "13-D", "SPLIT", "חג"],
        "exit":          ["10", "13", "13-T", "10-D", "SPLIT", "חג"],
        "escort":        ["200", "201", "300", "301", "400", "500"],
        "arrival_point": ["CHILE", "BRAZIL", "COLOMBIA", "BOLIVIA"],
        "theater":       ["משקפת", "רדיו", "תמונות"],
        "udex":          ["EMB-M", "EMB-T", "R-M", "R-T"],
        "vehicle":       ["BLACK", "YELLOW"],
        "axis":          ["A-U", "A-D", "B-U", "B-D", "C-U", "C-D", "D-U", "D-D"],
        "wait_spot":     ["2", "3", "4", "5"],
        "taxi_apt":          ["ARRIBA", "ABAJO"],
        "taxi_arrival":      ["2", "3", "4", "5"],
        "taxi_emb":          ["ARRIBA", "ABAJO"],
        "taxi_arrival_noon": ["2", "3", "4", "5"],
    },
    # Values with special meaning to auto-assign/validation. Editable so that
    # renaming an option in "options" doesn't silently break the logic.
    "special_values": {
        "holiday": "חג",          # excluded from entry/exit auto-assign
        "vehicle_special": "YELLOW",  # counted vehicle; enables taxi rows
        "udex_morning": ["EMB-M", "R-M"],
        "udex_noon":    ["EMB-T", "R-T"],
    },
    "targets": {
        "yellow_per_week": 3,
        "udex_m": 3,
        "udex_t": 2,
        "theater_per_week": 3,
    },
    # Display order of schedule rows (keys). Empty ⇒ natural order
    # (BASE_ROW_KEYS then custom rows). Keys not listed here are appended
    # at the end; unknown/stale keys are ignored. "dates"/"days" always first.
    "row_order": [],
    # {row_key: {"he": .., "en": .., "es": ..}} — overrides translations.py
    "row_labels": {},
    # [{"key": "custom_1", "labels": {"he","en","es"}, "input": "select"|"text",
    #   "options": [...]}] — rendered after the base rows
    "custom_rows": [],
}

_cache = {"mtime": -1.0, "cfg": None}


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def get_config() -> dict:
    """Load config.json merged over DEFAULTS, cached by file mtime."""
    mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else None
    if _cache["cfg"] is not None and _cache["mtime"] == mtime:
        return _cache["cfg"]
    cfg = deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            _deep_merge(cfg, json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass  # unreadable config → run on defaults; next Save rewrites it
    _cache["mtime"], _cache["cfg"] = mtime, cfg
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["cfg"] = None  # force re-read (mtime may not tick within 1s)


# ── Accessors ──────────────────────────────────────────────────────────────

def employees_il() -> list:
    return list(get_config()["employees"]["il"])


def employees_pe() -> list:
    return list(get_config()["employees"]["pe"])


def all_employees() -> list:
    return employees_il() + employees_pe()


def options(name: str) -> list:
    return [o for o in get_config()["options"].get(name, []) if o]


def options_with_blank(name: str) -> list:
    return [""] + options(name)


def special(name: str):
    return get_config()["special_values"][name]


def targets() -> dict:
    return dict(get_config()["targets"])


def vacation_budget() -> dict:
    return dict(get_config()["vacation_budget"])


def custom_rows() -> list:
    rows = []
    for r in get_config()["custom_rows"]:
        if isinstance(r, dict) and r.get("key"):
            rows.append({
                "key": r["key"],
                "labels": r.get("labels", {}),
                "input": r.get("input", "text"),
                "options": [o for o in r.get("options", []) if o],
            })
    return rows


def custom_row_keys() -> list:
    return [r["key"] for r in custom_rows()]


def reorderable_row_keys() -> list:
    """Row keys the user may reorder — everything except the header rows."""
    natural = [k for k in BASE_ROW_KEYS if k not in ("dates", "days")]
    natural += custom_row_keys()
    order = get_config().get("row_order", [])
    ordered = [k for k in order if k in natural]
    ordered += [k for k in natural if k not in ordered]  # new rows at the end
    return ordered


def all_row_keys() -> list:
    return ["dates", "days"] + reorderable_row_keys()


def row_label(key: str, lang: str) -> str:
    """Display label for a row: config override → custom row → translations."""
    cfg = get_config()
    override = cfg["row_labels"].get(key, {})
    if override.get(lang):
        return override[lang]
    for r in cfg["custom_rows"]:
        if r.get("key") == key:
            labels = r.get("labels", {})
            return labels.get(lang) or labels.get("he") or key
    from translations import t
    return t(f"row_{key}", lang)
