"""
Statistics computation: per-employee and per-field distributions.
"""
from schedule_logic import EMPLOYEES_IL, EMPLOYEES_PE, ALL_EMPLOYEES
from archive_storage import list_archive, load_schedule
from datetime import date

EMPLOYEE_ROLES = ["emb_il", "apt_il", "emb_pe", "apt_pe"]
EMPLOYEE_ROLE_LABELS = {
    "emb_il": "EMB IL",
    "apt_il": "R IL",
    "emb_pe": "EMB PE",
    "apt_pe": "R PE",
}

# Annual vacation budget per employee
VACATION_BUDGET = {
    "LEON": 14, "CUY": 14,
    "HALCON": 30, "CHCHORRO": 30, "BUHO": 30,
}

VALUE_FIELDS = [
    ("entry",           "Entry"),
    ("exit",            "Exit"),
    ("arrival_point",   "Arrival Point"),
    ("theater",         "Theater"),
    ("udex",            "UDEX"),
    ("vehicle_morning", "Vehicle Morning"),
    ("axis_morning",    "Axis Morning"),
    ("wait_morning",    "Wait Morning"),
    ("vehicle_noon",    "Vehicle Noon"),
    ("axis_noon",       "Axis Noon"),
    ("wait_noon",       "Wait Noon"),
]

# Normalize old theater option names to current names
_THEATER_NORMALIZE = {
    "מראה/espejo": "משקפת",
    "רדיו/radio":  "רדיו",
    "תמונות/fotos": "תמונות",
}

# Normalize old exit option names (renamed in the system)
_EXIT_NORMALIZE = {
    "10-T": "13-T",
    "13-D": "10-D",
}


def compute_stats(schedules: list) -> tuple:
    """
    Aggregate stats from a list of week schedule dicts.
    Returns:
        emp_counts      {employee: {role: count}}
        field_counts    {field_key: {value: count}}
        num_days        total number of working days across all schedules
        vacation_counts {employee: days_on_vacation}
    """
    emp_counts = {e: {r: 0 for r in EMPLOYEE_ROLES} for e in ALL_EMPLOYEES}
    field_counts = {f: {} for f, _ in VALUE_FIELDS}
    vacation_counts = {e: 0 for e in ALL_EMPLOYEES}
    other_counts = {e: 0 for e in ALL_EMPLOYEES}
    num_days = 0

    for schedule in schedules:
        for day in schedule.values():
            num_days += 1

            # Single-person roles
            for role in ("emb_il", "apt_il", "apt_pe"):
                val = day.get(role, "")
                if val in emp_counts:
                    emp_counts[val][role] += 1

            # EMB PE: can be "A+B" pair or single
            emb_pe = day.get("emb_pe", "")
            if emb_pe:
                for emp in emb_pe.split("+"):
                    if emp in emp_counts:
                        emp_counts[emp]["emb_pe"] += 1

            # Value fields (normalize renamed option values)
            for field, _ in VALUE_FIELDS:
                val = day.get(field, "")
                if val:
                    if field == "theater":
                        val = _THEATER_NORMALIZE.get(val, val)
                    elif field == "exit":
                        val = _EXIT_NORMALIZE.get(val, val)
                    field_counts[field][val] = field_counts[field].get(val, 0) + 1

            # Vacation
            for vac_field in ("vacation_il", "vacation_pe"):
                vac = day.get(vac_field, "")
                if vac and vac in vacation_counts:
                    vacation_counts[vac] += 1

            # Other task
            other = day.get("other_empl", "")
            if other and other in other_counts:
                other_counts[other] += 1

    return emp_counts, field_counts, num_days, vacation_counts, other_counts


def load_period_schedules(year: str = None, month: str = None) -> list:
    """Load archived schedules filtered by year and/or month string (e.g. '2026', '03')."""
    arch = list_archive()
    schedules = []
    for yr, months in arch.items():
        if year and yr != year:
            continue
        for mo, weeks in months.items():
            if month and mo != month:
                continue
            for ws_str in weeks:
                s = load_schedule(date.fromisoformat(ws_str))
                if s:
                    schedules.append(s)
    return schedules
