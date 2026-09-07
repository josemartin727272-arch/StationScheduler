"""
Export weekly schedule to a styled Excel file.
"""
import io
from datetime import date

try:
    from openpyxl import Workbook
    from openpyxl.styles import (
        PatternFill, Font, Alignment, Border, Side, numbers
    )
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


# Color palette
COLOR_HEADER_BG = "1F4E79"
COLOR_HEADER_FG = "FFFFFF"
COLOR_ROW_ODD = "EBF3FB"
COLOR_ROW_EVEN = "FFFFFF"
COLOR_IL_BG = "D6E4F0"
COLOR_PE_BG = "FAD7A0"
COLOR_YELLOW = "FFD700"
COLOR_EMB_M = "A9DFBF"
COLOR_EMB_T = "F9E79F"
COLOR_VACATION = "F1948A"
COLOR_SECTION_HEADER = "2E86C1"


def export_to_excel(schedule: dict, week_start: date, lang: str = "he") -> bytes:
    """
    Build and return an Excel workbook as bytes.
    """
    from translations import t
    import app_config as cfg

    if not OPENPYXL_AVAILABLE:
        raise RuntimeError("openpyxl not installed. Run: pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = f"Week {week_start.isoformat()}"

    day_keys = list(schedule.keys())
    num_days = len(day_keys)

    thin = Side(border_style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style_cell(cell, bg=None, fg="000000", bold=False, center=False, wrap=False):
        if bg:
            cell.fill = PatternFill(fill_type="solid", fgColor=bg)
        cell.font = Font(color=fg, bold=bold, size=9)
        cell.alignment = Alignment(
            horizontal="center" if center else "left",
            vertical="center",
            wrap_text=wrap,
        )
        cell.border = border

    # ── Header row: row label + 7 day columns ──────────────────────────────
    ws.column_dimensions["A"].width = 22
    for col_idx in range(2, num_days + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14

    # Row 1: dates
    ws.row_dimensions[1].height = 20
    label_cell = ws.cell(row=1, column=1, value=t("row_dates", lang))
    style_cell(label_cell, bg=COLOR_HEADER_BG, fg=COLOR_HEADER_FG, bold=True, center=True)
    for col_idx, dk in enumerate(day_keys, start=2):
        day = schedule[dk]
        d = day.get("date", "")
        val = d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
        c = ws.cell(row=1, column=col_idx, value=val)
        style_cell(c, bg=COLOR_HEADER_BG, fg=COLOR_HEADER_FG, bold=True, center=True)

    # Row 2: day names
    ws.row_dimensions[2].height = 18
    label_cell = ws.cell(row=2, column=1, value=t("row_days", lang))
    style_cell(label_cell, bg=COLOR_SECTION_HEADER, fg=COLOR_HEADER_FG, bold=True, center=True)
    day_name_keys = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    for col_idx, dk in enumerate(day_keys, start=2):
        d = schedule[dk].get("date")
        if hasattr(d, "weekday"):
            py_to_key = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
            day_name = cfg.work_day_label(py_to_key[d.weekday()]) \
                or t(py_to_key[d.weekday()], lang)
        else:
            day_name = ""
        c = ws.cell(row=2, column=col_idx, value=day_name)
        style_cell(c, bg=COLOR_SECTION_HEADER, fg=COLOR_HEADER_FG, bold=True, center=True)

    # Rows 3+: schedule rows (base + custom rows from config)
    row_display_keys = [k for k in cfg.all_row_keys() if k not in ("dates", "days")]
    # morning/noon value sets of every active extra-task row
    EXTRA_VALUES = {cfg.extra_row_key(e): {"m": set(e.get("morning_values", [])),
                                           "n": set(e.get("noon_values", []))}
                    for e in cfg.active_extras()}
    # each workplace-section row is tinted with its employee group's colour
    SECTION_GROUP_BG = {}
    for _w, _sec in cfg.all_sections():
        _g = cfg.group_by_id(_sec.get("group_id"))
        if _g and _g.get("color"):
            SECTION_GROUP_BG[_sec["row_key"]] = str(_g["color"]).lstrip("#").upper()

    # Special formatting by row key
    row_bg_map = {
        "vacation": COLOR_VACATION,
        "vehicle_morning": None,  # handled by value
        "vehicle_noon": None,
        "udex": None,
    }

    for excel_row, rk in enumerate(row_display_keys, start=3):
        ws.row_dimensions[excel_row].height = 16
        label = cfg.row_label(rk, lang)
        label_cell = ws.cell(row=excel_row, column=1, value=label)
        is_odd = (excel_row % 2 == 1)
        row_bg = COLOR_ROW_ODD if is_odd else COLOR_ROW_EVEN
        style_cell(label_cell, bg=row_bg, bold=True)

        for col_idx, dk in enumerate(day_keys, start=2):
            day = schedule[dk]
            # vacation combines one column per active employee group
            if rk == "vacation":
                val = " / ".join(p for p in
                                 (day.get(f, "") for f in cfg.vac_fields()) if p)
            else:
                val = day.get(rk, "")
            c = ws.cell(row=excel_row, column=col_idx, value=val)

            # Special coloring
            bg = row_bg
            if rk == "vacation" and val:
                bg = COLOR_VACATION
            elif rk in ("vehicle_morning", "vehicle_noon") and val == "YELLOW":
                bg = COLOR_YELLOW
            elif rk in EXTRA_VALUES and val in EXTRA_VALUES[rk]["m"]:
                bg = COLOR_EMB_M
            elif rk in EXTRA_VALUES and val in EXTRA_VALUES[rk]["n"]:
                bg = COLOR_EMB_T
            elif rk in SECTION_GROUP_BG:
                bg = SECTION_GROUP_BG[rk]

            style_cell(c, bg=bg, center=True)

    # ── Stats sheet ────────────────────────────────────────────────────────
    ws2 = wb.create_sheet(title=t("equality_stats", lang))
    ws2.column_dimensions["A"].width = 20
    ws2.column_dimensions["B"].width = 15
    ws2.column_dimensions["C"].width = 10

    # Count YELLOW
    _vs = cfg.special("vehicle_special")
    yellow_total = sum(
        1 for dk in day_keys
        for f in ("vehicle_morning", "vehicle_noon")
        if schedule[dk].get(f) == _vs
    )
    ws2.append(["YELLOW total", yellow_total, ""])
    for q in cfg.weekly_targets():
        def _hit(value, want=q["value"]):
            return value == want if want else bool(value)
        seen = sum(1 for dk in day_keys if _hit(schedule[dk].get(q["field"], "")))
        label = cfg.row_label(q["field"], lang) + (f' = {q["value"]}' if q["value"] else "")
        ws2.append([label, seen, "/ " + str(q["count"])])
    for et in cfg.active_extras():
        rk, tg = cfg.extra_row_key(et), cfg.extra_targets(et)
        name = cfg.extra_label(et, lang)
        m_vals, n_vals = et.get("morning_values", []), et.get("noon_values", [])
        ws2.append([name + " (AM)",
                    sum(1 for dk in day_keys if schedule[dk].get(rk) in m_vals),
                    "/ " + str(tg["morning"])])
        ws2.append([name + " (PM)",
                    sum(1 for dk in day_keys if schedule[dk].get(rk) in n_vals),
                    "/ " + str(tg["noon"])])

    # Save to bytes
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
