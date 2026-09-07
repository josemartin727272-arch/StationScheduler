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
from stats import compute_stats, load_period_schedules, EMPLOYEE_ROLES, EMPLOYEE_ROLE_LABELS, VALUE_FIELDS, vacation_budget

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Schedule 🚕", layout="wide",
                   initial_sidebar_state="collapsed")

# ── Session state ──────────────────────────────────────────────────────────
def _init():
    ss = st.session_state
    if "lang" not in ss:           ss.lang = "he"
    if "schedule" not in ss:       ss.schedule = None
    if "history" not in ss:
        # Rebuild cumulative history from ALL archived schedules so pre-planning
        # picks truly least-used options even after restarting the app.
        from stats import load_period_schedules as _lps
        ss.history = {}
        for _s in _lps():
            update_history(ss.history, _s)
    if "page" not in ss:           ss.page = "schedule"
    if "week_start" not in ss:
        today = date.today()
        diff = (7 - today.weekday()) % 7 or 7
        ss.week_start = today + timedelta(days=diff)
_init()

lang = st.session_state.lang

# ── Everything below re-reads config.json each rerun, so Settings-page
#    edits apply immediately ─────────────────────────────────────────────────
ACTIVE_GROUPS = cfg.active_groups()
ALL_EMPLOYEES = cfg.all_employees()
SECTIONS = cfg.all_sections()                 # [(workplace, section)]
SECTION_KEYS = cfg.section_row_keys()
VAC_FIELDS = cfg.vac_fields()
WORK_HOURS_WEEKDAY = cfg.options_with_blank("work_hours_weekday")
WORK_HOURS_FRIDAY  = cfg.options_with_blank("work_hours_friday")
ENTRY_OPTIONS = cfg.options_with_blank("entry")
EXIT_OPTIONS  = cfg.options_with_blank("exit")
ESCORT_OPTIONS = cfg.options_with_blank("escort")
ARRIVAL_POINT_OPTIONS = cfg.options_with_blank("arrival_point")
THEATER_OPTIONS = cfg.options_with_blank("theater")
UDEX_OPTIONS = [""] + cfg.extra_options()
VEHICLE_OPTIONS = cfg.options_with_blank("vehicle")
AXIS_OPTIONS = cfg.options_with_blank("axis")
WAIT_SPOT_OPTIONS = cfg.options_with_blank("wait_spot")
CUSTOM_ROWS = cfg.custom_rows()
CUSTOM_ROW_MAP = {r["key"]: r for r in CUSTOM_ROWS}
VACATION_BUDGET = vacation_budget()

# Fields that auto-assign fills (need session-state sync on assign)
AUTO_FIELDS = [
    "entry", "exit", "arrival_point", "theater", "udex",
    "vehicle_morning", "vehicle_noon",
    "axis_morning", "axis_noon", "wait_morning", "wait_noon",
    "taxi_apt", "taxi_arrival", "taxi_emb", "taxi_arrival_noon",
] + SECTION_KEYS

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
        st.caption(t("wp_notes_hint", lang))
        act_wps = [w for w in config["workplaces"] if w.get("active")]
        act_gids = [g["id"] for g in config["groups"] if g.get("active")]
        if not act_wps:
            st.warning(t("wp_none", lang))
        for w in act_wps:
            wid = w["id"]
            with st.expander(cfg.workplace_name(w), expanded=True):
                st.text_input(t("wp_name", lang), value=w.get("name", ""),
                              key=f"wpname_{wid}")
                st.markdown("**" + t("wp_sections", lang) + "**")
                for sec in w.get("sections", []):
                    sid = sec["id"]
                    s1, s2, s3, s4 = st.columns([3, 2, 2, 1])
                    s1.text_input(t("wp_sec_name", lang), value=sec.get("name", ""),
                                  key=f"scname_{sid}")
                    s2.selectbox(t("wp_sec_group", lang), act_gids,
                        index=act_gids.index(sec["group_id"]) if sec.get("group_id") in act_gids else 0,
                        key=f"scgroup_{sid}", format_func=lambda g: cfg.group_name(cfg.group_by_id(g)))
                    s3.checkbox(t("wp_sec_pair", lang), value=bool(sec.get("allow_pair")),
                                key=f"scpair_{sid}")
                    if s4.button("🗑", key=f"screm_{sid}"):
                        w["sections"] = [x for x in w["sections"] if x["id"] != sid]
                        cfg.save_config(config)
                        st.rerun()
                if st.button(t("wp_sec_add", lang), key=f"scadd_{wid}"):
                    uid = uuid4().hex[:8]
                    w.setdefault("sections", []).append({
                        "id": f"s_{uid}", "name": "",
                        "group_id": act_gids[0] if act_gids else "",
                        "row_key": f"sec_{uid}"})
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
                w["notes"] = st.session_state.get(f"wpnotes_{w['id']}", w.get("notes", ""))
                for sec in w.get("sections", []):
                    sid = sec["id"]
                    sec["name"] = st.session_state.get(f"scname_{sid}", sec.get("name", "")).strip()
                    sec["group_id"] = st.session_state.get(f"scgroup_{sid}", sec.get("group_id"))
                    sec["allow_pair"] = bool(st.session_state.get(f"scpair_{sid}"))
            cfg.save_config(config)
            st.success("✅ " + t("settings_saved", lang))
            st.rerun()
        free_wp = next((w for w in config["workplaces"] if not w.get("active")), None)
        if st.button(t("wp_add", lang), disabled=free_wp is None, key="add_wp"):
            free_wp["active"] = True
            free_wp["name"] = free_wp["name"] or free_wp["id"].upper()
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
            st.markdown("**" + t("wd_labels_title", lang) + "**")
            wl1, wl2 = st.columns(2)
            wl1.text_input(t("wd_lbl_weekday", lang),
                value=(config.get("work_day_labels") or {}).get("weekday", ""), key="wdl_weekday")
            wl2.text_input(t("wd_lbl_friday", lang),
                value=(config.get("work_day_labels") or {}).get("friday", ""), key="wdl_friday")
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                days = [d for d in cfg.DOW_ORDER if st.session_state.get(f"wd_{d}")]
                if not days:
                    st.error(t("wd_none", lang))
                else:
                    config["work_days"] = {
                        "days": days,
                        "labels": {d: (st.session_state.get(f"wdlbl_{d}", "").strip()
                                       or t(d, lang)) for d in cfg.DOW_ORDER}}
                    config["work_day_labels"] = {
                        "weekday": st.session_state.get("wdl_weekday", "").strip(),
                        "friday":  st.session_state.get("wdl_friday", "").strip()}
                    cfg.save_config(config)
                    st.success("✅ " + t("settings_saved", lang))
                    st.rerun()

    # ── Tab 4: The extra task (was UDEX) ───────────────────────────────────
    with tab_extra:
        et = config["extra_task"]
        with st.form("extra_form"):
            e1, e2, e3 = st.columns(3)
            v_he = e1.text_input(t("et_name", lang) + " (he)", value=et["label"].get("he", ""))
            v_en = e2.text_input(t("et_name", lang) + " (en)", value=et["label"].get("en", ""))
            v_es = e3.text_input(t("et_name", lang) + " (es)", value=et["label"].get("es", ""))
            o1, o2, o3 = st.columns(3)
            v_opts = o1.text_area(t("et_options", lang),
                value="\n".join(et.get("options", [])), height=130)
            v_m = o2.text_area(t("et_morning", lang),
                value="\n".join(et.get("morning_values", [])), height=130)
            v_n = o3.text_area(t("et_noon", lang),
                value="\n".join(et.get("noon_values", [])), height=130)
            g1, g2 = st.columns(2)
            v_tm = g1.number_input(t("et_tg_m", lang), min_value=0, max_value=7,
                value=int((et.get("targets") or {}).get("morning", 0)))
            v_tn = g2.number_input(t("et_tg_n", lang), min_value=0, max_value=7,
                value=int((et.get("targets") or {}).get("noon", 0)))
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                lines = lambda txt: [l.strip() for l in txt.splitlines() if l.strip()]
                config["extra_task"] = {
                    "label": {"he": v_he.strip() or "?", "en": v_en.strip() or v_he.strip() or "?",
                              "es": v_es.strip() or v_he.strip() or "?"},
                    "options": lines(v_opts),
                    "morning_values": lines(v_m),
                    "noon_values": lines(v_n),
                    "targets": {"morning": int(v_tm), "noon": int(v_tn)},
                }
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
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
        _wdl = cfg.work_day_type_labels()
        weekday_lbl = _wdl.get("weekday") or t("monday", lang)
        friday_lbl = _wdl.get("friday") or t("friday", lang)
        OPTION_GROUPS = [
            ("entry",         t("row_entry", lang)),
            ("exit",          t("row_exit", lang)),
            ("escort",        t("row_escort_morning", lang) + " / " + t("row_escort_noon", lang)),
            ("arrival_point", t("row_arrival_point", lang)),
            ("theater",       t("row_theater", lang)),
            ("vehicle",       t("row_vehicle_morning", lang) + " / " + t("row_vehicle_noon", lang)),
            ("axis",          t("row_axis_morning", lang) + " / " + t("row_axis_noon", lang)),
            ("wait_spot",     t("row_wait_morning", lang) + " / " + t("row_wait_noon", lang)),
            ("taxi_apt",          cfg.row_label("taxi_apt", lang)),
            ("taxi_arrival",      cfg.row_label("taxi_arrival", lang)),
            ("taxi_emb",          cfg.row_label("taxi_emb", lang)),
            ("taxi_arrival_noon", cfg.row_label("taxi_arrival_noon", lang)),
            ("work_hours_weekday", t("row_work_hours", lang) + f" ({weekday_lbl})"),
            ("work_hours_friday",  t("row_work_hours", lang) + f" ({friday_lbl})"),
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

    # ── Tab 4: Weekly targets ──────────────────────────────────────────────
    with tab_targets:
        with st.form("targets_form"):
            tg = config["targets"]
            g1, g2 = st.columns(2)
            v_yellow = g1.number_input(t("targets_yellow", lang),
                min_value=0, max_value=10, value=int(tg["yellow_per_week"]))
            v_theater = g2.number_input(t("targets_theater", lang),
                min_value=0, max_value=5, value=int(tg["theater_per_week"]))
            if st.form_submit_button("💾 " + t("save_settings", lang), type="primary"):
                config["targets"] = {
                    "yellow_per_week": int(v_yellow),
                    "theater_per_week": int(v_theater),
                    # keep the per-field percentages; the vehicle row is just
                    # another view of yellow_per_week, so re-derive it
                    "field_pcts": config["targets"].get("field_pcts", {}),
                }
                cfg.save_config(config)
                config["targets"]["field_pcts"]["vehicle"] = cfg.default_pcts("vehicle")
                cfg.save_config(config)
                st.success("✅ " + t("settings_saved", lang))
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
                        config["targets"].setdefault("field_pcts", {})[key] = \
                            {k: int(x) for k, x in entered.items()}
                        if key == "vehicle":
                            config["targets"]["yellow_per_week"] = round(
                                entered.get(cfg.special("vehicle_special"), 0) / 10)
                        cfg.save_config(config)
                        st.success("✅ " + t("settings_saved", lang))
                        st.rerun()

        # ── Manual entry/exit ↔ axis reference maps (never enforced) ───────
        st.markdown("### " + t("map_title", lang))
        st.caption(t("map_hint", lang))
        for opt_key, cfg_key, title_key in [
                ("entry", "entry_axis_map", "map_entry_title"),
                ("exit", "exit_axis_map", "map_exit_title")]:
            saved = cfg.reference_map(cfg_key)
            with st.form(f"map_form_{cfg_key}"):
                st.markdown(f"**{t(title_key, lang)}**")
                entered = {}
                for v in cfg.options(opt_key):
                    entered[v] = st.text_input(
                        f'{v} → {t("map_axes", lang)}', value=saved.get(v, ""),
                        key=f"map_{cfg_key}_{v}")
                if st.form_submit_button("💾 " + t("save_settings", lang)):
                    config[cfg_key] = {k: x.strip()
                                       for k, x in entered.items() if x.strip()}
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
    emp_counts, field_counts, num_days, vacation_counts, other_counts = compute_stats(schedules)

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

    # Extra task — always show every configured value, even at 0
    extra_counts = field_counts.get("udex", {})
    extra_total = sum(extra_counts.values()) or 1
    extra_name = cfg.extra_label(lang)
    for vals, suffix in ((cfg.extra_morning_values(), t("et_tg_m", lang)),
                         (cfg.extra_noon_values(), t("et_tg_n", lang))):
        if not vals:
            continue
        row = {v: f"{extra_counts.get(v, 0)} "
                  f"({extra_counts.get(v, 0) / extra_total * 100:.0f}%)" for v in vals}
        df_e = pd.DataFrame([row], index=[f"{extra_name} — {suffix}"])
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
    PRINT_ROWS = []
    for rk in cfg.reorderable_row_keys():
        if rk == "vacation":
            for g in cfg.active_groups():
                PRINT_ROWS.append((cfg.vac_field(g),
                                   cfg.row_label("vacation", lng) + " " + cfg.group_name(g)))
        else:
            PRINT_ROWS.append((rk, cfg.row_label(rk, lng)))

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
    first_vac = cfg.vac_fields()
    if first_vac:
        SECTION_DIVIDERS.setdefault(first_vac[0], "― " + cfg.row_label("vacation", lng) + " ―")

    body_rows = ""
    for rk, rlabel in PRINT_ROWS:
        if rk in SECTION_DIVIDERS:
            nc = len(dk_list) + 1
            body_rows += (f'<tr class="section-divider">'
                          f'<td colspan="{nc}">{SECTION_DIVIDERS[rk]}</td></tr>\n')
        cells = f"<td class='label'>{rlabel}</td>"
        for dk in dk_list:
            val = sched[dk].get(rk, "") or ""
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
        global_hist = st.session_state.history
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

        # Monthly history (last ~35 days of archive) drives the YELLOW
        # morning/noon split decision
        month_floor = (week_start - timedelta(days=35)).isoformat()
        monthly_hist = {}
        for _s in load_period_schedules():
            wk_keys = sorted(_s.keys())
            if wk_keys and wk_keys[0] >= month_floor:
                update_history(monthly_hist, _s)
        schedule = auto_assign_week_vehicles_udex(schedule, global_hist, monthly_hist)
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

    ALL_DISPLAY_FIELDS = []
    for _rk in cfg.reorderable_row_keys():
        if _rk == "vacation":
            for _g in cfg.active_groups():
                ALL_DISPLAY_FIELDS.append(
                    (cfg.vac_field(_g), "Vacation " + cfg.group_name(_g)))
        else:
            ALL_DISPLAY_FIELDS.append((_rk, cfg.row_label(_rk, lang)))

    import pandas as pd
    day_labels_en = [schedule[dk]["date"].strftime("%a %d/%m") for dk in day_keys]
    rows = {}
    for field, label in ALL_DISPLAY_FIELDS:
        rows[label] = {dl: (schedule[dk].get(field, "") or "") for dl, dk in zip(day_labels_en, day_keys)}
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
                opts = WORK_HOURS_FRIDAY if (hasattr(d,"weekday") and d.weekday()==4) else WORK_HOURS_WEEKDAY
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
                _vac = day.get(cfg.vac_field(_grp), "") if _grp else ""
                _people = [e for e in (cfg.group_employees(_sec.get("group_id"))
                                       if _grp else ALL_EMPLOYEES) if e != _vac]
                avail = [""] + _people
                if _sec.get("allow_pair"):
                    avail += [f"{a}+{b}" for ii, a in enumerate(_people)
                              for b in _people[ii + 1:]]
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

            elif rk == "udex":
                cur = day.get("udex","")
                day["udex"] = st.selectbox("", UDEX_OPTIONS,
                    index=UDEX_OPTIONS.index(cur) if cur in UDEX_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("vehicle_morning","vehicle_noon"):
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", VEHICLE_OPTIONS,
                    index=VEHICLE_OPTIONS.index(cur) if cur in VEHICLE_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk in ("axis_morning","axis_noon"):
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", AXIS_OPTIONS,
                    index=AXIS_OPTIONS.index(cur) if cur in AXIS_OPTIONS else 0,
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

            elif rk == "vacation":
                for _g in ACTIVE_GROUPS:
                    _f = cfg.vac_field(_g)
                    _av = [""] + cfg.group_employees(_g["id"])
                    _cur = day.get(_f, "")
                    day[_f] = st.selectbox(cfg.group_name(_g), _av,
                        index=_av.index(_cur) if _cur in _av else 0,
                        key=f"{ck}_{_g['id']}", label_visibility="collapsed")

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
    emp_counts, field_counts, num_days_w, vacation_counts_w, other_counts_w = compute_stats([schedule])

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
