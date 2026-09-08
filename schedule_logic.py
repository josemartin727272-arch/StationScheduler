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
MANUAL_ROWS = {"escort_morning", "escort_noon", "other_empl", "vacation", "trip"}

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
        # the axis must be one the day's entry/exit permits
        # someone cannot be on holiday and away on a trip at once
        on_vac = cfg.away_list(day, "vacation")
        for name in cfg.away_list(day, "trip"):
            if name in on_vac:
                errors.append(f"{d_str}: " + t("warn_vac_trip", lang, e=name))
        # a warning only — the user may knowingly exceed the daily absence cap
        cap = cfg.max_daily_absence()
        if len(cfg.away_today(day)) > cap:
            errors.append(f"{d_str}: " + t("warn_daily_absence", lang, n=cap))

        for value_field, axis_field in (("entry", "axis_morning"),
                                        ("exit", "axis_noon")):
            value, axis = day.get(value_field, ""), day.get(axis_field, "")
            if not value or not axis:
                continue
            if cfg.axis_letter_of(axis) not in cfg.allowed_axes_for(value_field, value):
                errors.append(f"{d_str}: " + t(
                    "warn_axis_rule", lang, f=cfg.row_label(axis_field, lang),
                    a=axis, e=cfg.row_label(value_field, lang), v=value))

        for wp in cfg.active_workplaces():
            missing = next((s for s in cfg.workplace_sections(wp)
                            if cfg.section_required(s) and cfg.section_size(s)
                            and not day.get(s["row_key"])), None)
            if missing:
                errors.append(f"{d_str}: " + t(
                    "warn_wp_skipped", lang, w=cfg.workplace_name(wp),
                    s=cfg.section_label(wp, missing)))
            # a section may be filled and still be under its daily floor
            for sec in cfg.workplace_sections(wp):
                floor = cfg.section_min(sec)
                if not floor or not cfg.section_size(sec):
                    continue
                n = len([e for e in str(day.get(sec["row_key"], "")).split("+") if e])
                if n and n < floor:
                    errors.append(f"{d_str}: " + t(
                        "warn_sec_min", lang, w=cfg.workplace_name(wp),
                        s=cfg.section_label(wp, sec), n=floor))
            wp_floor = cfg.workplace_min_sections(wp)
            staffed = len([s for s in cfg.workplace_sections(wp)
                           if cfg.section_size(s) and day.get(s["row_key"])])
            if staffed < wp_floor:
                errors.append(f"{d_str}: " + t(
                    "warn_wp_min_sections", lang, w=cfg.workplace_name(wp),
                    n=wp_floor, c=staffed))

        placed = {}                       # employee → the section holding them
        for wp, sec in sections:
            row_key = sec["row_key"]
            group = cfg.group_by_id(sec.get("group_id"))
            label = cfg.section_label(wp, sec)
            away = cfg.away_today(day)
            people = [e for e in str(day.get(row_key, "")).split("+") if e]
            for e in people:
                why = cfg.away_reason(day, e)
                if why:
                    errors.append(f"❌ {d_str}: " + t(
                        {"vacation": "err_sec_vac", "trip": "err_sec_trip",
                         "both": "err_sec_both"}[why], lang, e=e, s=label))
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
                        if e not in away and e != other_empl]
                if not pool:
                    errors.append(f"❌ {d_str}: " + t(
                        "err_sec_none", lang, s=label,
                        g=cfg.group_name(group) if group else "—"))

    # configuration-level faults, reported once rather than per day
    for a in cfg.active_axes():
        total = (a.get("pct_u") or 0) + (a.get("pct_d") or 0)
        if total != 100:
            errors.append("❌ " + t("err_axis_ud", lang,
                                    a=cfg.axis_label(a), n=total))
    for kind in ("entry", "exit"):
        for value, rule in cfg.axis_rules(kind).items():
            ids = rule.get("axes") or []
            if not ids:
                continue
            total = sum((rule.get("pcts") or {}).get(x, 0) for x in ids)
            if total != 100:
                errors.append("❌ " + t("err_axis_rule_pct", lang,
                                        f=cfg.row_label(kind, lang),
                                        v=value, n=total))

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
    gov = cfg.governed_fields()          # quota-governed rows are filled later

    # ── entry ↔ morning axis, exit ↔ noon axis ──────────────────────────────
    # The value chooses the axis letter through the station's rules; the axis's
    # own U/D split chooses the side. Whichever is already filled constrains
    # the other.
    for value_field, axis_field, auto_options in (
            ("entry", "axis_morning", entry_auto_options),
            ("exit", "axis_noon", exit_auto_options)):
        pool = auto_options()
        if value_field not in gov and not day.get(value_field) and pool:
            candidates = pool
            if day.get(axis_field):
                narrowed = cfg.values_allowing_axis(
                    value_field, cfg.axis_letter_of(day[axis_field]), pool)
                if narrowed:
                    candidates = narrowed
            day[value_field] = _least_used(
                candidates, history.get(value_field, {}), value_field)
        if axis_field not in gov and not day.get(axis_field) and cfg.active_axes():
            day[axis_field] = _pick_axis(
                value_field, day.get(value_field, ""), history.get(axis_field, {}))

    # ── workplaces in priority order ────────────────────────────────────────
    # A workplace whose required sections cannot all be filled is skipped
    # whole — its optional rows stay empty too, and the people it would have
    # used stay free for the workplaces below it.
    governed = cfg.governed_fields()
    taken = set()
    for _, sec in cfg.all_sections():          # whatever is already placed
        if day.get(sec["row_key"]):
            taken.update(e for e in str(day[sec["row_key"]]).split("+") if e)

    away = cfg.away_today(day)      # vacation and trip both mean unavailable

    def _pick(sec, busy, n):
        """Place exactly n names in a section, or "" when even that fails."""
        if not cfg.section_size(sec):
            return ""
        want = max(1, min(n, cfg.section_target(sec)))
        group = cfg.group_by_id(sec.get("group_id"))
        pool = [e for e in (cfg.group_employees(sec.get("group_id"))
                            if group else cfg.all_employees())
                if e not in away and e != other_empl and e not in busy]
        if len(pool) < want:                 # the floor cannot be met
            return ""
        counts = history.get(sec["row_key"], {})
        if want >= 2:
            return _least_used(_combos(pool, want), counts)
        return _least_used(pool, counts)

    def _top_up(sec, busy, owed):
        """Grow a section that already holds its floor up to max_workers."""
        have = [e for e in str(day.get(sec["row_key"], "")).split("+") if e]
        want = cfg.section_target(sec) - len(have)
        if want <= 0:
            return
        group = cfg.group_by_id(sec.get("group_id"))
        pool = [e for e in (cfg.group_employees(sec.get("group_id"))
                            if group else cfg.all_employees())
                if e not in away and e != other_empl and e not in busy]
        # never grow a row past its floor on someone a later workplace needs
        want = min(want, len(pool) - owed.get(sec.get("group_id") or "", 0))
        if want < 1 or not pool:
            return
        counts = history.get(sec["row_key"], {})
        add = (_least_used(_combos(pool, min(want, len(pool))), counts)
               if want >= 2 else _least_used(pool, counts))
        if not add:
            return
        day[sec["row_key"]] = "+".join(have + [e for e in str(add).split("+") if e])
        busy.update(e for e in str(add).split("+") if e)

    order = cfg.active_workplaces()
    wp_rows, skipped = {}, set()
    for wp in order:
        wp_rows[wp["id"]] = [s for s in cfg.workplace_sections(wp)
                             if cfg.section_size(s) and s["row_key"] not in governed]

    def _free_in(gid, busy):
        """People of a group still up for grabs right now."""
        group = cfg.group_by_id(gid)
        pool = cfg.group_employees(gid) if group else cfg.all_employees()
        return len([e for e in pool
                    if e not in away and e != other_empl and e not in busy])

    def _owed_after(idx, busy):
        """The planning step: heads each group still owes to the minimums of the
        workplaces further down the priority list. A workplace may spend these
        on its own minimum — priority decides that — but never on a spare."""
        need = {}
        for wp2 in order[idx + 1:]:
            rows = wp_rows[wp2["id"]]
            open_rows = [s for s in rows if not day.get(s["row_key"])]
            req = [s for s in open_rows if cfg.section_required(s)]
            for sec in req:
                gid = sec.get("group_id") or ""
                need[gid] = need.get(gid, 0) + max(1, cfg.section_min(sec))
            # one head per role it is still short of, taken from whichever role
            # has the most people free — that is the one it will actually use
            short = (cfg.workplace_min_sections(wp2)
                     - len([s for s in rows if day.get(s["row_key"])]) - len(req))
            for sec in sorted((s for s in open_rows if not cfg.section_required(s)),
                              key=lambda s: -_free_in(s.get("group_id"), busy)):
                if short <= 0:
                    break
                gid = sec.get("group_id") or ""
                need[gid] = need.get(gid, 0) + 1
                short -= 1
        return need

    def _pick_spare(sec, busy, n, owed):
        """A spare head: only from what no later workplace is counting on."""
        slack = (_free_in(sec.get("group_id"), busy)
                 - owed.get(sec.get("group_id") or "", 0))
        return "" if slack < 1 else _pick(sec, busy, min(n, slack))

    # Pass 1 — in priority order, every workplace takes only what it must, so a
    # high-priority workplace cannot spend the people a later one needs to reach
    # its own minimum. Pass 2 hands out the spares afterwards.
    for idx, wp in enumerate(order):
        rows = wp_rows[wp["id"]]
        open_secs = lambda: [s for s in rows if not day.get(s["row_key"])]
        # required rows are hard: all of them, or the workplace is skipped whole.
        # They go first — a role marked required outranks every other row here.
        trial, busy, ok = {}, set(taken), True
        for sec in [s for s in open_secs() if cfg.section_required(s)]:
            choice = _pick(sec, busy, max(1, cfg.section_min(sec)))
            if not choice:
                ok = False
                break
            trial[sec["row_key"]] = choice
            busy.update(e for e in str(choice).split("+") if e)
        if not ok:
            skipped.add(wp["id"])
            continue                            # whole workplace skipped today
        day.update(trial)
        taken |= busy
        # rows carrying their own daily floor come next — preferred, but soft:
        # one that cannot be filled leaves the workplace standing, because the
        # "at least N roles" rule below decides whether the workplace is short
        for sec in [s for s in open_secs() if cfg.section_min(s) > 0]:
            choice = _pick(sec, taken, cfg.section_min(sec))
            if not choice:
                continue
            day[sec["row_key"]] = choice
            taken.update(e for e in str(choice).split("+") if e)
        # "at least N roles staffed": fill roles until the floor is reached,
        # starting with the one whose group the workplaces below need least —
        # staffing this one through PE when IL is idle would starve them
        floor = cfg.workplace_min_sections(wp)
        staffed = lambda: len([s for s in rows if day.get(s["row_key"])])
        if staffed() < floor:
            owed = _owed_after(idx, taken)
            slack = lambda s: (_free_in(s.get("group_id"), taken)
                               - owed.get(s.get("group_id") or "", 0))
            for sec in sorted(open_secs(), key=lambda s: -slack(s)):
                if staffed() >= floor:
                    break
                choice = _pick(sec, taken, 1)
                if not choice:
                    continue
                day[sec["row_key"]] = choice
                taken.update(e for e in str(choice).split("+") if e)

    # Pass 2 — the discretionary half: top staffed rows up to max_workers, then
    # fill whatever optional rows are still open, priority order again.
    for idx, wp in enumerate(order):
        if wp["id"] in skipped:
            continue
        owed = _owed_after(idx, taken)
        for sec in wp_rows[wp["id"]]:
            if day.get(sec["row_key"]):
                _top_up(sec, taken, owed)
        for sec in wp_rows[wp["id"]]:
            if day.get(sec["row_key"]):
                continue
            choice = _pick_spare(sec, taken, 1, owed)
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


def _pick_axis(kind: str, value: str, counts: dict) -> str:
    """Pick a composite axis for `value`: the letter comes from that value's
    rule percentages balanced against history, then the chosen axis's own U/D
    split picks the side — also balanced against history, per letter."""
    counts = counts or {}
    letters = cfg.allowed_axes_for(kind, value)
    if not letters:
        return ""
    letter_counts = {}
    for v, n in counts.items():
        key = cfg.axis_letter_of(v)
        letter_counts[key] = letter_counts.get(key, 0) + n
    letter = _least_used(letters, letter_counts, cfg.axis_pcts_for(kind, value))
    axis = cfg.axis_by_id(letter)
    if not axis:
        return ""
    dir_counts = {"U": 0, "D": 0}
    for v, n in counts.items():
        if cfg.axis_letter_of(v) != letter:
            continue
        d = cfg.axis_dir_of(v)
        if d in dir_counts:
            dir_counts[d] += n
    side = _least_used(["U", "D"], dir_counts,
                       {"U": axis.get("pct_u", 0), "D": axis.get("pct_d", 0)})
    return f"{letter}-{side}" if side else letter


def _least_used(options: list, counts: dict, field=None) -> str:
    """Weighted least-used: pick the option whose share of past use sits
    furthest BELOW its target share. With equal targets — the default — this
    is exactly plain least-used. `field` names an app_config.PCT_FIELDS entry;
    pass None for ad-hoc lists (employees, EMB pairs) that have no table."""
    if not options:
        return ""
    # `field` is either a PCT_FIELDS key or an explicit {value: percent} map
    pcts = (field if isinstance(field, dict) else cfg.field_pcts(field)) if field else None
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
