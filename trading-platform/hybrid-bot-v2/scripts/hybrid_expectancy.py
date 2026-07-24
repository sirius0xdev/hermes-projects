#!/usr/bin/env python3
"""Summarize hybrid VWAP+orderflow paper trades (clean vs contaminated)."""
from __future__ import annotations

import os
import sqlite3
import statistics
from collections import defaultdict
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "hybrid_paper.sqlite"
SESSION = os.getenv("HYB_SESSION", "hybrid-clean-20260709")
FEE_BPS = float(os.getenv("HYB_FEE_BPS_RT", "2.0"))


def _sumr(rows, fee_frac: float) -> str:
    if not rows:
        return "n=0"
    nets = []
    for r in rows:
        pnl = float(r["pnl_usd"] or 0)
        size = float(r["size_usd"] or 0)
        nets.append(pnl - size * fee_frac)
    wins = [x for x in nets if x > 0]
    n = len(nets)
    wr = len(wins) / n if n else 0
    net = sum(nets)
    gw = sum(x for x in nets if x > 0)
    gl = abs(sum(x for x in nets if x < 0))
    pf = (gw / gl) if gl > 1e-9 else (999.0 if gw > 0 else 0.0)
    return f"n={n} WR={wr:.1%} net=${net:+.4f} PF={pf:.2f}"


def main() -> None:
    if not DB.is_file():
        print("No hybrid DB yet")
        return
    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    fee_frac = FEE_BPS / 10000.0

    # Ensure columns exist for older DBs
    cols = {r[1] for r in con.execute("PRAGMA table_info(paper_trades)").fetchall()}
    for col, typ in (("contaminated", "INTEGER DEFAULT 0"), ("session_id", "TEXT DEFAULT ''")):
        if col not in cols:
            try:
                con.execute(f"ALTER TABLE paper_trades ADD COLUMN {col} {typ}")
                con.commit()
            except sqlite3.OperationalError:
                pass

    trades = con.execute("SELECT * FROM paper_trades ORDER BY id").fetchall()
    sigs = con.execute("SELECT * FROM signals ORDER BY id").fetchall()
    metrics_n = con.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    try:
        gates_n = con.execute("SELECT COUNT(*) FROM gate_events").fetchone()[0]
    except sqlite3.OperationalError:
        gates_n = 0

    print("=== Hybrid VWAP+orderflow paper ===")
    print(f"metrics={metrics_n} signals={len(sigs)} trades={len(trades)} gate_events={gates_n}")
    print(f"fee model: {FEE_BPS:.1f} bps round-trip on size_usd")

    closed_all = [t for t in trades if t["status"] == "closed"]
    open_ = [t for t in trades if t["status"] == "open"]
    clean = [
        t
        for t in closed_all
        if not (t["contaminated"] if "contaminated" in t.keys() else 0)
        and (t["setup"] or "") != "test"
        and (t["exit_reason"] or "") != "contaminated_dup"
    ]
    session = [t for t in clean if (t["session_id"] if "session_id" in t.keys() else "") == SESSION]
    contaminated = [t for t in closed_all if t not in clean]

    print(f"open={len(open_)} closed_all={len(closed_all)} clean={len(clean)} session[{SESSION}]={len(session)} contaminated={len(contaminated)}")
    if open_:
        for t in open_:
            print(
                f"  OPEN id={t['id']} {t['coin']} {t['side']} {t['setup']} "
                f"entry={t['entry']} size=${t['size_usd']} lev={t['leverage']} "
                f"session={t['session_id'] if 'session_id' in t.keys() else ''}"
            )

    for label, rows in (("clean (go-live-ish)", clean), (f"session {SESSION}", session), ("raw all closed", closed_all)):
        if not rows:
            print(f"{label}: n=0")
            continue
        print(f"{label}: {_sumr(rows, fee_frac)}")
        by_setup: dict = defaultdict(list)
        by_zone: dict = defaultdict(list)
        for t in rows:
            by_setup[t["setup"] or "?"].append(t)
            reason = t["reason"] or ""
            z = "?"
            for cand in ("upper_band", "lower_band", "upper_half", "lower_half", "at_vwap"):
                if f"zone={cand}" in reason:
                    z = cand
                    break
            by_zone[z].append(t)
        for setup, rs in sorted(by_setup.items(), key=lambda kv: -len(kv[1])):
            print(f"  setup {setup}: {_sumr(rs, fee_frac)}")
        for z, rs in sorted(by_zone.items(), key=lambda kv: -len(kv[1])):
            print(f"  zone  {z}: {_sumr(rs, fee_frac)}")

    # Forward 5m signal direction
    vals = []
    for s in sigs:
        row = con.execute(
            "SELECT mid FROM metrics WHERE coin=? AND ts>=? ORDER BY ts ASC LIMIT 1",
            (s["coin"], s["ts"] + 300),
        ).fetchone()
        if not row or not s["mid"]:
            continue
        bps = (row["mid"] - s["mid"]) / s["mid"] * 10000
        if s["side"] == "SHORT":
            bps = -bps
        vals.append(bps)
    if vals:
        print(
            f"signal 5m gross: n={len(vals)} avg={statistics.mean(vals):+.2f}bps "
            f"WR={sum(x > 0 for x in vals)/len(vals):.1%}"
        )

    if gates_n:
        print("recent gate fails:")
        for g in con.execute("SELECT * FROM gate_events ORDER BY id DESC LIMIT 5"):
            print(f"  {g['coin']}: {g['reason'][:140]}")

    if sigs:
        print("last signals:")
        for s in sigs[-5:]:
            print(
                {
                    "id": s["id"],
                    "coin": s["coin"],
                    "side": s["side"],
                    "setup": s["setup"],
                    "zone": s["zone"],
                    "mood": s["mood"],
                    "mid": s["mid"],
                }
            )
    con.close()


if __name__ == "__main__":
    main()
