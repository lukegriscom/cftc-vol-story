"""
steelman_checks.py: tests the three ChatGPT arguments for the rejected story against the data.

Author: Luke Griscom (FA 550, A5). Code written with Claude (Opus 5.5); see amr_log.csv (Decision #63).

The rejected story: when implied vol spikes, volatility-targeting funds must cut equity
exposure, so the asset-manager selling in Friday's report is mechanical and keeps coming.
ChatGPT's three arguments for it, and the checks run here:
  1. The four indexes sell by almost the same amount, like one common deleveraging.
     -> Do the four indexes' changes move together week by week once each index's own
        price move is held fixed, and more so in spike weeks?
  2. A vol-driven sale can happen in a falling market, so holding price fixed may hide it.
     -> Does a larger rise in implied vol, or in realized vol (what vol-targeting funds
        actually target), predict more selling at the same price move?
  3. The Nasdaq-100 week-after selling may be delayed vol-targeting, not a Nasdaq anomaly.
     -> In the week after a spike, does vol stay higher in the Nasdaq-100 than elsewhere,
        and is the Nasdaq-100 selling larger when vol stays high?

Needs the daily ETF closes (data/etf_close_yahoo.csv, from A4's data/raw/etf_free/) for
realized vol. Writes steelman_checks.txt. Run from this folder: python steelman_checks.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

import analysis as A

HERE = Path(__file__).resolve().parent
AM, NQ = "Asset manager", "Nasdaq-100"
COL = A.MEASURES["net"][0]
ETF = {"S&P 500": "SPY", "Nasdaq-100": "QQQ", "Dow": "DIA", "Russell 2000": "IWM"}
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    OUT.append(line)


def ci(v):
    v = np.asarray(v, float)
    v = v[~np.isnan(v)]
    m, se = v.mean(), v.std(ddof=1) / np.sqrt(len(v))
    return m, m - 1.96 * se, m + 1.96 * se, len(v)


def fmt(t):
    return f"{t[0]:+.2f} ({t[1]:+.2f} to {t[2]:+.2f}), n={t[3]}"


def realized_vol(window=20):
    """Annualized realized vol of each ETF's daily log returns over the last `window` trading days."""
    px = pd.read_csv(HERE / "data" / "etf_close_yahoo.csv", parse_dates=["Date"]).set_index("Date").sort_index()
    lr = np.log(px).diff()
    return lr.rolling(window).std() * np.sqrt(252) * 100


def add_realized(f, rv):
    """As-of join of 20-day realized vol to each report date (latest close on or before it)."""
    out = []
    for idx, tk in ETF.items():
        d = f[f["index"] == idx].sort_values("report_date")
        s = rv[tk].dropna().rename("rv").reset_index().rename(columns={"Date": "rv_date"})
        d = pd.merge_asof(d, s, left_on="report_date", right_on="rv_date", direction="backward")
        out.append(d)
    g = pd.concat(out).sort_values(["index", "trader_type", "report_date"])
    g["d_rv"] = g.groupby(["index", "trader_type"])["rv"].diff()
    return g.reset_index(drop=True)


def ols(y, X):
    b, se = A._ols(np.asarray(y, float), np.column_stack(X))
    return b, se


def main():
    df = A.load()
    f = A.flag_spikes(df, 10)
    f = add_realized(f, realized_vol(20))
    am = f[f["trader_type"] == AM].copy()

    say("Steelman checks. Asset managers, change in net position in points of last week's open interest.")
    say("Spike week: top 10% of weekly % rises in the index's own implied vol. Realized vol: 20-day, annualized, from daily ETF closes.")

    # ------------------------------------------------------------------ argument 1
    say("\nArgument 1: one common deleveraging across the four indexes?")
    wide_y = am.pivot(index="report_date", columns="index", values=COL)[A.INDEXES]
    wide_r = am.pivot(index="report_date", columns="index", values="etf_ret_wk")[A.INDEXES]
    wide_s = am.pivot(index="report_date", columns="index", values="spike")[A.INDEXES].fillna(False).astype(bool)
    resid = pd.DataFrame(index=wide_y.index, columns=A.INDEXES, dtype=float)
    for idx in A.INDEXES:
        ok = wide_y[idx].notna() & wide_r[idx].notna()
        r = wide_r.loc[ok, idx].to_numpy(float)
        b, _ = ols(wide_y.loc[ok, idx], [np.ones_like(r), r, r ** 2])
        resid.loc[ok, idx] = wide_y.loc[ok, idx] - (b[0] + b[1] * r + b[2] * r ** 2)
    allfour = wide_s.all(axis=1)
    none = ~wide_s.any(axis=1)

    def avg_corr(frame):
        c = frame.dropna().corr().to_numpy()
        return c[np.triu_indices(4, 1)].mean(), len(frame.dropna())

    for label, mask in [("weeks that are spikes in all four indexes", allfour), ("weeks that are a spike in no index", none)]:
        cr, n = avg_corr(wide_y[mask])
        cres, _ = avg_corr(resid[mask])
        cret, _ = avg_corr(wide_r[mask])
        say(f"  {label} ({n} weeks): average pairwise correlation of the four indexes' changes {cr:+.2f};"
            f" of their ETF returns {cret:+.2f}; of the changes with each index's own price move held fixed {cres:+.2f}")
    say("  mean change in the shared spike weeks, as reported vs with own price move held fixed (vs the no-spike-week mean):")
    for idx in A.INDEXES:
        raw = ci(wide_y.loc[allfour, idx] - wide_y.loc[none, idx].mean())
        res = ci(resid.loc[allfour, idx] - resid.loc[none, idx].mean())
        say(f"    {idx:13s} as reported {fmt(raw)} | held fixed {fmt(res)}")

    # ------------------------------------------------------------------ argument 2
    say("\nArgument 2: does a bigger vol rise mean more selling at the same price move? (all weeks, HC1 intervals)")
    say("  change = a + b*vol_measure + c*ret + d*ret^2; b scaled to a 10-point rise (implied: 10% rise in the index's own vol index;"
        " realized: 10 points of annualized 20-day realized vol)")
    for idx in A.INDEXES:
        d = am[am["index"] == idx].dropna(subset=[COL, "etf_ret_wk", "pct_d_vol", "d_rv"])
        y, r = d[COL].to_numpy(float), d["etf_ret_wk"].to_numpy(float)
        one = np.ones_like(y)
        parts = []
        for name, v in [("implied %", d["pct_d_vol"].to_numpy(float)), ("realized pts", d["d_rv"].to_numpy(float))]:
            b0, s0 = ols(y, [one, v])
            b1, s1 = ols(y, [one, v, r, r ** 2])
            parts.append(f"{name}: alone {10*b0[1]:+.2f} ({10*(b0[1]-1.96*s0[1]):+.2f} to {10*(b0[1]+1.96*s0[1]):+.2f}),"
                         f" price held fixed {10*b1[1]:+.2f} ({10*(b1[1]-1.96*s1[1]):+.2f} to {10*(b1[1]+1.96*s1[1]):+.2f})")
        say(f"  {idx:13s} n={len(y)} | " + " | ".join(parts))
    say("  threshold check, Nasdaq-100: spike weeks by size of the VXN jump, change with price held fixed (residual from the ordinary-week curve)")
    d = am[(am["index"] == NQ)].dropna(subset=[COL, "etf_ret_wk"])
    o = d[d["ordinary"]]
    b, _ = ols(o[COL], [np.ones(len(o)), o["etf_ret_wk"], o["etf_ret_wk"] ** 2])
    d = d.assign(res=d[COL] - (b[0] + b[1] * d["etf_ret_wk"] + b[2] * d["etf_ret_wk"] ** 2))
    sp = d[d["spike"]]
    for lo_, hi_, lab in [(0, 25, "VXN up 14.7% to 25%"), (25, 40, "up 25% to 40%"), (40, 1e9, "up 40% or more")]:
        g = sp[(sp["pct_d_vol"] >= lo_) & (sp["pct_d_vol"] < hi_)]
        say(f"    {lab:22s} {fmt(ci(g['res']))}")

    # ------------------------------------------------------------------ argument 3
    say("\nArgument 3: is the Nasdaq-100 week-after selling delayed vol-targeting?")
    say("  vol in the week after an isolated spike (spike not followed by another spike), mean and 95% interval:")
    rows = {}
    for idx in A.INDEXES:
        d = am[am["index"] == idx].sort_values("report_date").reset_index(drop=True)
        nxt_spk = d["spike"].shift(-1, fill_value=False).astype(bool)
        iso = d.index[d["spike"] & ~nxt_spk]
        iso = iso[iso + 1 < len(d)]
        w1 = d.loc[iso + 1]
        rows[idx] = (d, iso)
        say(f"    {idx:13s} implied vol change in week +1 {fmt(ci(w1['pct_d_vol']))} % |"
            f" realized vol change in week +1 {fmt(ci(w1['d_rv']))} pts |"
            f" realized vol change in the spike week {fmt(ci(d.loc[iso, 'd_rv']))} pts")

    say("  Nasdaq-100 week-after change with both weeks' returns held fixed, split by what vol did in week +1:")
    d, iso = rows[NQ]
    keep = (d["ordinary"] | d["spike"]) & ~(d["spike"] & d["spike"].shift(-1, fill_value=False).astype(bool))
    y1, r1, r0 = d[COL].shift(-1), d["etf_ret_wk"].shift(-1), d["etf_ret_wk"]
    m = keep & y1.notna() & r1.notna() & r0.notna()
    s = d["spike"].astype(float)
    b, _ = ols(y1[m], [np.ones(m.sum()), s[m], r1[m], r1[m] ** 2, r0[m]])
    res = y1 - (b[0] + b[2] * r1 + b[3] * r1 ** 2 + b[4] * r0)      # spike weeks keep their gap in the residual
    base = res[m & (s == 0)].mean()
    g = pd.DataFrame({"res": res - base, "dvol1": d["pct_d_vol"].shift(-1), "drv1": d["d_rv"].shift(-1),
                      "long1": d["d_long_pct"].shift(-1), "short1": d["d_short_pct"].shift(-1)}).loc[[i for i in iso if m.iloc[i]]]
    say(f"    all isolated spikes: {fmt(ci(g['res']))} (matches the story's -1.35)")
    med = g["dvol1"].median()
    for lab, mm in [(f"VXN kept rising or fell less than the median ({med:+.1f}%) in week +1", g["dvol1"] >= med),
                    (f"VXN fell more than the median in week +1", g["dvol1"] < med),
                    ("realized vol rose in week +1", g["drv1"] > 0), ("realized vol fell in week +1", g["drv1"] <= 0)]:
        say(f"    {lab:62s} {fmt(ci(g.loc[mm, 'res']))}")
    b1, s1 = ols(g["res"], [np.ones(len(g)), g["dvol1"] / 10])
    say(f"    slope of week-after selling on week +1 VXN change, per 10%: {b1[1]:+.2f} ({b1[1]-1.96*s1[1]:+.2f} to {b1[1]+1.96*s1[1]:+.2f})")
    say("  same check for the S&P 500, where vol-targeting funds hold the most futures:")
    d2, iso2 = rows["S&P 500"]
    keep2 = (d2["ordinary"] | d2["spike"]) & ~(d2["spike"] & d2["spike"].shift(-1, fill_value=False).astype(bool))
    y2, r2_, r02 = d2[COL].shift(-1), d2["etf_ret_wk"].shift(-1), d2["etf_ret_wk"]
    m2 = keep2 & y2.notna() & r2_.notna() & r02.notna()
    s2 = d2["spike"].astype(float)
    bb, _ = ols(y2[m2], [np.ones(m2.sum()), s2[m2], r2_[m2], r2_[m2] ** 2, r02[m2]])
    res2 = y2 - (bb[0] + bb[2] * r2_ + bb[3] * r2_ ** 2 + bb[4] * r02)
    base2 = res2[m2 & (s2 == 0)].mean()
    g2 = pd.DataFrame({"res": res2 - base2, "drv1": d2["d_rv"].shift(-1)}).loc[[i for i in iso2 if m2.iloc[i]]]
    say(f"    S&P 500 all isolated spikes {fmt(ci(g2['res']))} | realized vol rose in week +1 {fmt(ci(g2.loc[g2['drv1'] > 0, 'res']))}"
        f" | fell {fmt(ci(g2.loc[g2['drv1'] <= 0, 'res']))}")

    (HERE / "steelman_checks.txt").write_text("\n".join(OUT) + "\n")
    say("\nwrote build/steelman_checks.txt")


if __name__ == "__main__":
    main()
