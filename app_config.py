"""
Central configuration layer: everything the Settings page can edit lives in
config.json next to this file. Any key missing from config.json falls back to
DEFAULTS, so a partial or old config file keeps the app working unchanged.
"""
import json
from copy import deepcopy
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

# Rows that exist regardless of configuration. Workplace-section rows and
# custom rows are spliced in at "@workplaces" / "@custom" (see row_keys()).
# "dates"/"days" are header rows; "vacation" expands to one column per group.
FIXED_ROW_ORDER = [
    "dates", "days", "work_hours",
    "entry", "exit",
    "escort_morning", "school", "escort_noon",
    "@workplaces",
    "other_empl",
    "arrival_point", "theater", "udex",
    "vehicle_morning", "axis_morning", "wait_morning",
    "taxi_apt", "taxi_arrival",
    "vehicle_noon", "axis_noon", "wait_noon",
    "taxi_emb", "taxi_arrival_noon",
    "@custom",
    "vacation",
]

MAX_GROUPS = 5
MAX_WORKPLACES = 5

# Monday-based, because a week always starts on a Monday here.
DOW_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]

# The two groups that shipped as IL/PE keep their original vacation field names
# so that already-archived weeks stay readable.
LEGACY_VAC = {"g1": "vacation_il", "g2": "vacation_pe"}

# Option lists are stored WITHOUT the leading blank; use options_with_blank().
# Nothing about a particular station is baked in: employee groups, workplaces,
# working days and the extra task are all data, editable from Settings.
DEFAULTS = {
    "schema_version": 2,
    "groups": [
        {"id": "g1", "name": "IL", "color": "#D6E4F0",
         "employees": ["LEON", "TORO"], "active": True},
        {"id": "g2", "name": "PE", "color": "#FAD7A0",
         "employees": ["HALCON", "CHCHORRO", "BUHO"], "active": True},
        {"id": "g3", "name": "", "color": "#D5F5E3", "employees": [], "active": False},
        {"id": "g4", "name": "", "color": "#FADBD8", "employees": [], "active": False},
        {"id": "g5", "name": "", "color": "#E8DAEF", "employees": [], "active": False},
    ],
    "workplaces": [
        {"id": "wp1", "name": "EMB", "active": True, "notes": "", "sections": [
            {"id": "s1", "name": "IL", "group_id": "g1", "row_key": "emb_il"},
            {"id": "s2", "name": "PE", "group_id": "g2", "row_key": "emb_pe",
             "allow_pair": True},
        ]},
        {"id": "wp2", "name": "דירה", "active": True, "notes": "", "sections": [
            {"id": "s3", "name": "IL", "group_id": "g1", "row_key": "apt_il"},
            {"id": "s4", "name": "PE", "group_id": "g2", "row_key": "apt_pe"},
        ]},
        {"id": "wp3", "name": "", "active": False, "notes": "", "sections": []},
        {"id": "wp4", "name": "", "active": False, "notes": "", "sections": []},
        {"id": "wp5", "name": "", "active": False, "notes": "", "sections": []},
    ],
    "work_days": {
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "labels": {"sunday": "ראשון", "monday": "שני", "tuesday": "שלישי",
                   "wednesday": "רביעי", "thursday": "חמישי",
                   "friday": "שישי 🕕", "saturday": "שבת"},
    },
    # headings of the two work-hours option lists
    "work_day_labels": {"weekday": "א'-ה'", "friday": "שישי"},
    "extra_task": {
        "label": {"he": "משימה נוספת", "en": "Extra Task", "es": "Tarea Extra"},
        "options": ["EMB-M", "EMB-T", "R-M", "R-T"],
        "targets": {"morning": 3, "noon": 2},
        "morning_values": ["EMB-M", "R-M"],
        "noon_values": ["EMB-T", "R-T"],
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
        "holiday": "חג",              # excluded from entry/exit auto-assign
        "vehicle_special": "YELLOW",  # counted vehicle; enables taxi rows
    },
    "targets": {
        "yellow_per_week": 3,
        "theater_per_week": 3,
        # {field_key: {option: percent}} — target share of each option for the
        # weighted-least-used auto-assign. Empty ⇒ equal split for every field
        # (which behaves exactly like plain least-used).
        "field_pcts": {},
    },
    # Manual reference maps edited on the Settings page: {entry/exit: free text}.
    # Documentation only — auto-assign and validation never read these.
    "entry_axis_map": {},
    "exit_axis_map": {},
    # Free-text station notes; documentation only, never read by the logic.
    "assign_notes": "",
    # Display order of schedule rows (keys). Empty ⇒ natural order.
    # Keys not listed here are appended at the end; unknown/stale keys are
    # ignored. "dates"/"days" always first.
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


def _migrate(cfg: dict, raw: dict) -> dict:
    """v1 → v2: employees {il, pe} became groups, and UDEX became the extra
    task. Reads the RAW stored object, because _deep_merge has already folded
    whatever it contained on top of the v2 defaults."""
    if raw.get("employees") and not raw.get("groups"):
        il = [e for e in raw["employees"].get("il", []) if e]
        pe = [e for e in raw["employees"].get("pe", []) if e]
        cfg["groups"][0]["employees"], cfg["groups"][0]["active"] = il, True
        cfg["groups"][1]["employees"], cfg["groups"][1]["active"] = pe, bool(pe)
    if not raw.get("extra_task"):
        opt = (raw.get("options") or {}).get("udex")
        sv, tg = raw.get("special_values") or {}, raw.get("targets") or {}
        if isinstance(opt, list) and opt:
            cfg["extra_task"]["options"] = [o for o in opt if o]
        if isinstance(sv.get("udex_morning"), list):
            cfg["extra_task"]["morning_values"] = [o for o in sv["udex_morning"] if o]
        if isinstance(sv.get("udex_noon"), list):
            cfg["extra_task"]["noon_values"] = [o for o in sv["udex_noon"] if o]
        if tg.get("udex_m") is not None:
            cfg["extra_task"]["targets"]["morning"] = int(tg["udex_m"])
        if tg.get("udex_t") is not None:
            cfg["extra_task"]["targets"]["noon"] = int(tg["udex_t"])
    cfg.pop("employees", None)
    cfg.get("options", {}).pop("udex", None)
    for k in ("udex_morning", "udex_noon"):
        cfg.get("special_values", {}).pop(k, None)
    for k in ("udex_m", "udex_t"):
        cfg.get("targets", {}).pop(k, None)
    while len(cfg["groups"]) < MAX_GROUPS:
        cfg["groups"].append({"id": f"g{len(cfg['groups']) + 1}", "name": "",
                              "color": "#eef2f7", "employees": [], "active": False})
    while len(cfg["workplaces"]) < MAX_WORKPLACES:
        cfg["workplaces"].append({"id": f"wp{len(cfg['workplaces']) + 1}", "name": "",
                                  "active": False, "notes": "", "sections": []})
    for g in cfg["groups"]:
        g["employees"] = [e for e in g.get("employees", []) if e]
    for w in cfg["workplaces"]:
        w["sections"] = [x for x in w.get("sections", []) if x and x.get("row_key")]
    cfg["schema_version"] = 2
    return cfg


def get_config() -> dict:
    """Load config.json merged over DEFAULTS, cached by file mtime."""
    mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else None
    if _cache["cfg"] is not None and _cache["mtime"] == mtime:
        return _cache["cfg"]
    cfg, raw = deepcopy(DEFAULTS), {}
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            _deep_merge(cfg, raw)
        except (json.JSONDecodeError, OSError):
            raw = {}  # unreadable config → run on defaults; next Save rewrites it
    cfg = _migrate(cfg, raw if isinstance(raw, dict) else {})
    _cache["mtime"], _cache["cfg"] = mtime, cfg
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["cfg"] = None  # force re-read (mtime may not tick within 1s)


# ── Accessors ──────────────────────────────────────────────────────────────

# ── employee groups ────────────────────────────────────────────────────────

def groups() -> list:
    return list(get_config()["groups"])


def active_groups() -> list:
    return [g for g in groups() if g.get("active")]


def group_by_id(gid: str):
    return next((g for g in groups() if g.get("id") == gid), None)


def group_name(g: dict) -> str:
    return (g.get("name") or "").strip() or g.get("id", "").upper()


def group_employees(gid: str) -> list:
    g = group_by_id(gid)
    return [e for e in (g or {}).get("employees", []) if e] if (g or {}).get("active") else []


def all_employees() -> list:
    out, seen = [], set()
    for g in active_groups():
        for e in g.get("employees", []):
            e = (e or "").strip()
            if e and e not in seen:
                seen.add(e)
                out.append(e)
    return out


def vac_field(g: dict) -> str:
    """Vacation column name for a group; the two original groups keep theirs."""
    return LEGACY_VAC.get(g.get("id"), "vacation_" + str(g.get("id")))


def vac_fields() -> list:
    return [vac_field(g) for g in active_groups()]


def default_vacation_budget(emp: str) -> int:
    g = next((x for x in active_groups() if emp in x.get("employees", [])), None)
    return 14 if g and g.get("id") == "g1" else 30


# ── workplaces & their sections ────────────────────────────────────────────

def workplaces() -> list:
    return list(get_config()["workplaces"])


def active_workplaces() -> list:
    return [w for w in workplaces() if w.get("active")]


def workplace_name(w: dict) -> str:
    return (w.get("name") or "").strip() or w.get("id", "").upper()


def workplace_sections(w: dict) -> list:
    return [x for x in w.get("sections", []) if x and x.get("row_key")]


def all_sections() -> list:
    """[(workplace, section)] across every active workplace, in display order."""
    return [(w, sec) for w in active_workplaces() for sec in workplace_sections(w)]


def section_row_keys() -> list:
    return [sec["row_key"] for _, sec in all_sections()]


def section_by_row(row_key: str):
    return next(((w, s) for w, s in all_sections() if s["row_key"] == row_key), None)


def section_label(w: dict, sec: dict) -> str:
    name = (sec.get("name") or "").strip()
    return workplace_name(w) + (" " + name if name else "")


# ── working days ───────────────────────────────────────────────────────────

def work_days() -> list:
    picked = (get_config().get("work_days") or {}).get("days") or []
    sel = [d for d in DOW_ORDER if d in picked]
    return sel or ["monday"]          # never produce an empty week


def work_day_label(dow: str) -> str:
    labels = (get_config().get("work_days") or {}).get("labels") or {}
    return labels.get(dow) or dow


def work_day_type_labels() -> dict:
    return dict(get_config().get("work_day_labels") or {})


# ── extra task (was UDEX) ──────────────────────────────────────────────────

def extra_task() -> dict:
    return dict(get_config()["extra_task"])


def extra_label(lang: str = "he") -> str:
    lbl = extra_task().get("label") or {}
    return lbl.get(lang) or lbl.get("he") or lbl.get("en") or "udex"


def extra_options() -> list:
    return [o for o in extra_task().get("options", []) if o]


def extra_morning_values() -> list:
    return [o for o in extra_task().get("morning_values", []) if o]


def extra_noon_values() -> list:
    return [o for o in extra_task().get("noon_values", []) if o]


def extra_targets() -> dict:
    t = extra_task().get("targets") or {}
    return {"morning": int(t.get("morning") or 0), "noon": int(t.get("noon") or 0)}


def assign_notes() -> str:
    return get_config().get("assign_notes") or ""


def options(name: str) -> list:
    return [o for o in get_config()["options"].get(name, []) if o]


def options_with_blank(name: str) -> list:
    return [""] + options(name)


def special(name: str):
    return get_config()["special_values"][name]


def targets() -> dict:
    return dict(get_config()["targets"])


# Fields carrying a target-% table, and the option list each one draws from.
# "skip_holiday" fields never auto-assign the holiday value.
PCT_FIELDS = [
    {"key": "entry",         "opt": "entry", "skip_holiday": True},
    {"key": "exit",          "opt": "exit",  "skip_holiday": True},
    {"key": "arrival_point", "opt": "arrival_point"},
    {"key": "axis_morning",  "opt": "axis"},
    {"key": "axis_noon",     "opt": "axis"},
    {"key": "vehicle",       "opt": "vehicle"},
    {"key": "wait_spot",     "opt": "wait_spot"},
    {"key": "taxi_apt",      "opt": "taxi_apt"},
    {"key": "taxi_arrival",  "opt": "taxi_arrival"},
]


def pct_options(key: str) -> list:
    """Values the target-% table for `key` covers."""
    spec = next((f for f in PCT_FIELDS if f["key"] == key), None)
    if not spec:
        return []
    holiday = special("holiday")
    return [o for o in options(spec["opt"])
            if not (spec.get("skip_holiday") and o == holiday)]


def _equal_pcts(values: list) -> dict:
    """100/N each, rounded, with the remainder absorbed by the last value."""
    if not values:
        return {}
    # int(x + .5) matches JS Math.round, so both front-ends show the same split
    base, total, out = int(100 / len(values) + 0.5), 0, {}
    for i, v in enumerate(values):
        p = 100 - total if i == len(values) - 1 else base
        out[v], total = p, total + p
    return out


def default_pcts(key: str) -> dict:
    """Equal split, except vehicles, which mirror the weekly special-vehicle
    target (3 of the 10 morning+noon slots ⇒ 30/70) so the two never disagree."""
    values = pct_options(key)
    if key != "vehicle":
        return _equal_pcts(values)
    vs = special("vehicle_special")
    if len(values) < 2 or vs not in values:
        return _equal_pcts(values)
    sp = max(0, min(100, int(targets().get("yellow_per_week", 0) * 10 + 0.5)))
    rest = [v for v in values if v != vs]
    out, total = {vs: sp}, sp
    base = int((100 - sp) / len(rest) + 0.5)
    for i, v in enumerate(rest):
        p = 100 - total if i == len(rest) - 1 else base
        out[v], total = p, total + p
    return out


def field_pcts(key: str) -> dict:
    """Saved percentages for `key`; options added since the last save fall back
    to their default share."""
    values = pct_options(key)
    default = default_pcts(key)
    saved = (get_config()["targets"].get("field_pcts") or {}).get(key)
    if not saved:
        return default
    out, any_saved = {}, False
    for v in values:
        if saved.get(v) is not None:
            out[v], any_saved = _to_num(saved[v]), True
        else:
            out[v] = default.get(v, 0)
    return out if any_saved else default


def _to_num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def pct_label(key: str, lang: str) -> str:
    """Heading for a target-% table. vehicle/wait_spot name option lists rather
    than schedule rows, so they take their label from the options tab."""
    if key == "vehicle":
        return row_label("vehicle_morning", lang) + " / " + row_label("vehicle_noon", lang)  # noqa: E501
    if key == "wait_spot":
        return row_label("wait_morning", lang) + " / " + row_label("wait_noon", lang)
    return row_label(key, lang)


def reference_map(name: str) -> dict:
    """entry_axis_map / exit_axis_map — manual notes, never enforced."""
    return dict(get_config().get(name, {}) or {})


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


def natural_row_keys() -> list:
    """Fixed rows with workplace sections and custom rows spliced in."""
    out = []
    for k in FIXED_ROW_ORDER:
        if k == "@workplaces":
            out += section_row_keys()
        elif k == "@custom":
            out += custom_row_keys()
        else:
            out.append(k)
    return out


def reorderable_row_keys() -> list:
    """Row keys the user may reorder — everything except the header rows."""
    natural = [k for k in natural_row_keys() if k not in ("dates", "days")]
    order = get_config().get("row_order", [])
    ordered = [k for k in order if k in natural]
    ordered += [k for k in natural if k not in ordered]  # new rows at the end
    return ordered


def all_row_keys() -> list:
    return ["dates", "days"] + reorderable_row_keys()


def schedule_fields() -> list:
    """Every field a day object carries."""
    return [k for k in reorderable_row_keys() if k != "vacation"] + vac_fields()


BASE_ROW_KEYS = [k for k in FIXED_ROW_ORDER if not k.startswith("@")]


def row_label(key: str, lang: str) -> str:
    """Display label for a row: config override → custom row → translations."""
    cfg = get_config()
    override = cfg["row_labels"].get(key, {})
    if override.get(lang):
        return override[lang]
    if key == "udex":
        return extra_label(lang)
    sx = section_by_row(key)
    if sx:
        return section_label(*sx)
    for r in cfg["custom_rows"]:
        if r.get("key") == key:
            labels = r.get("labels", {})
            return labels.get(lang) or labels.get("he") or key
    from translations import t
    return t(f"row_{key}", lang)
