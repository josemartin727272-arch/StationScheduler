"""
Statistics computation: per-employee and per-field distributions.
"""
import app_config as cfg
from archive_storage import list_archive, load_schedule
from datetime import date

# Roles are the workplace sections the station configured, so they change with
# the configuration rather than being fixed here.
EMPLOYEE_ROLES = cfg.section_row_keys()
EMPLOYEE_ROLE_LABELS = {sec["row_key"]: cfg.section_label(w, sec)
                        for w, sec in cfg.all_sections()}


def vacation_budget() -> dict:
    """Annual vacation budget per employee (from config.json)."""
    return cfg.vacation_budget()

VALUE_FIELDS = [
    ("entry",           "Entry"),
    ("exit",            "Exit"),
    ("arrival_point",   "Arrival Point"),
    ("theater",         "Theater"),
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
    all_employees = cfg.all_employees()
    roles = cfg.section_row_keys()
    emp_counts = {e: {r: 0 for r in roles} for e in all_employees}
    field_counts = {f: {} for f, _ in VALUE_FIELDS}
    for _et in cfg.active_extras():          # one column per extra-task row
        field_counts.setdefault(cfg.extra_row_key(_et), {})
    vacation_counts = {e: 0 for e in all_employees}
    other_counts = {e: 0 for e in all_employees}
    num_days = 0

    for schedule in schedules:
        for day in schedule.values():
            num_days += 1

            # Workplace sections; a section may hold a pair ("A+B") — credit both
            for role in roles:
                for emp in str(day.get(role, "")).split("+"):
                    if emp and emp in emp_counts:
                        emp_counts[emp][role] += 1

            # Value fields (normalize renamed option values)
            for field in field_counts:
                val = day.get(field, "")
                if val:
                    if field == "theater":
                        val = _THEATER_NORMALIZE.get(val, val)
                    elif field == "exit":
                        val = _EXIT_NORMALIZE.get(val, val)
                    field_counts[field][val] = field_counts[field].get(val, 0) + 1

            # Vacation — one column per active group
            for vac_field in cfg.vac_fields():
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
