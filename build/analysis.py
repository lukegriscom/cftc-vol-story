"""
analysis.py: every statistic the A4 dashboard shows, in one place.

Author: Luke Griscom (FA 550, A4). Code written with Claude (Opus 5.5); see amr_log.csv.

The dashboard (app.py) only draws what these functions return, and
report_numbers.py prints the same results for the written documents, so a
number in the walkthrough and the number on screen come from one function.

Input: data/processed/positioning_vol_weekly.csv, the output of the A3 pipeline
(revised in A4 to add weekly ETF returns; see pipeline/ and a3_validation.md).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data" / "positioning_vol_weekly.csv"

INDEXES = ["S&P 500", "Nasdaq-100", "Dow", "Russell 2000"]
TRADERS = ["Asset manager", "Leveraged funds", "Dealer", "Other reportables", "Nonreportables"]

# Measures a reader can switch between. Each is a weekly change, in percentage
# points of open interest, for one trader type in one index.
MEASURES = {
    "net": ("net_change_pct_prior_oi", "Net selling or buying",
            "Change in net contracts, percent of last week's open interest"),
    "long": ("d_long_pct", "Longs only",
             "Change in long contracts, percent of last week's open interest"),
    "short": ("d_short_pct", "Shorts only",
              "Change in short contracts, percent of last week's open interest"),
    "stance": ("d_net_pct_oi", "Stance (net % of OI)",
               "Change in net position as a percent of open interest"),
}


# ------------------------------------------------------------------ load
def load(path: Path = DATA) -> pd.DataFrame:
    """Equity-index rows only, with the long and short legs of the activity measure.

    net_change_pct_prior_oi (A3 Decision #34) = (net_t - net_t-1) / OI_t-1 x 100.
    Because net = long - short, it splits exactly into d_long_pct - d_short_pct.
    Those two legs are left missing wherever the A3 pipeline left the activity
    measure missing (venue roll weeks, gaps over 10 days), so the split always
    adds back to the published measure.
    """
    df = pd.read_csv(path, parse_dates=["report_date"])
    df = df[df["index"].isin(INDEXES)].sort_values(["index", "trader_type", "report_date"]).copy()
    g = df.groupby(["index", "trader_type"])
    prior_oi = g["open_interest"].shift(1)
    ok = df["net_change_pct_prior_oi"].notna()
    df["d_long_pct"] = (100 * g["long"].diff() / prior_oi).where(ok)
    df["d_short_pct"] = (100 * g["short"].diff() / prior_oi).where(ok)
    return df.reset_index(drop=True)


def has_prices(df: pd.DataFrame) -> bool:
    return "etf_ret_wk" in df.columns and df["etf_ret_wk"].notna().any()


# ------------------------------------------------------------------ spikes
def flag_spikes(df: pd.DataFrame, top_pct: float, start=None, end=None, by: str = "pct") -> pd.DataFrame:
    """Restrict to the sample window and mark each index's spike weeks.

    A spike week is one of the top `top_pct` percent of weekly percentage
    increases in that index's own implied volatility (VIX, VXN, VXD or RVX)
    within the window. The cutoff is recomputed whenever the window changes, so
    "top 10%" always means the top 10% of the weeks on screen.

    by="pct" ranks percentage changes (the A3 definition, Decision #31);
    by="points" ranks changes in index points, which favors weeks that start
    from a higher level of vol; by="vix" gives every index the same spike
    weeks, the top weekly percentage increases in the VIX (added after the
    adversarial pass, Decision #51, so indexes can be compared on identical dates). Spikes are defined from volatility alone: a
    week with a known vol change is ranked even if its positioning change is
    blank (A4 revision; see a3_validation.md).
    """
    vcol = "d_vol" if by == "points" else "pct_d_vol"
    out = df.copy()
    if by == "vix":
        vix = out.loc[out["index"] == "S&P 500"].drop_duplicates("report_date").set_index("report_date")["pct_d_vol"]
        out["pct_d_vol"] = out["report_date"].map(vix)
    if start is not None:
        out = out[out["report_date"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["report_date"] <= pd.Timestamp(end)]
    wk = out.drop_duplicates(["index", "report_date"])[["index", "report_date", vcol]].dropna()
    cut = wk.groupby("index")[vcol].quantile(1 - top_pct / 100).rename("spike_cutoff")
    out = out.merge(cut, left_on="index", right_index=True, how="left")
    known = out[vcol].notna()
    out["spike"] = known & (out[vcol] >= out["spike_cutoff"])
    out["ordinary"] = known & ~out["spike"]       # weeks with a known vol change that are not spikes
    return out.reset_index(drop=True)


def _gap(a: pd.Series, b: pd.Series) -> tuple:
    """Mean of a minus mean of b, with a 95% Welch interval."""
    a, b = a.dropna(), b.dropna()
    diff = a.mean() - b.mean()
    se = np.sqrt(a.var() / len(a) + b.var() / len(b)) if len(a) > 1 and len(b) > 1 else np.nan
    return diff, diff - 1.96 * se, diff + 1.96 * se, len(a), len(b)


# ------------------------------------------------------------------ Q1
def gap_table(f: pd.DataFrame, measure: str = "net") -> pd.DataFrame:
    """Spike-week gap for every index x trader type: the average change in
    spike weeks minus the average in all other weeks of the window."""
    col = MEASURES[measure][0]
    rows = []
    for (idx, tt), d in f.groupby(["index", "trader_type"]):
        s, n = d["spike"], d["ordinary"]
        gap, lo, hi, ns, nn = _gap(d.loc[s, col], d.loc[n, col])
        rows.append(dict(index=idx, trader_type=tt, gap=gap, lo=lo, hi=hi, n_spike=ns, n_other=nn,
                         spike_mean=d.loc[s, col].mean(), other_mean=d.loc[n, col].mean()))
    return pd.DataFrame(rows)


def long_short_split(f: pd.DataFrame, trader: str) -> pd.DataFrame:
    """For one trader type, the net spike-week gap split into its long leg
    (change in longs) and its short leg (minus the change in shorts)."""
    lg = gap_table(f, "long").query("trader_type == @trader").set_index("index")["gap"]
    sh = gap_table(f, "short").query("trader_type == @trader").set_index("index")["gap"]
    nt = gap_table(f, "net").query("trader_type == @trader").set_index("index")
    out = pd.DataFrame({"from_longs": lg, "from_shorts": -sh, "net": nt["gap"],
                        "net_lo": nt["lo"], "net_hi": nt["hi"], "longs_gap": lg, "shorts_gap": sh})
    return out.reindex([i for i in INDEXES if i in out.index])


# ------------------------------------------------------------------ Q2
def index_differences(f: pd.DataFrame, trader: str, measure: str = "net", horizon: int = 0,
                      drop_back_to_back: bool = False, n_boot: int = 2000, seed: int = 550) -> pd.DataFrame:
    """Pairwise differences in the spike-week gap between indexes, with 95%
    intervals from a bootstrap that resamples whole report dates.

    Most spike weeks are shared (a jump in the VIX usually comes with jumps in
    VXN, VXD and RVX), so two indexes' gaps are not independent and comparing
    their separate intervals is not a test. Resampling whole dates keeps each
    week's four index values together, so the interval on a difference reflects
    how the indexes move jointly.

    horizon=1 compares the week after the spike instead of the spike week
    itself, using the same spike weeks and baseline as event_study(), so the
    two views agree.
    """
    col = MEASURES[measure][0]
    d = f[f["trader_type"] == trader]
    act = d.pivot(index="report_date", columns="index", values=col).reindex(columns=INDEXES)
    spk = d.pivot(index="report_date", columns="index", values="spike").reindex(columns=INDEXES)
    orn = d.pivot(index="report_date", columns="index", values="ordinary").reindex(columns=INDEXES)
    act_s = act.shift(-horizon)                      # the four equity indexes share report dates
    spk_b = spk.fillna(False).astype(bool)
    if drop_back_to_back and horizon >= 1:
        spk_b = spk_b & ~spk_b.shift(-1, fill_value=False)
    S = (spk_b & act_s.notna()).to_numpy(float)
    N = (orn.fillna(False).astype(bool) & act.notna()).to_numpy(float)
    As, An = act_s.fillna(0).to_numpy(float), act.fillna(0).to_numpy(float)

    def gaps(W):
        return (W @ (As * S)) / (W @ S) - (W @ (An * N)) / (W @ N)

    point = gaps(np.ones((1, len(An))))[0]
    rng = np.random.default_rng(seed)
    W = rng.multinomial(len(An), np.full(len(An), 1 / len(An)), size=n_boot).astype(float)
    boot = gaps(W)
    rows = []
    for i in range(len(INDEXES)):
        for j in range(i + 1, len(INDEXES)):
            diff = boot[:, i] - boot[:, j]
            lo, hi = np.nanpercentile(diff, [2.5, 97.5])
            p = 2 * min((diff <= 0).mean(), (diff >= 0).mean())
            rows.append(dict(a=INDEXES[i], b=INDEXES[j], diff=point[i] - point[j], lo=lo, hi=hi,
                             p_boot=min(p, 1.0)))
    out = pd.DataFrame(rows)
    out["pair"] = out["a"] + " minus " + out["b"]
    return out


def shared_spike_weeks(f: pd.DataFrame) -> dict:
    """How many spike weeks each pair of indexes shares, and how many all four share."""
    wk = f[f["spike"]].drop_duplicates(["index", "report_date"])
    sets = {i: set(wk.loc[wk["index"] == i, "report_date"]) for i in INDEXES}
    return {"per_index": {i: len(s) for i, s in sets.items()},
            "all_four": len(set.intersection(*sets.values())) if all(sets.values()) else 0,
            "any": len(set.union(*sets.values()))}


# ------------------------------------------------------------------ Q3
def event_study(f: pd.DataFrame, trader: str, measure: str = "net", horizons=range(-2, 5),
                drop_back_to_back: bool = False, cumulative: bool = False) -> pd.DataFrame:
    """Average change in the weeks around a spike, relative to the average
    non-spike week, for each index.

    Week 0 is the spike week, the one in the report a reader sees that Friday
    (positions as of Tuesday). Week +1 is the change from that Tuesday to the
    next, most of which happens after the report comes out. With
    drop_back_to_back, spikes whose following week is also a spike are left
    out, so week +1 is never itself a spike week.
    """
    col = MEASURES[measure][0]
    rows = []
    for idx, d in f[f["trader_type"] == trader].groupby("index"):
        d = d.sort_values("report_date").reset_index(drop=True)
        is_spk = d["spike"].to_numpy()
        base = d.loc[d["ordinary"], col].dropna()
        pos = np.flatnonzero(is_spk)
        if drop_back_to_back:
            nxt = np.r_[is_spk[1:], False]
            pos = pos[~nxt[pos]]
        vals = d[col].to_numpy()
        hs = list(horizons)
        mat = np.full((len(pos), len(hs)), np.nan)
        for k, h in enumerate(hs):
            ok = (pos + h >= 0) & (pos + h < len(d))
            mat[ok, k] = vals[pos[ok] + h]
        rel = mat - base.mean()
        if cumulative:                      # running total from week 0 on; pre-weeks stay as they are
            z = hs.index(0)
            rel[:, z:] = np.nancumsum(rel[:, z:], axis=1)
        for k, h in enumerate(hs):
            v = rel[:, k][~np.isnan(rel[:, k])]
            se = np.sqrt(v.var(ddof=1) / len(v) + base.var() / len(base)) if len(v) > 1 else np.nan
            rows.append(dict(index=idx, h=h, gap=v.mean(), lo=v.mean() - 1.96 * se,
                             hi=v.mean() + 1.96 * se, n=len(v)))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ Q4
def _ols(y: np.ndarray, X: np.ndarray) -> tuple:
    """OLS coefficients with HC1 (heteroskedasticity-robust) standard errors."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ X.T @ y
    e = y - X @ b
    n, k = X.shape
    meat = (X * e[:, None] ** 2).T @ X
    V = XtX_inv @ meat @ XtX_inv * n / (n - k)
    return b, np.sqrt(np.diag(V))


def price_control(f: pd.DataFrame, trader: str, measure: str = "net", horizon: int = 0,
                  drop_back_to_back: bool = False) -> pd.DataFrame:
    """Spike-week gap with and without the index ETF's weekly return.

    horizon=0 (the spike week):
      raw:        change = a + b*spike
      controlled: change = a + b*spike + c*return + d*return^2
    horizon=1 (the week after; y and return are the following week's):
      raw:        change(t+1) = a + b*spike(t)
      controlled: change(t+1) = a + b*spike(t) + c*return(t+1) + d*return(t+1)^2 + e*return(t)
    The squared term lets large down and up weeks pull differently; the week-1
    model also holds the spike week's own return fixed, so a lagged reaction to
    the first drop cannot pass as persistence. Both models use the same weeks,
    so a shift in b comes from the control, not from a change in sample.
    Intervals use heteroskedasticity-robust (HC1) standard errors.
    """
    if not has_prices(f):
        return pd.DataFrame()
    col = MEASURES[measure][0]
    rows = []
    for idx, d in f[f["trader_type"] == trader].groupby("index"):
        d = d.sort_values("report_date").reset_index(drop=True)
        d["y"] = d[col].shift(-horizon)
        d["r_now"] = d["etf_ret_wk"].shift(-horizon)
        d["r_spk"] = d["etf_ret_wk"]
        keep = d["ordinary"] | d["spike"]
        if drop_back_to_back and horizon >= 1:
            keep &= ~(d["spike"] & d["spike"].shift(-1, fill_value=False))
        d = d[keep].dropna(subset=["y", "r_now", "r_spk"])
        y = d["y"].to_numpy(float)
        s = d["spike"].astype(float).to_numpy()
        r, r0 = d["r_now"].to_numpy(float), d["r_spk"].to_numpy(float)
        one = np.ones_like(y)
        b1, se1 = _ols(y, np.column_stack([one, s]))
        X2 = [one, s, r, r ** 2] + ([r0] if horizon >= 1 else [])
        b2, se2 = _ols(y, np.column_stack(X2))
        rows.append(dict(index=idx, n_weeks=len(y), n_spike=int(s.sum()),
                         gap_raw=b1[1], lo_raw=b1[1] - 1.96 * se1[1], hi_raw=b1[1] + 1.96 * se1[1],
                         gap_ctrl=b2[1], lo_ctrl=b2[1] - 1.96 * se2[1], hi_ctrl=b2[1] + 1.96 * se2[1],
                         ret_coef=b2[2], ret_lo=b2[2] - 1.96 * se2[2], ret_hi=b2[2] + 1.96 * se2[2],
                         spike_mean_ret=d.loc[d["spike"], "r_now"].mean(),
                         other_mean_ret=d.loc[d["ordinary"], "r_now"].mean(),
                         share_spike_down=(d.loc[d["spike"], "r_now"] < 0).mean()))
    out = pd.DataFrame(rows).set_index("index")
    return out.reindex([i for i in INDEXES if i in out.index])


def spike_return_split(f: pd.DataFrame, trader: str, measure: str = "net") -> pd.DataFrame:
    """Spike weeks split by whether the ETF fell or rose that week, each
    compared with ordinary weeks of the same sign. If the selling were only a
    reaction to falling prices, spike weeks with a rising ETF would show none."""
    if not has_prices(f):
        return pd.DataFrame()
    col = MEASURES[measure][0]
    rows = []
    for idx, d in f[f["trader_type"] == trader].groupby("index"):
        d = d[d["spike"] | d["ordinary"]].dropna(subset=[col, "etf_ret_wk"])
        for label, m in [("ETF fell", d["etf_ret_wk"] < 0), ("ETF rose", d["etf_ret_wk"] >= 0)]:
            x = d[m]
            gap, lo, hi, ns, nn = _gap(x.loc[x["spike"], col], x.loc[x["ordinary"], col])
            rows.append(dict(index=idx, week=label, gap=gap, lo=lo, hi=hi, n_spike=ns, n_other=nn))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ latest report
def latest_report(f_full: pd.DataFrame, trader: str = "Asset manager") -> pd.DataFrame:
    """For the most recent report: each index's vol move, whether it clears the
    spike cutoff, and where the trader type's change ranks among all weeks."""
    rows = []
    for idx, d in f_full[f_full["trader_type"] == trader].groupby("index"):
        d = d.sort_values("report_date")
        last = d.iloc[-1]
        hist = d["net_change_pct_prior_oi"].dropna()
        rows.append(dict(index=idx, report_date=last["report_date"], vol_series=last["vol_series"],
                         vol_level=last["vol_level"], pct_d_vol=last["pct_d_vol"],
                         spike_cutoff=last["spike_cutoff"], is_spike=bool(last["spike"]),
                         activity=last["net_change_pct_prior_oi"],
                         activity_pctile=100 * (hist < last["net_change_pct_prior_oi"]).mean(),
                         stance=last["net_pct_oi"],
                         stance_pctile=100 * (d["net_pct_oi"] < last["net_pct_oi"]).mean()))
    out = pd.DataFrame(rows).set_index("index")
    return out.reindex([i for i in INDEXES if i in out.index])


def week_detail(f: pd.DataFrame, date, index: str) -> pd.DataFrame:
    """Every trader type's moves in one index on one report date."""
    d = f[(f["report_date"] == pd.Timestamp(date)) & (f["index"] == index)].set_index("trader_type")
    cols = ["net_change_pct_prior_oi", "d_long_pct", "d_short_pct", "net_pct_oi", "d_net_pct_oi",
            "vol_level", "pct_d_vol", "spike"] + (["etf_ret_wk"] if "etf_ret_wk" in f.columns else [])
    return d.reindex(TRADERS)[cols]


def controlled_difference(f: pd.DataFrame, trader: str, a: str, b: str, measure: str = "net", horizon: int = 1,
                          drop_back_to_back: bool = True, n_boot: int = 1000, seed: int = 550) -> dict:
    """Difference between two indexes' price-controlled gaps (price_control's
    'controlled' model), with a 95% interval from resampling whole report dates,
    so each date's pair of index values stays together."""
    col = MEASURES[measure][0]
    mats = {}
    for idx in (a, b):
        d = f[(f["trader_type"] == trader) & (f["index"] == idx)].sort_values("report_date").reset_index(drop=True)
        d["y"] = d[col].shift(-horizon)
        d["r_now"] = d["etf_ret_wk"].shift(-horizon)
        keep = d["ordinary"] | d["spike"]
        if drop_back_to_back and horizon >= 1:
            keep &= ~(d["spike"] & d["spike"].shift(-1, fill_value=False))
        d = d[keep].dropna(subset=["y", "r_now", "etf_ret_wk"]).set_index("report_date")
        r, r0 = d["r_now"], d["etf_ret_wk"]
        X = np.column_stack([np.ones(len(d)), d["spike"].astype(float), r, r ** 2] + ([r0] if horizon >= 1 else []))
        mats[idx] = (d.index, X, d["y"].to_numpy(float))
    dates = mats[a][0].union(mats[b][0])
    pos = {idx: dates.get_indexer(mats[idx][0]) for idx in (a, b)}

    def coef(idx, w):
        _, X, y = mats[idx]
        ww = w[pos[idx]]
        Xw = X * ww[:, None]
        return np.linalg.lstsq(Xw.T @ X, Xw.T @ y, rcond=None)[0][1]

    point = coef(a, np.ones(len(dates))) - coef(b, np.ones(len(dates)))
    rng = np.random.default_rng(seed)
    W = rng.multinomial(len(dates), np.full(len(dates), 1 / len(dates)), size=n_boot).astype(float)
    boot = np.array([coef(a, w) - coef(b, w) for w in W])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return dict(pair=f"{a} minus {b}", diff=point, lo=lo, hi=hi,
                p_boot=min(1.0, 2 * min((boot <= 0).mean(), (boot >= 0).mean())))
