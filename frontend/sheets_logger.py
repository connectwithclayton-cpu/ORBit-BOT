"""
sheets_logger.py — Google Sheets live logging for the ORBit bot.

Logs to 6 tabs:
  • Trades          — every entry & exit with full context (trend, VIX regime, day color)
  • Decisions       — every signal evaluated (enters AND skips)
  • Daily Summary   — EOD totals with proven edge written once per day
  • Alerts          — errors, circuit breakers, connection issues
  • Monthly Analysis — auto-aggregates Daily Summary by month (QUERY formula, no manual work)
  • Dashboard       — live KPI cards: win rate, proven edge, symbol/direction breakdown

Setup:
  1. Follow GOOGLE_SETUP.md to create service account credentials
  2. Add GOOGLE_SHEET_ID and GOOGLE_CREDS_PATH to your .env file
  3. Share the Google Sheet with your service account email
"""

import os
import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Optional import — bot still works if gspread isn't installed ──────────────
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    print("[SheetsLogger] gspread not installed — run: pip install gspread google-auth")

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID   = os.getenv("GOOGLE_SHEET_ID", "")
CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "")
SCOPES     = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tab names
TAB_TRADES    = "Trades"
TAB_DECISIONS = "Decisions"
TAB_SUMMARY   = "Daily Summary"
TAB_ALERTS    = "Alerts"
TAB_MONTHLY   = "Monthly Analysis"
TAB_DASHBOARD = "Dashboard"
# Canonical Moomoo paper reconcile tabs (broker-authoritative snapshots)
TAB_BROKER_FILLS = "Broker Fills"
TAB_RECON_TRADES = "Reconciled Trades"
TAB_OPEN_INVENTORY = "Open Inventory"

# Headers for each data tab
HEADERS = {
    TAB_TRADES: [
        "Date", "Symbol", "Direction", "Entry Time", "Entry Price ($)",
        "Strike", "Expiry", "Contracts", "Exit Time", "Exit Price ($)",
        "P&L ($)", "Return (%)", "Exit Reason", "VIX", "OR/ATR (%)",
        "Capital After ($)", "Trend", "VIX Regime", "Day Color", "Notes"
    ],
    TAB_DECISIONS: [
        "Timestamp", "Symbol", "Direction", "Decision", "Reason",
        "VIX", "OR/ATR (%)", "Gap (%)", "Regime"
    ],
    TAB_SUMMARY: [
        "Date", "Total Trades", "Winners", "Losers", "Win Rate (%)",
        "Net P&L ($)", "Gross Winners ($)", "Gross Losers ($)",
        "Capital ($)", "Daily Return (%)", "Notes"
    ],
    TAB_ALERTS: [
        "Timestamp", "Type", "Message", "Symbol"
    ],
    TAB_BROKER_FILLS: [
        "Fill ID",
        "Time",
        "Date",
        "Code",
        "Symbol",
        "Direction",
        "Side",
        "Qty",
        "Price ($)",
        "Leg Notional ($)",
        "Realized P&L ($)",
        "Source",
    ],
    TAB_RECON_TRADES: [
        "Close Time",
        "Date",
        "Code",
        "Symbol",
        "Direction",
        "Qty",
        "Entry Time",
        "Entry Price ($)",
        "Exit Time",
        "Exit Price ($)",
        "P&L ($)",
        "Return (%)",
        "Source",
    ],
    TAB_OPEN_INVENTORY: [
        "Updated",
        "Lot Date",
        "Code",
        "Symbol",
        "Direction",
        "Qty",
        "Entry Time",
        "Entry Price ($)",
        "Notional ($)",
        "Source",
    ],
}

# ── Dark header style ─────────────────────────────────────────────────────────
DARK_HEADER = {
    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    "backgroundColor": {"red": 0.10, "green": 0.10, "blue": 0.10},
    "horizontalAlignment": "CENTER",
}
SECTION_STYLE = {
    "textFormat": {"bold": True},
    "backgroundColor": {"red": 0.17, "green": 0.17, "blue": 0.17},
}


def _coerce_sheet_cell(v):
    """Cell values acceptable to the Sheets API."""
    if v is None:
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return str(v)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    return str(v)


def _normalize_sheet_row(width: int, row: list) -> list:
    r = list(row) + [""] * width
    return [_coerce_sheet_cell(x) for x in r[:width]]


class SheetsLogger:
    """Logs ORBit bot activity to Google Sheets in real time."""

    def __init__(self):
        self._gc      = None
        self._sheet   = None
        self._tabs    = {}
        self._enabled = False
        self._connect()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self):
        """Authenticate and open the spreadsheet."""
        if not GSPREAD_AVAILABLE:
            return
        if not SHEET_ID or not CREDS_PATH:
            print("[SheetsLogger] GOOGLE_SHEET_ID or GOOGLE_CREDS_PATH not set — logging disabled")
            return
        if not os.path.exists(CREDS_PATH):
            print(f"[SheetsLogger] Credentials file not found: {CREDS_PATH}")
            return
        try:
            creds       = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
            self._gc    = gspread.authorize(creds)
            self._sheet = self._gc.open_by_key(SHEET_ID)
            self._ensure_tabs()
            self._enabled = True
            print(f"[SheetsLogger] ✅ Connected to Google Sheet: {self._sheet.title}")
        except Exception as e:
            print(f"[SheetsLogger] ❌ Connection failed: {e}")

    def _col_letter(self, n: int) -> str:
        """1-based column index to A..Z, AA.. (Sheets letters)."""
        if n <= 0:
            return "A"
        letters = ""
        idx = n
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            letters = chr(65 + rem) + letters
        return letters


    def _ensure_tabs(self):
        """Create any missing tabs, update headers if columns were added."""
        existing = {ws.title: ws for ws in self._sheet.worksheets()}

        for tab_name, headers in HEADERS.items():
            n = len(headers)
            if tab_name not in existing:
                ws = self._sheet.add_worksheet(title=tab_name, rows=2000, cols=n)
                ws.update(f"A1:{self._col_letter(n)}1", [headers],
                          value_input_option="USER_ENTERED")
                self._format_header(ws, n)
                self._apply_pnl_formatting(ws, tab_name)
                print(f"[SheetsLogger] Created tab: {tab_name}")
            else:
                ws = existing[tab_name]
                try:
                    current = ws.row_values(1)
                    if len(current) < n:
                        # New columns were added — update header row only
                        ws.update(f"A1:{self._col_letter(n)}1", [headers],
                                  value_input_option="USER_ENTERED")
                        self._format_header(ws, n)
                        print(f"[SheetsLogger] Updated headers: {tab_name} "
                              f"({len(current)} → {n} columns)")
                    elif not current or current[0] != headers[0]:
                        ws.insert_row(headers, 1, value_input_option="USER_ENTERED")
                        self._format_header(ws, n)
                except Exception:
                    pass
            self._tabs[tab_name] = ws

        # Formula-driven tabs — only create once
        if TAB_MONTHLY not in existing:
            self._create_monthly_tab()
        else:
            self._tabs[TAB_MONTHLY] = existing[TAB_MONTHLY]

        if TAB_DASHBOARD not in existing:
            self._create_dashboard_tab()
        else:
            self._tabs[TAB_DASHBOARD] = existing[TAB_DASHBOARD]

    def _format_header(self, ws, num_cols: int):
        """Bold dark header + freeze row 1."""
        try:
            end = self._col_letter(num_cols)
            ws.format(f"A1:{end}1", DARK_HEADER)
            ws.freeze(rows=1)
        except Exception:
            pass

    def _apply_pnl_formatting(self, ws, tab_name: str):
        """Green for positive P&L, red for negative — on the P&L column."""
        try:
            sheet_id = ws.id
            if tab_name == TAB_TRADES:
                col_idx = 10   # Column K (0-indexed)
            elif tab_name == TAB_SUMMARY:
                col_idx = 5    # Column F (0-indexed)
            elif tab_name in (TAB_BROKER_FILLS, TAB_RECON_TRADES):
                col_idx = 10
            else:
                return

            data_range = {
                "sheetId": sheet_id,
                "startRowIndex": 1, "endRowIndex": 2000,
                "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
            }
            requests = [
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [data_range],
                            "booleanRule": {
                                "condition": {
                                    "type": "NUMBER_GREATER",
                                    "values": [{"userEnteredValue": "0"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.20, "green": 0.53, "blue": 0.22},
                                    "textFormat": {
                                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                        "bold": True
                                    }
                                }
                            }
                        },
                        "index": 0
                    }
                },
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [data_range],
                            "booleanRule": {
                                "condition": {
                                    "type": "NUMBER_LESS",
                                    "values": [{"userEnteredValue": "0"}]
                                },
                                "format": {
                                    "backgroundColor": {"red": 0.80, "green": 0.19, "blue": 0.19},
                                    "textFormat": {
                                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                        "bold": True
                                    }
                                }
                            }
                        },
                        "index": 1
                    }
                },
            ]
            self._sheet.batch_update({"requests": requests})
        except Exception as e:
            print(f"[SheetsLogger] Conditional format skipped for {tab_name}: {e}")

    # ── Formula-driven tabs ───────────────────────────────────────────────────

    def _create_monthly_tab(self):
        """
        Monthly Analysis — single QUERY formula auto-aggregates Daily Summary.
        The formula groups rows by yyyy-MM and sums every key metric.
        """
        try:
            ws = self._sheet.add_worksheet(title=TAB_MONTHLY, rows=120, cols=10)
            self._tabs[TAB_MONTHLY] = ws

            # QUERY against 'Daily Summary'!A:J  (header row = 1)
            # Columns: A=Date, B=Trades, C=Win, D=Loss, E=WinRate%, F=NetPnL,
            #          G=GrossWin, H=GrossLoss, I=Capital, J=DailyReturn%
            formula = (
                "=IFERROR("
                "QUERY('Daily Summary'!A:J,"
                "\"SELECT TEXT(A,'yyyy-MM'), COUNT(A), SUM(B), SUM(C), SUM(D), "
                "SUM(F), SUM(G), SUM(H), AVG(J) "
                "WHERE A IS NOT NULL "
                "GROUP BY TEXT(A,'yyyy-MM') "
                "ORDER BY TEXT(A,'yyyy-MM') "
                "LABEL TEXT(A,'yyyy-MM') 'Month', "
                "COUNT(A) 'Trading Days', "
                "SUM(B) 'Total Trades', "
                "SUM(C) 'Winners', "
                "SUM(D) 'Losers', "
                "SUM(F) 'Net P&L ($)', "
                "SUM(G) 'Gross Win ($)', "
                "SUM(H) 'Gross Loss ($)', "
                "AVG(J) 'Avg Daily Ret (%)'\")"
                ",\"No daily summary data yet — come back after your first session!\")"
            )

            ws.update("A1", [[formula]], value_input_option="USER_ENTERED")
            # Header will be written by QUERY itself — format row 1 after data arrives
            ws.format("A1:I1", DARK_HEADER)
            ws.freeze(rows=1)
            print(f"[SheetsLogger] Created tab: {TAB_MONTHLY}")
        except Exception as e:
            print(f"[SheetsLogger] Could not create Monthly Analysis tab: {e}")

    def _create_dashboard_tab(self):
        """
        Dashboard — live KPI formulas, never needs manual maintenance.
        All metrics auto-update as Trades and Daily Summary rows are appended.
        """
        try:
            ws = self._sheet.add_worksheet(title=TAB_DASHBOARD, rows=60, cols=3)
            self._tabs[TAB_DASHBOARD] = ws

            rows = [
                # [Metric, Value formula, Notes]
                ["Metric", "Value", "Notes"],  # row 1 — header
                [""],
                ["── OVERALL STATS ──", "", ""],
                ["Total Trades",
                 '=IFERROR(COUNTA(Trades!A2:A),0)',
                 "All completed trades logged"],
                ["Win Rate",
                 '=IFERROR(TEXT(COUNTIF(Trades!K2:K,">0")/COUNTA(Trades!A2:A),"0.0%"),"—")',
                 "% of trades closing positive"],
                ["Avg Win ($)",
                 '=IFERROR(ROUND(AVERAGEIF(Trades!K2:K,">0",Trades!K2:K),2),"—")',
                 "Mean P&L on winning trades"],
                ["Avg Loss ($)",
                 '=IFERROR(ROUND(AVERAGEIF(Trades!K2:K,"<0",Trades!K2:K),2),"—")',
                 "Mean P&L on losing trades"],
                ["Proven Edge ($)",
                 ('=IFERROR(ROUND('
                  '(AVERAGEIF(Trades!K2:K,">0",Trades!K2:K)'
                  ' * COUNTIF(Trades!K2:K,">0") / COUNTA(Trades!A2:A))'
                  '+(AVERAGEIF(Trades!K2:K,"<0",Trades!K2:K)'
                  ' * COUNTIF(Trades!K2:K,"<0") / COUNTA(Trades!A2:A))'
                  ',2),"—")'),
                 "(Avg Win × Win%) + (Avg Loss × Loss%)"],
                ["Net P&L All Time ($)",
                 '=IFERROR(ROUND(SUM(Trades!K2:K),2),0)',
                 "Sum of all realized P&L"],
                [""],
                ["── SYMBOL BREAKDOWN ──", "", ""],
                ["SPY — Trades",
                 '=IFERROR(COUNTIF(Trades!B2:B,"SPY"),0)', ""],
                ["SPY — P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!B2:B,"SPY",Trades!K2:K),2),0)', ""],
                ["QQQ — Trades",
                 '=IFERROR(COUNTIF(Trades!B2:B,"QQQ"),0)', ""],
                ["QQQ — P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!B2:B,"QQQ",Trades!K2:K),2),0)', ""],
                ["NVDA — Trades",
                 '=IFERROR(COUNTIF(Trades!B2:B,"NVDA"),0)', ""],
                ["NVDA — P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!B2:B,"NVDA",Trades!K2:K),2),0)', ""],
                [""],
                ["── DIRECTION BREAKDOWN ──", "", ""],
                ["CALL Trades",
                 '=IFERROR(COUNTIF(Trades!C2:C,"CALL"),0)', ""],
                ["CALL P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!C2:C,"CALL",Trades!K2:K),2),0)', ""],
                ["PUT Trades",
                 '=IFERROR(COUNTIF(Trades!C2:C,"PUT"),0)', ""],
                ["PUT P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!C2:C,"PUT",Trades!K2:K),2),0)', ""],
                ["With-Trend Trades",
                 '=IFERROR(COUNTIF(Trades!Q2:Q,"WITH"),0)',
                 "Breakout in EMA trend direction"],
                ["Counter-Trend Trades",
                 '=IFERROR(COUNTIF(Trades!Q2:Q,"COUNTER"),0)',
                 "Breakout against trend (smaller size)"],
                ["With-Trend P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!Q2:Q,"WITH",Trades!K2:K),2),0)', ""],
                ["Counter-Trend P&L ($)",
                 '=IFERROR(ROUND(SUMIF(Trades!Q2:Q,"COUNTER",Trades!K2:K),2),0)', ""],
                [""],
                ["── EXIT REASON BREAKDOWN ──", "", ""],
                ["OR Re-entry Exits",
                 '=IFERROR(COUNTIF(Trades!M2:M,"OR re-entry"),0)',
                 "Thesis invalidated — price back inside OR"],
                ["EMA Cross Exits",
                 '=IFERROR(COUNTIF(Trades!M2:M,"EMA cross"),0)',
                 "10 EMA crossed on exit timeframe"],
                ["EOD Exits",
                 '=IFERROR(COUNTIF(Trades!M2:M,"EOD"),0)',
                 "Force-closed at 3:45 PM"],
                [""],
                ["── RECENT PERFORMANCE ──", "", ""],
                ["Last 7-Day P&L ($)",
                 "=IFERROR(ROUND(SUMPRODUCT(('Daily Summary'!A2:A>=TODAY()-7)*('Daily Summary'!F2:F)),2),0)",
                 "Rolling 7 calendar days"],
                ["Last 30-Day P&L ($)",
                 "=IFERROR(ROUND(SUMPRODUCT(('Daily Summary'!A2:A>=TODAY()-30)*('Daily Summary'!F2:F)),2),0)",
                 "Rolling 30 calendar days"],
                ["Days Traded (Total)",
                 "=IFERROR(COUNTA('Daily Summary'!A2:A),0)", ""],
                ["Days With ≥1 Trade",
                 "=IFERROR(COUNTIF('Daily Summary'!B2:B,\">0\"),0)", ""],
                ["Best Single Day ($)",
                 "=IFERROR(MAX('Daily Summary'!F2:F),0)", ""],
                ["Worst Single Day ($)",
                 "=IFERROR(MIN('Daily Summary'!F2:F),0)", ""],
                [""],
                ["── LAST UPDATED ──", "", ""],
                ["Timestamp",
                 '=TEXT(NOW(),"yyyy-mm-dd hh:mm:ss")',
                 "Refreshes each time sheet is opened"],
            ]

            ws.update("A1", rows, value_input_option="USER_ENTERED")
            ws.format("A1:C1", DARK_HEADER)
            ws.freeze(rows=1)

            # Bold + shade section-header rows
            section_rows = [i + 1 for i, r in enumerate(rows)
                            if r and isinstance(r[0], str) and r[0].startswith("──")]
            batch_fmt = []
            for row_num in section_rows:
                batch_fmt.append({
                    "updateCells": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": row_num - 1,
                            "endRowIndex": row_num,
                            "startColumnIndex": 0,
                            "endColumnIndex": 3,
                        },
                        "rows": [{"values": [
                            {
                                "userEnteredFormat": {
                                    "textFormat": {"bold": True},
                                    "backgroundColor": {"red": 0.17, "green": 0.17, "blue": 0.17},
                                }
                            }
                        ]}],
                        "fields": "userEnteredFormat(textFormat,backgroundColor)",
                    }
                })

            # Set column widths: A=210, B=150, C=280
            batch_fmt += [
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                                  "startIndex": 0, "endIndex": 1},
                        "properties": {"pixelSize": 210},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                                  "startIndex": 1, "endIndex": 2},
                        "properties": {"pixelSize": 150},
                        "fields": "pixelSize",
                    }
                },
                {
                    "updateDimensionProperties": {
                        "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                                  "startIndex": 2, "endIndex": 3},
                        "properties": {"pixelSize": 290},
                        "fields": "pixelSize",
                    }
                },
            ]

            if batch_fmt:
                self._sheet.batch_update({"requests": batch_fmt})

            print(f"[SheetsLogger] Created tab: {TAB_DASHBOARD}")
        except Exception as e:
            print(f"[SheetsLogger] Could not create Dashboard tab: {e}")

    def replace_tab_rows(self, tab_name: str, headers: list, rows: list) -> bool:
        """Overwrite a tab with header + rows; return True when Sheets accepted the write."""
        if not self._enabled:
            print(f"[SheetsLogger] replace_tab_rows skipped ({tab_name}): logger disabled")
            return False
        ws = self._tabs.get(tab_name)
        if ws is None:
            try:
                self._ensure_tabs()
            except Exception:
                pass
            ws = self._tabs.get(tab_name)
        if ws is None:
            print(f"[SheetsLogger] replace_tab_rows: unknown tab {tab_name!r}")
            return False
        n = len(headers)
        if not n:
            print(f"[SheetsLogger] replace_tab_rows: empty headers for {tab_name!r}")
            return False
        try:
            body = [_normalize_sheet_row(n, headers)]
            for row in rows or []:
                body.append(_normalize_sheet_row(n, row))
            end_row = len(body)
            try:
                ws.resize(rows=max(end_row + 50, 100), cols=max(n, 2))
            except Exception:
                pass
            ws.clear()
            rng = f"A1:{self._col_letter(n)}{end_row}"
            ws.update(rng, body, value_input_option="USER_ENTERED")
            self._format_header(ws, n)
            self._apply_pnl_formatting(ws, tab_name)
            print(
                f"[SheetsLogger] ✅ replace_tab_rows {tab_name!r} wrote "
                f"{end_row - 1} data row(s) (+ header)"
            )
            return True
        except Exception as e:
            import traceback

            print(f"[SheetsLogger] replace_tab_rows failed ({tab_name}): {e}")
            traceback.print_exc()
            return False

    def _append(self, tab_name: str, row: list):
        """Safely append a row; silently skips if logging is disabled."""
        if not self._enabled:
            return
        try:
            self._tabs[tab_name].append_row(row, value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"[SheetsLogger] Write error ({tab_name}): {e}")

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _today() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def _compute_circuit_snapshot_from_recon_rows(rows, iso_date: str):
        """
        closed rows: Reconciled Trades shape (Date col 1, P&L col 10).
        Returns dict with trade_count, realized_pnl, loss_streak (trailing losses)
        or None if no rows for iso_date.
        """
        if not rows:
            return None
        dated = []
        for r in rows:
            if len(r) < 11:
                continue
            if str(r[1]).strip() != iso_date:
                continue
            dated.append(r)
        if not dated:
            return None
        dated.sort(key=lambda rr: str(rr[0]))
        pnls = []
        for r in dated:
            cell = str(r[10]).strip() if len(r) > 10 else ""
            if cell in ("", "—", "-"):
                pnls.append(0.0)
            else:
                try:
                    pnls.append(float(cell))
                except (TypeError, ValueError):
                    pnls.append(0.0)
        trade_count = len(pnls)
        realized_pnl = sum(pnls)
        loss_streak = 0
        for p in reversed(pnls):
            if p < 0:
                loss_streak += 1
            else:
                break
        return {
            "trade_count": trade_count,
            "realized_pnl": realized_pnl,
            "loss_streak": loss_streak,
        }

    def get_today_circuit_snapshot(self):
        """Load today's closed trades from Reconciled Trades for circuit hydration."""
        if not self.is_connected():
            return None
        ws = self._tabs.get(TAB_RECON_TRADES)
        if ws is None:
            return None
        try:
            vals = ws.get_all_values()
        except Exception as e:
            print(f"[SheetsLogger] get_today_circuit_snapshot: {e}")
            return None
        body = vals[1:] if len(vals) > 1 else []
        return SheetsLogger._compute_circuit_snapshot_from_recon_rows(
            body, SheetsLogger._today()
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def log_trade_entry(self, symbol: str, direction: str, entry_time,
                        entry_price: float, strike, expiry, contracts: int,
                        vix: float, or_atr_pct: float, capital: float,
                        trend: str = "", vix_regime: str = "",
                        day_color: str = "", notes: str = ""):
        """
        Call immediately when a trade is entered.
        New optional fields: trend ('WITH'|'COUNTER'), vix_regime, day_color, notes.
        """
        row = [
            self._today(), symbol, direction,
            str(entry_time)[:8], round(entry_price, 4),
            strike, str(expiry), contracts,
            "", "", "", "",            # exit fields — filled on close
            "OPEN", round(vix, 2), round(or_atr_pct, 1), "",
            trend, vix_regime, day_color, notes,
        ]
        self._append(TAB_TRADES, row)
        print(f"[SheetsLogger] Trade entry logged: {symbol} {direction}"
              + (f" ({trend})" if trend else ""))

    def log_trade_exit(self, symbol: str, direction: str, entry_time,
                       entry_price: float, exit_time, exit_price: float,
                       pnl: float, exit_reason: str, vix: float,
                       or_atr_pct: float, strike, expiry, contracts: int,
                       capital_after: float, trend: str = "",
                       vix_regime: str = "", day_color: str = "", notes: str = ""):
        """
        Call when a trade is closed. Writes a complete row (not appended to entry row —
        each exit is a standalone record for easy filtering/sorting).
        """
        entry_cost = entry_price * contracts * 100
        return_pct = round((pnl / entry_cost) * 100, 2) if entry_cost else 0
        row = [
            self._today(), symbol, direction,
            str(entry_time)[:8], round(entry_price, 4),
            strike, str(expiry), contracts,
            str(exit_time)[:8], round(exit_price, 4),
            round(pnl, 2), return_pct,
            exit_reason, round(vix, 2), round(or_atr_pct, 1),
            round(capital_after, 2),
            trend, vix_regime, day_color, notes,
        ]
        self._append(TAB_TRADES, row)
        print(f"[SheetsLogger] Trade exit logged: {symbol} {direction} | "
              f"P&L ${pnl:+.2f} | {exit_reason}")

    def log_decision(self, symbol: str, direction, decision: str, reason: str,
                     vix=None, or_atr_pct=None, gap_pct=None, regime=None):
        """
        Log every signal evaluation — entries AND skips.
        decision: 'ENTER' | 'SKIP' | 'EXIT' | 'HOLD'
        """
        row = [
            self._now(), symbol, direction or "—", decision, reason,
            round(vix, 2) if vix is not None else "",
            round(or_atr_pct, 1) if or_atr_pct is not None else "",
            round(gap_pct, 2) if gap_pct is not None else "",
            regime or "",
        ]
        self._append(TAB_DECISIONS, row)

    def log_daily_summary(self, trades_today: list, capital: float,
                          capital_start: float):
        """
        Call at EOD with the day's completed trades list.
        Calculates proven edge and embeds it in the Notes column.
        """
        if not trades_today:
            self._append(TAB_SUMMARY, [
                self._today(), 0, 0, 0, 0, 0, 0, 0,
                round(capital, 2), 0, "No trades today",
            ])
            return

        winners      = [t for t in trades_today if t.get("pnl", 0) >= 0]
        losers       = [t for t in trades_today if t.get("pnl", 0) < 0]
        net_pnl      = sum(t.get("pnl", 0) for t in trades_today)
        gross_win    = sum(t.get("pnl", 0) for t in winners)
        gross_loss   = sum(t.get("pnl", 0) for t in losers)
        win_rate     = round(len(winners) / len(trades_today) * 100, 1)
        daily_return = round((net_pnl / capital_start) * 100, 2) if capital_start else 0

        # Proven Edge = (Avg Win × Win%) + (Avg Loss × Loss%)
        avg_win      = (gross_win  / len(winners)) if winners else 0
        avg_loss     = (gross_loss / len(losers))  if losers  else 0
        wr           = len(winners) / len(trades_today)
        proven_edge  = round((avg_win * wr) + (avg_loss * (1 - wr)), 2)

        notes = f"Proven edge: ${proven_edge:+.2f}"

        row = [
            self._today(), len(trades_today), len(winners), len(losers),
            win_rate, round(net_pnl, 2), round(gross_win, 2), round(gross_loss, 2),
            round(capital, 2), daily_return, notes,
        ]
        self._append(TAB_SUMMARY, row)
        print(f"[SheetsLogger] Daily summary logged: {len(trades_today)} trades | "
              f"Net ${net_pnl:+.2f} | Win rate {win_rate}% | Edge ${proven_edge:+.2f}")

    def log_alert(self, alert_type: str, message: str, symbol: str = ""):
        """
        Log errors, circuit breakers, connection issues.
        alert_type: 'ERROR' | 'CIRCUIT_BREAKER' | 'CONNECTION' | 'ORDER_FAIL' | 'INFO'
        """
        row = [self._now(), alert_type, message, symbol]
        self._append(TAB_ALERTS, row)
        print(f"[SheetsLogger] Alert logged: [{alert_type}] {message}")

    def is_connected(self) -> bool:
        return self._enabled
