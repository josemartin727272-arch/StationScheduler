"""
Google Sheets integration using gspread + service account or OAuth.
Falls back gracefully if credentials are not configured.
"""
import json
import os
from datetime import date
from typing import Optional

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HISTORY_TAB = "history"
SCHEDULE_TAB_PREFIX = "week_"


def _get_client(creds_json: str):
    """Return authenticated gspread client from JSON credentials string."""
    if not GSPREAD_AVAILABLE:
        raise RuntimeError("gspread not installed. Run: pip install gspread google-auth")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def load_history(sheet_url: str, creds_json: str) -> dict:
    """Load equality history dict from the 'history' tab."""
    try:
        gc = _get_client(creds_json)
        sh = gc.open_by_url(sheet_url)
        try:
            ws = sh.worksheet(HISTORY_TAB)
        except gspread.WorksheetNotFound:
            return {}
        data = ws.get_all_values()
        if not data or len(data) < 2:
            return {}
        history = {}
        for row in data[1:]:  # skip header
            if len(row) >= 3:
                field, value, count = row[0], row[1], row[2]
                history.setdefault(field, {})
                try:
                    history[field][value] = int(count)
                except ValueError:
                    pass
        return history
    except Exception as e:
        return {"_error": str(e)}


def save_history(sheet_url: str, creds_json: str, history: dict) -> bool:
    """Persist equality history dict to the 'history' tab."""
    try:
        gc = _get_client(creds_json)
        sh = gc.open_by_url(sheet_url)
        try:
            ws = sh.worksheet(HISTORY_TAB)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=HISTORY_TAB, rows=500, cols=5)

        rows = [["field", "value", "count"]]
        for field, counts in history.items():
            if field.startswith("_"):
                continue
            for value, count in counts.items():
                rows.append([field, value, str(count)])
        ws.update(rows)
        return True
    except Exception as e:
        return False


def save_week(sheet_url: str, creds_json: str, week_start: date, schedule: dict) -> bool:
    """Save a week's schedule to a tab named week_YYYY-MM-DD."""
    try:
        gc = _get_client(creds_json)
        sh = gc.open_by_url(sheet_url)
        tab_name = f"{SCHEDULE_TAB_PREFIX}{week_start.isoformat()}"
        try:
            ws = sh.worksheet(tab_name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab_name, rows=30, cols=10)

        from schedule_logic import ROW_KEYS
        # Header
        header = ["row"] + list(schedule.keys())
        rows = [header]
        for rk in ROW_KEYS:
            row = [rk] + [str(day.get(rk, "")) for day in schedule.values()]
            rows.append(row)
        ws.update(rows)
        return True
    except Exception as e:
        return False


def load_week(sheet_url: str, creds_json: str, week_start: date) -> Optional[dict]:
    """Load a week's schedule from Google Sheets. Returns None if not found."""
    try:
        gc = _get_client(creds_json)
        sh = gc.open_by_url(sheet_url)
        tab_name = f"{SCHEDULE_TAB_PREFIX}{week_start.isoformat()}"
        try:
            ws = sh.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            return None
        data = ws.get_all_values()
        if not data or len(data) < 2:
            return None

        from schedule_logic import empty_week
        from datetime import date as _date
        schedule = empty_week(week_start)
        day_keys = list(schedule.keys())
        headers = data[0][1:]  # skip "row" col

        for row in data[1:]:
            if not row:
                continue
            rk = row[0]
            for i, dk in enumerate(day_keys):
                if i + 1 < len(row):
                    schedule[dk][rk] = row[i + 1]
        return schedule
    except Exception as e:
        return None


def list_saved_weeks(sheet_url: str, creds_json: str) -> list:
    """Return list of saved week tab names."""
    try:
        gc = _get_client(creds_json)
        sh = gc.open_by_url(sheet_url)
        return [
            ws.title.replace(SCHEDULE_TAB_PREFIX, "")
            for ws in sh.worksheets()
            if ws.title.startswith(SCHEDULE_TAB_PREFIX)
        ]
    except Exception:
        return []
