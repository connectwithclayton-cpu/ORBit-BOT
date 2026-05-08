"""Background worker for Telegram, Sheets, and dashboard (non-blocking).

Dashboard session writes are enqueued as critical so they are not dropped when
the queue is full (matches daily summary / trade logs).
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

import telegram_bot as tg
from dashboard_writer import DashboardWriter
from fabio_live.constants import OPS_QUEUE_MAXSIZE
from sheets_logger import SheetsLogger


class AsyncOpsWorker:
    """
    Offloads non-critical side effects (Telegram, Sheets, dashboard writes)
    from the trading path to a single background worker thread.
    """

    def __init__(
        self,
        sheets: SheetsLogger,
        dashboard: DashboardWriter,
        max_queue_size: int = OPS_QUEUE_MAXSIZE,
    ):
        self.sheets = sheets
        self.dashboard = dashboard
        self._q: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._stop = threading.Event()
        self._errors = 0
        self._last_error = ""
        self._max_queue_size = max_queue_size
        self._dropped_noncritical = 0
        self._dropped_critical = 0
        self._coalesced_updates = 0
        self._inline_critical_fallbacks = 0
        self._lock = threading.Lock()
        self._coalesced_pending: dict[str, tuple[str, Any, tuple, dict]] = {}
        self._last_dashboard_intraday_refresh_ts = 0.0
        self._last_dashboard_broker_open_refresh_ts = 0.0
        self._dashboard_intraday_refresh_requests = 0
        self._dashboard_intraday_refresh_enqueued = 0
        self._dashboard_intraday_refresh_throttled = 0
        self._dashboard_open_refresh_requests = 0
        self._dashboard_open_refresh_enqueued = 0
        self._dashboard_open_refresh_throttled = 0
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="fabio-async-ops"
        )
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                self._q.task_done()
                continue
            kind, payload = item
            if kind == "coalesced":
                key = str(payload)
                with self._lock:
                    packed = self._coalesced_pending.pop(key, None)
                if packed is None:
                    self._q.task_done()
                    continue
                label, fn, args, kwargs = packed
            else:
                label, fn, args, kwargs = payload
            try:
                fn(*args, **kwargs)
            except Exception as e:
                self._errors += 1
                self._last_error = f"{label}: {e}"
                print(f"[AsyncOps] {label} failed: {e}")
            finally:
                self._q.task_done()

    def enqueue(
        self,
        label: str,
        fn,
        *args,
        critical: bool = False,
        coalesce_key: str | None = None,
        **kwargs,
    ):
        if coalesce_key:
            with self._lock:
                if coalesce_key in self._coalesced_pending:
                    self._coalesced_pending[coalesce_key] = (label, fn, args, kwargs)
                    self._coalesced_updates += 1
                    return
                self._coalesced_pending[coalesce_key] = (label, fn, args, kwargs)
            item = ("coalesced", coalesce_key)
        else:
            item = ("direct", (label, fn, args, kwargs))

        try:
            self._q.put_nowait(item)
            return
        except queue.Full:
            pass

        if coalesce_key:
            with self._lock:
                if coalesce_key in self._coalesced_pending:
                    self._coalesced_pending.pop(coalesce_key, None)
            self._dropped_noncritical += 1
            return

        if not critical:
            self._dropped_noncritical += 1
            return

        self._dropped_critical += 1
        try:
            fn(*args, **kwargs)
            self._inline_critical_fallbacks += 1
        except Exception as e:
            self._errors += 1
            self._last_error = f"{label}: {e}"
            print(f"[AsyncOps] {label} failed via inline fallback: {e}")

    def alert(self, text: str):
        self.enqueue("telegram.alert", tg.alert, text, critical=True)

    def log_decision(self, *args, **kwargs):
        decision = str(args[2]) if len(args) >= 3 else str(kwargs.get("decision", ""))
        symbol = str(args[0]) if args else str(kwargs.get("symbol", ""))
        reason = str(args[3]) if len(args) >= 4 else str(kwargs.get("reason", ""))
        if decision.upper() == "HEARTBEAT":
            self.enqueue(
                "sheets.log_decision",
                self.sheets.log_decision,
                *args,
                coalesce_key=f"heartbeat:{symbol}:{reason[:80]}",
                **kwargs,
            )
            return
        self.enqueue("sheets.log_decision", self.sheets.log_decision, *args, **kwargs)

    def log_alert(self, *args, **kwargs):
        self.enqueue(
            "sheets.log_alert", self.sheets.log_alert, *args, critical=True, **kwargs
        )

    def log_trade_entry(self, *args, **kwargs):
        self.enqueue(
            "sheets.log_trade_entry",
            self.sheets.log_trade_entry,
            *args,
            critical=True,
            **kwargs,
        )

    def log_trade_exit(self, *args, **kwargs):
        self.enqueue(
            "sheets.log_trade_exit",
            self.sheets.log_trade_exit,
            *args,
            critical=True,
            **kwargs,
        )

    def log_daily_summary(self, *args, **kwargs):
        self.enqueue(
            "sheets.log_daily_summary",
            self.sheets.log_daily_summary,
            *args,
            critical=True,
            **kwargs,
        )

    def append_dashboard_session(self, *args, **kwargs):
        self.enqueue(
            "dashboard.append_session",
            self.dashboard.append_session,
            *args,
            critical=True,
            **kwargs,
        )

    def refresh_dashboard_intraday(
        self,
        trades: list[dict],
        *,
        open_positions: list[dict] | None = None,
        throttle_sec: float = 2.0,
    ):
        """
        Coalesced, non-blocking intraday dashboard refresh.
        This should never block trading path.
        """
        self._dashboard_intraday_refresh_requests += 1
        now = time.time()
        if throttle_sec > 0 and (now - self._last_dashboard_intraday_refresh_ts) < throttle_sec:
            self._dashboard_intraday_refresh_throttled += 1
            self._coalesced_updates += 1
            return
        self._last_dashboard_intraday_refresh_ts = now
        self._dashboard_intraday_refresh_enqueued += 1
        self.enqueue(
            "dashboard.refresh_intraday",
            self.dashboard.refresh_intraday,
            list(trades or []),
            open_positions=list(open_positions) if open_positions is not None else None,
            coalesce_key="dashboard.intraday.refresh",
        )

    def refresh_dashboard_broker_open_positions(
        self,
        fetcher,
        *,
        throttle_sec: float = 60.0,
    ):
        """
        Optional display-only broker open-position refresh path.
        Runs in worker thread and is coalesced.
        """
        self._dashboard_open_refresh_requests += 1
        now = time.time()
        if throttle_sec > 0 and (now - self._last_dashboard_broker_open_refresh_ts) < throttle_sec:
            self._dashboard_open_refresh_throttled += 1
            self._coalesced_updates += 1
            return
        self._last_dashboard_broker_open_refresh_ts = now
        self._dashboard_open_refresh_enqueued += 1

        def _refresh():
            opens = fetcher()
            self.dashboard.refresh_intraday_open_positions(list(opens or []))

        self.enqueue(
            "dashboard.refresh_broker_opens",
            _refresh,
            coalesce_key="dashboard.broker_open.refresh",
        )

    def stop(self, timeout: float = 5.0):
        start = time.time()
        while not self._q.empty() and (time.time() - start) < timeout:
            time.sleep(0.05)
        self._stop.set()
        self._q.put(None)
        self._thread.join(timeout=timeout)

    def health(self) -> dict:
        return {
            "queue_depth": self._q.qsize(),
            "queue_max": self._max_queue_size,
            "errors": self._errors,
            "last_error": self._last_error,
            "dropped_noncritical": self._dropped_noncritical,
            "dropped_critical": self._dropped_critical,
            "coalesced_updates": self._coalesced_updates,
            "inline_critical_fallbacks": self._inline_critical_fallbacks,
            "dashboard_intraday_refresh_requests": self._dashboard_intraday_refresh_requests,
            "dashboard_intraday_refresh_enqueued": self._dashboard_intraday_refresh_enqueued,
            "dashboard_intraday_refresh_throttled": self._dashboard_intraday_refresh_throttled,
            "dashboard_open_refresh_requests": self._dashboard_open_refresh_requests,
            "dashboard_open_refresh_enqueued": self._dashboard_open_refresh_enqueued,
            "dashboard_open_refresh_throttled": self._dashboard_open_refresh_throttled,
            "thread_alive": self._thread.is_alive(),
        }
