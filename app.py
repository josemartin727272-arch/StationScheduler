"""
Weekly Work Schedule – Taxi Company
Streamlit app: multilingual (HE/EN/ES), local archive, Excel export.
"""
from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from translations import t
import app_config as cfg
from schedule_logic import (
    empty_week, validate_schedule,
    auto_assign_day, auto_assign_week_vehicles_udex, update_history,
)
from excel_export import export_to_excel
from archive_storage import save_schedule, load_schedule, list_archive, delete_schedule

try:
    from streamlit_sortables import sort_items
    HAS_SORTABLES = True
except ImportError:
    HAS_SORTABLES = False  # settings page falls back to ↑/↓ buttons
from stats import (compute_stats, load_period_schedules, load_recent_schedules,
                   HISTORY_DAYS, EMPLOYEE_ROLES, EMPLOYEE_ROLE_LABELS,
                   VALUE_FIELDS, vacation_budget)

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Schedule 🚕", layout="wide",
                   initial_sidebar_state="collapsed")

# ── Session state ──────────────────────────────────────────────────────────
def build_history(week_start) -> dict:
    """Usage counts over the 90 days before `week_start`.
    90-day window: covers ~13 weeks so year-boundary never creates a cold start."""
    history = {}
    for sched in load_recent_schedules(week_start, HISTORY_DAYS):
        update_history(history, sched)
    return history


def _init():
    ss = st.session_state
    if "lang" not in ss:           ss.lang = "he"
    if "schedule" not in ss:       ss.schedule = None
    if "page" not in ss:           ss.page = "schedule"
    if "week_start" not in ss:
        today = date.today()
        diff = (7 - today.weekday()) % 7 or 7
        ss.week_start = today + timedelta(days=diff)
    if "history" not in ss:
        ss.history = build_history(ss.week_start)
_init()

lang = st.session_state.lang

# ── Everything below re-reads config.json each rerun, so Settings-page
#    edits apply immediately ─────────────────────────────────────────────────
ACTIVE_GROUPS = cfg.active_groups()
ALL_EMPLOYEES = cfg.all_employees()
SECTIONS = cfg.all_sections()                 # [(workplace, section)]
SECTION_KEYS = cfg.section_row_keys()
AWAY_FIELDS = cfg.AWAY_ROWS
WORK_HOURS = [""] + cfg.hour_options()
ENTRY_OPTIONS = cfg.options_with_blank("entry")
EXIT_OPTIONS  = cfg.options_with_blank("exit")
ESCORT_OPTIONS = cfg.options_with_blank("escort")
ARRIVAL_POINT_OPTIONS = cfg.options_with_blank("arrival_point")
THEATER_OPTIONS = cfg.options_with_blank("theater")
EXTRA_ROW_KEYS = cfg.extra_row_keys()
VEHICLE_OPTIONS = cfg.options_with_blank("vehicle")
AXIS_OPTIONS = [""] + cfg.axis_values()
WAIT_SPOT_OPTIONS = cfg.options_with_blank("wait_spot")
CUSTOM_ROWS = cfg.custom_rows()
CUSTOM_ROW_MAP = {r["key"]: r for r in CUSTOM_ROWS}
VACATION_BUDGET = vacation_budget()

# Fields that auto-assign fills (need session-state sync on assign)
AUTO_FIELDS = [
    "entry", "exit", "arrival_point", "theater",
    "vehicle_morning", "vehicle_noon",
    "axis_morning", "axis_noon", "wait_morning", "wait_noon",
    "taxi_apt", "taxi_arrival", "taxi_emb", "taxi_arrival_noon",
] + SECTION_KEYS + EXTRA_ROW_KEYS

# ── Sidebar (settings only) ────────────────────────────────────────────────
with st.sidebar:
    with st.expander("⚙️ " + t("settings", lang)):
        sheets_url = st.text_input(t("sheets_url", lang),
            value=st.session_state.get("sheets_url",""),
            placeholder="https://docs.google.com/spreadsheets/d/...")
        st.session_state.sheets_url = sheets_url
        creds_text = st.text_area("Service Account JSON",
            value=st.session_state.get("sheets_creds",""), height=80)
        st.session_state.sheets_creds = creds_text

# ── Header row ─────────────────────────────────────────────────────────────
h1, h2, h3, h4, h5, h6 = st.columns([3, 1, 1, 1, 1, 1])
h1.title(t("app_title", lang))

lang_map = {"עברית": "he", "English": "en", "Español": "es"}
chosen_lang = h2.selectbox(t("select_language", lang), list(lang_map.keys()),
    index=list(lang_map.values()).index(lang), key="lang_sel",
    label_visibility="collapsed")
if lang_map[chosen_lang] != lang:
    st.session_state.lang = lang_map[chosen_lang]
    st.rerun()

if h3.button("📁 " + t("archive", lang), use_container_width=True):
    st.session_state.page = "archive"
    st.rerun()

if h4.button("📊 " + ("סטטיסטיקה" if lang=="he" else "Statistics"), use_container_width=True):
    st.session_state.page = "stats"
    st.rerun()

if h5.button("📋 " + t("schedule_tab", lang), use_container_width=True):
    st.session_state.page = "schedule"
    st.rerun()

if h6.button("⚙️ " + t("settings", lang), use_container_width=True):
    st.session_state.page = "settings"
    st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════
# PAGE: SETTINGS — everything here reads/writes config.json
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.page == "settings":
    st.subheader("⚙️ " + t("settings", lang))
    config = cfg.get_config()

    (tab_grp, tab_wp, tab_wd, tab_extra,
     tab_rows, tab_opts, tab_targets, tab_notes) = st.tabs([
        "👤 " + t("tab_groups", lang),
        "🏢 " + t("tab_workplaces", lang),
        "📆 " + t("tab_workdays", lang),
        "➕ " + t("tab_extra", lang),
        "📋 " + t("tab_rows", lang),
        "📝 " + t("tab_options", lang),
        "🎯 " + t("tab_targets", lang),
        "📄 " + t("notes_general", lang),
    ])

    # ── Tab 1: Employee groups + vacation budgets ──────────────────────────
    with tab_grp:
        active = [g for g in config["groups"] if g.get("active")]
        if not active:
            st.warning(t("grp_none", lang))
        with st.form("groups_form"):
            for g in active:
                gid = g["id"]
                c1, c2 = st.columns([3, 1])
                c1.text_input(t("grp_name", lang), value=g.get("name", ""),
                              key=f"gname_{gid}")
                c2.color_picker(t("grp_color", lang), value=g.get("color", "#eef2f7"),
                                key=f"gcolor_{gid}")
                st.text_area(t("grp_emps", lang),
                             value="\n".join(g.get("employees", [])),
                             help=t("one_per_line", lang), height=110,
                             key=f"gemps_{gid}")
                st.divider()
            st.caption("⚠️ " + t("rename_warning", lang))
            st.markdown("**🏖 " + t("vacation_budget_label", lang) + "**")
            budget_cols = st.columns(max(len(ALL_EMPLOYEES), 1))
            for col, emp in zip(budget_cols, ALL_EMPLOYEES):
                col.number_input(emp, min_value=0, max_value=365,
                    value=int(VACATION_BUDGET.get(emp, cfg.default_vacation_budget(emp))),
                    key=f"vb_{emp}")
            st.number_input(t("max_absence", lang), min_value=0, max_value=20,
                            value=cfg.max_daily_absence(), key="max_absence",
                            help=t("max_absence_hint", lang))
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                roster = []
                for g in config["groups"]:
                    if not g.get("active"):
                        continue
                    gid = g["id"]
                    g["name"] = st.session_state.get(f"gname_{gid}", g.get("name", "")).strip()
                    g["color"] = st.session_state.get(f"gcolor_{gid}", g.get("color", ""))
                    g["employees"] = [l.strip() for l in
                        st.session_state.get(f"gemps_{gid}", "").splitlines() if l.strip()]
                    roster += g["employees"]
                vb = {}
                for emp in roster:
                    vb[emp] = int(st.session_state.get(f"vb_{emp}",
                        config["vacation_budget"].get(emp, 30)))
                config["vacation_budget"] = vb
                config["max_daily_absence"] = int(
                    st.session_state.get("max_absence", 2))
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()

        cg1, cg2 = st.columns(2)
        free = next((g for g in config["groups"] if not g.get("active")), None)
        if cg1.button(t("grp_add", lang), disabled=free is None, key="add_group"):
            free["active"] = True
            free["name"] = free["name"] or free["id"].upper()
            cfg.save_config(config)
            st.rerun()
        if free is None:
            cg1.caption(t("grp_max", lang))
        rm = cg2.selectbox(t("grp_remove", lang), [""] + [g["id"] for g in active],
                           key="rm_group")
        if rm and cg2.button("🗑", key="rm_group_go"):
            cfg.group_by_id(rm)  # existence check
            for g in config["groups"]:
                if g["id"] == rm:
                    g["active"] = False        # switched off, never deleted
            cfg.save_config(config)
            st.rerun()

    # ── Tab 2: Workplaces and the roles inside them ────────────────────────
    with tab_wp:
        st.caption(t("wp_prio_hint", lang))
        st.caption(t("wp_notes_hint", lang))
        act_wps = [w for w in config["workplaces"] if w.get("active")]
        act_gids = [g["id"] for g in config["groups"] if g.get("active")]
        if not act_wps:
            st.warning(t("wp_none", lang))
        for w in act_wps:
            wid = w["id"]
            with st.expander(cfg.workplace_name(w), expanded=True):
                wc1, wc2 = st.columns([3, 1])
                wc1.text_input(t("wp_name", lang), value=w.get("name", ""),
                               key=f"wpname_{wid}")
                wc2.number_input(t("wp_priority", lang), min_value=1,
                                 max_value=cfg.MAX_WORKPLACES,
                                 value=int(w.get("priority") or 1),
                                 key=f"wpprio_{wid}")
                st.markdown("**" + t("wp_sections", lang) + "**")
                for sec in w.get("sections", []):
                    sid = sec["id"]
                    s1, s2, s3, s6, s5, s4 = st.columns([3, 2, 2, 2, 2, 1])
                    s1.text_input(t("wp_sec_name", lang), value=sec.get("name", ""),
                                  key=f"scname_{sid}")
                    s2.selectbox(t("wp_sec_group", lang), act_gids,
                        index=act_gids.index(sec["group_id"]) if sec.get("group_id") in act_gids else 0,
                        key=f"scgroup_{sid}", format_func=lambda g: cfg.group_name(cfg.group_by_id(g)))
                    s3.number_input(t("wp_sec_size", lang), min_value=0, max_value=10,
                                    value=cfg.section_size(sec), key=f"scsize_{sid}")
                    s6.number_input(t("wp_sec_min", lang), min_value=0, max_value=10,
                                    value=cfg.section_min(sec), key=f"scmin_{sid}")
                    s5.checkbox(t("wp_sec_required", lang),
                                value=cfg.section_required(sec), key=f"screq_{sid}")
                    if s4.button("🗑", key=f"screm_{sid}"):
                        w["sections"] = [x for x in w["sections"] if x["id"] != sid]
                        cfg.save_config(config)
                        st.rerun()
                if st.button(t("wp_sec_add", lang), key=f"scadd_{wid}"):
                    uid = uuid4().hex[:8]
                    w.setdefault("sections", []).append({
                        "id": f"s_{uid}", "name": "",
                        "group_id": act_gids[0] if act_gids else "",
                        "row_key": f"sec_{uid}", "max_workers": 1,
                        "min_workers": 0, "required": False})
                    cfg.save_config(config)
                    st.rerun()
                st.text_area(t("wp_notes", lang), value=w.get("notes", ""),
                             height=90, key=f"wpnotes_{wid}")
                if st.button("🗑 " + t("wp_remove", lang), key=f"wprem_{wid}"):
                    w["active"] = False
                    cfg.save_config(config)
                    st.rerun()
        if st.button("💾 " + t("save_settings", lang), type="primary", key="save_wps"):
            for w in config["workplaces"]:
                if not w.get("active"):
                    continue
                w["name"] = st.session_state.get(f"wpname_{w['id']}", w.get("name", "")).strip()
                w["priority"] = int(st.session_state.get(f"wpprio_{w['id']}",
                                                         w.get("priority") or 1))
                w["notes"] = st.session_state.get(f"wpnotes_{w['id']}", w.get("notes", ""))
                for sec in w.get("sections", []):
                    sid = sec["id"]
                    sec["name"] = st.session_state.get(f"scname_{sid}", sec.get("name", "")).strip()
                    sec["group_id"] = st.session_state.get(f"scgroup_{sid}", sec.get("group_id"))
                    sec["max_workers"] = int(st.session_state.get(f"scsize_{sid}", 1))
                    sec["min_workers"] = int(st.session_state.get(f"scmin_{sid}", 0))
                    sec["required"] = bool(st.session_state.get(f"screq_{sid}"))
            cfg.save_config(config)
            st.success("✅ " + t("settings_saved", lang))
            st.rerun()
        free_wp = next((w for w in config["workplaces"] if not w.get("active")), None)
        if st.button(t("wp_add", lang), disabled=free_wp is None, key="add_wp"):
            free_wp["active"] = True
            free_wp["name"] = free_wp["name"] or free_wp["id"].upper()
            # a newly switched-on workplace goes to the end of the staffing order
            free_wp["priority"] = min(cfg.MAX_WORKPLACES, 1 + max(
                [x.get("priority") or 0 for x in config["workplaces"]
                 if x.get("active")] or [0]))
            cfg.save_config(config)
            st.rerun()
        if free_wp is None:
            st.caption(t("wp_max", lang))

    # ── Tab 3: Which weekdays the week is built from ───────────────────────
    with tab_wd:
        st.caption(t("wd_pick", lang))
        picked = cfg.work_days()
        labels = (config.get("work_days") or {}).get("labels") or {}
        with st.form("workdays_form"):
            for d in cfg.DOW_ORDER:
                c1, c2 = st.columns([1, 2])
                c1.checkbox(t(d, lang), value=d in picked, key=f"wd_{d}")
                c2.text_input(t("wd_label", lang), value=labels.get(d, t(d, lang)),
                              key=f"wdlbl_{d}", label_visibility="collapsed")
            st.markdown("**" + t("wd_hours_title", lang) + "**")
            st.caption(t("wd_hours_hint", lang))
            v_hours = st.text_area(t("wd_hours_title", lang), height=150,
                value="\n".join(cfg.hour_options()), label_visibility="collapsed")
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                days = [d for d in cfg.DOW_ORDER if st.session_state.get(f"wd_{d}")]
                if not days:
                    st.error(t("wd_none", lang))
                else:
                    config["work_days"] = {
                        "days": days,
                        "labels": {d: (st.session_state.get(f"wdlbl_{d}", "").strip()
                                       or t(d, lang)) for d in cfg.DOW_ORDER},
                        "hour_options": [l.strip() for l in v_hours.splitlines() if l.strip()]}
                    cfg.save_config(config)
                    st.success("✅ " + t("settings_saved", lang))
                    st.rerun()

    # ── Tab 4: Extra tasks (was the single UDEX row) ───────────────────────
    with tab_extra:
        act_extras = [e for e in config["extra_tasks"] if e.get("active")]
        if not act_extras:
            st.warning(t("et_none", lang))
        with st.form("extra_form"):
            for et in act_extras:
                eid = et["id"]
                st.markdown(f"**{cfg.extra_label(et, lang)}**")
                e1, e2, e3 = st.columns(3)
                e1.text_input(t("et_name", lang) + " (he)",
                              value=(et.get("label") or {}).get("he", ""), key=f"ethe_{eid}")
                e2.text_input(t("et_name", lang) + " (en)",
                              value=(et.get("label") or {}).get("en", ""), key=f"eten_{eid}")
                e3.text_input(t("et_name", lang) + " (es)",
                              value=(et.get("label") or {}).get("es", ""), key=f"etes_{eid}")
                o1, o2, o3 = st.columns(3)
                o1.text_area(t("et_options", lang), height=130,
                             value="\n".join(et.get("options", [])), key=f"etopts_{eid}")
                o2.text_area(t("et_morning", lang), height=130,
                             value="\n".join(et.get("morning_values", [])), key=f"etm_{eid}")
                o3.text_area(t("et_noon", lang), height=130,
                             value="\n".join(et.get("noon_values", [])), key=f"etn_{eid}")
                g1, g2 = st.columns(2)
                g1.number_input(t("et_tg_m", lang), min_value=0, max_value=7,
                                value=int(et.get("target_morning") or 0), key=f"ettgm_{eid}")
                g2.number_input(t("et_tg_n", lang), min_value=0, max_value=7,
                                value=int(et.get("target_noon") or 0), key=f"ettgn_{eid}")
                st.divider()
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                lines = lambda txt: [l.strip() for l in txt.splitlines() if l.strip()]
                for et in config["extra_tasks"]:
                    if not et.get("active"):
                        continue
                    eid = et["id"]
                    he = st.session_state.get(f"ethe_{eid}", "").strip()
                    et["label"] = {
                        "he": he or eid,
                        "en": st.session_state.get(f"eten_{eid}", "").strip() or he or eid,
                        "es": st.session_state.get(f"etes_{eid}", "").strip() or he or eid}
                    et["options"] = lines(st.session_state.get(f"etopts_{eid}", ""))
                    et["morning_values"] = lines(st.session_state.get(f"etm_{eid}", ""))
                    et["noon_values"] = lines(st.session_state.get(f"etn_{eid}", ""))
                    et["target_morning"] = int(st.session_state.get(f"ettgm_{eid}", 0))
                    et["target_noon"] = int(st.session_state.get(f"ettgn_{eid}", 0))
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()

        ce1, ce2 = st.columns(2)
        free_et = next((e for e in config["extra_tasks"] if not e.get("active")), None)
        if ce1.button(t("et_add", lang), disabled=free_et is None, key="add_extra"):
            free_et["active"] = True
            if not (free_et.get("label") or {}).get("he"):
                name = free_et["id"].upper()
                free_et["label"] = {"he": name, "en": name, "es": name}
            cfg.save_config(config)
            st.rerun()
        if free_et is None:
            ce1.caption(t("et_max", lang))
        rm_et = ce2.selectbox(t("et_remove", lang), [""] + [e["id"] for e in act_extras],
                              key="rm_extra")
        if rm_et and ce2.button("🗑", key="rm_extra_go"):
            for e in config["extra_tasks"]:
                if e["id"] == rm_et:
                    e["active"] = False       # switched off; its values are kept
            cfg.save_config(config)
            st.rerun()

    # ── Tab 8: Free-text assignment notes ──────────────────────────────────
    with tab_notes:
        st.caption(t("notes_hint", lang))
        with st.form("notes_form"):
            v_notes = st.text_area(t("notes_general", lang),
                value=config.get("assign_notes", ""), height=220)
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                config["assign_notes"] = v_notes
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()

    # ── Tab 2: Row order + row labels + custom rows ────────────────────────
    with tab_rows:
        st.markdown("**↕️ " + t("row_order_title", lang) + "**")
        order_keys = cfg.reorderable_row_keys()
        if HAS_SORTABLES:
            st.caption(t("row_order_hint_drag", lang))
            item_to_key, items = {}, []
            for k in order_keys:
                lbl = f"⠿ {cfg.row_label(k, lang)}"
                while lbl in item_to_key:   # duplicate labels → disambiguate
                    lbl += " ·"
                item_to_key[lbl] = k
                items.append(lbl)
            sorted_items = sort_items(items, direction="vertical",
                                      key="row_order_sort")
            if st.button("💾 " + t("save_settings", lang), type="primary",
                         key="row_order_save"):
                config["row_order"] = [item_to_key[i] for i in sorted_items]
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()
        else:
            st.caption(t("row_order_hint_buttons", lang))
            for idx, k in enumerate(order_keys):
                c_lbl, c_up, c_dn = st.columns([8, 1, 1])
                c_lbl.write(f"⠿ {cfg.row_label(k, lang)}")
                if c_up.button("↑", key=f"ro_up_{k}", disabled=(idx == 0)):
                    order_keys[idx - 1], order_keys[idx] = order_keys[idx], order_keys[idx - 1]
                    config["row_order"] = order_keys
                    cfg.save_config(config)
                    st.rerun()
                if c_dn.button("↓", key=f"ro_dn_{k}",
                               disabled=(idx == len(order_keys) - 1)):
                    order_keys[idx + 1], order_keys[idx] = order_keys[idx], order_keys[idx + 1]
                    config["row_order"] = order_keys
                    cfg.save_config(config)
                    st.rerun()

        st.divider()
        st.markdown("**" + t("row_labels_title", lang) + "**")
        _sec = set(cfg.section_row_keys())
        editable_rows = [k for k in cfg.natural_row_keys()
                         if k not in ("dates", "days", "udex")
                         and k not in _sec and k not in cfg.custom_row_keys()]
        with st.form("labels_form"):
            lh, le, ls_ = st.columns(3)
            lh.markdown("**עברית**"); le.markdown("**English**"); ls_.markdown("**Español**")
            for rk in editable_rows:
                c1, c2, c3 = st.columns(3)
                c1.text_input("he", value=cfg.row_label(rk, "he"),
                    key=f"lbl_{rk}_he", label_visibility="collapsed")
                c2.text_input("en", value=cfg.row_label(rk, "en"),
                    key=f"lbl_{rk}_en", label_visibility="collapsed")
                c3.text_input("es", value=cfg.row_label(rk, "es"),
                    key=f"lbl_{rk}_es", label_visibility="collapsed")
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                for rk in editable_rows:
                    config["row_labels"][rk] = {
                        "he": st.session_state.get(f"lbl_{rk}_he", "").strip(),
                        "en": st.session_state.get(f"lbl_{rk}_en", "").strip(),
                        "es": st.session_state.get(f"lbl_{rk}_es", "").strip(),
                    }
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()

        st.divider()
        st.markdown("**➕ " + t("add_custom_row", lang) + "**")
        with st.form("add_row_form"):
            n1, n2, n3 = st.columns(3)
            new_he = n1.text_input(t("row_name_he", lang))
            new_en = n2.text_input(t("row_name_en", lang))
            new_es = n3.text_input(t("row_name_es", lang))
            it1, it2 = st.columns(2)
            input_labels = {
                "select": t("input_select", lang),
                "text": t("input_text", lang),
            }
            new_type = it1.selectbox(t("row_input_type", lang),
                list(input_labels.keys()), format_func=lambda k: input_labels[k])
            new_opts = it2.text_area(t("row_options_label", lang),
                help=t("one_per_line", lang), height=80)
            if st.form_submit_button("➕ " + t("add_row_btn", lang)):
                if not new_he.strip():
                    st.error(t("row_name_required", lang))
                else:
                    existing_nums = [
                        int(r["key"].split("_")[1])
                        for r in config["custom_rows"]
                        if r.get("key", "").startswith("custom_")
                        and r["key"].split("_")[1].isdigit()
                    ]
                    next_num = max(existing_nums, default=0) + 1
                    config["custom_rows"].append({
                        "key": f"custom_{next_num}",
                        "labels": {"he": new_he.strip(),
                                   "en": new_en.strip() or new_he.strip(),
                                   "es": new_es.strip() or new_he.strip()},
                        "input": new_type,
                        "options": [l.strip() for l in new_opts.splitlines() if l.strip()],
                    })
                    cfg.save_config(config)
                    st.success("✅ " + t("row_added", lang))
                    st.rerun()

        st.markdown("**" + t("custom_rows_title", lang) + "**")
        if not config["custom_rows"]:
            st.info(t("no_custom_rows", lang))
        for i, crow in enumerate(config["custom_rows"]):
            key = crow["key"]
            with st.expander(f"📌 {crow.get('labels', {}).get(lang) or crow.get('labels', {}).get('he') or key}"):
                e1, e2, e3 = st.columns(3)
                u_he = e1.text_input(t("row_name_he", lang),
                    value=crow.get("labels", {}).get("he", ""), key=f"cr_{key}_he")
                u_en = e2.text_input(t("row_name_en", lang),
                    value=crow.get("labels", {}).get("en", ""), key=f"cr_{key}_en")
                u_es = e3.text_input(t("row_name_es", lang),
                    value=crow.get("labels", {}).get("es", ""), key=f"cr_{key}_es")
                u_opts = st.text_area(t("row_options_label", lang),
                    value="\n".join(crow.get("options", [])),
                    help=t("one_per_line", lang), key=f"cr_{key}_opts", height=80)
                b1, b2 = st.columns(2)
                if b1.button("💾 " + t("save_settings", lang), key=f"cr_{key}_save"):
                    crow["labels"] = {"he": u_he.strip(), "en": u_en.strip(), "es": u_es.strip()}
                    crow["options"] = [l.strip() for l in u_opts.splitlines() if l.strip()]
                    cfg.save_config(config)
                    st.success("✅ " + t("settings_saved", lang))
                    st.rerun()
                if b2.button("🗑 " + t("delete_row_btn", lang), key=f"cr_{key}_del"):
                    config["custom_rows"] = [
                        r for r in config["custom_rows"] if r.get("key") != key]
                    cfg.save_config(config)
                    st.success("✅ " + t("row_deleted", lang))
                    st.rerun()

    # ── Tab 3: Dropdown options ────────────────────────────────────────────
    with tab_opts:
        OPTION_GROUPS = [
            ("entry",         t("row_entry", lang)),
            ("exit",          t("row_exit", lang)),
            ("escort",        t("row_escort_morning", lang) + " / " + t("row_escort_noon", lang)),
            ("arrival_point", t("row_arrival_point", lang)),
            ("theater",       t("row_theater", lang)),
            ("vehicle",       t("row_vehicle_morning", lang) + " / " + t("row_vehicle_noon", lang)),
            ("wait_spot",     t("row_wait_morning", lang) + " / " + t("row_wait_noon", lang)),
            ("taxi_apt",          cfg.row_label("taxi_apt", lang)),
            ("taxi_arrival",      cfg.row_label("taxi_arrival", lang)),
            ("taxi_emb",          cfg.row_label("taxi_emb", lang)),
            ("taxi_arrival_noon", cfg.row_label("taxi_arrival_noon", lang)),
        ]
        with st.form("opts_form"):
            grid = st.columns(3)
            for i, (opt_key, opt_label) in enumerate(OPTION_GROUPS):
                grid[i % 3].text_area(opt_label,
                    value="\n".join(config["options"].get(opt_key, [])),
                    help=t("one_per_line", lang), key=f"opt_{opt_key}",
                    height=140)

            st.divider()
            st.caption("⚠️ " + t("special_values_note", lang))
            sv = config["special_values"]
            s1, s2 = st.columns(2)
            sv_holiday = s1.text_input("Holiday", value=sv["holiday"], key="sv_holiday")
            sv_vehicle = s2.text_input("Special vehicle", value=sv["vehicle_special"], key="sv_vehicle")

            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                for opt_key, _ in OPTION_GROUPS:
                    raw = st.session_state.get(f"opt_{opt_key}", "")
                    config["options"][opt_key] = [
                        l.strip() for l in raw.splitlines() if l.strip()]
                config["special_values"] = {
                    "holiday": sv_holiday.strip(),
                    "vehicle_special": sv_vehicle.strip(),
                }
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()

    # ── Tab 4: Weekly quotas ───────────────────────────────────────────────
    with tab_targets:
        st.caption(t("wt_hint", lang))
        quotas = cfg.weekly_targets()
        if not quotas:
            st.warning(t("wt_none", lang))
        field_keys = cfg.target_fields()
        with st.form("targets_form"):
            for i, q in enumerate(quotas):
                c1, c2, c3 = st.columns([3, 3, 1])
                c1.selectbox(t("rules_field", lang) if False else "", field_keys,
                    index=field_keys.index(q["field"]) if q["field"] in field_keys else 0,
                    key=f"tgfield_{i}", label_visibility="collapsed",
                    format_func=lambda k: cfg.row_label(k, lang))
                vals = [""] + cfg.target_field_values(q["field"])
                c2.selectbox("", vals,
                    index=vals.index(q["value"]) if q["value"] in vals else 0,
                    key=f"tgvalue_{i}", label_visibility="collapsed",
                    format_func=lambda v: v or t("wt_any", lang))
                c3.number_input("", min_value=0, max_value=14, value=int(q["count"]),
                                key=f"tgcount_{i}", label_visibility="collapsed")
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                config["weekly_targets"] = [
                    {"field": st.session_state.get(f"tgfield_{i}"),
                     "value": st.session_state.get(f"tgvalue_{i}") or "",
                     "count": int(st.session_state.get(f"tgcount_{i}", 0))}
                    for i in range(len(quotas))]
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
                st.rerun()

        ct1, ct2 = st.columns(2)
        if ct1.button(t("wt_add", lang), key="add_target"):
            config.setdefault("weekly_targets", []).append(
                {"field": field_keys[0] if field_keys else "theater",
                 "value": "", "count": 1})
            cfg.save_config(config)
            st.rerun()
        rm_i = ct2.selectbox(
            "🗑", [""] + [str(i) for i in range(len(quotas))], key="rm_target",
            format_func=lambda i: "" if i == "" else
                cfg.row_label(quotas[int(i)]["field"], lang) +
                (f' = {quotas[int(i)]["value"]}' if quotas[int(i)]["value"] else ""))
        if rm_i != "" and ct2.button("🗑", key="rm_target_go"):
            config["weekly_targets"].pop(int(rm_i))
            cfg.save_config(config)
            st.rerun()

        # ── Target percentages per balanced field ──────────────────────────
        st.markdown("### " + t("pct_title", lang))
        st.caption(t("pct_hint", lang))
        for spec in cfg.PCT_FIELDS:
            key = spec["key"]
            values = cfg.pct_options(key)
            if not values:
                continue
            current = cfg.field_pcts(key)
            with st.form(f"pct_form_{key}"):
                st.markdown(f"**{cfg.pct_label(key, lang)}**")
                cols = st.columns(min(len(values), 5))
                entered = {}
                for i, v in enumerate(values):
                    entered[v] = cols[i % len(cols)].number_input(
                        v, min_value=0, max_value=100,
                        value=int(current.get(v, 0)), key=f"pct_{key}_{v}")
                total = sum(entered.values())
                (st.success if total == 100 else st.error)(
                    f'{t("pct_total", lang)}: {total}%')
                if st.form_submit_button("💾 " + t("save_settings", lang)):
                    if total != 100:
                        st.warning("⚠️ " + t("pct_err_100", lang))
                    else:
                        saved_pcts = config["targets"].setdefault("field_pcts", {})
                        # merge, never replace: a value later deleted from the
                        # option list keeps its saved share
                        merged = dict(saved_pcts.get(key, {}))
                        merged.update({k: int(x) for k, x in entered.items()})
                        saved_pcts[key] = merged
                        cfg.save_config(config)
                        st.success("✅ " + t("settings_saved", lang))
                        st.rerun()

        # ── Axes: each one's U/D split ─────────────────────────────────────
        st.markdown("### " + t("ax_split_title", lang))
        act_axes = [a for a in config["axes"] if a.get("active")]
        if not act_axes:
            st.warning(t("ax_none", lang))
        with st.form("axes_form"):
            for a in act_axes:
                aid = a["id"]
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                c1.text_input(t("opt_axis", lang), value=cfg.axis_label(a),
                              key=f"axlabel_{aid}")
                c2.number_input("% U", min_value=0, max_value=100,
                                value=int(a.get("pct_u") or 0), key=f"axu_{aid}")
                c3.number_input("% D", min_value=0, max_value=100,
                                value=int(a.get("pct_d") or 0), key=f"axd_{aid}")
                total = int(a.get("pct_u") or 0) + int(a.get("pct_d") or 0)
                c4.markdown(("✅ " if total == 100 else "⚠️ ") + f"{total}%")
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                bad = None
                for a in config["axes"]:
                    if not a.get("active"):
                        continue
                    aid = a["id"]
                    a["label"] = st.session_state.get(f"axlabel_{aid}", aid).strip() or aid
                    a["pct_u"] = int(st.session_state.get(f"axu_{aid}", 0))
                    a["pct_d"] = int(st.session_state.get(f"axd_{aid}", 0))
                    if a["pct_u"] + a["pct_d"] != 100:
                        bad = a
                if bad:
                    st.error(t("err_axis_ud", lang, a=cfg.axis_label(bad),
                               n=bad["pct_u"] + bad["pct_d"]))
                else:
                    cfg.save_config(config)
                    st.success("✅ " + t("settings_saved", lang))
                    st.rerun()

        # ── Which axes each entry/exit value may use, and in what share ─────
        letters = cfg.axis_letters()
        for kind, title_key in (("entry", "ax_entry_title"), ("exit", "ax_exit_title")):
            st.markdown("### " + t(title_key, lang))
            rules = cfg.axis_rules(kind)
            values = [v for v in cfg.options(kind) if v != cfg.special("holiday")]
            with st.form(f"axrules_{kind}"):
                for v in values:
                    rule = rules.get(v) or {}
                    on, pcts = rule.get("axes", []), rule.get("pcts", {})
                    cols = st.columns([2] + [2] * len(letters))
                    cols[0].markdown(f"**{v}**")
                    for i, letter in enumerate(letters, start=1):
                        cols[i].checkbox(letter, value=letter in on,
                                         key=f"arax_{kind}_{v}_{letter}")
                        cols[i].number_input("%", min_value=0, max_value=100,
                                             value=int(pcts.get(letter) or 0),
                                             key=f"arpct_{kind}_{v}_{letter}",
                                             label_visibility="collapsed")
                if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                    out, bad = {}, None
                    for v in values:
                        ids, pcts = [], {}
                        for letter in letters:
                            if st.session_state.get(f"arax_{kind}_{v}_{letter}"):
                                ids.append(letter)
                                pcts[letter] = int(
                                    st.session_state.get(f"arpct_{kind}_{v}_{letter}", 0))
                        if not ids:
                            continue          # nothing ticked ⇒ no rule, any axis
                        if sum(pcts.values()) != 100:
                            bad = (v, sum(pcts.values()))
                            break
                        out[v] = {"axes": ids, "pcts": pcts}
                    if bad:
                        st.error(t("err_axis_rule_pct", lang,
                                   f=cfg.row_label(kind, lang), v=bad[0], n=bad[1]))
                    else:
                        config[cfg.AXIS_RULE_KEY[kind]] = out
                        cfg.save_config(config)
                        st.success("✅ " + t("settings_saved", lang))
                        st.rerun()

    st.stop()

# ══════════════════════════════════════════════════════════════════════════
# PAGE: ARCHIVE
# ══════════════════════════════════════════════════════════════════════════
if st.session_state.page == "archive":
    st.subheader("📁 " + t("archive", lang))
    arch = list_archive()
    if not arch:
        st.info(t("archive_empty", lang))
    else:
        for year in sorted(arch.keys(), reverse=True):
            with st.expander(f"📅 {year}", expanded=True):
                for month in sorted(arch[year].keys(), reverse=True):
                    st.markdown(f"**{month}**")
                    for ws_str in sorted(arch[year][month], reverse=True):
                        ca, cb, cc = st.columns([4, 1, 1])
                        ca.write(ws_str)
                        if cb.button(t("load_archive", lang), key=f"arch_{ws_str}"):
                            loaded = load_schedule(date.fromisoformat(ws_str))
                            if loaded:
                                st.session_state.schedule = loaded
                                st.session_state.week_start = date.fromisoformat(ws_str)
                                for dk in loaded:
                                    for f in AUTO_FIELDS:
                                        st.session_state.pop(f"{f}_{dk}", None)
                                st.session_state.page = "schedule"
                                st.rerun()
                        if cc.button("🗑", key=f"del_{ws_str}", help="מחק שבוע זה"):
                            delete_schedule(date.fromisoformat(ws_str))
                            st.rerun()
    st.stop()

# ══════════════════════════════════════════════════════════════════════════
# PAGE: STATISTICS
# ══════════════════════════════════════════════════════════════════════════
def _render_stats(schedules: list, title: str):
    """Render employee + field distribution tables for a list of schedules."""
    import pandas as pd
    import matplotlib.pyplot as plt

    if not schedules:
        st.info("אין נתונים לתקופה זו" if lang=="he" else "No data for this period")
        return
    (emp_counts, field_counts, num_days, vacation_counts, other_counts,
     trip_counts) = compute_stats(schedules)

    st.markdown(f"**{title}** — {len(schedules)} {'שבועות' if lang=='he' else 'weeks'} · {num_days} {'ימים' if lang=='he' else 'days'}")

    # ── Employee table with % and vacation ─────────────────────────────
    st.markdown("##### 👤 " + ("חלוקת עובדים" if lang=="he" else "Employee Distribution"))
    rows = {}
    for emp in ALL_EMPLOYEES:
        row = {}
        for r in EMPLOYEE_ROLES:
            cnt = emp_counts[emp][r]
            pct = (cnt / num_days * 100) if num_days else 0
            row[EMPLOYEE_ROLE_LABELS[r]] = f"{cnt} ({pct:.0f}%)"
        vac = vacation_counts.get(emp, 0)
        vac_pct = (vac / num_days * 100) if num_days else 0
        row["Vacation"] = f"{vac} ({vac_pct:.0f}%)"
        # "Other" = days explicitly assigned to the "other_empl" field
        other = other_counts.get(emp, 0)
        other_pct = (other / num_days * 100) if num_days else 0
        row["Other"] = f"{other} ({other_pct:.0f}%)"
        rows[emp] = row
    emp_df = pd.DataFrame(rows).T
    emp_df.index.name = ""
    st.dataframe(emp_df, use_container_width=True)

    # ── one pie per active employee group (English labels to avoid RTL flip) ──
    if ACTIVE_GROUPS:
        pie_cols = st.columns(len(ACTIVE_GROUPS))
        for col, grp in zip(pie_cols, ACTIVE_GROUPS):
            grp_rows = [sec["row_key"] for _, sec in SECTIONS
                        if sec.get("group_id") == grp["id"]]
            with col:
                fig, ax = plt.subplots(figsize=(5, 4))
                fig.patch.set_alpha(0.0); ax.set_facecolor("none")
                labels, values = [], []
                for emp in grp.get("employees", []):
                    for r in grp_rows:
                        cnt = emp_counts.get(emp, {}).get(r, 0)
                        if cnt:
                            labels.append(f"{emp}\n{EMPLOYEE_ROLE_LABELS.get(r, r)}")
                            values.append(cnt)
                if values:
                    ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
                ax.set_title(cfg.group_name(grp))
                st.pyplot(fig)
                plt.close(fig)

    # ── Vacation breakdown with annual budget ──────────────────────────
    st.markdown("##### 🏖 " + ("חופשות" if lang == "he" else "Vacations"))
    vac_rows = {}
    for emp in ALL_EMPLOYEES:
        vac = vacation_counts.get(emp, 0)
        budget = VACATION_BUDGET.get(emp, 0)
        pct_used = (vac / budget * 100) if budget else 0
        vac_rows[emp] = {
            "Days Used": vac,
            "Annual Budget": budget,
            "% Used": f"{pct_used:.0f}%",
            "Remaining": budget - vac,
        }
    vac_df = pd.DataFrame(vac_rows).T
    vac_df.index.name = ""
    st.dataframe(vac_df, use_container_width=True)
    # Individual pies — one per employee showing % utilization of annual budget
    pie_cols = st.columns(max(len(ALL_EMPLOYEES), 1))
    for col, emp in zip(pie_cols, ALL_EMPLOYEES):
        vac = vacation_counts.get(emp, 0)
        budget = VACATION_BUDGET.get(emp, 0)
        remaining = max(budget - vac, 0)
        with col:
            fig, ax = plt.subplots(figsize=(2.2, 2.2))
            fig.patch.set_alpha(0.0); ax.set_facecolor("none")
            if vac > 0:
                ax.pie([vac, remaining],
                       labels=[f"Used\n{vac}d", f"Left\n{remaining}d"],
                       autopct="%1.0f%%", startangle=90,
                       colors=["#E07B54", "#A8D5A2"], textprops={"fontsize": 7})
            else:
                ax.pie([1], labels=["0 days"], colors=["#CCCCCC"],
                       textprops={"fontsize": 7})
            ax.set_title(emp, fontsize=8)
            st.pyplot(fig)
            plt.close(fig)

    # ── Entry / Exit ────────────────────────────────────────────────────
    st.markdown("##### 🚪 " + ("כניסה / יציאה" if lang == "he" else "Entry / Exit"))
    col_en, col_ex = st.columns(2)
    for col, (field, label) in zip([col_en, col_ex],
                                    [("entry", "Entry"), ("exit", "Exit")]):
        with col:
            counts = field_counts.get(field, {})
            if not counts:
                continue
            total = sum(counts.values())
            row = {v: f"{c} ({c/total*100:.0f}%)" for v, c in sorted(counts.items())}
            df = pd.DataFrame([row], index=[label])
            df.index.name = ""
            st.dataframe(df, use_container_width=True)
            fig, ax = plt.subplots(figsize=(4, 4))
            fig.patch.set_alpha(0.0); ax.set_facecolor("none")
            ax.pie(list(counts.values()), labels=list(counts.keys()),
                   autopct="%1.0f%%", startangle=90)
            ax.set_title(label)
            st.pyplot(fig)
            plt.close(fig)

    # ── Vehicles (with 60/40 target) ────────────────────────────────────
    st.markdown("##### 🚗 " + ("רכבים — יעד: BLACK 60% / YELLOW 40%" if lang == "he"
                                else "Vehicles — Target: BLACK 60% / YELLOW 40%"))
    col_vm, col_vn = st.columns(2)
    vehicle_colors = {"BLACK": "#444444", "YELLOW": "#FFD700"}
    for col, (field, label) in zip([col_vm, col_vn],
                                    [("vehicle_morning", "Vehicle Morning"),
                                     ("vehicle_noon",    "Vehicle Noon")]):
        with col:
            counts = field_counts.get(field, {})
            if not counts:
                continue
            total = sum(counts.values())
            # Actual vs target
            actual_black = counts.get("BLACK", 0)
            actual_yellow = counts.get("YELLOW", 0)
            target_black = round(total * 0.6)
            target_yellow = total - target_black
            tbl = {
                "BLACK": f"{actual_black} ({actual_black/total*100:.0f}%)  target {target_black} (60%)",
                "YELLOW": f"{actual_yellow} ({actual_yellow/total*100:.0f}%)  target {target_yellow} (40%)",
            }
            df = pd.DataFrame([tbl], index=[label])
            df.index.name = ""
            st.dataframe(df, use_container_width=True)
            lbls = list(counts.keys())
            vals = list(counts.values())
            colors = [vehicle_colors.get(l, "#888888") for l in lbls]
            fig, ax = plt.subplots(figsize=(4, 4))
            fig.patch.set_alpha(0.0); ax.set_facecolor("none")
            ax.pie(vals, labels=lbls, autopct="%1.0f%%", startangle=90, colors=colors)
            ax.set_title(label)
            st.pyplot(fig)
            plt.close(fig)

    # ── Morning fields ──────────────────────────────────────────────────
    st.markdown("##### 🌅 " + ("בוקר" if lang == "he" else "Morning"))
    # Arrival Point and Theater — table only
    for field, label in [("arrival_point","Arrival Point"), ("theater","Theater")]:
        counts = field_counts.get(field, {})
        if not counts:
            continue
        total = sum(counts.values())
        row = {v: f"{counts[v]} ({counts[v]/total*100:.0f}%)" for v in sorted(counts.keys())}
        df = pd.DataFrame([row], index=[label])
        df.index.name = ""
        st.dataframe(df, use_container_width=True)

    # Extra tasks — always show every configured value, even at 0
    for _et in cfg.active_extras():
        counts = field_counts.get(cfg.extra_row_key(_et), {})
        total = sum(counts.values()) or 1
        name = cfg.extra_label(_et, lang)
        for vals, suffix in ((_et.get("morning_values", []), t("et_tg_m", lang)),
                             (_et.get("noon_values", []), t("et_tg_n", lang))):
            if not vals:
                continue
            row = {v: f"{counts.get(v, 0)} "
                      f"({counts.get(v, 0) / total * 100:.0f}%)" for v in vals}
            df_e = pd.DataFrame([row], index=[f"{name} — {suffix}"])
            df_e.index.name = ""
            st.dataframe(df_e, use_container_width=True)

    def _axis_bar(counts_ax, title, color):
        """Horizontal bar chart for axis values — A1 at top, clear labels."""
        all_axes = [v for v in AXIS_OPTIONS if v]   # A1…D5 in order
        total = sum(counts_ax.values()) or 1
        # Reverse so A1 is at top
        axes_rev = list(reversed(all_axes))
        cnts = [counts_ax.get(a, 0) for a in axes_rev]
        pcts = [c / total * 100 for c in cnts]
        ideal = 100 / len(all_axes)

        fig, ax = plt.subplots(figsize=(6, 6))
        fig.patch.set_alpha(0.0); ax.set_facecolor("none")
        bars = ax.barh(axes_rev, pcts, color=color, edgecolor="white", linewidth=0.4)
        ax.axvline(ideal, color="red", linestyle="--", linewidth=1.2,
                   label=f"Ideal {ideal:.1f}%")
        ax.set_xlabel("%", fontsize=10)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.tick_params(axis="y", labelsize=9)
        ax.tick_params(axis="x", labelsize=9)
        ax.legend(fontsize=8)
        # Label: count + % inside bar if wide enough, otherwise outside
        for bar, cnt, pct in zip(bars, cnts, pcts):
            lbl = f"{cnt}  ({pct:.0f}%)"
            x_inside = pct / 2
            if pct >= 3:   # enough room inside
                ax.text(x_inside, bar.get_y() + bar.get_height() / 2,
                        lbl, va="center", ha="center",
                        fontsize=8, fontweight="bold", color="white")
            elif pct > 0:  # bar too short → label to the right
                ax.text(pct + 0.1, bar.get_y() + bar.get_height() / 2,
                        lbl, va="center", ha="left", fontsize=8)
        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    # Axis Morning: bar chart (20 options — pie unreadable)
    col_axm, col_waitm = st.columns(2)
    with col_axm:
        counts_axm = field_counts.get("axis_morning", {})
        if counts_axm:
            _axis_bar(counts_axm, "Axis Morning", "#4C9BE8")

    # Wait Morning: pie chart (5 options)
    with col_waitm:
        counts_wm = field_counts.get("wait_morning", {})
        if counts_wm:
            fig, ax = plt.subplots(figsize=(4, 4))
            fig.patch.set_alpha(0.0); ax.set_facecolor("none")
            ax.pie(list(counts_wm.values()), labels=[f"Wait {k}" for k in counts_wm.keys()],
                   autopct="%1.0f%%", startangle=90)
            ax.set_title("Wait Morning")
            st.pyplot(fig)
            plt.close(fig)

    # ── Noon fields ─────────────────────────────────────────────────────
    st.markdown("##### 🌆 " + ("צהריים" if lang == "he" else "Noon"))
    col_axn, col_waitn = st.columns(2)
    with col_axn:
        counts_axn = field_counts.get("axis_noon", {})
        if counts_axn:
            _axis_bar(counts_axn, "Axis Noon", "#F4845F")

    with col_waitn:
        counts_wn = field_counts.get("wait_noon", {})
        if counts_wn:
            fig, ax = plt.subplots(figsize=(4, 4))
            fig.patch.set_alpha(0.0); ax.set_facecolor("none")
            ax.pie(list(counts_wn.values()), labels=[f"Wait {k}" for k in counts_wn.keys()],
                   autopct="%1.0f%%", startangle=90)
            ax.set_title("Wait Noon")
            st.pyplot(fig)
            plt.close(fig)

if st.session_state.page == "stats":
    st.subheader("📊 " + ("סטטיסטיקה" if lang=="he" else "Statistics"))
    arch = list_archive()

    tab_week, tab_month, tab_year = st.tabs([
        "📅 " + ("שבוע נוכחי" if lang=="he" else "Current Week"),
        "🗓 " + ("חודשי"      if lang=="he" else "Monthly"),
        "📆 " + ("שנתי"       if lang=="he" else "Yearly"),
    ])

    with tab_week:
        if st.session_state.schedule:
            _render_stats([st.session_state.schedule],
                          "שבוע נוכחי" if lang=="he" else "Current Week")
        else:
            st.info("צור סידור תחילה" if lang=="he" else "Generate a schedule first")

    with tab_month:
        if not arch:
            st.info(t("archive_empty", lang))
        else:
            year_opts = sorted(arch.keys(), reverse=True)
            sel_year = st.selectbox("שנה" if lang=="he" else "Year", year_opts, key="stats_year")
            month_opts = sorted(arch.get(sel_year, {}).keys(), reverse=True)
            sel_month = st.selectbox("חודש" if lang=="he" else "Month", month_opts, key="stats_month")
            scheds = load_period_schedules(year=sel_year, month=sel_month)
            _render_stats(scheds, f"{sel_year}/{sel_month}")

    with tab_year:
        if not arch:
            st.info(t("archive_empty", lang))
        else:
            year_opts2 = sorted(arch.keys(), reverse=True)
            sel_year2 = st.selectbox("שנה" if lang=="he" else "Year", year_opts2, key="stats_year2")
            scheds2 = load_period_schedules(year=sel_year2)
            _render_stats(scheds2, f"{sel_year2}")

    st.stop()

# ══════════════════════════════════════════════════════════════════════════
# PAGE: SCHEDULE
# ══════════════════════════════════════════════════════════════════════════

# ── Week picker + generate ─────────────────────────────────────────────────
wc1, wc2 = st.columns([3, 1])
with wc1:
    week_start = st.date_input(t("week_start", lang),
        value=st.session_state.week_start, key="week_start_picker")
    st.session_state.week_start = week_start
with wc2:
    st.write("")
    # Check if a schedule already exists for this week date
    existing = st.session_state.schedule
    week_occupied = (existing is not None and
                     list(existing.keys())[0] == week_start.isoformat() if existing else False)
    if not st.session_state.get("confirm_generate"):
        btn_label = ("🔄 " if week_occupied else "") + t("generate", lang)
        if st.button(btn_label, type="primary", use_container_width=True):
            if week_occupied:
                st.session_state.confirm_generate = True
                st.rerun()
            else:
                st.session_state.schedule = empty_week(week_start)
                for f in AUTO_FIELDS:
                    for key in list(st.session_state.keys()):
                        if key.startswith(f + "_"):
                            del st.session_state[key]
                st.rerun()
    else:
        st.warning("⚠️ " + ("יש כבר סידור — להחליף?" if lang=="he" else "Schedule exists — replace?"))
        ga, gb = st.columns(2)
        if ga.button("✅", use_container_width=True, key="gen_yes"):
            st.session_state.confirm_generate = False
            st.session_state.schedule = empty_week(week_start)
            for f in AUTO_FIELDS:
                for key in list(st.session_state.keys()):
                    if key.startswith(f + "_"):
                        del st.session_state[key]
            st.rerun()
        if gb.button("❌", use_container_width=True, key="gen_no"):
            st.session_state.confirm_generate = False
            st.rerun()

if st.session_state.schedule is None:
    st.info(t("generate", lang) + " ↑")
    st.stop()

schedule = st.session_state.schedule
day_keys = list(schedule.keys())
num_days = len(day_keys)
py_to_key = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]

# ── Print helper ───────────────────────────────────────────────────────────
def generate_print_html(sched: dict, dk_list: list, lng: str) -> str:
    """Generate a self-contained, printable HTML table of the schedule."""
    # Rows follow the configured order; "vacation" fans out to one column
    # per active employee group.
    PRINT_ROWS = [(rk, cfg.row_label(rk, lng)) for rk in cfg.reorderable_row_keys()]

    py_keys = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]

    # Build header: day name + date
    hdr_cells = "<th></th>"
    for dk in dk_list:
        d = sched[dk]["date"]
        dname = cfg.work_day_label(py_keys[d.weekday()]) or t(py_keys[d.weekday()], lng)
        hdr_cells += f"<th>{dname}<br><span class='date'>{d.strftime('%d/%m/%Y')}</span></th>"

    # Section dividers (before these row keys insert a divider row)
    SECTION_DIVIDERS = {}
    for w in cfg.active_workplaces():
        secs = cfg.workplace_sections(w)
        if secs:
            SECTION_DIVIDERS[secs[0]["row_key"]] = "― " + cfg.workplace_name(w) + " ―"
    for k in ("arrival_point", "vehicle_morning", "vehicle_noon"):
        SECTION_DIVIDERS.setdefault(k, "― " + cfg.row_label(k, lng) + " ―")
    SECTION_DIVIDERS.setdefault("trip", "― " + cfg.row_label("trip", lng) + " ―")

    body_rows = ""
    for rk, rlabel in PRINT_ROWS:
        if rk in SECTION_DIVIDERS:
            nc = len(dk_list) + 1
            body_rows += (f'<tr class="section-divider">'
                          f'<td colspan="{nc}">{SECTION_DIVIDERS[rk]}</td></tr>\n')
        cells = f"<td class='label'>{rlabel}</td>"
        for dk in dk_list:
            val = sched[dk].get(rk, "") or ""
            if rk in cfg.AWAY_ROWS:
                val = ", ".join(cfg.away_list(sched[dk], rk))
            cls = ""
            if rk == "vehicle_morning" or rk == "vehicle_noon":
                cls = " yellow" if val == "YELLOW" else (" black" if val == "BLACK" else "")
            cells += f"<td class='val{cls}'>{val}</td>"
        body_rows += f"<tr>{cells}</tr>\n"

    dir_attr = 'dir="rtl"' if lng == "he" else ""
    week_label = dk_list[0] + " — " + dk_list[-1] if dk_list else ""

    html = f"""<!DOCTYPE html>
<html {dir_attr}>
<head>
<meta charset="UTF-8">
<title>Schedule {week_label}</title>
<style>
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; margin: 20px; }}
  h2 {{ font-size: 14px; margin-bottom: 8px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 6px; text-align: center; }}
  th {{ background: #2c3e50; color: #fff; font-size: 12px; }}
  th .date {{ font-size: 10px; font-weight: normal; }}
  td.label {{ text-align: {"right" if lng=="he" else "left"}; font-weight: bold;
               background: #f5f5f5; white-space: nowrap; padding-right: 8px; }}
  tr:nth-child(even) td {{ background: #fafafa; }}
  td.label {{ background: #f0f0f0 !important; }}
  tr.section-divider td {{
    background: #dde3ea; color: #555; font-size: 10px;
    text-align: center; padding: 2px; border-top: 2px solid #aaa;
  }}
  td.yellow {{ background: #fff9c4; font-weight: bold; }}
  td.black  {{ background: #e0e0e0; font-weight: bold; }}
  .print-btn {{
    display: inline-block; margin-bottom: 14px; padding: 8px 18px;
    background: #2c3e50; color: #fff; border: none; border-radius: 4px;
    cursor: pointer; font-size: 13px;
  }}
  @media print {{
    .print-btn {{ display: none; }}
    body {{ margin: 6px; }}
  }}
</style>
</head>
<body>
<button class="print-btn" onclick="window.print()">🖨 Print</button>
<h2>📅 Schedule &nbsp; {week_label}</h2>
<table>
  <thead><tr>{hdr_cells}</tr></thead>
  <tbody>
{body_rows}
  </tbody>
</table>
</body>
</html>"""
    return html

# ── Action bar ─────────────────────────────────────────────────────────────
ac1, ac2, ac3, ac4, ac5 = st.columns(5)

with ac1:
    if st.button("⚡ " + t("auto_assign", lang), type="primary", use_container_width=True):
        # 90-day window, recomputed for the week being generated
        global_hist = build_history(week_start)
        st.session_state.history = global_hist
        # Workplace sections, employee groups and working days all come from the
        # configuration, so auto_assign_day fills them; nothing is pre-planned
        # for a particular station shape here.

        # Axis and wait spots are filled per-day by auto_assign_day via
        # least-used against cumulative+weekly history (equal balance rule).

        # ── Day-by-day fill for remaining fields (entry, exit, arrival, etc.) ─
        weekly_hist = {}
        for dk in day_keys:
            combined = {}
            for field, counts in global_hist.items():
                combined[field] = dict(counts)
            for field, counts in weekly_hist.items():
                combined.setdefault(field, {})
                for val, cnt in counts.items():
                    combined[field][val] = combined[field].get(val, 0) + cnt
            schedule[dk] = auto_assign_day(schedule[dk], combined, day_keys)
            for field in AUTO_FIELDS:
                val = schedule[dk].get(field, "")
                if val:
                    weekly_hist.setdefault(field, {})
                    weekly_hist[field][val] = weekly_hist[field].get(val, 0) + 1

        schedule = auto_assign_week_vehicles_udex(schedule, global_hist)
        st.session_state.schedule = schedule
        # Clear widget keys so they re-init from index= (avoids session-state conflict warning)
        for dk in day_keys:
            for f in AUTO_FIELDS:
                st.session_state.pop(f"{f}_{dk}", None)
        st.session_state.auto_assigned = True
        st.rerun()

with ac2:
    if st.button("🔒 " + t("lock_schedule", lang), use_container_width=True):
        save_schedule(week_start, schedule)
        update_history(st.session_state.history, schedule)
        st.toast("✅ " + t("schedule_locked", lang))

with ac3:
    xlsx_bytes = export_to_excel(schedule, week_start, lang)
    st.download_button(t("export_excel", lang), data=xlsx_bytes,
        file_name=f"schedule_{week_start.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True)

with ac5:
    print_html = generate_print_html(schedule, day_keys, lang)
    st.download_button(
        label="🖨️ " + ("הדפסה" if lang == "he" else ("Imprimir" if lang == "es" else "Print")),
        data=print_html.encode("utf-8"),
        file_name=f"schedule_{week_start.isoformat()}.html",
        mime="text/html",
        use_container_width=True,
    )

with ac4:
    if not st.session_state.get("confirm_reset"):
        if st.button("🗑 " + t("reset", lang), use_container_width=True):
            st.session_state.confirm_reset = True
            st.rerun()
    else:
        st.warning("⚠️ " + ("בטוח?" if lang=="he" else "Sure?"))
        ca, cb = st.columns(2)
        if ca.button("✅ " + ("כן, מחק" if lang=="he" else "Yes, clear"), use_container_width=True):
            st.session_state.confirm_reset = False
            st.session_state.schedule = empty_week(week_start)
            for dk in day_keys:
                for f in AUTO_FIELDS:
                    st.session_state.pop(f"{f}_{dk}", None)
            st.rerun()
        if cb.button("❌ " + ("ביטול" if lang=="he" else "Cancel"), use_container_width=True):
            st.session_state.confirm_reset = False
            st.rerun()

st.divider()

# ── Auto-assign result banner ──────────────────────────────────────────────
if st.session_state.get("auto_assigned"):
    st.session_state.auto_assigned = False

    ALL_DISPLAY_FIELDS = [(_rk, cfg.row_label(_rk, lang))
                          for _rk in cfg.reorderable_row_keys()]

    import pandas as pd
    day_labels_en = [schedule[dk]["date"].strftime("%a %d/%m") for dk in day_keys]
    rows = {}
    for field, label in ALL_DISPLAY_FIELDS:
        rows[label] = {dl: (", ".join(cfg.away_list(schedule[dk], field))
                            if field in cfg.AWAY_ROWS
                            else (schedule[dk].get(field, "") or ""))
                       for dl, dk in zip(day_labels_en, day_keys)}
    df = pd.DataFrame(rows).T
    df.index.name = ""

    any_filled = any(schedule[dk].get(f) for f, _ in ALL_DISPLAY_FIELDS for dk in day_keys)
    if any_filled:
        st.success("✅ " + ("שיבוץ אוטומטי הושלם:" if lang=="he" else "Auto-assign complete:"))
        st.table(df)
    else:
        st.warning("⚠️ " + ("לא היה מה למלא — כל השדות כבר מולאו" if lang == "he"
                             else "Nothing to fill — all fields already assigned"))

# ── Column headers ─────────────────────────────────────────────────────────
hcols = st.columns([2] + [1.5] * num_days)
hcols[0].markdown(f"**{t('row_dates', lang)}**")
for i, dk in enumerate(day_keys):
    d = schedule[dk]["date"]
    dname = t(py_to_key[d.weekday()], lang)
    suffix = " ⏱6h" if d.weekday() == 4 else ""
    hcols[i+1].markdown(f"**{dname}{suffix}**  \n{d.strftime('%d/%m')}")

# ── Row renderer ───────────────────────────────────────────────────────────
def render_row(rk: str):
    cols = st.columns([2] + [1.5] * num_days)
    label = cfg.row_label(rk, lang)
    if rk in ("entry", "exit"):
        cols[0].markdown(f"**🕐 {label}**")
    elif rk == "work_hours":
        cols[0].markdown(f"**⏰ {label}**")
    elif rk in AUTO_FIELDS:
        cols[0].markdown(f"⚡ *{label}*")
    else:
        cols[0].markdown(f"*{label}*")

    for i, dk in enumerate(day_keys):
        day = schedule[dk]
        ck = f"{rk}_{dk}"
        sx = cfg.section_by_row(rk)

        with cols[i+1]:
            if rk == "work_hours":
                d = day.get("date")
                opts = WORK_HOURS          # one shared list for every day
                cur = day.get("work_hours","")
                day["work_hours"] = st.selectbox("", opts,
                    index=opts.index(cur) if cur in opts else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "entry":
                cur = day.get("entry","")
                day["entry"] = st.selectbox("", ENTRY_OPTIONS,
                    index=ENTRY_OPTIONS.index(cur) if cur in ENTRY_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "exit":
                cur = day.get("exit","")
                day["exit"] = st.selectbox("", EXIT_OPTIONS,
                    index=EXIT_OPTIONS.index(cur) if cur in EXIT_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("escort_morning","escort_noon"):
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", ESCORT_OPTIONS,
                    index=ESCORT_OPTIONS.index(cur) if cur in ESCORT_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "school":
                day["school"] = st.text_input("", value=day.get("school",""),
                    key=ck, label_visibility="collapsed")

            elif sx:
                _wp, _sec = sx
                _grp = cfg.group_by_id(_sec.get("group_id"))
                _away = cfg.away_today(day)
                _people = [e for e in (cfg.group_employees(_sec.get("group_id"))
                                       if _grp else ALL_EMPLOYEES) if e not in _away]
                avail = [""] + _people
                _size = cfg.section_size(_sec)
                if _size >= 2:
                    from schedule_logic import _combos
                    avail += _combos(_people, min(_size, len(_people)))
                cur = day.get(rk, "")
                day[rk] = st.selectbox("", avail,
                    index=avail.index(cur) if cur in avail else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "other_empl":
                avail = [""] + ALL_EMPLOYEES
                cur = day.get("other_empl","")
                day["other_empl"] = st.selectbox("", avail,
                    index=avail.index(cur) if cur in avail else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "arrival_point":
                cur = day.get("arrival_point","")
                day["arrival_point"] = st.selectbox("", ARRIVAL_POINT_OPTIONS,
                    index=ARRIVAL_POINT_OPTIONS.index(cur) if cur in ARRIVAL_POINT_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "theater":
                cur = day.get("theater","")
                day["theater"] = st.selectbox("", THEATER_OPTIONS,
                    index=THEATER_OPTIONS.index(cur) if cur in THEATER_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in EXTRA_ROW_KEYS:
                _et = cfg.extra_by_row(rk) or {}
                eopts = [""] + [o for o in _et.get("options", []) if o]
                cur = day.get(rk, "")
                day[rk] = st.selectbox("", eopts,
                    index=eopts.index(cur) if cur in eopts else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("vehicle_morning","vehicle_noon"):
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", VEHICLE_OPTIONS,
                    index=VEHICLE_OPTIONS.index(cur) if cur in VEHICLE_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("axis_morning","axis_noon"):
                _kind = "entry" if rk == "axis_morning" else "exit"
                _allowed = (cfg.allowed_axes_for(_kind, day[_kind])
                            if day.get(_kind) else cfg.axis_letters())
                aopts = [""] + [v for v in cfg.axis_values()
                                if cfg.axis_letter_of(v) in _allowed]
                cur = day.get(rk, "")
                if cur and cur not in aopts:
                    aopts.append(cur)
                day[rk] = st.selectbox("", aopts,
                    index=aopts.index(cur) if cur in aopts else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("wait_morning","wait_noon"):
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", WAIT_SPOT_OPTIONS,
                    index=WAIT_SPOT_OPTIONS.index(cur) if cur in WAIT_SPOT_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("taxi_apt","taxi_arrival","taxi_emb","taxi_arrival_noon"):
                topts = cfg.options_with_blank(rk)
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", topts,
                    index=topts.index(cur) if cur in topts else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in CUSTOM_ROW_MAP:
                rdef = CUSTOM_ROW_MAP[rk]
                if rdef["input"] == "select" and rdef["options"]:
                    copts = [""] + rdef["options"]
                    cur = day.get(rk, "")
                    day[rk] = st.selectbox("", copts,
                        index=copts.index(cur) if cur in copts else 0,
                        key=ck, label_visibility="collapsed")
                else:
                    day[rk] = st.text_input("", value=day.get(rk, ""),
                        key=ck, label_visibility="collapsed")

            elif rk in cfg.AWAY_ROWS:
                day[rk] = st.multiselect(rk, ALL_EMPLOYEES,
                    default=[e for e in cfg.away_list(day, rk) if e in ALL_EMPLOYEES],
                    key=ck, label_visibility="collapsed")

        schedule[dk] = day

# ── Section dividers ───────────────────────────────────────────────────────
ROW_DIVIDERS = {}
for _w in cfg.active_workplaces():
    _secs = cfg.workplace_sections(_w)
    if _secs:
        ROW_DIVIDERS[_secs[0]["row_key"]] = "― " + cfg.workplace_name(_w) + " ―"
for _k in ("arrival_point", "vehicle_morning", "vehicle_noon", "vacation"):
    ROW_DIVIDERS.setdefault(_k, "― " + cfg.row_label(_k, lang) + " ―")

render_rows = [k for k in cfg.all_row_keys() if k not in ("dates","days")]
for rk in render_rows:
    if rk in ROW_DIVIDERS:
        st.markdown(f"<div style='color:#999;font-size:0.75rem;margin:8px 0 2px'>{ROW_DIVIDERS[rk]}</div>",
                    unsafe_allow_html=True)
    render_row(rk)

st.session_state.schedule = schedule

# ── Weekly stats summary ───────────────────────────────────────────────────
st.divider()
with st.expander("📊 " + ("סיכום שוויון שבועי" if lang=="he" else "Weekly Equality Summary")):
    import pandas as pd
    (emp_counts, field_counts, num_days_w, vacation_counts_w, other_counts_w,
     trip_counts_w) = compute_stats([schedule])

    st.markdown("**👤 " + ("חלוקת עובדים" if lang=="he" else "Employee Distribution") + "**")
    emp_rows = {}
    for emp in ALL_EMPLOYEES:
        row = {}
        for r in EMPLOYEE_ROLES:
            cnt = emp_counts[emp][r]
            pct = (cnt / num_days_w * 100) if num_days_w else 0
            row[EMPLOYEE_ROLE_LABELS[r]] = f"{cnt} ({pct:.0f}%)"
        vac = vacation_counts_w.get(emp, 0)
        row["Vacation"] = str(vac)
        other_w = other_counts_w.get(emp, 0)
        row["Other"] = str(other_w)
        emp_rows[emp] = row
    emp_df = pd.DataFrame(emp_rows).T
    emp_df.index.name = ""
    st.dataframe(emp_df, use_container_width=True)

    st.markdown("**📋 " + ("חלוקת ערכים" if lang=="he" else "Value Distribution") + "**")
    for field, label in VALUE_FIELDS:
        counts = field_counts.get(field, {})
        if not counts:
            continue
        total_w = sum(counts.values())
        all_vals = sorted(counts.keys())
        row = {v: f"{counts[v]} ({counts[v]/total_w*100:.0f}%)" for v in all_vals}
        df = pd.DataFrame([row], index=[label])
        df.index.name = ""
        st.dataframe(df, use_container_width=True)

# ── Validation ─────────────────────────────────────────────────────────────
st.divider()
errs = validate_schedule(schedule, lang)
if errs:
    for e in errs:
        if e.startswith("❌"):   # critical conflict → red error
            st.error(e)
        else:                    # soft warning (counts etc.) → yellow
            st.warning(e)
else:
    st.success(t("valid", lang))
