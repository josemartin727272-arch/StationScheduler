"""
Business logic for schedule generation, validation, and equality tracking.
"""
import random
from datetime import date, timedelta
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────
EMPLOYEES_IL = ["LEON", "CUY"]
EMPLOYEES_PE = ["HALCON", "CHCHORRO", "BUHO"]
ALL_EMPLOYEES = EMPLOYEES_IL + EMPLOYEES_PE

# Work hours: start time → calculated end (8h Mon-Thu, 6h Fri)
WORK_HOURS_WEEKDAY = ["", "7:30-16:00", "8:00-16:30", "8:30-17:00"]
WORK_HOURS_FRIDAY  = ["", "7:30-13:30", "8:00-14:00", "8:30-14:30"]

ENTRY_OPTIONS = ["", "10", "13", "10-T", "13-D", "SPLIT", "חג"]
EXIT_OPTIONS  = ["", "10", "13", "13-T", "10-D", "SPLIT", "חג"]
ESCORT_OPTIONS = ["", "200", "201", "300", "301", "400", "500"]
ARRIVAL_POINT_OPTIONS = ["", "CHILE", "BRAZIL", "COLOMBIA", "BOLIVIA"]
THEATER_OPTIONS = ["", "משקפת", "רדיו", "תמונות"]
UDEX_OPTIONS = ["", "EMB-M", "EMB-T", "R-M", "R-T"]
VEHICLE_OPTIONS = ["", "BLACK", "YELLOW"]
AXIS_OPTIONS = [""] + [f"{col}{num}" for col in "ABCD" for num in range(1, 6)]
WAIT_SPOT_OPTIONS = ["", "1", "2", "3", "4", "5"]

DAYS_ORDER = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]

# Rows in display order (26 rows)
ROW_KEYS = [
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

# Which rows are manually entered (not auto-assigned)
MANUAL_ROWS = {"escort_morning", "escort_noon", "other_empl", "vacation"}

# Entry/exit options for auto-assign (exclude blank and חג)
ENTRY_AUTO_OPTIONS = [o for o in ENTRY_OPTIONS if o and o != "חג"]
EXIT_AUTO_OPTIONS  = [o for o in EXIT_OPTIONS  if o and o != "חג"]

# Which rows are optional (can be blank)
OPTIONAL_ROWS = {"escort_morning", "escort_noon"}

# EMB PE can be single or pair
EMB_PE_OPTIONS = (
    [""] + EMPLOYEES_PE +
    [f"{a}+{b}" for i, a in enumerate(EMPLOYEES_PE) for b in EMPLOYEES_PE[i+1:]]
)

# ── Data model ─────────────────────────────────────────────────────────────

def empty_week(week_start: date) -> dict:
    """Return a blank weekly schedule dict keyed by date string (Mon–Fri only)."""
    # Snap to Monday if not already
    if week_start.weekday() != 0:
        week_start = week_start - timedelta(days=week_start.weekday())
    schedule = {}
    for i in range(5):  # Monday=0 .. Friday=4
        day = week_start + timedelta(days=i)
        key = day.isoformat()
        schedule[key] = {
            "date": day,
            "work_hours": "",
            "entry": "",
            "exit": "",
            "escort_morning": "",
            "school": "",
            "escort_noon": "",
            "emb_il": "",
            "emb_pe": "",
            "other_empl": "",
            "arrival_point": "",
            "theater": "",
            "udex": "",
            "apt_il": "",
            "apt_pe": "",
            "vehicle_morning": "",
            "axis_morning": "",
            "wait_morning": "",
            "taxi_apt": "",
            "taxi_arrival": "",
            "vehicle_noon": "",
            "axis_noon": "",
            "wait_noon": "",
            "taxi_emb": "",
            "taxi_arrival_noon": "",
            "vacation_il": "",   # one of EMPLOYEES_IL or ""
            "vacation_pe": "",   # one of EMPLOYEES_PE or ""
        }
    return schedule


# ── Validation ─────────────────────────────────────────────────────────────

def validate_schedule(schedule: dict, lang: str = "he") -> list:
    """Return list of warning/error strings."""
    from translations import t
    errors = []

    yellow_count = 0
    udex_m = 0
    udex_t = 0

    for day_key, day in schedule.items():
        # YELLOW count
        if day.get("vehicle_morning") == "YELLOW":
            yellow_count += 1
        if day.get("vehicle_noon") == "YELLOW":
            yellow_count += 1

        # UDEX (EMB-M and R-M count as morning; EMB-T and R-T as noon)
        udex = day.get("udex", "")
        if udex in ("EMB-M", "R-M"):
            udex_m += 1
        elif udex in ("EMB-T", "R-T"):
            udex_t += 1

        # Vacation constraints
        vac_il = day.get("vacation_il", "")
        vac_pe = day.get("vacation_pe", "")
        other_empl = day.get("other_empl", "")
        d_str = day.get("date").strftime("%d/%m") if day.get("date") else day_key
        # Check if multiple IL on vacation same day
        if vac_il and "," in vac_il:
            errors.append(f"{day_key}: {t('error_two_il_vacation', lang)}")
        if vac_pe and "," in vac_pe:
            errors.append(f"{day_key}: {t('error_two_pe_vacation', lang)}")
        # Check EMB IL conflict: assigned IL employee is on vacation or in other_empl
        emb_il = day.get("emb_il", "")
        if emb_il and emb_il in EMPLOYEES_IL:
            if emb_il == vac_il:
                errors.append(f"❌ {d_str}: {emb_il} שובץ ל-EMB IL אך הוא בחופשה")
            elif emb_il == other_empl:
                errors.append(f"❌ {d_str}: {emb_il} שובץ ל-EMB IL אך הוא כבר במשימת אחר")
        # Check if no IL available for EMB IL at all
        unavail_il = {e for e in [vac_il, other_empl] if e in EMPLOYEES_IL}
        available_il = [e for e in EMPLOYEES_IL if e not in unavail_il]
        if not available_il and not emb_il:
            errors.append(f"❌ {d_str}: אין עובד IL פנוי ל-EMB IL (חופשה + משימת אחר)")
        elif not available_il and emb_il not in EMPLOYEES_PE:
            errors.append(f"❌ {d_str}: כל עובדי IL לא זמינים — EMB IL חייב להיות ממולא")

    theater_count = sum(1 for day in schedule.values() if day.get("theater", ""))

    if yellow_count != 4:
        errors.append(t("warning_yellow_count", lang, count=yellow_count))
    if udex_m != 3:
        errors.append(t("warning_udex_m", lang, count=udex_m))
    if udex_t != 2:
        errors.append(t("warning_udex_t", lang, count=udex_t))
    if theater_count != 3:
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
    vac_il = day.get("vacation_il", "")
    vac_pe = day.get("vacation_pe", "")
    other_empl = day.get("other_empl", "")   # employee on a non-standard task today
    # Exclude vacationing employees AND the employee in "other" task from auto-assign
    active_il = [e for e in EMPLOYEES_IL if e != vac_il and e != other_empl]
    active_pe = [e for e in EMPLOYEES_PE if e != vac_pe and e != other_empl]

    # Entry / Exit — rotate equally among options
    if not day.get("entry"):
        day["entry"] = _least_used(ENTRY_AUTO_OPTIONS, history.get("entry", {}))
    if not day.get("exit"):
        day["exit"] = _least_used(EXIT_AUTO_OPTIONS, history.get("exit", {}))

    # ── Step 1: EMB IL ──────────────────────────────────────────────────────
    # Normally an IL employee; if IL on vacation assign a PE employee instead
    if not day.get("emb_il"):
        if active_il:
            day["emb_il"] = _least_used(active_il, history.get("emb_il", {}))
        elif active_pe:
            day["emb_il"] = _least_used(active_pe, history.get("emb_il", {}))
    emb_il = day.get("emb_il", "")

    # ── Step 2: Apt IL ──────────────────────────────────────────────────────
    # Must differ from EMB IL (no double-assignment)
    if not day.get("apt_il"):
        apt_il_opts = [e for e in active_il if e != emb_il]
        if apt_il_opts:
            day["apt_il"] = _least_used(apt_il_opts, history.get("apt_il", {}))
    apt_il = day.get("apt_il", "")

    # ── Step 3: Apt PE ──────────────────────────────────────────────────────
    # One PE employee for the apartment (must differ from emb_il if emb_il is PE)
    if not day.get("apt_pe"):
        emb_il_pe = emb_il if emb_il in EMPLOYEES_PE else ""
        apt_pe_opts = [e for e in active_pe if e != emb_il_pe]
        if apt_pe_opts:
            day["apt_pe"] = _least_used(apt_pe_opts, history.get("apt_pe", {}))
    apt_pe = day.get("apt_pe", "")

    # ── Step 4: EMB PE ──────────────────────────────────────────────────────
    # Normally TWO PE employees (pair); single only when limited by vacation+Apt PE
    # Cannot use: person already in Apt PE, or PE person doing EMB IL
    if not day.get("emb_pe"):
        emb_il_pe = emb_il if emb_il in EMPLOYEES_PE else ""
        available = [e for e in active_pe if e != apt_pe and e != emb_il_pe]

        if len(available) >= 2:
            # Build available pairs in canonical EMPLOYEES_PE order
            pairs = [
                f"{EMPLOYEES_PE[i]}+{EMPLOYEES_PE[j]}"
                for i in range(len(EMPLOYEES_PE))
                for j in range(i + 1, len(EMPLOYEES_PE))
                if EMPLOYEES_PE[i] in available and EMPLOYEES_PE[j] in available
            ]
            if pairs:
                day["emb_pe"] = _least_used(pairs, history.get("emb_pe", {}))
        elif len(available) == 1:
            day["emb_pe"] = available[0]

    # ── Arrival point ───────────────────────────────────────────────────────
    if not day.get("arrival_point"):
        day["arrival_point"] = _least_used(
            [p for p in ARRIVAL_POINT_OPTIONS if p],
            history.get("arrival_point", {})
        )

    # ── Axis morning / noon ─────────────────────────────────────────────────
    axis_vals = [v for v in AXIS_OPTIONS if v]
    if not day.get("axis_morning") and axis_vals:
        day["axis_morning"] = _least_used(axis_vals, history.get("axis_morning", {}))
    if not day.get("axis_noon") and axis_vals:
        day["axis_noon"] = _least_used(axis_vals, history.get("axis_noon", {}))

    # ── Wait spots ──────────────────────────────────────────────────────────
    wait_vals = [v for v in WAIT_SPOT_OPTIONS if v]
    if not day.get("wait_morning") and wait_vals:
        day["wait_morning"] = _least_used(wait_vals, history.get("wait_morning", {}))
    if not day.get("wait_noon") and wait_vals:
        day["wait_noon"] = _least_used(wait_vals, history.get("wait_noon", {}))

    # NOTE: taxis assigned after vehicle type is known (in auto_assign_week_vehicles_udex)
    return day


def auto_assign_week_vehicles_udex(schedule: dict, history: dict = None) -> dict:
    """
    Assign VEHICLE (4 YELLOW total morning+noon), UDEX (3 EMB-M + 2 EMB-T),
    Theater (3 days), and Taxis (only on YELLOW days).
    """
    if history is None:
        history = {}
    keys = list(schedule.keys())

    # YELLOW: 4 slots total across morning+noon for the week
    slots = [(k, "vehicle_morning") for k in keys] + [(k, "vehicle_noon") for k in keys]
    unassigned = [(k, f) for k, f in slots if not schedule[k].get(f)]
    yellow_needed = 4 - sum(
        1 for k in keys
        for f in ("vehicle_morning", "vehicle_noon")
        if schedule[k].get(f) == "YELLOW"
    )
    if yellow_needed > 0 and len(unassigned) >= yellow_needed:
        chosen = random.sample(unassigned, yellow_needed)
        for k, f in chosen:
            schedule[k][f] = "YELLOW"
    for k, f in unassigned:
        if not schedule[k].get(f):
            schedule[k][f] = "BLACK"

    # UDEX: 3 M-type (EMB-M/R-M) + 2 T-type (EMB-T/R-T) — balance within each type via history
    udex_unassigned = [k for k in keys if not schedule[k].get("udex")]
    udex_m_needed = 3 - sum(1 for k in keys if schedule[k].get("udex") in ("EMB-M", "R-M"))
    udex_t_needed = 2 - sum(1 for k in keys if schedule[k].get("udex") in ("EMB-T", "R-T"))
    random.shuffle(udex_unassigned)
    # Track within-call counts to avoid repeating the same M/T sub-type
    m_hist = dict(history.get("udex", {}))
    t_hist = dict(history.get("udex", {}))
    for _ in range(max(0, udex_m_needed)):
        if udex_unassigned:
            chosen = _least_used(["EMB-M", "R-M"], m_hist)
            m_hist[chosen] = m_hist.get(chosen, 0) + 1
            schedule[udex_unassigned.pop(0)]["udex"] = chosen
    for _ in range(max(0, udex_t_needed)):
        if udex_unassigned:
            chosen = _least_used(["EMB-T", "R-T"], t_hist)
            t_hist[chosen] = t_hist.get(chosen, 0) + 1
            schedule[udex_unassigned.pop(0)]["udex"] = chosen

    # Theater: assign to exactly 3 days per week
    theater_vals = [v for v in THEATER_OPTIONS if v]
    theater_unassigned = [k for k in keys if not schedule[k].get("theater")]
    theater_needed = 3 - sum(1 for k in keys if schedule[k].get("theater"))
    if theater_needed > 0 and len(theater_unassigned) >= theater_needed:
        chosen_theater_days = random.sample(theater_unassigned, theater_needed)
        for k in chosen_theater_days:
            schedule[k]["theater"] = _least_used(theater_vals, history.get("theater", {}))

    # Taxis: morning taxis only when vehicle_morning=YELLOW; noon taxis only when vehicle_noon=YELLOW
    taxi_vals = ["1", "2", "3", "4", "5"]
    for k in keys:
        day = schedule[k]
        yellow_morning = day.get("vehicle_morning") == "YELLOW"
        yellow_noon    = day.get("vehicle_noon")    == "YELLOW"

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
