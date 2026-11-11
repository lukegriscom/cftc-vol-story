"""
story_numbers.py: every number and chart dataset in the A5 story.

Author: Luke Griscom (FA 550, A5). Code written with Claude (Opus 5.5); see amr_log.csv.

It reuses the A4 statistics module (analysis.py, copied unchanged except for the
data path) on the A4 pipeline output (data/positioning_vol_weekly.csv, Yahoo
Finance interim ETF prices). Running it writes:
  ../story_data.json and ../story_data.js   the data the page draws
  story_numbers.txt         every number quoted in the story and the documents

Run from this folder:  python story_numbers.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import analysis as A

HERE = Path(__file__).resolve().parent
SITE = HERE.parent  # build/ sits inside the site folder (the repository root)
AM = "Asset manager"
NQ = "Nasdaq-100"
COL = A.MEASURES["net"][0]
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    print(line)
    OUT.append(line)


def r2(x):
    return None if x is None or pd.isna(x) else round(float(x), 2)


# ------------------------------------------------------------------ event path
def event_path(f, trader=AM, measure="net", horizons=range(-2, 5)):
    """Weeks around a spike, raw and with the ETF return held fixed, per index.

    For each horizon h, over every week t that is a spike or an ordinary week,
    leaving out spikes followed by another spike (as in A4 Q3):
      raw:        change(t+h) = a + b*spike(t)
      controlled: change(t+h) = a + b*spike(t) + c*ret(t+h) + d*ret(t+h)^2 [+ e*ret(t) when h != 0]
    b is the gap. At h = 1 this is exactly A4's price_control(horizon=1,
    drop_back_to_back=True), so the week-after numbers match A4 Q4.
    Both models use the same weeks at each horizon.
    """
    col = A.MEASURES[measure][0]
    rows = []
    for idx, d in f[f["trader_type"] == trader].groupby("index"):
        d = d.sort_values("report_date").reset_index(drop=True)
        nxt = d["spike"].shift(-1, fill_value=False).astype(bool)
        keep = (d["ordinary"] | d["spike"]) & ~(d["spike"] & nxt)
        r0 = d["etf_ret_wk"]
        for h in horizons:
            y, r = d[col].shift(-h), d["etf_ret_wk"].shift(-h)
            m = keep & y.notna() & r.notna() & r0.notna()
            yy, s = y[m].to_numpy(float), d.loc[m, "spike"].astype(float).to_numpy()
            rr, rr0 = r[m].to_numpy(float), r0[m].to_numpy(float)
            one = np.ones_like(yy)
            b1, se1 = A._ols(yy, np.column_stack([one, s]))
            X2 = [one, s, rr, rr ** 2] + ([rr0] if h != 0 else [])
            b2, se2 = A._ols(yy, np.column_stack(X2))
            rows.append(dict(index=idx, h=h, n_spike=int(s.sum()),
                             raw=b1[1], raw_lo=b1[1] - 1.96 * se1[1], raw_hi=b1[1] + 1.96 * se1[1],
                             ctrl=b2[1], ctrl_lo=b2[1] - 1.96 * se2[1], ctrl_hi=b2[1] + 1.96 * se2[1]))
    return pd.DataFrame(rows)


def drop_windows(f, windows):
    """Leave out weeks t where t or t+1 falls in a window, so neither the spike
    week nor the week after comes from those dates."""
    g = f.copy()
    dates = np.sort(g["report_date"].unique())
    inwin = pd.Series(False, index=pd.DatetimeIndex(dates))
    for a, b in windows:
        inwin |= (inwin.index >= pd.Timestamp(a)) & (inwin.index <= pd.Timestamp(b))
    bad = inwin | inwin.shift(-1, fill_value=False)
    hit = g["report_date"].map(bad)
    g.loc[hit, ["spike", "ordinary"]] = False
    return g


def main():
    df = A.load()
    f = A.flag_spikes(df, 10)
    data = {}

    say("A5 story numbers. Source: A4 pipeline output, Yahoo Finance interim ETF prices.")
    say("Measure: change in asset managers' net position, percentage points of last week's open interest.")
    say("Spike week: top 10% of weekly % increases in the index's own implied vol (VIX, VXN, VXD, RVX).")
    say("Coverage:", f["report_date"].min().date(), "to", f["report_date"].max().date(),
        "|", f["report_date"].nunique(), "report dates")

    # ---------------------------------------------------------- 0. two Fridays (hook)
    say("\n0. Hook: two Nasdaq-100 spike weeks")
    d = f[(f["trader_type"] == AM) & (f["index"] == NQ)].sort_values("report_date").set_index("report_date")
    hook = []
    for spike_date, release in [("2018-02-06", "Friday, February 9, 2018"), ("2025-04-08", "Friday, April 11, 2025")]:
        t = pd.Timestamp(spike_date)
        i = d.index.get_loc(t)
        w0, w1 = d.iloc[i], d.iloc[i + 1]
        row = dict(spike_date=spike_date, release=release, vxn_before=r2(d.iloc[i - 1]["vol_level"]),
                   vxn=r2(w0["vol_level"]), vxn_pct=r2(w0["pct_d_vol"]), spike=bool(w0["spike"]),
                   wk0=r2(w0[COL]), wk0_ret=r2(w0["etf_ret_wk"]),
                   wk1_date=str(d.index[i + 1].date()), wk1=r2(w1[COL]), wk1_ret=r2(w1["etf_ret_wk"]),
                   wk1_long=r2(w1["d_long_pct"]), wk1_short=r2(w1["d_short_pct"]))
        hist = d[COL].dropna()
        row["wk1_rank_low"] = int((hist <= w1[COL]).sum())        # 1 = the largest weekly sale on record
        row["net_contracts"] = [int(d.iloc[i]["net"]), int(w1["net"])]
        hook.append(row)
        say(" ", row)
        say(f"    next week's change ranks {row['wk1_rank_low']} of {len(hist)} weeks from the most negative;"
            f" net contracts {row['net_contracts'][0]:,} at the spike, {row['net_contracts'][1]:,} a week later")
    data["hook"] = hook

    # ---------------------------------------------------------- 1 and 3. spike week, raw vs price held fixed
    say("\n1/3. Spike week, all 106 spikes per index (A4 Q4 price_control, horizon 0)")
    pc0 = A.price_control(f, AM, horizon=0)
    bars = []
    for idx, r in pc0.iterrows():
        share = 1 - r["gap_ctrl"] / r["gap_raw"]
        bars.append(dict(index=idx, n_spike=int(r["n_spike"]), raw=r2(r["gap_raw"]), raw_lo=r2(r["lo_raw"]),
                         raw_hi=r2(r["hi_raw"]), ctrl=r2(r["gap_ctrl"]), ctrl_lo=r2(r["lo_ctrl"]),
                         ctrl_hi=r2(r["hi_ctrl"]), share_down=r2(100 * r["share_spike_down"]),
                         spike_ret=r2(r["spike_mean_ret"]), other_ret=r2(r["other_mean_ret"]),
                         explained_pct=r2(100 * share), ret_coef=r2(r["ret_coef"])))
        say(f"  {idx:13s} raw {r['gap_raw']:+.2f} ({r['lo_raw']:+.2f} to {r['hi_raw']:+.2f})"
            f" | price held fixed {r['gap_ctrl']:+.2f} ({r['lo_ctrl']:+.2f} to {r['hi_ctrl']:+.2f})"
            f" | share of raw gap gone {100*share:.0f}% | spike weeks down {100*r['share_spike_down']:.0f}%"
            f" | mean ETF return spike {r['spike_mean_ret']:+.2f}% vs other {r['other_mean_ret']:+.2f}%"
            f" | slope {r['ret_coef']:.2f} pts per 1% return")
    data["spike_week"] = bars

    # ---------------------------------------------------------- 2. scatter, Nasdaq-100
    say("\n2. Scatter: Nasdaq-100 asset managers, weekly change vs QQQ weekly return")
    x = f[(f["trader_type"] == AM) & (f["index"] == NQ) & (f["spike"] | f["ordinary"])]
    x = x.dropna(subset=[COL, "etf_ret_wk"]).sort_values("report_date")
    y, s, r = x[COL].to_numpy(float), x["spike"].astype(float).to_numpy(), x["etf_ret_wk"].to_numpy(float)
    b, _ = A._ols(y, np.column_stack([np.ones_like(y), s, r, r ** 2]))
    assert abs(b[1] - pc0.loc[NQ, "gap_ctrl"]) < 1e-9, "scatter fit must match A4 price_control"
    grid = np.linspace(np.floor(r.min()), np.ceil(r.max()), 61)
    data["scatter"] = dict(
        points=[dict(d=str(t.date()), r=round(float(a), 2), y=round(float(c), 2), s=bool(k))
                for t, a, c, k in zip(x["report_date"], r, y, x["spike"])],
        curve=[dict(r=round(float(g), 2), y=round(float(b[0] + b[2] * g + b[3] * g * g), 3)) for g in grid],
        coef=dict(a=r2(b[0]), spike=r2(b[1]), ret=round(float(b[2]), 3), ret2=round(float(b[3]), 4)),
        n=len(y), n_spike=int(s.sum()))
    sp = x[x["spike"]]
    say(f"  weeks {len(y)}, spike weeks {int(s.sum())}, spike weeks with QQQ down {(sp['etf_ret_wk']<0).sum()}"
        f", mean QQQ return in spike weeks {sp['etf_ret_wk'].mean():+.2f}%")
    say(f"  fitted on all weeks: change = {b[0]:+.2f} {b[1]:+.2f}*spike {b[2]:+.3f}*ret {b[3]:+.4f}*ret^2")
    # Matched comparison: each spike week against the ordinary weeks whose QQQ return was within w points of it.
    # Spike weeks with fewer than 3 such ordinary weeks (the most extreme crashes) are left out.
    rs, ys_, ss = x["etf_ret_wk"].to_numpy(float), x[COL].to_numpy(float), x["spike"].to_numpy(bool)
    matched = {}
    for w in (0.5, 0.75, 1.0):
        diffs, left_out = [], []
        for i in np.flatnonzero(ss):
            mm = (~ss) & (np.abs(rs - rs[i]) <= w)
            if mm.sum() >= 3:
                diffs.append(ys_[i] - ys_[mm].mean())
            else:
                left_out.append(str(x["report_date"].iloc[i].date()))
        diffs = np.array(diffs)
        se = diffs.std(ddof=1) / np.sqrt(len(diffs))
        matched[str(w)] = dict(n=len(diffs), diff=r2(diffs.mean()), lo=r2(diffs.mean() - 1.96 * se), hi=r2(diffs.mean() + 1.96 * se))
        say(f"  matched within +/-{w} pts of QQQ return: {len(diffs)} spike weeks, spike minus matched ordinary weeks"
            f" {diffs.mean():+.2f} ({diffs.mean()-1.96*se:+.2f} to {diffs.mean()+1.96*se:+.2f}); left out {len(left_out)}")
    say("  spike weeks left out at +/-0.75 (no close ordinary match):")
    lo75 = [str(x["report_date"].iloc[i].date()) for i in np.flatnonzero(ss) if ((~ss) & (np.abs(rs - rs[i]) <= 0.75)).sum() < 3]
    say("   ", ", ".join(lo75))
    data["matched"] = matched
    # Why the matched comparison replaced a 3%-threshold comparison: at a fixed threshold the spike weeks fall further.
    for c in (-2, -3, -4):
        o, k = (~ss) & (rs <= c), ss & (rs <= c)
        say(f"  (threshold check, not used in the story) QQQ <= {c}%: ordinary {o.sum()} weeks, mean return {rs[o].mean():+.2f}%,"
            f" mean change {ys_[o].mean():+.2f} | spike {k.sum()} weeks, mean return {rs[k].mean():+.2f}%, mean change {ys_[k].mean():+.2f}")

    # ---------------------------------------------------------- 4. the week after (event path)
    say("\n4. Weeks around a spike, spikes not followed by another spike, raw vs price held fixed")
    ep = event_path(f)
    say(ep.round(2).to_string(index=False))
    pc1 = A.price_control(f, AM, horizon=1, drop_back_to_back=True)
    for idx in A.INDEXES:
        e = ep[(ep["index"] == idx) & (ep["h"] == 1)].iloc[0]
        assert abs(e["ctrl"] - pc1.loc[idx, "gap_ctrl"]) < 1e-9 and abs(e["raw"] - pc1.loc[idx, "gap_raw"]) < 1e-9
    say("  check: week +1 matches A4 price_control(horizon=1, drop_back_to_back=True) for all four indexes")
    say("  mean ETF return the week after a spike:",
        {i: r2(pc1.loc[i, "spike_mean_ret"]) for i in A.INDEXES},
        "| share of those weeks the ETF fell:", {i: r2(100 * pc1.loc[i, "share_spike_down"]) for i in A.INDEXES})
    data["path"] = [{k: (r2(v) if isinstance(v, float) else v) for k, v in row.items()} for row in ep.to_dict("records")]
    data["week_after_ret"] = {i: r2(pc1.loc[i, "spike_mean_ret"]) for i in A.INDEXES}

    legs = {}
    for m in ["long", "short"]:
        e = event_path(f, measure=m, horizons=[0, 1])
        legs[m] = e[e["index"] == NQ].set_index("h")
    net1 = ep[(ep["index"] == NQ) & (ep["h"] == 1)].iloc[0]
    for kind in ["raw", "ctrl"]:
        lo, sh = legs["long"].loc[1, kind], -legs["short"].loc[1, kind]
        say(f"  Nasdaq-100 week +1 {kind}: net {net1[kind]:+.2f} = closing longs {lo:+.2f} + adding shorts {sh:+.2f}")
        assert abs(lo + sh - net1[kind]) < 1e-3  # legs add up to the net up to the pipeline's rounding
    data["nq_legs_wk1"] = dict(raw_long=r2(legs["long"].loc[1, "raw"]), raw_short=r2(-legs["short"].loc[1, "raw"]),
                               ctrl_long=r2(legs["long"].loc[1, "ctrl"]), ctrl_short=r2(-legs["short"].loc[1, "ctrl"]))

    # ---------------------------------------------------------- 5. how much to trust it
    say("\n5. Week after, price held fixed, across choices (spikes not followed by another spike)")
    specs = [
        ("main", "As in this story: own vol, top 10%, 2006 to 2026", A.flag_spikes(df, 10)),
        ("top5", "Top 5% of vol jumps", A.flag_spikes(df, 5)),
        ("top15", "Top 15%", A.flag_spikes(df, 15)),
        ("top20", "Top 20%", A.flag_spikes(df, 20)),
        ("top25", "Top 25%", A.flag_spikes(df, 25)),
        ("points", "Vol jumps ranked in points, not percent", A.flag_spikes(df, 10, by="points")),
        ("vix", "Same VIX spike weeks for all four indexes", A.flag_spikes(df, 10, by="vix")),
        ("nocrisis", "Without Sep to Nov 2008 and Mar 2020",
         drop_windows(A.flag_spikes(df, 10), [("2008-09-01", "2008-11-30"), ("2020-03-01", "2020-03-31")])),
        ("pre2020", "2006 to 2019 only", A.flag_spikes(df, 10, end="2019-12-31")),
        ("post2020", "2020 to 2026 only", A.flag_spikes(df, 10, start="2020-01-01")),
    ]
    forest = []
    for key, label, g in specs:
        pc = A.price_control(g, AM, horizon=1, drop_back_to_back=True)
        row = dict(key=key, label=label)
        for idx in A.INDEXES:
            row[idx] = dict(gap=r2(pc.loc[idx, "gap_ctrl"]), lo=r2(pc.loc[idx, "lo_ctrl"]),
                            hi=r2(pc.loc[idx, "hi_ctrl"]), n=int(pc.loc[idx, "n_spike"]))
        forest.append(row)
        q = row[NQ]
        others = ", ".join(f"{i} {row[i]['gap']:+.2f}" for i in A.INDEXES if i != NQ)
        say(f"  {label:50s} Nasdaq {q['gap']:+.2f} ({q['lo']:+.2f} to {q['hi']:+.2f}), n={q['n']} | {others}")
    data["forest"] = forest

    say("\n  Controlled week-after difference, Nasdaq-100 minus S&P 500 (bootstrap over report dates):")
    diffs = {}
    for key, label, g in [s_ for s_ in specs if s_[0] in ("main", "vix", "pre2020", "post2020")]:
        cd = A.controlled_difference(g, AM, NQ, "S&P 500")
        diffs[key] = dict(diff=r2(cd["diff"]), lo=r2(cd["lo"]), hi=r2(cd["hi"]), p=round(float(cd["p_boot"]), 3))
        say(f"    {label:50s} {cd['diff']:+.2f} ({cd['lo']:+.2f} to {cd['hi']:+.2f}), p = {cd['p_boot']:.3f}")
    data["nq_minus_spx"] = diffs

    SITE.mkdir(exist_ok=True)
    blob = json.dumps(data, separators=(",", ":"))
    (SITE / "story_data.json").write_text(blob)
    # The same data as a script, so the page also opens straight from a folder (file://), where fetch() is blocked.
    (SITE / "story_data.js").write_text("// Generated by build/story_numbers.py. Do not edit by hand.\nwindow.STORY_DATA = " + blob + ";\n")
    say("\nwrote story_data.json and story_data.js (site folder) and build/story_numbers.txt")
    (HERE / "story_numbers.txt").write_text("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
