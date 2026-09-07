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

# Entry, exit and both axes are independent: nothing constrains an axis to a
# particular entry/exit. The entry_axis_map / exit_axis_map in config.json are
# free-text notes for humans and are deliberately never read here.


def entry_auto_options() -> list:
    holiday = cfg.special("holiday")
    return [o for o in cfg.options("entry") if o != holiday]


def exit_auto_options() -> list:
    holiday = cfg.special("holiday")
    return [o for o in cfg.options("exit") if o != holiday]


def section_options(row_key: str) -> list:
    """Pickable values for a workplace-section row: the employees of its group,
    plus every pair (A+B) when the section allows a pair."""
    sx = cfg.section_by_row(row_key)
    if not sx:
        return [""] + cfg.all_employees()
    _, sec = sx
    people = cfg.group_employees(sec.get("group_id")) or cfg.all_employees()
    out = [""] + people
    if sec.get("allow_pair"):
        out += [f"{a}+{b}" for i, a in enumerate(people) for b in people[i + 1:]]
    return out


# ── Data model ─────────────────────────────────────────────────────────────

def empty_week(week_start: date) -> dict:
    """Blank weekly schedule keyed by date string, one entry per configured
    working day. Monday is offset 0, so a Sunday shift lands at the end."""
    if week_start.weekday() != 0:
        week_start = week_start - timedelta(days=week_start.weekday())
    fields = cfg.schedule_fields()
    schedule = {}
    for name in cfg.work_days():
        day = week_start + timedelta(days=cfg.DOW_ORDER.index(name))
        entry = {f: "" for f in fields}
        entry["date"] = day
        schedule[day.isoformat()] = entry
    return dict(sorted(schedule.items()))


# ── Validation ─────────────────────────────────────────────────────────────

def validate_schedule(schedule: dict, lang: str = "he") -> list:
    """Return list of warning/error strings. Every rule is derived from the
    configured groups, workplaces and extra task — nothing is hard-coded."""
    from translations import t
    errors = []

    targets = cfg.targets()
    vehicle_special = cfg.special("vehicle_special")
    extras = cfg.active_extras()
    extra_counts = {cfg.extra_row_key(e): {"m": 0, "n": 0} for e in extras}
    sections = cfg.all_sections()

    yellow_count = 0

    for day_key, day in schedule.items():
        if day.get("vehicle_morning") == vehicle_special:
            yellow_count += 1
        if day.get("vehicle_noon") == vehicle_special:
            yellow_count += 1

        for et in extras:
            row_key = cfg.extra_row_key(et)
            val = day.get(row_key, "")
            if not val:
                continue
            if val in et.get("morning_values", []):
                extra_counts[row_key]["m"] += 1
            elif val in et.get("noon_values", []):
                extra_counts[row_key]["n"] += 1

        other_empl = day.get("other_empl", "")
        d_str = day.get("date").strftime("%d/%m") if day.get("date") else day_key
        placed = {}                       # employee → the section holding them
        for wp, sec in sections:
            row_key = sec["row_key"]
            group = cfg.group_by_id(sec.get("group_id"))
            label = cfg.section_label(wp, sec)
            vac = day.get(cfg.vac_field(group), "") if group else ""
            people = [e for e in str(day.get(row_key, "")).split("+") if e]
            for e in people:
                if e == vac:
                    errors.append(f"❌ {d_str}: " +
                                  t("err_sec_vac", lang, e=e, s=label))
                elif e == other_empl:
                    errors.append(f"❌ {d_str}: " +
                                  t("err_sec_other", lang, e=e, s=label))
                if e in placed:
                    errors.append(f"{d_str}: " +
                                  t("warn_sec_dup", lang, e=e, s=placed[e], s2=label))
                else:
                    placed[e] = label
            if not people:
                pool = [e for e in (cfg.group_employees(sec.get("group_id"))
                                    if group else cfg.all_employees())
                        if e not in (vac, other_empl)]
                if not pool:
                    errors.append(f"❌ {d_str}: " + t(
                        "err_sec_none", lang, s=label,
                        g=cfg.group_name(group) if group else "—"))

    theater_count = sum(1 for day in schedule.values() if day.get("theater", ""))

    if yellow_count != targets["yellow_per_week"]:
        errors.append(t("warning_yellow_count", lang, count=yellow_count))
    for et in extras:
        counts, tg = extra_counts[cfg.extra_row_key(et)], cfg.extra_targets(et)
        name = cfg.extra_label(et, lang)
        if counts["m"] != tg["morning"]:
            errors.append(t("warn_extra_m", lang, n=counts["m"],
                            t=tg["morning"], f=name))
        if counts["n"] != tg["noon"]:
            errors.append(t("warn_extra_n", lang, n=counts["n"],
                            t=tg["noon"], f=name))
    if theater_count != targets["theater_per_week"]:
        errors.append(t("warning_theater_count", lang, count=theater_count))

    return errors


# ── Auto-assign helpers ────────────────────────────────────────────────────

def auto_assign_day(day: dict, history: dict, week_days: list) -> dict:
    """
    Fill in auto-assigned fields for a single day from the equality history.
    Everything comes from the configuration:
    - each workplace section draws from its own employee group
    - nobody is booked twice on the same day
    - a section marked allow_pair may hold two employees ("A+B")
    - taxis are assigned later (once the vehicle type is known) in
      auto_assign_week_vehicles_udex
    """
    day = day.copy()
    other_empl = day.get("other_empl", "")
    axis_vals = cfg.options("axis")

    # ── entry/exit and both axes: independent, each balanced against its own
    #    target percentages ───────────────────────────────────────────────────
    if not day.get("axis_morning") and axis_vals:
        day["axis_morning"] = _least_used(
            axis_vals, history.get("axis_morning", {}), "axis_morning")
    if not day.get("axis_noon") and axis_vals:
        day["axis_noon"] = _least_used(
            axis_vals, history.get("axis_noon", {}), "axis_noon")
    if not day.get("entry"):
        day["entry"] = _least_used(
            entry_auto_options(), history.get("entry", {}), "entry")
    if not day.get("exit"):
        day["exit"] = _least_used(
            exit_auto_options(), history.get("exit", {}), "exit")

    # ── workplace sections, in configured order ─────────────────────────────
    taken = set()
    for wp, sec in cfg.all_sections():
        row_key = sec["row_key"]
        if day.get(row_key):
            taken.update(e for e in str(day[row_key]).split("+") if e)
            continue
        group = cfg.group_by_id(sec.get("group_id"))
        vac = day.get(cfg.vac_field(group), "") if group else ""
        pool = [e for e in (cfg.group_employees(sec.get("group_id"))
                            if group else cfg.all_employees())
                if e not in (vac, other_empl) and e not in taken]
        if not pool:
            continue
        if sec.get("allow_pair") and len(pool) >= 2:
            pairs = [f"{a}+{b}" for i, a in enumerate(pool) for b in pool[i + 1:]]
            choice = _least_used(pairs, history.get(row_key, {}))
        else:
            choice = _least_used(pool, history.get(row_key, {}))
        day[row_key] = choice
        taken.update(e for e in str(choice).split("+") if e)

    # ── Arrival point ───────────────────────────────────────────────────────
    if not day.get("arrival_point"):
        day["arrival_point"] = _least_used(
            cfg.options("arrival_point"), history.get("arrival_point", {}),
            "arrival_point")

    # ── Wait spots ──────────────────────────────────────────────────────────
    wait_vals = cfg.options("wait_spot")
    if not day.get("wait_morning") and wait_vals:
        day["wait_morning"] = _least_used(
            wait_vals, history.get("wait_morning", {}), "wait_spot")
    if not day.get("wait_noon") and wait_vals:
        day["wait_noon"] = _least_used(
            wait_vals, history.get("wait_noon", {}), "wait_spot")

    # NOTE: taxis assigned after vehicle type is known (in auto_assign_week_vehicles_udex)
    return day


def auto_assign_week_vehicles_udex(schedule: dict, history: dict = None,
                                   monthly_history: dict = None) -> dict:
    """
    Assign VEHICLE (yellow_per_week special vehicles across morning+noon,
    default 3 of 10 = 70/30; the morning/noon split is chosen to best balance
    the last-month history), UDEX (udex_m + udex_t), Theater
    (theater_per_week days), and Taxis (only on special-vehicle slots).
    """
    if history is None:
        history = {}
    keys = list(schedule.keys())

    targets = cfg.targets()
    vehicle_special = cfg.special("vehicle_special")
    vehicle_regular = next(
        (v for v in cfg.options("vehicle") if v != vehicle_special), "")


    # Special vehicle: choose the morning/noon split that best balances the
    # monthly history (falls back to the cumulative history if not provided)
    mh = monthly_history if monthly_history is not None else history
    y_m_hist = mh.get("vehicle_morning", {}).get(vehicle_special, 0)
    y_n_hist = mh.get("vehicle_noon", {}).get(vehicle_special, 0)
    cur_m = sum(1 for k in keys if schedule[k].get("vehicle_morning") == vehicle_special)
    cur_n = sum(1 for k in keys if schedule[k].get("vehicle_noon") == vehicle_special)
    free_m = [k for k in keys if not schedule[k].get("vehicle_morning")]
    free_n = [k for k in keys if not schedule[k].get("vehicle_noon")]
    random.shuffle(free_m)
    random.shuffle(free_n)
    need = max(0, targets["yellow_per_week"] - cur_m - cur_n)
    # Allowed splits: each period gets at least one special vehicle when the
    # week has 2+ to place (e.g. for 3 → only 2+1 or 1+2, never 3+0)
    if need >= 2 and cur_m == 0 and cur_n == 0:
        candidates = list(range(1, need))
    else:
        candidates = list(range(need + 1))
    best_x, best_diff = 0 if 0 in candidates else (candidates[0] if candidates else 0), None
    random.shuffle(candidates)  # random tie-break between equal splits
    for x in candidates:
        if x > len(free_m) or need - x > len(free_n):
            continue
        diff = abs((y_m_hist + cur_m + x) - (y_n_hist + cur_n + need - x))
        if best_diff is None or diff < best_diff:
            best_diff, best_x = diff, x
    for k in free_m[:best_x]:
        schedule[k]["vehicle_morning"] = vehicle_special
    for k in free_n[:need - best_x]:
        schedule[k]["vehicle_noon"] = vehicle_special
    for k in keys:
        for f in ("vehicle_morning", "vehicle_noon"):
            if not schedule[k].get(f):
                schedule[k][f] = vehicle_regular

    # Extra tasks: each row gets its own targets, balanced within each type
    for et in cfg.active_extras():
        row_key = cfg.extra_row_key(et)
        m_vals = [v for v in et.get("morning_values", []) if v]
        n_vals = [v for v in et.get("noon_values", []) if v]
        tg = cfg.extra_targets(et)
        unassigned = [k for k in keys if not schedule[k].get(row_key)]
        m_needed = tg["morning"] - sum(
            1 for k in keys if schedule[k].get(row_key) in m_vals)
        n_needed = tg["noon"] - sum(
            1 for k in keys if schedule[k].get(row_key) in n_vals)
        random.shuffle(unassigned)
        m_hist = dict(history.get(row_key, {}))
        n_hist = dict(history.get(row_key, {}))
        for _ in range(max(0, m_needed)):
            if unassigned and m_vals:
                chosen = _least_used(m_vals, m_hist)
                m_hist[chosen] = m_hist.get(chosen, 0) + 1
                schedule[unassigned.pop(0)][row_key] = chosen
        for _ in range(max(0, n_needed)):
            if unassigned and n_vals:
                chosen = _least_used(n_vals, n_hist)
                n_hist[chosen] = n_hist.get(chosen, 0) + 1
                schedule[unassigned.pop(0)][row_key] = chosen

    # Theater: assign to exactly theater_per_week days
    theater_vals = cfg.options("theater")
    theater_unassigned = [k for k in keys if not schedule[k].get("theater")]
    theater_needed = targets["theater_per_week"] - sum(
        1 for k in keys if schedule[k].get("theater"))
    if theater_needed > 0 and len(theater_unassigned) >= theater_needed and theater_vals:
        chosen_theater_days = random.sample(theater_unassigned, theater_needed)
        for k in chosen_theater_days:
            schedule[k]["theater"] = _least_used(theater_vals, history.get("theater", {}))

    # Taxis: morning taxis only when vehicle_morning is special; noon likewise.
    # Each taxi row draws from its own option list.
    for k in keys:
        day = schedule[k]
        yellow_morning = day.get("vehicle_morning") == vehicle_special
        yellow_noon    = day.get("vehicle_noon")    == vehicle_special

        # noon taxi rows share the morning rows' percentage tables
        for field, pct_key in [("taxi_apt", "taxi_apt"),
                               ("taxi_arrival", "taxi_arrival")]:
            if yellow_morning:
                if not day.get(field):
                    day[field] = _least_used(
                        cfg.options(field), history.get(field, {}), pct_key)
            else:
                day[field] = ""

        for field, pct_key in [("taxi_emb", "taxi_apt"),
                               ("taxi_arrival_noon", "taxi_arrival")]:
            if yellow_noon:
                if not day.get(field):
                    day[field] = _least_used(
                        cfg.options(field), history.get(field, {}), pct_key)
            else:
                day[field] = ""

        schedule[k] = day

    return schedule


def _least_used(options: list, counts: dict, field: str = None) -> str:
    """Weighted least-used: pick the option whose share of past use sits
    furthest BELOW its target share. With equal targets — the default — this
    is exactly plain least-used. `field` names an app_config.PCT_FIELDS entry;
    pass None for ad-hoc lists (employees, EMB pairs) that have no table."""
    if not options:
        return ""
    pcts = cfg.field_pcts(field) if field else None
    pool = list(options)
    if pcts:  # an explicit 0% target means "never assign"
        positive = [o for o in pool if pcts.get(o) is None or pcts[o] > 0]
        if positive:
            pool = positive
    # values outside the table (a taxi list that diverged, say) get the mean
    # target so they stay neutral instead of silently dropping to 0%
    covered = [pcts[o] for o in pool if pcts and pcts.get(o) is not None]
    fallback = (sum(covered) / len(covered)) if covered else 1.0
    tgt = {o: max(0.0, pcts[o] if pcts and pcts.get(o) is not None else fallback)
           for o in pool} if pcts else {o: 1.0 for o in pool}
    weight = sum(tgt.values())
    if weight <= 0:
        tgt, weight = {o: 1.0 for o in pool}, float(len(pool))
    total = sum(counts.get(o, 0) for o in pool)

    def gap(o):
        return tgt[o] / weight - (counts.get(o, 0) / total if total else 0.0)

    best = max(gap(o) for o in pool)
    return random.choice([o for o in pool if gap(o) >= best - 1e-9])


def update_history(history: dict, schedule: dict) -> dict:
    """Add this week's assignments to the cumulative history counts."""
    fields_to_track = [
        "entry", "exit", "arrival_point", "theater",
        "axis_morning", "axis_noon",
        "wait_morning", "wait_noon", "taxi_apt", "taxi_arrival",
        "vehicle_morning", "vehicle_noon",
        "taxi_emb", "taxi_arrival_noon",
    ] + cfg.section_row_keys() + cfg.extra_row_keys()
    for day in schedule.values():
        for field in fields_to_track:
            val = day.get(field, "")
            if val:
                history.setdefault(field, {})
                history[field][val] = history[field].get(val, 0) + 1
    return history
