"""
Weekly Work Schedule – Taxi Company
Streamlit app: multilingual (HE/EN/ES), local archive, Excel export.
"""
from datetime import date, timedelta

import streamlit as st

from translations import t
from schedule_logic import (
    EMPLOYEES_IL, EMPLOYEES_PE, ALL_EMPLOYEES,
    WORK_HOURS_WEEKDAY, WORK_HOURS_FRIDAY,
    ENTRY_OPTIONS, EXIT_OPTIONS, ESCORT_OPTIONS,
    ARRIVAL_POINT_OPTIONS, THEATER_OPTIONS, UDEX_OPTIONS,
    VEHICLE_OPTIONS, AXIS_OPTIONS, WAIT_SPOT_OPTIONS,
    ROW_KEYS, empty_week, validate_schedule,
    auto_assign_day, auto_assign_week_vehicles_udex, update_history,
)
from excel_export import export_to_excel
from archive_storage import save_schedule, load_schedule, list_archive, delete_schedule
from stats import compute_stats, load_period_schedules, EMPLOYEE_ROLES, EMPLOYEE_ROLE_LABELS, VALUE_FIELDS, VACATION_BUDGET

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

# Fields that auto-assign fills (need session-state sync on assign)
AUTO_FIELDS = [
    "entry", "exit",
    "emb_il", "emb_pe", "arrival_point", "theater", "udex",
    "apt_il", "apt_pe", "vehicle_morning", "vehicle_noon",
    "axis_morning", "axis_noon", "wait_morning", "wait_noon",
    "taxi_apt", "taxi_arrival", "taxi_emb", "taxi_arrival_noon",
]

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
h1, h2, h3, h4, h5 = st.columns([3, 1, 1, 1, 1])
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

st.divider()

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
    for emp in ["LEON", "CUY", "HALCON", "CHCHORRO", "BUHO"]:
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

    # ── IL / PE pie charts (English labels to avoid RTL reversal) ───────
    col_il, col_pe = st.columns(2)
    with col_il:
        fig, ax = plt.subplots(figsize=(5, 4))
        fig.patch.set_alpha(0.0); ax.set_facecolor("none")
        labels, values = [], []
        for emp in ["LEON", "CUY"]:
            for r in ["emb_il", "apt_il"]:
                cnt = emp_counts[emp][r]
                if cnt:
                    labels.append(f"{emp}\n{EMPLOYEE_ROLE_LABELS[r]}")
                    values.append(cnt)
        if values:
            ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
        ax.set_title("IL Employees")
        st.pyplot(fig)
        plt.close(fig)

    with col_pe:
        fig, ax = plt.subplots(figsize=(5, 4))
        fig.patch.set_alpha(0.0); ax.set_facecolor("none")
        labels, values = [], []
        for emp in ["HALCON", "CHCHORRO", "BUHO"]:
            for r in ["emb_pe", "apt_pe"]:
                cnt = emp_counts[emp][r]
                if cnt:
                    labels.append(f"{emp}\n{EMPLOYEE_ROLE_LABELS[r]}")
                    values.append(cnt)
        if values:
            ax.pie(values, labels=labels, autopct="%1.0f%%", startangle=90)
        ax.set_title("PE Employees")
        st.pyplot(fig)
        plt.close(fig)

    # ── Vacation breakdown with annual budget ──────────────────────────
    st.markdown("##### 🏖 " + ("חופשות" if lang == "he" else "Vacations"))
    vac_rows = {}
    for emp in ["LEON", "CUY", "HALCON", "CHCHORRO", "BUHO"]:
        vac = vacation_counts.get(emp, 0)
        budget = VACATION_BUDGET[emp]
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
    # 5 individual pies — one per employee showing % utilization of annual budget
    pie_cols = st.columns(5)
    for col, emp in zip(pie_cols, ["LEON", "CUY", "HALCON", "CHCHORRO", "BUHO"]):
        vac = vacation_counts.get(emp, 0)
        budget = VACATION_BUDGET[emp]
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

    # UDEX — always show all 4 options (EMB-M, R-M, EMB-T, R-T) even if 0
    udex_counts = field_counts.get("udex", {})
    udex_total = sum(udex_counts.values()) or 1
    udex_row_m = {}
    for v in ["EMB-M", "R-M"]:
        cnt = udex_counts.get(v, 0)
        udex_row_m[v] = f"{cnt} ({cnt/udex_total*100:.0f}%)"
    udex_row_t = {}
    for v in ["EMB-T", "R-T"]:
        cnt = udex_counts.get(v, 0)
        udex_row_t[v] = f"{cnt} ({cnt/udex_total*100:.0f}%)"
    df_um = pd.DataFrame([udex_row_m], index=["UDEX (M-type)"]); df_um.index.name = ""
    df_ut = pd.DataFrame([udex_row_t], index=["UDEX (T-type)"]); df_ut.index.name = ""
    st.dataframe(df_um, use_container_width=True)
    st.dataframe(df_ut, use_container_width=True)

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
    PRINT_ROWS = [
        ("work_hours",        t("row_work_hours",   lng)),
        ("entry",             t("row_entry",        lng)),
        ("exit",              t("row_exit",         lng)),
        ("escort_morning",    t("row_escort_morning", lng)),
        ("school",            t("row_school",       lng)),
        ("escort_noon",       t("row_escort_noon",  lng)),
        ("emb_il",            t("row_emb_il",       lng)),
        ("emb_pe",            t("row_emb_pe",       lng)),
        ("other_empl",        t("row_other_empl",   lng)),
        ("arrival_point",     t("row_arrival_point",lng)),
        ("theater",           t("row_theater",      lng)),
        ("udex",              t("row_udex",         lng)),
        ("apt_il",            t("row_apt_il",       lng)),
        ("apt_pe",            t("row_apt_pe",       lng)),
        ("vehicle_morning",   t("row_vehicle_morning", lng)),
        ("axis_morning",      t("row_axis_morning", lng)),
        ("wait_morning",      t("row_wait_morning", lng)),
        ("vehicle_noon",      t("row_vehicle_noon", lng)),
        ("axis_noon",         t("row_axis_noon",    lng)),
        ("wait_noon",         t("row_wait_noon",    lng)),
        ("vacation_il",       t("row_vacation",     lng) + " IL"),
        ("vacation_pe",       t("row_vacation",     lng) + " PE"),
    ]

    py_keys = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]

    # Build header: day name + date
    hdr_cells = "<th></th>"
    for dk in dk_list:
        d = sched[dk]["date"]
        dname = t(py_keys[d.weekday()], lng)
        hdr_cells += f"<th>{dname}<br><span class='date'>{d.strftime('%d/%m/%Y')}</span></th>"

    # Section dividers (before these row keys insert a divider row)
    SECTION_DIVIDERS = {
        "emb_il":          "― EMB ―",
        "arrival_point":   "― " + t("row_arrival_point",lng) + " / " + t("row_theater",lng) + " / UDEX ―",
        "apt_il":          "― " + t("row_apt_il",lng) + " / " + t("row_apt_pe",lng) + " ―",
        "vehicle_morning": "― " + t("row_vehicle_morning",lng) + " ―",
        "vehicle_noon":    "― " + t("row_vehicle_noon",lng) + " ―",
        "vacation_il":     "― " + t("row_vacation",lng) + " ―",
    }

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
        import random as _rnd
        global_hist = st.session_state.history

        # ── Pre-plan EMB IL: guaranteed 3:2 split across the week ────────────
        il_hist = global_hist.get("emb_il", {})
        sorted_il = sorted(EMPLOYEES_IL, key=lambda e: il_hist.get(e, 0))
        if il_hist.get(sorted_il[0], 0) == il_hist.get(sorted_il[1], 0):
            _rnd.shuffle(sorted_il)
        # Alternating pattern so no employee works consecutive days at same role
        # sorted_il[0] = less-used → gets days 0,2,4 (3 days); [1] gets 1,3 (2 days)
        emb_il_plan = [sorted_il[i % 2] for i in range(5)]

        # ── Pre-plan Apt PE: guaranteed 2:2:1 split across the week ─────────
        pe_hist = global_hist.get("apt_pe", {})
        sorted_pe = sorted(EMPLOYEES_PE, key=lambda e: pe_hist.get(e, 0))
        # sorted_pe[0] least-used → 2 days, [1] → 2 days, [2] most-used → 1 day
        apt_pe_plan = [sorted_pe[0]] * 2 + [sorted_pe[1]] * 2 + [sorted_pe[2]] * 1
        _rnd.shuffle(apt_pe_plan)

        # ── Pre-populate employee fields respecting vacations ─────────────────
        for i, dk in enumerate(day_keys):
            vac_il = schedule[dk].get("vacation_il", "")
            vac_pe = schedule[dk].get("vacation_pe", "")

            other_empl_day = schedule[dk].get("other_empl", "")

            # EMB IL — exclude vacationing AND employee in "other" task
            if not schedule[dk].get("emb_il"):
                planned = emb_il_plan[i]
                if planned == vac_il or planned == other_empl_day:
                    others = [e for e in EMPLOYEES_IL if e != vac_il and e != other_empl_day]
                    planned = others[0] if others else ""
                schedule[dk]["emb_il"] = planned

            # Apt IL (must differ from emb_il, vac_il, other_empl)
            if not schedule[dk].get("apt_il"):
                emb = schedule[dk].get("emb_il", "")
                apt_opts = [e for e in EMPLOYEES_IL if e != emb and e != vac_il and e != other_empl_day]
                schedule[dk]["apt_il"] = apt_opts[0] if apt_opts else ""

            # Apt PE
            if not schedule[dk].get("apt_pe"):
                planned_pe = apt_pe_plan[i]
                if planned_pe == vac_pe:
                    others_pe = [e for e in EMPLOYEES_PE if e != vac_pe]
                    planned_pe = min(others_pe, key=lambda e: pe_hist.get(e, 0)) if others_pe else ""
                schedule[dk]["apt_pe"] = planned_pe

            # EMB PE: pair from remaining active PE (not apt_pe, not vac_pe, not emb_il if PE)
            if not schedule[dk].get("emb_pe"):
                emb_il_val = schedule[dk].get("emb_il", "")
                emb_il_pe = emb_il_val if emb_il_val in EMPLOYEES_PE else ""
                apt_pe_val = schedule[dk].get("apt_pe", "")
                pair = [e for e in EMPLOYEES_PE
                        if e != apt_pe_val and e != emb_il_pe and e != vac_pe]
                ordered = [e for e in EMPLOYEES_PE if e in pair]
                schedule[dk]["emb_pe"] = "+".join(ordered) if len(ordered) >= 2 else (ordered[0] if ordered else "")

        # ── Pre-plan Axis: always pick the 5 LEAST-USED axes (compensates imbalance)
        # History is rebuilt from archive at session start, so this reads true
        # cumulative usage and always corrects any existing imbalance.
        all_axes = [v for v in AXIS_OPTIONS if v]   # A1-D5, 20 values
        axis_hist_m = global_hist.get("axis_morning", {})
        axis_hist_n = global_hist.get("axis_noon", {})
        sorted_axes_m = sorted(all_axes, key=lambda x: (axis_hist_m.get(x, 0), x))
        axis_morning_plan = sorted_axes_m[:5]
        _rnd.shuffle(axis_morning_plan)
        sorted_axes_n = sorted(all_axes, key=lambda x: (axis_hist_n.get(x, 0), x))
        axis_noon_plan = [x for x in sorted_axes_n if x not in axis_morning_plan][:5]
        if len(axis_noon_plan) < 5:
            axis_noon_plan += [x for x in sorted_axes_n if x in axis_morning_plan][:5 - len(axis_noon_plan)]
        _rnd.shuffle(axis_noon_plan)

        # ── Pre-plan Wait spots: strict round-robin (all 5 values once each) ──
        wait_vals = [v for v in WAIT_SPOT_OPTIONS if v]
        wait_hist_m = global_hist.get("wait_morning", {})
        wait_hist_n = global_hist.get("wait_noon", {})
        wait_morning_plan = sorted(wait_vals, key=lambda x: wait_hist_m.get(x, 0))[:5]
        _rnd.shuffle(wait_morning_plan)
        wait_noon_plan = sorted(wait_vals, key=lambda x: wait_hist_n.get(x, 0))[:5]
        _rnd.shuffle(wait_noon_plan)

        # ── Pre-populate axis and wait ────────────────────────────────────────
        for i, dk in enumerate(day_keys):
            if not schedule[dk].get("axis_morning"):
                schedule[dk]["axis_morning"] = axis_morning_plan[i]
            if not schedule[dk].get("axis_noon"):
                schedule[dk]["axis_noon"] = axis_noon_plan[i]
            if not schedule[dk].get("wait_morning"):
                schedule[dk]["wait_morning"] = wait_morning_plan[i]
            if not schedule[dk].get("wait_noon"):
                schedule[dk]["wait_noon"] = wait_noon_plan[i]

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

    ALL_DISPLAY_FIELDS = [
        ("work_hours",        "Work Hours"),
        ("entry",             "Entry"),
        ("exit",              "Exit"),
        ("escort_morning",    "Morning Escort"),
        ("school",            "School"),
        ("escort_noon",       "Noon Escort"),
        ("emb_il",            "EMB IL"),
        ("emb_pe",            "EMB PE"),
        ("other_empl",        "Other"),
        ("arrival_point",     "Arrival Point"),
        ("theater",           "Theater"),
        ("udex",              "UDEX"),
        ("apt_il",            "Apt IL"),
        ("apt_pe",            "Apt PE"),
        ("vehicle_morning",   "Vehicle Morning"),
        ("axis_morning",      "Axis Morning"),
        ("wait_morning",      "Wait Morning"),
        ("taxi_apt",          "Taxi Apt"),
        ("taxi_arrival",      "Taxi Arrival"),
        ("vehicle_noon",      "Vehicle Noon"),
        ("axis_noon",         "Axis Noon"),
        ("wait_noon",         "Wait Noon"),
        ("taxi_emb",          "Taxi EMB"),
        ("taxi_arrival_noon", "Taxi Arrival Noon"),
        ("vacation_il",       "Vacation IL"),
        ("vacation_pe",       "Vacation PE"),
    ]

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
    label = t(f"row_{rk}", lang)
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
        vac_il = day.get("vacation_il", "")
        vac_pe = day.get("vacation_pe", "")

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

            elif rk == "emb_il":
                avail = [""] + [e for e in EMPLOYEES_IL if e != vac_il]
                cur = day.get("emb_il","")
                day["emb_il"] = st.selectbox("", avail,
                    index=avail.index(cur) if cur in avail else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "emb_pe":
                avail = [""] + [e for e in EMPLOYEES_PE if e != vac_pe] + \
                    [f"{a}+{b}" for ii,a in enumerate(EMPLOYEES_PE)
                     for b in EMPLOYEES_PE[ii+1:]
                     if a != vac_pe and b != vac_pe]
                cur = day.get("emb_pe","")
                day["emb_pe"] = st.selectbox("", avail,
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

            elif rk == "apt_il":
                avail = [""] + [e for e in EMPLOYEES_IL if e != vac_il]
                cur = day.get("apt_il","")
                day["apt_il"] = st.selectbox("", avail,
                    index=avail.index(cur) if cur in avail else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "apt_pe":
                avail = [""] + [e for e in EMPLOYEES_PE if e != vac_pe]
                cur = day.get("apt_pe","")
                day["apt_pe"] = st.selectbox("", avail,
                    index=avail.index(cur) if cur in avail else 0,
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

            elif rk in ("wait_morning","wait_noon","taxi_apt","taxi_arrival","taxi_emb","taxi_arrival_noon"):
                cur = day.get(rk,"")
                day[rk] = st.selectbox("", WAIT_SPOT_OPTIONS,
                    index=WAIT_SPOT_OPTIONS.index(cur) if cur in WAIT_SPOT_OPTIONS else 0,
                    key=ck, label_visibility="collapsed")

            elif rk == "vacation":
                avail_il = [""] + EMPLOYEES_IL
                avail_pe = [""] + EMPLOYEES_PE
                cur_il = day.get("vacation_il","")
                cur_pe = day.get("vacation_pe","")
                day["vacation_il"] = st.selectbox("IL", avail_il,
                    index=avail_il.index(cur_il) if cur_il in avail_il else 0,
                    key=ck+"_il", label_visibility="collapsed")
                day["vacation_pe"] = st.selectbox("PE", avail_pe,
                    index=avail_pe.index(cur_pe) if cur_pe in avail_pe else 0,
                    key=ck+"_pe", label_visibility="collapsed")

        schedule[dk] = day

# ── Section dividers ───────────────────────────────────────────────────────
SECTIONS = {
    "emb_il":         "― EMB ―",
    "arrival_point":  "― " + t("row_arrival_point",lang) + " / " + t("row_theater",lang) + " / UDEX ―",
    "apt_il":         "― " + t("row_apt_il",lang) + " / " + t("row_apt_pe",lang) + " ―",
    "vehicle_morning":"― " + t("row_vehicle_morning",lang) + " ―",
    "vehicle_noon":   "― " + t("row_vehicle_noon",lang) + " ―",
    "vacation":       "― " + t("row_vacation",lang) + " ―",
}

render_rows = [k for k in ROW_KEYS if k not in ("dates","days")]
for rk in render_rows:
    if rk in SECTIONS:
        st.markdown(f"<div style='color:#999;font-size:0.75rem;margin:8px 0 2px'>{SECTIONS[rk]}</div>",
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
    for emp in ["LEON","CUY","HALCON","CHCHORRO","BUHO"]:
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
