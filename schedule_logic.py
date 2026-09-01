"""
Business logic for schedule generation, validation, and equality tracking.
All employee lists, option lists and weekly targets come from app_config
(config.json), so Settings-page edits apply on the next rerun.
"""
import random
from datetime import date, timedelta

import app_config as cfg

DAYS_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

# Which rows are manually entered (not auto-assigned)
MANUAL_ROWS = {"escort_morning", "escort_noon", "other_empl", "vacation"}

# Which rows are optional (can be blank)
OPTIONAL_ROWS = {"escort_morning", "escort_noon"}


def entry_auto_options() -> list:
    holiday = cfg.special("holiday")
    return [o for o in cfg.options("entry") if o != holiday]


def exit_auto_options() -> list:
    holiday = cfg.special("holiday")
    return [o for o in cfg.options("exit") if o != holiday]


def emb_pe_options() -> list:
    """Single PE employees plus all ordered pairs (A+B)."""
    pe = cfg.employees_pe()
    return ([""] + pe +
            [f"{a}+{b}" for i, a in enumerate(pe) for b in pe[i + 1:]])


# ── Data model ─────────────────────────────────────────────────────────────

def empty_week(week_start: date) -> dict:
    """Return a blank weekly schedule dict keyed by date string (Mon–Fri only)."""
    if week_start.weekday() != 0:
        week_start = week_start - timedelta(days=week_start.weekday())
    base_fields = [
        "work_hours", "entry", "exit",
        "escort_morning", "school", "escort_noon",
        "emb_il", "emb_pe", "other_empl",
        "arrival_point", "theater", "udex",
        "apt_il", "apt_pe",
        "vehicle_morning", "axis_morning", "wait_morning",
        "taxi_apt", "taxi_arrival",
        "vehicle_noon", "axis_noon", "wait_noon",
        "taxi_emb", "taxi_arrival_noon",
        "vacation_il", "vacation_pe",
    ]
    fields = base_fields + cfg.custom_row_keys()
    schedule = {}
    for i in range(5):  # Monday=0 .. Friday=4
        day = week_start + timedelta(days=i)
        entry = {f: "" for f in fields}
        entry["date"] = day
        schedule[day.isoformat()] = entry
    return schedule


# ── Validation ─────────────────────────────────────────────────────────────

def validate_schedule(schedule: dict, lang: str = "he") -> list:
    """Return list of warning/error strings."""
    from translations import t
    errors = []

    employees_il = cfg.employees_il()
    employees_pe = cfg.employees_pe()
    targets = cfg.targets()
    vehicle_special = cfg.special("vehicle_special")
    udex_m_vals = set(cfg.special("udex_morning"))
    udex_t_vals = set(cfg.special("udex_noon"))

    yellow_count = 0
    udex_m = 0
    udex_t = 0

    for day_key, day in schedule.items():
        if day.get("vehicle_morning") == vehicle_special:
            yellow_count += 1
        if day.get("vehicle_noon") == vehicle_special:
            yellow_count += 1

        udex = day.get("udex", "")
        if udex in udex_m_vals:
            udex_m += 1
        elif udex in udex_t_vals:
            udex_t += 1

        vac_il = day.get("vacation_il", "")
        vac_pe = day.get("vacation_pe", "")
        other_empl = day.get("other_empl", "")
        d_str = day.get("date").strftime("%d/%m") if day.get("date") else day_key
        if vac_il and "," in vac_il:
            errors.append(f"{day_key}: {t('error_two_il_vacation', lang)}")
        if vac_pe and "," in vac_pe:
            errors.append(f"{day_key}: {t('error_two_pe_vacation', lang)}")
        emb_il = day.get("emb_il", "")
        if emb_il and emb_il in employees_il:
            if emb_il == vac_il:
                errors.append(f"❌ {d_str}: {emb_il} שובץ ל-EMB IL אך הוא בחופשה")
            elif emb_il == other_empl:
                errors.append(f"❌ {d_str}: {emb_il} שובץ ל-EMB IL אך הוא כבר במשימת אחר")
        unavail_il = {e for e in [vac_il, other_empl] if e in employees_il}
        available_il = [e for e in employees_il if e not in unavail_il]
        if not available_il and not emb_il:
            errors.append(f"❌ {d_str}: אין עובד IL פנוי ל-EMB IL (חופשה + משימת אחר)")
        elif not available_il and emb_il not in employees_pe:
            errors.append(f"❌ {d_str}: כל עובדי IL לא זמינים — EMB IL חייב להיות ממולא")

    theater_count = sum(1 for day in schedule.values() if day.get("theater", ""))

    if yellow_count != targets["yellow_per_week"]:
        errors.append(t("warning_yellow_count", lang, count=yellow_count))
    if udex_m != targets["udex_m"]:
        errors.append(t("warning_udex_m", lang, count=udex_m))
    if udex_t != targets["udex_t"]:
        errors.append(t("warning_udex_t", lang, count=udex_t))
    if theater_count != targets["theater_per_week"]:
        errors.append(t("warning_theater_count", lang, count=theater_count))

    return errors


# ── Auto-assign helpers ────────────────────────────────────────────────────

def auto_assign_day(day: dict, history: dict, week_days: list) -> dict:
    """
    Fill in auto-assigned fields for a single day based on equality history.
    Rules:
    - No employee assigned to two tasks on the same day
    - EMB IL: always IL employee (or PE if IL on vacation)
    - EMB PE: normally a pair of 2 PE employees; single only if limited by vacation+Apt PE
    - Taxis assigned later (after vehicle type known) in auto_assign_week_vehicles_udex
    """
    day = day.copy()
    employees_il = cfg.employees_il()
    employees_pe = cfg.employees_pe()
    vac_il = day.get("vacation_il", "")
    vac_pe = day.get("vacation_pe", "")
    other_empl = day.get("other_empl", "")
    active_il = [e for e in employees_il if e != vac_il and e != other_empl]
    active_pe = [e for e in employees_pe if e != vac_pe and e != other_empl]

    if not day.get("entry"):
        day["entry"] = _least_used(entry_auto_options(), history.get("entry", {}))
    if not day.get("exit"):
        day["exit"] = _least_used(exit_auto_options(), history.get("exit", {}))

    # ── Step 1: EMB IL ──────────────────────────────────────────────────────
    if not day.get("emb_il"):
        if active_il:
            day["emb_il"] = _least_used(active_il, history.get("emb_il", {}))
        elif active_pe:
            day["emb_il"] = _least_used(active_pe, history.get("emb_il", {}))
    emb_il = day.get("emb_il", "")

    # ── Step 2: Apt IL ──────────────────────────────────────────────────────
    if not day.get("apt_il"):
        apt_il_opts = [e for e in active_il if e != emb_il]
        if apt_il_opts:
            day["apt_il"] = _least_used(apt_il_opts, history.get("apt_il", {}))

    # ── Step 3: Apt PE ──────────────────────────────────────────────────────
    if not day.get("apt_pe"):
        emb_il_pe = emb_il if emb_il in employees_pe else ""
        apt_pe_opts = [e for e in active_pe if e != emb_il_pe]
        if apt_pe_opts:
            day["apt_pe"] = _least_used(apt_pe_opts, history.get("apt_pe", {}))
    apt_pe = day.get("apt_pe", "")

    # ── Step 4: EMB PE ──────────────────────────────────────────────────────
    if not day.get("emb_pe"):
        emb_il_pe = emb_il if emb_il in employees_pe else ""
        available = [e for e in active_pe if e != apt_pe and e != emb_il_pe]

        if len(available) >= 2:
            pairs = [
                f"{employees_pe[i]}+{employees_pe[j]}"
                for i in range(len(employees_pe))
                for j in range(i + 1, len(employees_pe))
                if employees_pe[i] in available and employees_pe[j] in available
            ]
            if pairs:
                day["emb_pe"] = _least_used(pairs, history.get("emb_pe", {}))
        elif len(available) == 1:
            day["emb_pe"] = available[0]

    # ── Arrival point ───────────────────────────────────────────────────────
    if not day.get("arrival_point"):
        day["arrival_point"] = _least_used(
            cfg.options("arrival_point"), history.get("arrival_point", {}))

    # ── Axis morning / noon ─────────────────────────────────────────────────
    axis_vals = cfg.options("axis")
    if not day.get("axis_morning") and axis_vals:
        day["axis_morning"] = _least_used(axis_vals, history.get("axis_morning", {}))
    if not day.get("axis_noon") and axis_vals:
        day["axis_noon"] = _least_used(axis_vals, history.get("axis_noon", {}))

    # ── Wait spots ──────────────────────────────────────────────────────────
    wait_vals = cfg.options("wait_spot")
    if not day.get("wait_morning") and wait_vals:
        day["wait_morning"] = _least_used(wait_vals, history.get("wait_morning", {}))
    if not day.get("wait_noon") and wait_vals:
        day["wait_noon"] = _least_used(wait_vals, history.get("wait_noon", {}))

    # NOTE: taxis assigned after vehicle type is known (in auto_assign_week_vehicles_udex)
    return day


def auto_assign_week_vehicles_udex(schedule: dict, history: dict = None) -> dict:
    """
    Assign VEHICLE (yellow_per_week special vehicles across morning+noon),
    UDEX (udex_m morning-type + udex_t noon-type), Theater (theater_per_week
    days), and Taxis (only on special-vehicle slots).
    """
    if history is None:
        history = {}
    keys = list(schedule.keys())

    targets = cfg.targets()
    vehicle_special = cfg.special("vehicle_special")
    vehicle_regular = next(
        (v for v in cfg.options("vehicle") if v != vehicle_special), "")
    udex_m_vals = list(cfg.special("udex_morning"))
    udex_t_vals = list(cfg.special("udex_noon"))

    # Special vehicle: N slots total across morning+noon for the week
    slots = [(k, "vehicle_morning") for k in keys] + [(k, "vehicle_noon") for k in keys]
    unassigned = [(k, f) for k, f in slots if not schedule[k].get(f)]
    yellow_needed = targets["yellow_per_week"] - sum(
        1 for k in keys
        for f in ("vehicle_morning", "vehicle_noon")
        if schedule[k].get(f) == vehicle_special
    )
    if yellow_needed > 0 and len(unassigned) >= yellow_needed:
        chosen = random.sample(unassigned, yellow_needed)
        for k, f in chosen:
            schedule[k][f] = vehicle_special
    for k, f in unassigned:
        if not schedule[k].get(f):
            schedule[k][f] = vehicle_regular

    # UDEX: balance within each type via history
    udex_unassigned = [k for k in keys if not schedule[k].get("udex")]
    udex_m_needed = targets["udex_m"] - sum(
        1 for k in keys if schedule[k].get("udex") in udex_m_vals)
    udex_t_needed = targets["udex_t"] - sum(
        1 for k in keys if schedule[k].get("udex") in udex_t_vals)
    random.shuffle(udex_unassigned)
    m_hist = dict(history.get("udex", {}))
    t_hist = dict(history.get("udex", {}))
    for _ in range(max(0, udex_m_needed)):
        if udex_unassigned:
            chosen = _least_used(udex_m_vals, m_hist)
            m_hist[chosen] = m_hist.get(chosen, 0) + 1
            schedule[udex_unassigned.pop(0)]["udex"] = chosen
    for _ in range(max(0, udex_t_needed)):
        if udex_unassigned:
            chosen = _least_used(udex_t_vals, t_hist)
            t_hist[chosen] = t_hist.get(chosen, 0) + 1
            schedule[udex_unassigned.pop(0)]["udex"] = chosen

    # Theater: assign to exactly theater_per_week days
    theater_vals = cfg.options("theater")
    theater_unassigned = [k for k in keys if not schedule[k].get("theater")]
    theater_needed = targets["theater_per_week"] - sum(
        1 for k in keys if schedule[k].get("theater"))
    if theater_needed > 0 and len(theater_unassigned) >= theater_needed and theater_vals:
        chosen_theater_days = random.sample(theater_unassigned, theater_needed)
        for k in chosen_theater_days:
            schedule[k]["theater"] = _least_used(theater_vals, history.get("theater", {}))

    # Taxis: morning taxis only when vehicle_morning is special; noon likewise
    taxi_vals = cfg.options("wait_spot")
    for k in keys:
        day = schedule[k]
        yellow_morning = day.get("vehicle_morning") == vehicle_special
        yellow_noon    = day.get("vehicle_noon")    == vehicle_special

        for field in ["taxi_apt", "taxi_arrival"]:
            if yellow_morning:
                if not day.get(field):
                    day[field] = _least_used(taxi_vals, history.get(field, {}))
            else:
                day[field] = ""

        for field in ["taxi_emb", "taxi_arrival_noon"]:
            if yellow_noon:
                if not day.get(field):
                    day[field] = _least_used(taxi_vals, history.get(field, {}))
            else:
                day[field] = ""

        schedule[k] = day

    return schedule


def _least_used(options: list, counts: dict) -> str:
    """Pick option with lowest cumulative usage count."""
    if not options:
        return ""
    min_count = min(counts.get(o, 0) for o in options)
    candidates = [o for o in options if counts.get(o, 0) == min_count]
    return random.choice(candidates)


def update_history(history: dict, schedule: dict) -> dict:
    """Add this week's assignments to the cumulative history counts."""
    fields_to_track = [
        "entry", "exit",
        "emb_il", "emb_pe", "arrival_point", "theater",
        "apt_il", "apt_pe", "axis_morning", "axis_noon",
        "wait_morning", "wait_noon", "taxi_apt", "taxi_arrival",
        "vehicle_morning", "vehicle_noon", "udex",
        "taxi_emb", "taxi_arrival_noon",
    ]
    for day in schedule.values():
        for field in fields_to_track:
            val = day.get(field, "")
            if val:
                history.setdefault(field, {})
                history[field][val] = history[field].get(val, 0) + 1
    return history
