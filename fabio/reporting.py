"""Statistics, console summary, and matplotlib report."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from fabio.settings import FabioBacktestSettings


def compute_stats(
    trades_df: pd.DataFrame, equity_df: pd.DataFrame, cfg: FabioBacktestSettings
) -> dict:
    t = trades_df
    n = len(t)
    if n == 0:
        return {}

    wins = t[t["total_pnl"] > 0]
    loses = t[t["total_pnl"] <= 0]

    eq = equity_df["capital"]
    roll_max = eq.cummax()
    dd_series = (eq - roll_max) / roll_max * 100
    ic = cfg.initial_capital
    daily_ret = equity_df["day_pnl"] / equity_df["capital"].shift(1).fillna(ic)
    sharpe = (
        (daily_ret.mean() / daily_ret.std() * math.sqrt(252)) if daily_ret.std() > 0 else 0
    )

    avg_win = wins["total_pnl"].mean() if len(wins) else 0
    avg_loss = loses["total_pnl"].mean() if len(loses) else 0
    gross_win = wins["total_pnl"].sum() if len(wins) else 0
    gross_loss = loses["total_pnl"].sum() if len(loses) else 0
    pf = abs(gross_win / gross_loss) if gross_loss != 0 else float("inf")

    return {
        "n": n,
        "wins": len(wins),
        "losses": len(loses),
        "win_rate": len(wins) / n * 100,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf,
        "expectancy": t["total_pnl"].mean(),
        "total_pnl": t["total_pnl"].sum(),
        "total_return": (eq.iloc[-1] / ic - 1) * 100,
        "max_dd": dd_series.min(),
        "sharpe": sharpe,
        "final_cap": eq.iloc[-1],
        "dd_series": dd_series,
        "daily_ret": daily_ret,
        "by_exit": t.groupby("exit_reason")["total_pnl"]
        .agg(["count", "mean", lambda x: (x > 0).mean() * 100])
        .rename(columns={"count": "n", "mean": "avg", "<lambda_0>": "win%"}),
        "by_dir": t.groupby("direction")["total_pnl"]
        .agg(["count", "mean", lambda x: (x > 0).mean() * 100])
        .rename(columns={"count": "n", "mean": "avg", "<lambda_0>": "win%"}),
        "by_trend": t.groupby("counter_trend")["total_pnl"]
        .agg(["count", "mean", lambda x: (x > 0).mean() * 100])
        .rename(columns={"count": "n", "mean": "avg", "<lambda_0>": "win%"}),
        "by_symbol": t.groupby("symbol")["total_pnl"]
        .agg(["count", "mean", lambda x: (x > 0).mean() * 100])
        .rename(columns={"count": "n", "mean": "avg", "<lambda_0>": "win%"}),
    }


def print_summary(s: dict, cfg: FabioBacktestSettings, title: str = "FABIO STRATEGY BACKTEST RESULTS"):
    if not s:
        print("No trades generated.")
        return
    pf_str = f"{s['profit_factor']:.2f}" if s["profit_factor"] != float("inf") else "∞"
    sym_join = " + ".join(cfg.symbols)
    print("\n" + "═" * 60)
    print(f"  {title}")
    print(f"  {cfg.start_date}  →  {cfg.end_date}  |  {sym_join}")
    print("═" * 60)
    print(f"  Total trades      : {s['n']}")
    print(f"  Win rate          : {s['win_rate']:.1f}%  ({s['wins']}W / {s['losses']}L)")
    print(f"  Avg win           : ${s['avg_win']:,.0f}")
    print(f"  Avg loss          : ${s['avg_loss']:,.0f}")
    print(f"  Profit factor     : {pf_str}")
    print(f"  Expectancy/trade  : ${s['expectancy']:,.0f}")
    print(f"  Total P&L         : ${s['total_pnl']:,.0f}")
    print(f"  Total return      : {s['total_return']:.1f}%")
    print(f"  Max drawdown      : {s['max_dd']:.1f}%")
    print(f"  Sharpe ratio      : {s['sharpe']:.2f}")
    print(f"  Final capital     : ${s['final_cap']:,.0f}")
    print("─" * 60)
    print("\n  Exit reasons:")
    for r, row in s["by_exit"].iterrows():
        print(
            f"    {r:<20}: {int(row['n']):>4} trades | avg ${row['avg']:>7,.0f} | win% {row['win%']:.0f}%"
        )
    print("\n  Direction:")
    for d, row in s["by_dir"].iterrows():
        print(
            f"    {d:<8}: {int(row['n']):>4} trades | avg ${row['avg']:>7,.0f} | win% {row['win%']:.0f}%"
        )
    print("\n  Trend alignment:")
    for flag, row in s["by_trend"].iterrows():
        label = "Counter" if flag else "With trend"
        print(
            f"    {label:<12}: {int(row['n']):>4} trades | avg ${row['avg']:>7,.0f} | win% {row['win%']:.0f}%"
        )
    print("\n  Symbol:")
    for sym, row in s["by_symbol"].iterrows():
        print(
            f"    {sym:<6}: {int(row['n']):>4} trades | avg ${row['avg']:>7,.0f} | win% {row['win%']:.0f}%"
        )
    print("═" * 60)


def plot_results(
    trades_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    s: dict,
    cfg: FabioBacktestSettings,
    out_path: str = "Fabio_backtest_report.png",
    chart_title: str | None = None,
):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        from matplotlib.ticker import FuncFormatter
    except ImportError:
        print("⚠  matplotlib not found — skipping chart.")
        return

    BG = "#131722"
    PANEL = "#1E222D"
    GREEN = "#26A69A"
    RED = "#EF5350"
    YELLOW = "#F9A825"
    BLUE = "#2196F3"
    GRAY = "#434651"
    TEXT = "#D1D4DC"
    SUBTEXT = "#787B86"
    WHITE = "#FFFFFF"
    ic = cfg.initial_capital

    dollar_fmt = FuncFormatter(lambda x, _: f"${x:,.0f}")
    pct_fmt = FuncFormatter(lambda x, _: f"{x:.1f}%")

    fig = plt.figure(figsize=(20, 14), facecolor=BG)
    title_main = chart_title or (
        f"Fabio Strategy Backtest  ·  {cfg.start_date} → {cfg.end_date}  ·  {' + '.join(cfg.symbols)}"
    )
    fig.suptitle(title_main, color=TEXT, fontsize=14, fontweight="bold", y=0.98)

    gs = gridspec.GridSpec(
        3,
        4,
        figure=fig,
        height_ratios=[2.2, 1, 1],
        hspace=0.45,
        wspace=0.35,
        left=0.06,
        right=0.98,
        top=0.93,
        bottom=0.06,
    )

    ax1 = fig.add_subplot(gs[0, :])
    ax1.set_facecolor(PANEL)
    ax1.tick_params(colors=SUBTEXT)
    for spine in ax1.spines.values():
        spine.set_edgecolor(GRAY)

    dates = pd.to_datetime(equity_df["date"])
    equity = equity_df["capital"].values
    ax1.plot(dates, equity, color=GREEN, linewidth=1.8, zorder=3)
    ax1.fill_between(dates, ic, equity, where=(equity >= ic), alpha=0.12, color=GREEN)
    ax1.fill_between(dates, ic, equity, where=(equity < ic), alpha=0.18, color=RED)
    ax1.axhline(ic, color=GRAY, linewidth=0.8, linestyle="--")

    ax1_dd = ax1.twinx()
    ax1_dd.set_facecolor("none")
    ax1_dd.fill_between(dates, 0, s["dd_series"].values, alpha=0.25, color=RED)
    ax1_dd.set_ylim(-50, 5)
    ax1_dd.yaxis.set_major_formatter(pct_fmt)
    ax1_dd.tick_params(colors=SUBTEXT, labelsize=8)
    ax1_dd.set_ylabel("Drawdown", color=SUBTEXT, fontsize=8)

    t = trades_df.copy()
    t["date"] = pd.to_datetime(t["date"])
    eq_by_date = equity_df.set_index("date")["capital"]
    for _, row in t.iterrows():
        d = str(row["date"].date())
        if d not in eq_by_date.index:
            continue
        clr = GREEN if row["direction"] == "CALL" else RED
        mrk = "^" if row["direction"] == "CALL" else "v"
        ax1.scatter(row["date"], eq_by_date[d], color=clr, marker=mrk, s=28, zorder=5, alpha=0.8)

    ax1.yaxis.set_major_formatter(dollar_fmt)
    ax1.set_ylabel("Portfolio Value", color=TEXT, fontsize=9)
    ax1.set_title(
        "Equity Curve  ·  ▲ CALL   ▼ PUT   shading = drawdown",
        color=SUBTEXT,
        fontsize=8,
        loc="left",
        pad=4,
    )
    ax1.grid(axis="y", color=GRAY, alpha=0.3, linewidth=0.5)

    ax2 = fig.add_subplot(gs[1, :2])
    ax2.set_facecolor(PANEL)
    ax2.tick_params(colors=SUBTEXT, labelsize=7)
    for spine in ax2.spines.values():
        spine.set_edgecolor(GRAY)
    t["month"] = t["date"].dt.to_period("M")
    monthly = t.groupby("month")["total_pnl"].sum()
    clrs = [GREEN if v >= 0 else RED for v in monthly.values]
    ax2.bar(range(len(monthly)), monthly.values, color=clrs, alpha=0.85, width=0.7)
    ax2.axhline(0, color=GRAY, linewidth=0.8)
    ax2.set_xticks(range(len(monthly)))
    ax2.set_xticklabels([str(m) for m in monthly.index], rotation=45, ha="right", fontsize=6)
    ax2.yaxis.set_major_formatter(dollar_fmt)
    ax2.set_title("Monthly P&L", color=TEXT, fontsize=9, loc="left")
    ax2.grid(axis="y", color=GRAY, alpha=0.3, linewidth=0.5)

    ax3 = fig.add_subplot(gs[1, 2])
    ax3.set_facecolor(PANEL)
    wr = s["win_rate"]
    ax3.pie(
        [wr, 100 - wr],
        colors=[GREEN, RED],
        startangle=90,
        wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 2},
        counterclock=False,
    )
    ax3.text(0, 0, f"{wr:.1f}%", ha="center", va="center", color=WHITE, fontsize=16, fontweight="bold")
    ax3.text(0, -0.6, "Win Rate", ha="center", color=SUBTEXT, fontsize=8)
    ax3.set_title("Win Rate", color=TEXT, fontsize=9, loc="left")

    ax4 = fig.add_subplot(gs[1, 3])
    ax4.set_facecolor(PANEL)
    ax4.tick_params(colors=SUBTEXT, labelsize=7)
    for spine in ax4.spines.values():
        spine.set_edgecolor(GRAY)
    er = s["by_exit"]
    clrs = [GREEN if v >= 0 else RED for v in er["avg"]]
    ax4.barh(er.index, er["avg"], color=clrs, alpha=0.85, height=0.5)
    ax4.axvline(0, color=GRAY, linewidth=0.8)
    ax4.xaxis.set_major_formatter(dollar_fmt)
    ax4.set_title("Avg P&L by Exit Reason", color=TEXT, fontsize=9, loc="left")
    ax4.grid(axis="x", color=GRAY, alpha=0.3, linewidth=0.5)

    ax5 = fig.add_subplot(gs[2, :2])
    ax5.set_facecolor(PANEL)
    ax5.tick_params(colors=SUBTEXT, labelsize=7)
    for spine in ax5.spines.values():
        spine.set_edgecolor(GRAY)
    pnls = t["total_pnl"].values
    bins = np.linspace(pnls.min(), pnls.max(), 40)
    ax5.hist(pnls[pnls >= 0], bins=bins, color=GREEN, alpha=0.75, label="Wins")
    ax5.hist(pnls[pnls < 0], bins=bins, color=RED, alpha=0.75, label="Losses")
    ax5.axvline(
        s["expectancy"],
        color=YELLOW,
        linewidth=1.2,
        linestyle="--",
        label=f"Expectancy ${s['expectancy']:,.0f}",
    )
    ax5.axvline(0, color=GRAY, linewidth=0.8)
    ax5.xaxis.set_major_formatter(dollar_fmt)
    ax5.set_title("P&L Distribution", color=TEXT, fontsize=9, loc="left")
    ax5.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, framealpha=0.6)
    ax5.grid(axis="y", color=GRAY, alpha=0.3, linewidth=0.5)

    ax6 = fig.add_subplot(gs[2, 2:])
    ax6.set_facecolor(PANEL)
    ax6.tick_params(colors=SUBTEXT, labelsize=7)
    for spine in ax6.spines.values():
        spine.set_edgecolor(GRAY)
    roll_ret = s["daily_ret"]
    roll_sharpe = roll_ret.rolling(63).mean() / roll_ret.rolling(63).std() * math.sqrt(252)
    rs_dates = pd.to_datetime(equity_df["date"])
    ax6.plot(rs_dates, roll_sharpe.values, color=BLUE, linewidth=1.4)
    ax6.axhline(0, color=GRAY, linewidth=0.8)
    ax6.axhline(1, color=GREEN, linewidth=0.6, linestyle="--", alpha=0.6)
    ax6.fill_between(rs_dates, 0, roll_sharpe.values, where=(roll_sharpe.values >= 0), alpha=0.12, color=GREEN)
    ax6.fill_between(rs_dates, 0, roll_sharpe.values, where=(roll_sharpe.values < 0), alpha=0.18, color=RED)
    ax6.set_title("Rolling 63-Day Sharpe Ratio", color=TEXT, fontsize=9, loc="left")
    ax6.grid(axis="y", color=GRAY, alpha=0.3, linewidth=0.5)

    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"\n  Chart saved → {out_path}")
