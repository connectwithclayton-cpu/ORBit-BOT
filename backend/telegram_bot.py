"""
telegram_bot.py — Send alerts and receive /stop /pause /resume /status commands.
Uses plain requests (no extra library needed).
"""
import threading
import time
import requests
from config import TG_GROUP_ID, TG_PERSONAL_ID, TG_STOP_CONFIRM_CODE, TG_TOKEN
from fabio_live.constants import TELEGRAM_CMD_MIN_INTERVAL_SEC, TELEGRAM_STOP_CONFIRM_TTL_SEC

_last_update_id = 0
_risk_ref        = None    # set by orb_bot.py at startup
_execution_ref   = None    # set by orb_bot.py at startup
_last_cmd_ts_by_chat = {}
_stop_pending_until_by_chat = {}


def _send(chat_id: str, text: str):
    if not TG_TOKEN or not chat_id or TG_TOKEN.startswith("your_"):
        print(f"[TG] {text}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
    except Exception as e:
        print(f"[TG] Send failed: {e}")


def alert(text: str):
    """Send to personal chat and group."""
    _send(TG_PERSONAL_ID, text)
    if TG_GROUP_ID and TG_GROUP_ID != TG_PERSONAL_ID:
        _send(TG_GROUP_ID, text)


def alert_personal(text: str):
    """Send to personal chat only."""
    _send(TG_PERSONAL_ID, text)


def send_signal(sig: dict, contract: str, strike: float, expiry: str,
                contracts: int, dollar_risk: float, vix: float | None):
    vix_str = f"{vix:.1f}" if vix else "N/A"
    trend   = "✓ WITH TREND"
    msg = (
        f"🟢 <b>ORB SIGNAL</b>\n"
        f"Symbol: {sig['code'].replace('US.','')}  Direction: {sig['direction']}\n"
        f"Option: {contract}  Strike: ${strike:.0f}  Expiry: {expiry}\n"
        f"Stock Price: ${sig['stock_price']:.2f}\n"
        f"Risk: ${dollar_risk:.0f}  Contracts: {contracts}\n"
        f"OR High: {sig['or_high']:.2f}  OR Low: {sig['or_low']:.2f}\n"
        f"VIX: {vix_str}  | {trend}\n"
        f"Time: {sig['time']}"
    )
    alert(msg)


def send_fill(contract: str, qty: int, direction: str, premium: float):
    msg = (
        f"✅ <b>ORDER FILLED</b>\n"
        f"{direction} {contract}\n"
        f"Qty: {qty}  Premium: ${premium:.2f}/contract\n"
        f"Total cost: ${premium * qty * 100:.0f}"
    )
    alert(msg)


def send_exit(contract: str, qty: int, reason: str, pnl: float):
    emoji = "🟩" if pnl >= 0 else "🟥"
    msg = (
        f"{emoji} <b>EXIT</b>\n"
        f"{contract}  Qty: {qty}\n"
        f"Reason: {reason}\n"
        f"P&L: ${pnl:+.0f}"
    )
    alert(msg)


def send_circuit_breaker(reason: str):
    msg = f"⚠️ <b>CIRCUIT BREAKER</b>\n{reason}"
    alert(msg)


def send_status(risk_mgr, open_positions: list):
    pos_lines = "\n".join(
        f"  {p['code']} × {int(p['qty'])} | P&L: {p['pl_ratio']:.1%}"
        for p in open_positions
    ) or "  None"
    msg = (
        f"📊 <b>STATUS</b>\n"
        f"{risk_mgr.status_summary()}\n"
        f"Open positions:\n{pos_lines}"
    )
    alert_personal(msg)


def send_eod(closed: list, daily_pnl: float):
    msg = (
        f"🔔 <b>EOD — 3:45 PM</b>\n"
        f"Closed {len(closed)} position(s)\n"
        f"Daily P&L: ${daily_pnl:+.0f}"
    )
    alert(msg)


# ── Command listener (background thread) ─────────────────────────────────────


def dispatch_authorized_command(text: str, chat_id: str, now_ts: float) -> None:
    """
    Handle a single validated Telegram command (already authorized + throttled).
    Exposed for tests; production uses _poll_commands.
    """
    global _risk_ref, _execution_ref
    if text == "/stop":
        _stop_pending_until_by_chat[chat_id] = now_ts + TELEGRAM_STOP_CONFIRM_TTL_SEC
        alert_personal(
            "⚠️ Stop requested. Confirm within "
            f"{int(TELEGRAM_STOP_CONFIRM_TTL_SEC)}s with /stop confirm"
            + (" <code>" if TG_STOP_CONFIRM_CODE else "")
        )
    elif text.startswith("/stop confirm"):
        until_ts = float(_stop_pending_until_by_chat.get(chat_id, 0.0))
        if now_ts > until_ts:
            alert_personal("⚠️ Stop confirmation expired. Send /stop again.")
            return
        if TG_STOP_CONFIRM_CODE:
            parts = text.split()
            code = parts[2] if len(parts) >= 3 else ""
            if code != TG_STOP_CONFIRM_CODE.lower():
                alert_personal("❌ Stop confirmation code invalid.")
                return
        if _risk_ref:
            _risk_ref.stopped = True
            _risk_ref.paused = True
        if _execution_ref:
            _execution_ref()
        _stop_pending_until_by_chat.pop(chat_id, None)
        alert_personal("🛑 Bot STOPPED — all positions closed.")

    elif text == "/pause":
        if _risk_ref:
            if hasattr(_risk_ref, "set_operator_manual_pause"):
                _risk_ref.set_operator_manual_pause()
            else:
                _risk_ref.paused = True
        alert_personal("⏸ Bot PAUSED — monitoring continues.")

    elif text == "/resume":
        if _risk_ref:
            _risk_ref.paused = False
            _risk_ref.stopped = False
            if hasattr(_risk_ref, "clear_pause_diagnostics"):
                _risk_ref.clear_pause_diagnostics()
        alert_personal("▶️ Bot RESUMED — new entries enabled.")

    elif text == "/status":
        if _risk_ref and hasattr(_risk_ref, "status_summary"):
            alert_personal(f"📊 <b>STATUS</b>\n{_risk_ref.status_summary()}")
        elif _risk_ref:
            from execution import get_positions

            positions = get_positions()
            send_status(_risk_ref, positions)


def _poll_commands():
    """Background thread: poll Telegram for /stop /pause /resume /status."""
    global _last_update_id
    if not TG_TOKEN or TG_TOKEN.startswith("your_"):
        return

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                params={"offset": _last_update_id + 1, "timeout": 10},
                timeout=15,
            )
            data = resp.json()
            for update in data.get("result", []):
                _last_update_id = update["update_id"]
                msg = update.get("message", {})
                text = msg.get("text", "").strip().lower()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Only accept commands from authorized chats
                if chat_id not in (TG_PERSONAL_ID, TG_GROUP_ID):
                    continue

                now_ts = time.time()
                prev_ts = float(_last_cmd_ts_by_chat.get(chat_id, 0.0))
                if now_ts - prev_ts < TELEGRAM_CMD_MIN_INTERVAL_SEC:
                    continue
                _last_cmd_ts_by_chat[chat_id] = now_ts

                dispatch_authorized_command(text, chat_id, now_ts)

        except Exception as e:
            print(f"[TG poll] {e}")


def start_listener(risk_mgr, stop_all_fn):
    """Start background polling thread. Call once at bot startup."""
    global _risk_ref, _execution_ref
    _risk_ref       = risk_mgr
    _execution_ref  = stop_all_fn
    t = threading.Thread(target=_poll_commands, daemon=True)
    t.start()
