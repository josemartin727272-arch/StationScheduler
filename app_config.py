"""
Central configuration layer: everything the Settings page can edit lives in
config.json next to this file. Any key missing from config.json falls back to
DEFAULTS, so a partial or old config file keeps the app working unchanged.
"""
import json
import re
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
    "arrival_point", "theater", "@extras",
    "vehicle_morning", "axis_morning", "wait_morning",
    "taxi_apt", "taxi_arrival",
    "vehicle_noon", "axis_noon", "wait_noon",
    "taxi_emb", "taxi_arrival_noon",
    "@custom",
    "vacation",
]

MAX_GROUPS = 5
MAX_WORKPLACES = 5
MAX_EXTRAS = 5
DEFAULT_VAC_BUDGET = 14

# Monday-based, because a week always starts on a Monday here.
DOW_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday",
             "saturday", "sunday"]

# The two groups that shipped as IL/PE keep their original vacation field names
# so that already-archived weeks stay readable.
LEGACY_VAC = {"g1": "vacation_il", "g2": "vacation_pe"}

# Which config option list feeds each fixed select row.
ROW_OPTS = {
    "entry": "entry", "exit": "exit",
    "escort_morning": "escort", "escort_noon": "escort",
    "arrival_point": "arrival_point", "theater": "theater",
    "vehicle_morning": "vehicle", "vehicle_noon": "vehicle",
    "axis_morning": "axis", "axis_noon": "axis",
    "wait_morning": "wait_spot", "wait_noon": "wait_spot",
    "taxi_apt": "taxi_apt", "taxi_arrival": "taxi_arrival",
    "taxi_emb": "taxi_emb", "taxi_arrival_noon": "taxi_arrival_noon",
}

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
    # Workplaces are staffed in `priority` order. A section marked `required`
    # must be filled for its workplace to be staffed at all — if it cannot be,
    # the whole workplace is skipped that day and its people stay free for the
    # ones further down the list.
    "workplaces": [
        {"id": "wp1", "name": "EMB", "active": True, "notes": "", "priority": 1,
         "sections": [
            {"id": "s1", "name": "IL", "group_id": "g1", "row_key": "emb_il",
             "max_workers": 1, "required": True},
            {"id": "s2", "name": "PE", "group_id": "g2", "row_key": "emb_pe",
             "max_workers": 2, "required": True},
        ]},
        {"id": "wp2", "name": "דירה", "active": True, "notes": "", "priority": 2,
         "sections": [
            {"id": "s3", "name": "IL", "group_id": "g1", "row_key": "apt_il",
             "max_workers": 1, "required": False},
            {"id": "s4", "name": "PE", "group_id": "g2", "row_key": "apt_pe",
             "max_workers": 1, "required": False},
        ]},
        {"id": "wp3", "name": "", "active": False, "notes": "", "priority": 3,
         "sections": []},
        {"id": "wp4", "name": "", "active": False, "notes": "", "priority": 4,
         "sections": []},
        {"id": "wp5", "name": "", "active": False, "notes": "", "priority": 5,
         "sections": []},
    ],
    "work_days": {
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "labels": {"sunday": "ראשון", "monday": "שני", "tuesday": "שלישי",
                   "wednesday": "רביעי", "thursday": "חמישי",
                   "friday": "שישי 🕕", "saturday": "שבת"},
        # one shared work-hours list for every working day
        "hour_options": ["7:30-16:00", "8:00-16:30", "8:30-17:00",
                         "7:30-13:30", "8:00-14:00", "8:30-14:30",
                         "7:30-13:00", "8:00-13:30"],
    },
    # Up to MAX_EXTRAS independent extra-task rows. The first keeps the row key
    # "udex" so already-archived weeks stay readable.
    "extra_tasks": [
        {"id": "et1",
         "label": {"he": "משימה נוספת", "en": "Extra Task", "es": "Tarea Extra"},
         "options": ["EMB-M", "EMB-T", "R-M", "R-T"],
         "morning_values": ["EMB-M", "R-M"], "noon_values": ["EMB-T", "R-T"],
         "target_morning": 3, "target_noon": 2, "active": True},
    ] + [
        {"id": f"et{i}", "label": {"he": "", "en": "", "es": ""}, "options": [],
         "morning_values": [], "noon_values": [],
         "target_morning": 0, "target_noon": 0, "active": False}
        for i in range(2, MAX_EXTRAS + 1)
    ],
    "vacation_budget": {
        "LEON": 14, "TORO": 14,
        "HALCON": 30, "CHCHORRO": 30, "BUHO": 30,
    },
    "options": {
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
    # Weekly quotas, any number of them. `value: ""` means "this row is
    # filled", any other value means "this exact value". A field listed here is
    # governed entirely by its quotas: remaining days take the other values, or
    # stay blank when a value-less quota is used.
    "weekly_targets": [
        {"field": "vehicle_morning", "value": "YELLOW", "count": 2},
        {"field": "vehicle_noon",    "value": "YELLOW", "count": 1},
        {"field": "theater",         "value": "",       "count": 3},
    ],
    "targets": {
        # {field_key: {option: percent}} — target share of each option for the
        # weighted-least-used auto-assign. Empty ⇒ equal split for every field
        # (which behaves exactly like plain least-used).
        "field_pcts": {},
    },
    # Manual reference maps edited on the Settings page:
    # {entry/exit value: [axis letters]}. Documentation only — auto-assign and
    # validation never read these.
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
    # v1 UDEX → the first extra task
    if not raw.get("extra_task") and not raw.get("extra_tasks"):
        opt = (raw.get("options") or {}).get("udex")
        sv, tg = raw.get("special_values") or {}, raw.get("targets") or {}
        et = cfg["extra_tasks"][0]
        if isinstance(opt, list) and opt:
            et["options"] = [o for o in opt if o]
        if isinstance(sv.get("udex_morning"), list):
            et["morning_values"] = [o for o in sv["udex_morning"] if o]
        if isinstance(sv.get("udex_noon"), list):
            et["noon_values"] = [o for o in sv["udex_noon"] if o]
        if tg.get("udex_m") is not None:
            et["target_morning"] = int(tg["udex_m"])
        if tg.get("udex_t") is not None:
            et["target_noon"] = int(tg["udex_t"])
    # v2 single extra_task → extra_tasks[0]
    if raw.get("extra_task") and not raw.get("extra_tasks"):
        old, et = raw["extra_task"], cfg["extra_tasks"][0]
        t0 = old.get("targets") or {}
        if old.get("label"):
            et["label"] = {k: old["label"].get(k, "") for k in ("he", "en", "es")}
        for src, dst in (("options", "options"), ("morning_values", "morning_values"),
                         ("noon_values", "noon_values")):
            if isinstance(old.get(src), list):
                et[dst] = [o for o in old[src] if o]
        if t0.get("morning") is not None:
            et["target_morning"] = int(t0["morning"])
        if t0.get("noon") is not None:
            et["target_noon"] = int(t0["noon"])
        et["active"] = True
    cfg.pop("extra_task", None)
    while len(cfg["extra_tasks"]) < MAX_EXTRAS:
        cfg["extra_tasks"].append(
            {"id": f"et{len(cfg['extra_tasks']) + 1}",
             "label": {"he": "", "en": "", "es": ""}, "options": [],
             "morning_values": [], "noon_values": [],
             "target_morning": 0, "target_noon": 0, "active": False})
    for et in cfg["extra_tasks"]:
        et.setdefault("label", {"he": "", "en": "", "es": ""})
        for k in ("options", "morning_values", "noon_values"):
            et[k] = [o for o in et.get(k, []) if o]

    # The two per-day-type work-hours lists became one shared list. Test the
    # RAW config, not the merged one: a v1 file has no work_days at all, so the
    # merged copy already carries the shipped defaults and would mask the
    # user's own hours.
    wd = cfg["work_days"]
    if not [h for h in (raw.get("work_days") or {}).get("hour_options", []) or [] if h]:
        merged, seen = [], set()
        for key in ("work_hours_weekday", "work_hours_friday"):
            for v in (raw.get("options") or {}).get(key, []) or []:
                if v and v not in seen:
                    seen.add(v)
                    merged.append(v)
        if merged:
            wd["hour_options"] = merged
    wd["hour_options"] = [h for h in wd.get("hour_options", []) if h]
    for k in ("work_hours_weekday", "work_hours_friday"):
        cfg.get("options", {}).pop(k, None)
    cfg.pop("work_day_labels", None)

    # axis reference maps: free text ("D, B") → a list of axis letters
    for key in ("entry_axis_map", "exit_axis_map"):
        out = {}
        for value, raw_axes in (cfg.get(key) or {}).items():
            items = raw_axes if isinstance(raw_axes, list) else \
                re.split(r"[,\s]+", str(raw_axes or ""))
            letters = []
            for x in items:
                letter = str(x or "").strip()[:1].upper()
                if letter and letter not in letters:
                    letters.append(letter)
            if letters:
                out[value] = letters
        cfg[key] = out

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
                                  "active": False, "notes": "",
                                  "priority": len(cfg["workplaces"]) + 1,
                                  "sections": []})
    for g in cfg["groups"]:
        g["employees"] = [e for e in g.get("employees", []) if e]
    for i, w in enumerate(cfg["workplaces"]):
        # an older config has no priority; the list order becomes it
        try:
            w["priority"] = max(1, min(MAX_WORKPLACES, int(w.get("priority") or i + 1)))
        except (TypeError, ValueError):
            w["priority"] = i + 1
        w["sections"] = [x for x in w.get("sections", []) if x and x.get("row_key")]
        for sec in w["sections"]:
            sec["required"] = bool(sec.get("required"))
        # allow_pair was a two-state flag; max_workers is a count
        for sec in w["sections"]:
            if sec.get("max_workers") is None:
                sec["max_workers"] = 2 if sec.get("allow_pair") else 1
            try:
                sec["max_workers"] = max(0, min(10, int(sec["max_workers"])))
            except (TypeError, ValueError):
                sec["max_workers"] = 1
            sec.pop("allow_pair", None)

    # the fixed YELLOW / theater counts became a list of weekly quotas
    if not raw.get("weekly_targets"):
        tg, out = raw.get("targets") or {}, []
        if tg.get("yellow_per_week") is not None:
            n = int(tg["yellow_per_week"] or 0)
            vs = cfg["special_values"]["vehicle_special"]
            if n > 0:
                out.append({"field": "vehicle_morning", "value": vs,
                            "count": -(-n // 2)})
                if n > 1:
                    out.append({"field": "vehicle_noon", "value": vs, "count": n // 2})
        if int(tg.get("theater_per_week") or 0) > 0:
            out.append({"field": "theater", "value": "",
                        "count": int(tg["theater_per_week"])})
        if out:
            cfg["weekly_targets"] = out
    clean = []
    for q in cfg.get("weekly_targets") or []:
        if not (q and q.get("field")):
            continue
        try:
            count = max(0, int(q.get("count") or 0))
        except (TypeError, ValueError):
            count = 0
        clean.append({"field": q["field"], "value": q.get("value") or "", "count": count})
    cfg["weekly_targets"] = clean
    for k in ("yellow_per_week", "theater_per_week"):
        cfg.get("targets", {}).pop(k, None)
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


# ── workplaces & their sections ────────────────────────────────────────────

def workplaces() -> list:
    return list(get_config()["workplaces"])


def active_workplaces() -> list:
    """Active workplaces in staffing order; list order breaks a priority tie."""
    return [w for _, w in sorted(
        ((i, w) for i, w in enumerate(workplaces()) if w.get("active")),
        key=lambda p: (p[1].get("priority") or 0, p[0]))]


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


def section_size(sec: dict) -> int:
    """How many employees a section takes; 0 means "never assign this row"."""
    try:
        return max(0, min(10, int(sec.get("max_workers", 1))))
    except (TypeError, ValueError):
        return 1


def section_required(sec: dict) -> bool:
    return bool(sec.get("required"))


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


def hour_options() -> list:
    """The one work-hours list, offered on every working day."""
    return [h for h in (get_config().get("work_days") or {}).get("hour_options", []) if h]


# ── extra tasks (was the single UDEX row) ──────────────────────────────────

def extra_tasks() -> list:
    return list(get_config()["extra_tasks"])


def active_extras() -> list:
    return [e for e in extra_tasks() if e.get("active")]


def extra_row_key(et: dict) -> str:
    """The first task keeps the original row key so archived weeks still read."""
    return "udex" if et.get("id") == "et1" else "extra_" + str(et.get("id"))


def extra_row_keys() -> list:
    return [extra_row_key(e) for e in active_extras()]


def extra_by_row(row_key: str):
    return next((e for e in active_extras() if extra_row_key(e) == row_key), None)


def extra_label(et, lang: str = "he") -> str:
    if isinstance(et, str):              # called with a language only
        et, lang = active_extras()[0] if active_extras() else {}, et
    lbl = (et or {}).get("label") or {}
    return lbl.get(lang) or lbl.get("he") or lbl.get("en") or str((et or {}).get("id", ""))


def extra_targets(et: dict) -> dict:
    return {"morning": int(et.get("target_morning") or 0),
            "noon": int(et.get("target_noon") or 0)}


# ── weekly quotas ──────────────────────────────────────────────────────────

def weekly_targets() -> list:
    return [dict(q) for q in get_config().get("weekly_targets") or []]


def governed_fields() -> set:
    """Rows a quota owns — auto-assign leaves these to the quota pass."""
    return {q["field"] for q in weekly_targets()}


def target_field_values(key: str) -> list:
    """Pickable values of any row that can carry a quota."""
    if key == "work_hours":
        return hour_options()
    et = extra_by_row(key)
    if et:
        return [o for o in et.get("options", []) if o]
    sx = section_by_row(key)
    if sx:
        group = group_by_id(sx[1].get("group_id"))
        return group_employees(group["id"]) if group else all_employees()
    for r in custom_rows():
        if r["key"] == key:
            return list(r.get("options", []))
    if key == "other_empl":
        return all_employees()
    return options(ROW_OPTS.get(key, ""))


def target_fields() -> list:
    """Rows offered in the quota field picker: every select row."""
    text_rows = {"school"}
    custom = {r["key"]: r for r in custom_rows()}
    out = []
    for k in natural_row_keys():
        if k in ("dates", "days", "vacation") or k in text_rows:
            continue
        if k in custom and custom[k].get("input") != "select":
            continue
        out.append(k)
    return out


def axis_letters() -> list:
    """Distinct axis letters behind the configured axis values (A-U, A-D → A)."""
    out = []
    for a in options("axis"):
        letter = str(a).strip()[:1].upper()
        if letter and letter not in out:
            out.append(letter)
    return out


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
    """Every field defaults to an equal split. Vehicles used to derive theirs
    from the weekly YELLOW count; that count is now an explicit weekly quota,
    so the percentages only matter for a field with no quota on it."""
    return _equal_pcts(pct_options(key))


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
    """entry_axis_map / exit_axis_map — {value: [axis letters]}, never enforced."""
    return {k: list(v) for k, v in (get_config().get(name) or {}).items()}


def default_vacation_budget(emp: str = "") -> int:
    return DEFAULT_VAC_BUDGET


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
        elif k == "@extras":
            out += extra_row_keys()
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
    et = extra_by_row(key)
    if et:
        return extra_label(et, lang)
    sx = section_by_row(key)
    if sx:
        return section_label(*sx)
    for r in cfg["custom_rows"]:
        if r.get("key") == key:
            labels = r.get("labels", {})
            return labels.get(lang) or labels.get("he") or key
    from translations import t
    return t(f"row_{key}", lang)
