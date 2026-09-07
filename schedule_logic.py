"""
Business logic for schedule generation, validation, and equality tracking.
All employee lists, option lists and weekly targets come from app_config
(config.json), so Settings-page edits apply on the next rerun.
"""
import random
from datetime import date, timedelta
from itertools import combinations

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
    size = cfg.section_size(sec)
    out = [""] + people
    if size >= 2:
        out += _combos(people, min(size, len(people)))
    return out


def _combos(pool: list, n: int, cap: int = 300) -> list:
    """Every way of picking n names out of pool, joined with "+"."""
    if n <= 0 or not pool:
        return []
    if n >= len(pool):
        return ["+".join(pool)]
    out = []
    for combo in combinations(pool, n):
        out.append("+".join(combo))
        if len(out) >= cap:
            break
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

    extras = cfg.active_extras()
    extra_counts = {cfg.extra_row_key(e): {"m": 0, "n": 0} for e in extras}
    sections = cfg.all_sections()
    quotas = [dict(q, seen=0) for q in cfg.weekly_targets()]

    for day_key, day in schedule.items():
        for q in quotas:
            value = day.get(q["field"], "")
            if (value == q["value"]) if q["value"] else bool(value):
                q["seen"] += 1

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
        for wp in cfg.active_workplaces():
            missing = next((s for s in cfg.workplace_sections(wp)
                            if cfg.section_required(s) and cfg.section_size(s)
                            and not day.get(s["row_key"])), None)
            if missing:
                errors.append(f"{d_str}: " + t(
                    "warn_wp_skipped", lang, w=cfg.workplace_name(wp),
                    s=cfg.section_label(wp, missing)))

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
            if not people and not cfg.section_required(sec) and cfg.section_size(sec):
                pool = [e for e in (cfg.group_employees(sec.get("group_id"))
                                    if group else cfg.all_employees())
                        if e not in (vac, other_empl)]
                if not pool:
                    errors.append(f"❌ {d_str}: " + t(
                        "err_sec_none", lang, s=label,
                        g=cfg.group_name(group) if group else "—"))

    for q in quotas:
        if q["seen"] == q["count"]:
            continue
        name = cfg.row_label(q["field"], lang)
        errors.append(
            t("warn_target", lang, f=name, v=q["value"], n=q["seen"], t=q["count"])
            if q["value"] else
            t("warn_target_any", lang, f=name, n=q["seen"], t=q["count"]))
    for et in extras:
        counts, tg = extra_counts[cfg.extra_row_key(et)], cfg.extra_targets(et)
        name = cfg.extra_label(et, lang)
        if counts["m"] != tg["morning"]:
            errors.append(t("warn_extra_m", lang, n=counts["m"],
                            t=tg["morning"], f=name))
        if counts["n"] != tg["noon"]:
            errors.append(t("warn_extra_n", lang, n=counts["n"],
                            t=tg["noon"], f=name))

    return errors


# ── Auto-assign helpers ────────────────────────────────────────────────────

def auto_assign_day(day: dict, history: dict, week_days: list) -> dict:
    """
    Fill in auto-assigned fields for a single day from the equality history.
    Everything comes from the configuration:
    - each workplace section draws from its own employee group
    - nobody is booked twice on the same day
    - workplaces are staffed in priority order
    - a section holds max_workers employees, joined with "+" when 2 or more
    - a workplace whose required sections cannot be filled is skipped whole
    - taxis are assigned later (once the vehicle type is known) in
      auto_assign_week_vehicles_udex
    """
    day = day.copy()
    other_empl = day.get("other_empl", "")
    axis_vals = cfg.options("axis")
    gov = cfg.governed_fields()          # quota-governed rows are filled later

    # ── entry/exit and both axes: independent, each balanced against its own
    #    target percentages ───────────────────────────────────────────────────
    if "axis_morning" not in gov and not day.get("axis_morning") and axis_vals:
        day["axis_morning"] = _least_used(
            axis_vals, history.get("axis_morning", {}), "axis_morning")
    if "axis_noon" not in gov and not day.get("axis_noon") and axis_vals:
        day["axis_noon"] = _least_used(
            axis_vals, history.get("axis_noon", {}), "axis_noon")
    if "entry" not in gov and not day.get("entry"):
        day["entry"] = _least_used(
            entry_auto_options(), history.get("entry", {}), "entry")
    if "exit" not in gov and not day.get("exit"):
        day["exit"] = _least_used(
            exit_auto_options(), history.get("exit", {}), "exit")

    # ── workplaces in priority order ────────────────────────────────────────
    # A workplace whose required sections cannot all be filled is skipped
    # whole — its optional rows stay empty too, and the people it would have
    # used stay free for the workplaces below it.
    governed = cfg.governed_fields()
    taken = set()
    for _, sec in cfg.all_sections():          # whatever is already placed
        if day.get(sec["row_key"]):
            taken.update(e for e in str(day[sec["row_key"]]).split("+") if e)

    def _pick(sec, busy):
        size = cfg.section_size(sec)
        if not size:
            return ""
        group = cfg.group_by_id(sec.get("group_id"))
        vac = day.get(cfg.vac_field(group), "") if group else ""
        pool = [e for e in (cfg.group_employees(sec.get("group_id"))
                            if group else cfg.all_employees())
                if e not in (vac, other_empl) and e not in busy]
        if not pool:
            return ""
        counts = history.get(sec["row_key"], {})
        if size >= 2:
            return _least_used(_combos(pool, min(size, len(pool))), counts)
        return _least_used(pool, counts)

    for wp in cfg.active_workplaces():
        assignable = [s for s in cfg.workplace_sections(wp)
                      if cfg.section_size(s) and s["row_key"] not in governed]
        open_secs = [s for s in assignable if not day.get(s["row_key"])]
        # required rows first, on a trial set we can throw away
        trial, busy, ok = {}, set(taken), True
        for sec in (s for s in open_secs if cfg.section_required(s)):
            choice = _pick(sec, busy)
            if not choice:
                ok = False
                break
            trial[sec["row_key"]] = choice
            busy.update(e for e in str(choice).split("+") if e)
        if not ok:
            continue                            # whole workplace skipped today
        day.update(trial)
        taken |= busy
        for sec in (s for s in open_secs if not cfg.section_required(s)):
            choice = _pick(sec, taken)
            if not choice:
                continue
            day[sec["row_key"]] = choice
            taken.update(e for e in str(choice).split("+") if e)

    # ── Arrival point ───────────────────────────────────────────────────────
    if "arrival_point" not in gov and not day.get("arrival_point"):
        day["arrival_point"] = _least_used(
            cfg.options("arrival_point"), history.get("arrival_point", {}),
            "arrival_point")

    # ── Wait spots ──────────────────────────────────────────────────────────
    wait_vals = cfg.options("wait_spot")
    if "wait_morning" not in gov and not day.get("wait_morning") and wait_vals:
        day["wait_morning"] = _least_used(
            wait_vals, history.get("wait_morning", {}), "wait_spot")
    if "wait_noon" not in gov and not day.get("wait_noon") and wait_vals:
        day["wait_noon"] = _least_used(
            wait_vals, history.get("wait_noon", {}), "wait_spot")

    # NOTE: taxis assigned after vehicle type is known (in auto_assign_week_vehicles_udex)
    return day


def apply_weekly_targets(schedule: dict, history: dict = None) -> dict:
    """Place every weekly quota, then decide what the untargeted days of those
    same fields get. A field carrying a value-less quota stays blank outside
    it; a field carrying only value quotas fills its remaining days from the
    values no quota claimed."""
    history = history or {}
    keys = list(schedule.keys())
    by_field = {}
    for q in cfg.weekly_targets():
        by_field.setdefault(q["field"], []).append(q)

    holiday = cfg.special("holiday")
    for field, quotas in by_field.items():
        # the holiday value is manual-only, so it never fills a spare day —
        # an explicit quota on it still places it
        claimed = [q["value"] for q in quotas if q["value"]] + [holiday]
        any_q = next((q for q in quotas if not q["value"]), None)
        counts = dict(history.get(field, {}))

        for q in (x for x in quotas if x["value"]):
            need = q["count"] - sum(1 for k in keys if schedule[k].get(field) == q["value"])
            free = [k for k in keys if not schedule[k].get(field)]
            random.shuffle(free)
            for k in free[:max(0, need)]:
                schedule[k][field] = q["value"]
                counts[q["value"]] = counts.get(q["value"], 0) + 1

        pool = [v for v in cfg.target_field_values(field) if v not in claimed]
        if any_q:
            # "any value" quota: fill up to count days, leave the rest blank
            need = any_q["count"] - sum(1 for k in keys if schedule[k].get(field))
            free = [k for k in keys if not schedule[k].get(field)]
            random.shuffle(free)
            for k in free[:max(0, need)]:
                if not pool:
                    break
                chosen = _least_used(pool, counts)
                counts[chosen] = counts.get(chosen, 0) + 1
                schedule[k][field] = chosen
        elif pool:
            # only exact-value quotas: the other days take the unclaimed values
            for k in keys:
                if not schedule[k].get(field):
                    chosen = _least_used(pool, counts)
                    counts[chosen] = counts.get(chosen, 0) + 1
                    schedule[k][field] = chosen
    return schedule


def auto_assign_week_vehicles_udex(schedule: dict, history: dict = None) -> dict:
    """
    Apply the weekly quotas, then fill what they do not govern: the extra-task
    rows (their own morning/noon targets), any vehicle row without a quota, and
    the taxis (only on special-vehicle slots).
    """
    if history is None:
        history = {}
    keys = list(schedule.keys())
    gov = cfg.governed_fields()
    vehicle_special = cfg.special("vehicle_special")

    apply_weekly_targets(schedule, history)

    # a vehicle row with no quota of its own still needs a value on every day
    veh_vals = cfg.options("vehicle")
    for field in ("vehicle_morning", "vehicle_noon"):
        if field in gov or not veh_vals:
            continue
        counts = dict(history.get(field, {}))
        for k in keys:
            if not schedule[k].get(field):
                chosen = _least_used(veh_vals, counts, "vehicle")
                counts[chosen] = counts.get(chosen, 0) + 1
                schedule[k][field] = chosen

    # Extra tasks: each row gets its own targets, balanced within each type
    for et in cfg.active_extras():
        row_key = cfg.extra_row_key(et)
        if row_key in gov:
            continue
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
