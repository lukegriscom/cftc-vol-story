/* story.js: draws the five charts of "Mostly Old News" and drives the scroll steps.
   Author: Luke Griscom (FA 550, A5). Code written with Claude (Opus 5.5); see amr_log.csv.
   Data: window.STORY_DATA, written by build/story_numbers.py. No number is typed in by hand here
   except axis ranges. ?static=1 lays every step out with its own chart (used for the PDF backup). */
(function () {
  "use strict";
  const D = window.STORY_DATA;
  const IDX = ["S&P 500", "Nasdaq-100", "Dow", "Russell 2000"];
  const NQ = "Nasdaq-100";
  const STATIC = new URLSearchParams(location.search).has("static");
  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DUR = REDUCED ? 0 : 750;
  const MINUS = "−";
  const num = (v, d = 2) => (v < 0 ? MINUS : "") + Math.abs(v).toFixed(d);
  const sgn = (v, d = 2) => (v < 0 ? MINUS : v > 0 ? "+" : "") + Math.abs(v).toFixed(d);
  const ivl = (lo, hi) => `${sgn(lo)} to ${sgn(hi)}`;
  const mean = a => a.reduce((s, v) => s + v, 0) / a.length;

  if (STATIC) document.body.classList.add("static");

  // ------------------------------------------------------------ tooltip (textContent only)
  const tip = document.getElementById("tip");
  function showTip(evt, head, rows) {
    tip.replaceChildren();
    const h = document.createElement("div");
    h.className = "t-head";
    h.textContent = head;
    tip.appendChild(h);
    rows.forEach(r => {
      const row = document.createElement("div");
      row.className = "t-row";
      if (r.key) {
        const k = document.createElement("span");
        k.className = "t-key";
        k.style.background = r.key;
        row.appendChild(k);
      }
      const v = document.createElement("span");
      v.className = "t-v";
      v.textContent = r.v;
      const l = document.createElement("span");
      l.className = "t-l";
      l.textContent = r.l;
      row.append(v, l);
      tip.appendChild(row);
    });
    tip.hidden = false;
    let x, y;
    if (evt && typeof evt.clientX === "number" && evt.type !== "focus") {
      x = evt.clientX; y = evt.clientY;
    } else {
      const b = evt.target.getBoundingClientRect();
      x = b.left + b.width / 2; y = b.top;
    }
    const w = tip.offsetWidth, hh = tip.offsetHeight;
    let left = x + 14, top = y - hh - 12;
    if (left + w > innerWidth - 8) left = x - w - 14;
    if (top < 8) top = y + 18;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = top + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  // ------------------------------------------------------------ helpers
  function frame(el, m, minH) {
    const W = Math.max(300, el.clientWidth);
    // Fill the space the layout gives the chart; minH is only a fallback when the box has no height yet.
    const H = el.clientHeight > 0 ? Math.max(170, el.clientHeight) : minH;
    const svg = d3.select(el).append("svg").attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    return { svg, W, H };
  }
  // Horizontal bar from the zero line x0 to xv: 4px rounded at the data end, square at zero.
  function hbar(xv, x0, h) {
    const left = Math.min(xv, x0), right = Math.max(xv, x0), w = right - left;
    const r = Math.min(4, w / 2, h / 2);
    if (xv <= x0) return `M${right},0H${left + r}A${r},${r} 0 0 0 ${left},${r}V${h - r}A${r},${r} 0 0 0 ${left + r},${h}H${right}Z`;
    return `M${left},0H${right - r}A${r},${r} 0 0 1 ${right},${r}V${h - r}A${r},${r} 0 0 1 ${right - r},${h}H${left}Z`;
  }
  // Wrap an SVG <text> into tspans no wider than `width`.
  function wrap(text, str, width, lh = 15) {
    const x = text.attr("x");
    text.text(null);
    let line = [], tspan = text.append("tspan").attr("x", x).attr("dy", 0);
    str.split(/\s+/).forEach(word => {
      line.push(word);
      tspan.text(line.join(" "));
      if (tspan.node().getComputedTextLength() > width && line.length > 1) {
        line.pop();
        tspan.text(line.join(" "));
        line = [word];
        tspan = text.append("tspan").attr("x", x).attr("dy", lh).text(word);
      }
    });
  }
  function hoverable(sel, fn) {
    sel.attr("tabindex", 0)
      .on("pointermove", (e, d) => fn(e, d))
      .on("focus", (e, d) => fn(e, d))
      .on("pointerleave blur", hideTip);
  }
  const C = name => `var(--${name})`;

  // ------------------------------------------------------------ 1 and 3: spike-week bars
  function makeBars(el) {
    const narrow = el.clientWidth < 520;
    const m = { t: 50, r: narrow ? 74 : 104, b: 48, l: narrow ? 86 : 100 };
    const { svg, W, H } = frame(el, m, 280);
    svg.attr("role", "img").attr("aria-label", "Spike-week change in asset managers' net position by index");
    const rows = IDX.map(i => D.spike_week.find(r => r.index === i));
    const x = d3.scaleLinear().domain([-3.5, 0.9]).range([m.l, W - m.r]);
    const y = d3.scaleBand().domain(IDX).range([m.t, H - m.b]).paddingInner(0.5).paddingOuter(0.25);
    const bh = Math.min(24, y.bandwidth());
    const x0 = x(0);
    svg.append("g").attr("class", "grid").selectAll("line").data([-3, -2, -1]).join("line")
      .attr("x1", d => x(d)).attr("x2", d => x(d)).attr("y1", m.t - 8).attr("y2", H - m.b);
    svg.append("line").attr("class", "baseline").attr("x1", x0).attr("x2", x0).attr("y1", m.t - 8).attr("y2", H - m.b);
    svg.append("g").selectAll("text").data([-3, -2, -1, 0]).join("text").attr("class", "tick-label")
      .attr("x", d => x(d)).attr("y", H - m.b + 17).attr("text-anchor", "middle").text(d => (d === 0 ? "0" : num(d, 0)));
    svg.append("text").attr("class", "axis-title").attr("x", m.l).attr("y", H - m.b + 36)
      .text("← More selling than in an ordinary week");

    const g = svg.append("g").selectAll("g").data(rows).join("g")
      .attr("transform", d => `translate(0,${y(d.index) + (y.bandwidth() - bh) / 2})`);
    g.append("text").attr("class", d => "row-label" + (d.index === NQ ? " em" : ""))
      .attr("x", m.l - 12).attr("y", bh / 2).attr("dy", "0.35em").attr("text-anchor", "end").text(d => d.index);
    g.append("path").attr("class", "bar-raw").attr("d", d => hbar(x(d.raw), x0, bh));
    const ctrl = g.append("path").attr("class", "bar-ctrl").attr("d", () => hbar(x0, x0, bh));
    const ci = g.append("line").attr("class", "ci").attr("y1", bh / 2).attr("y2", bh / 2)
      .attr("x1", d => x(d.raw_lo)).attr("x2", d => x(d.raw_hi));
    const v1 = g.append("text").attr("class", "val").attr("x", W - m.r + 12).attr("y", bh / 2 - 1).attr("dy", "0.35em");
    const v2 = g.append("text").attr("class", "val-sub").attr("x", W - m.r + 12).attr("y", bh / 2 + 15).attr("dy", "0.35em");
    const ann = svg.append("text").attr("class", "note-strong").attr("x", m.l).attr("y", 16).style("opacity", 0);

    let cur = "raw";
    hoverable(g.append("rect").attr("class", "hit").attr("x", 0).attr("width", W)
      .attr("y", -(y.step() - bh) / 2).attr("height", y.step()), (e, d) => {
      const rowsT = [{ v: num(d.raw), l: `as reported (${ivl(d.raw_lo, d.raw_hi)})`, key: C("blue-light") }];
      if (cur === "ctrl" || cur === "ctrl-spx") {
        rowsT.push({ v: num(d.ctrl), l: `price held fixed (${ivl(d.ctrl_lo, d.ctrl_hi)})`, key: C("blue") });
        rowsT.push({ v: `${Math.round(d.explained_pct)}%`, l: "of the gap removed by the price" });
      }
      rowsT.push({ v: `${Math.round(d.share_down)}%`, l: `of ${d.n_spike} spike weeks were down weeks` });
      showTip(e, d.index, rowsT);
    });

    function update(state, dur) {
      cur = state;
      const showC = state === "ctrl" || state === "ctrl-spx";
      const t = svg.transition().duration(dur).ease(d3.easeCubicInOut);
      ctrl.transition(t).attr("d", d => hbar(showC ? x(d.ctrl) : x0, x0, bh));
      ci.transition(t).attr("x1", d => x(showC ? d.ctrl_lo : d.raw_lo)).attr("x2", d => x(showC ? d.ctrl_hi : d.raw_hi));
      v1.text(d => num(showC ? d.ctrl : d.raw));
      v2.text(d => (showC ? `from ${num(d.raw)}` : ""));
      g.transition(t).style("opacity", d => (state === "ctrl-spx" && d.index !== "S&P 500" ? 0.28 : 1));
      const note = state === "raw-note" ? "If this is forced, vol-driven selling, more should follow next week."
        : state === "ctrl-spx" ? "S&P 500: the one interval still clear of zero once price is held fixed." : "";
      wrap(ann, note, W - m.l - 10);
      ann.transition(t).style("opacity", note ? 1 : 0);
    }
    function legend(state) {
      if (state === "ctrl" || state === "ctrl-spx") {
        return [{ kind: "bar", color: C("blue-light"), label: "As reported" },
                { kind: "bar", color: C("blue"), label: "Price held fixed" },
                { kind: "line", color: C("ink-2"), label: "95% interval" }];
      }
      return [{ kind: "line", color: C("ink-2"), label: "95% interval" }];
    }
    return { update, legend };
  }

  // ------------------------------------------------------------ 2: Nasdaq-100 scatter
  function makeScatter(el) {
    const m = { t: 14, r: 14, b: 50, l: 50 };
    const { svg, W, H } = frame(el, m, 300);
    svg.attr("role", "img").attr("aria-label", "Nasdaq-100 asset managers' weekly change against QQQ's weekly return");
    const S = D.scatter;
    const x = d3.scaleLinear().domain([-17, 11]).range([m.l, W - m.r]);
    const y = d3.scaleLinear().domain([-24, 18]).range([H - m.b, m.t]);
    const gr = svg.append("g").attr("class", "grid");
    gr.selectAll("line.v").data([-15, -10, -5, 5, 10]).join("line").attr("class", "v")
      .attr("x1", d => x(d)).attr("x2", d => x(d)).attr("y1", m.t).attr("y2", H - m.b);
    gr.selectAll("line.h").data([-20, -10, 10]).join("line").attr("class", "h")
      .attr("x1", m.l).attr("x2", W - m.r).attr("y1", d => y(d)).attr("y2", d => y(d));
    svg.append("line").attr("class", "baseline").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(0)).attr("y2", y(0));
    svg.append("line").attr("class", "baseline").attr("x1", x(0)).attr("x2", x(0)).attr("y1", m.t).attr("y2", H - m.b);
    svg.append("g").selectAll("text").data([-15, -10, -5, 0, 5, 10]).join("text").attr("class", "tick-label")
      .attr("x", d => x(d)).attr("y", H - m.b + 17).attr("text-anchor", "middle").text(d => sgn(d, 0).replace("+0", "0"));
    svg.append("g").selectAll("text").data([-20, -10, 0, 10]).join("text").attr("class", "tick-label")
      .attr("x", m.l - 8).attr("y", d => y(d)).attr("dy", "0.35em").attr("text-anchor", "end").text(d => sgn(d, 0).replace("+0", "0"));
    svg.append("text").attr("class", "axis-title").attr("x", W - m.r).attr("y", H - m.b + 36).attr("text-anchor", "end")
      .text("QQQ return that week (%) →");
    svg.append("text").attr("class", "axis-title").attr("transform", `translate(${m.l - 36},${m.t}) rotate(-90)`)
      .attr("text-anchor", "end").text("Change in net position (pts)");

    const fit = svg.append("path").attr("class", "fit").style("opacity", 0)
      .attr("d", d3.line().x(d => x(d.r)).y(d => y(d.y)).curve(d3.curveBasis)(S.curve.filter(d => d.r >= -17 && d.r <= 11)));
    const ord = S.points.filter(p => !p.s), spk = S.points.filter(p => p.s);
    svg.append("g").selectAll("circle").data(ord).join("circle").attr("class", "dot-ord")
      .attr("cx", d => x(d.r)).attr("cy", d => y(d.y)).attr("r", 3);
    const spkG = svg.append("g");
    const spkDots = spkG.selectAll("circle").data(spk).join("circle").attr("class", "dot-spk")
      .attr("cx", d => x(d.r)).attr("cy", d => y(d.y)).attr("r", 4).style("fill", C("dot"));
    const ring = svg.append("circle").attr("r", 7).attr("fill", "none").attr("stroke", C("ink")).attr("stroke-width", 1.5).style("display", "none");

    const all = S.points;
    const delaunay = d3.Delaunay.from(all, d => x(d.r), d => y(d.y));
    let cur = "all";
    svg.append("rect").attr("class", "hit").attr("x", m.l).attr("y", m.t).attr("width", W - m.l - m.r).attr("height", H - m.t - m.b)
      .on("pointermove", e => {
        const [px, py] = d3.pointer(e);
        const i = delaunay.find(px, py), d = all[i];
        if (Math.hypot(x(d.r) - px, y(d.y) - py) > 24) { ring.style("display", "none"); hideTip(); return; }
        ring.style("display", null).attr("cx", x(d.r)).attr("cy", y(d.y));
        const kind = d.s ? "Spike week" : "Ordinary week";
        showTip(e, `Week to ${d.d}`, [
          { v: sgn(d.y), l: "change in net position (pts)" },
          { v: sgn(d.r) + "%", l: "QQQ return that week" },
          { v: "", l: cur === "all" ? "" : kind }].filter(r => r.v || r.l));
      })
      .on("pointerleave", () => { ring.style("display", "none"); hideTip(); });

    function update(state, dur) {
      cur = state;
      const t = svg.transition().duration(dur);
      const lit = state !== "all";
      // A CSS variable cannot be interpolated by d3, so the fill change is animated by a CSS transition instead.
      spkDots.classed("lit", lit).style("fill", lit ? C("blue") : C("dot"));
      fit.transition(t).style("opacity", state === "fit" ? 1 : 0);
    }
    function legend(state) {
      if (state === "all") return [{ kind: "dot", color: C("dot"), label: `One week (${S.n.toLocaleString()} weeks)` }];
      if (state === "spikes") return [{ kind: "dot", color: C("dot"), label: "Ordinary week" },
        { kind: "dot", color: C("blue"), label: `Spike week (${S.n_spike})` }];
      const mt = D.matched["0.75"];
      return [{ kind: "line", color: C("ink-2"), label: "An ordinary week, given QQQ's move" },
        { kind: "dot", color: C("blue"), label: `Spike weeks: ${num(Math.abs(S.coef.spike))} below the curve on average` },
        { kind: "text", label: `Matched to ordinary weeks with similar returns: ${sgn(mt.diff)} (${ivl(mt.lo, mt.hi)})` }];
    }
    return { update, legend };
  }

  // ------------------------------------------------------------ 4: weeks around a spike
  function makePath(el) {
    const m = { t: 22, r: 20, b: 50, l: 46 };
    const { svg, W, H } = frame(el, m, 300);
    svg.attr("role", "img").attr("aria-label", "Asset managers' change in the weeks around a spike, by index");
    const HS = [-2, -1, 0, 1, 2, 3, 4];
    const series = IDX.map(i => ({ index: i, pts: HS.map(h => D.path.find(p => p.index === i && p.h === h)) }));
    const nq = series.find(s => s.index === NQ), others = series.filter(s => s.index !== NQ);
    const x = d3.scaleLinear().domain([-2.4, 4.4]).range([m.l, W - m.r]);
    const y = d3.scaleLinear().domain([-3.8, 1.6]).range([H - m.b, m.t]);
    svg.append("rect").attr("class", "zone").attr("x", x(0.5)).attr("width", x(4.4) - x(0.5)).attr("y", m.t).attr("height", H - m.b - m.t);
    svg.append("text").attr("class", "zone-label").attr("x", x(0.5) + 8).attr("y", m.t + 15).text("After the report's positions");
    svg.append("g").attr("class", "grid").selectAll("line").data([-3, -2, -1, 1]).join("line")
      .attr("x1", m.l).attr("x2", W - m.r).attr("y1", d => y(d)).attr("y2", d => y(d));
    svg.append("line").attr("class", "baseline").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(0)).attr("y2", y(0));
    svg.append("g").selectAll("text").data([-3, -2, -1, 0, 1]).join("text").attr("class", "tick-label")
      .attr("x", m.l - 8).attr("y", d => y(d)).attr("dy", "0.35em").attr("text-anchor", "end").text(d => sgn(d, 0).replace("+0", "0"));
    svg.append("g").selectAll("text").data(HS).join("text").attr("class", "tick-label")
      .attr("x", d => x(d)).attr("y", H - m.b + 17).attr("text-anchor", "middle")
      .text(d => (d === 0 ? "Spike" : sgn(d, 0)));
    svg.append("text").attr("class", "axis-title").attr("x", W - m.r).attr("y", H - m.b + 36).attr("text-anchor", "end")
      .text("Weeks from the spike week");
    svg.append("text").attr("class", "axis-title").attr("transform", `translate(${m.l - 34},${m.t}) rotate(-90)`)
      .attr("text-anchor", "end").text("← Selling   vs ordinary week (pts)");

    let key = "raw";
    const line = k => d3.line().x(d => x(d.h)).y(d => y(d[k]));
    const area = k => d3.area().x(d => x(d.h)).y0(d => y(d[k + "_lo"])).y1(d => y(d[k + "_hi"]));
    const band = svg.append("path").attr("class", "band").attr("d", area("raw")(nq.pts));
    const oLines = svg.append("g").selectAll("path").data(others).join("path").attr("class", "line-other").attr("d", s => line("raw")(s.pts));
    const nLine = svg.append("path").attr("class", "line-nq").attr("d", line("raw")(nq.pts));
    const nDots = svg.append("g").selectAll("circle").data(nq.pts).join("circle").attr("class", "dot-nq")
      .attr("cx", d => x(d.h)).attr("cy", d => y(d.raw)).attr("r", 4.5);
    const w1 = nq.pts.find(p => p.h === 1);
    const lab = svg.append("text").attr("class", "val").attr("x", x(1) + 10).attr("dy", "0.35em");
    const ann = svg.append("text").attr("class", "note").attr("x", x(1) - 4).attr("y", y(-2.75)).style("opacity", 0);
    const hl = svg.append("line").attr("class", "hover-line").attr("y1", m.t).attr("y2", H - m.b).style("display", "none");

    svg.append("rect").attr("class", "hit").attr("x", m.l).attr("y", m.t).attr("width", W - m.l - m.r).attr("height", H - m.t - m.b)
      .on("pointermove", e => {
        const h = Math.max(-2, Math.min(4, Math.round(x.invert(d3.pointer(e)[0]))));
        hl.style("display", null).attr("x1", x(h)).attr("x2", x(h));
        const rows = series.map(s => {
          const p = s.pts.find(q => q.h === h);
          return { v: sgn(p[key]), l: s.index + (s.index === NQ ? ` (${ivl(p[key + "_lo"], p[key + "_hi"])})` : ""), key: s.index === NQ ? C("blue") : C("gray-line") };
        });
        const head = (h === 0 ? "Spike week" : `Week ${sgn(h, 0)}`) + (key === "raw" ? ", as reported" : ", returns held fixed");
        showTip(e, head, rows);
      })
      .on("pointerleave", () => { hl.style("display", "none"); hideTip(); });

    function update(state, dur) {
      key = state === "raw" ? "raw" : "ctrl";
      const t = svg.transition().duration(dur).ease(d3.easeCubicInOut);
      band.transition(t).attr("d", area(key)(nq.pts));
      oLines.transition(t).attr("d", s => line(key)(s.pts));
      nLine.transition(t).attr("d", line(key)(nq.pts));
      nDots.transition(t).attr("cy", d => y(d[key]));
      lab.text(num(w1[key])).transition(t).attr("y", y(w1[key]) + 2);
      const legs = D.nq_legs_wk1;
      const note = `QQQ rose ${D.week_after_ret[NQ].toFixed(2)}% on average this week. Of the ${num(Math.abs(w1.ctrl))}: ${num(Math.abs(legs.ctrl_long))} from closing longs, ${num(Math.abs(legs.ctrl_short))} from adding shorts.`;
      wrap(ann, note, Math.min(260, W - m.r - x(1) - 4));
      ann.transition(t).style("opacity", state === "ctrl-legs" ? 1 : 0);
    }
    function legend(state) {
      return [{ kind: "line", color: C("blue"), label: "Nasdaq-100" },
        { kind: "wash", label: "95% interval" },
        { kind: "line", color: C("gray-line"), label: "S&P 500, Dow, Russell 2000" },
        { kind: "text", label: state === "raw" ? "Showing: as reported" : "Showing: both weeks' returns held fixed" }];
    }
    return { update, legend };
  }

  // ------------------------------------------------------------ 5: robustness rows
  function makeForest(el) {
    const narrow = el.clientWidth < 520;
    const m = { t: 10, r: narrow ? 46 : 60, b: 44, l: narrow ? 150 : 210 };
    const { svg, W, H } = frame(el, m, 320);
    svg.attr("role", "img").attr("aria-label", "Nasdaq-100 week-after change under alternative choices");
    const SHORT = { main: "As in this story", top5: "Top 5% of vol jumps", top15: "Top 15%", top20: "Top 20%", top25: "Top 25%",
      points: "Ranked by vol points", vix: "Same VIX weeks for all", nocrisis: narrow ? "No 2008, Mar 2020" : "Without 2008 crisis, Mar 2020",
      pre2020: "2006 to 2019", post2020: "2020 to 2026" };
    const GROUP = { main: 0, top5: 1, top15: 1, top20: 1, top25: 1, points: 1, vix: 1, nocrisis: 2, pre2020: 3, post2020: 3 };
    const ERA = new Set(["pre2020", "post2020"]);
    const LABELED = new Set(["main", "pre2020", "post2020"]);
    const rows = D.forest;
    const gaps = rows.filter((r, i) => i > 0 && GROUP[r.key] !== GROUP[rows[i - 1].key]).length;
    const step = Math.min(34, (H - m.t - m.b) / (rows.length + gaps * 0.6));
    const ys = [];
    let yy = m.t + step / 2;
    rows.forEach((r, i) => { if (i > 0 && GROUP[r.key] !== GROUP[rows[i - 1].key]) yy += step * 0.6; ys.push(yy); yy += step; });
    const bottom = yy - step / 2 + 6;
    const x = d3.scaleLinear().domain([-2.9, 1.6]).range([m.l, W - m.r]);
    svg.append("g").attr("class", "grid").selectAll("line").data([-2, -1, 1]).join("line")
      .attr("x1", d => x(d)).attr("x2", d => x(d)).attr("y1", m.t).attr("y2", bottom);
    svg.append("line").attr("class", "baseline").attr("x1", x(0)).attr("x2", x(0)).attr("y1", m.t).attr("y2", bottom);
    svg.append("g").selectAll("text").data([-2, -1, 0, 1]).join("text").attr("class", "tick-label")
      .attr("x", d => x(d)).attr("y", bottom + 16).attr("text-anchor", "middle").text(d => sgn(d, 0).replace("+0", "0"));
    svg.append("text").attr("class", "axis-title").attr("x", m.l).attr("y", bottom + 34).text("← More selling the week after");
    rows.forEach((r, i) => {
      if (i > 0 && GROUP[r.key] !== GROUP[rows[i - 1].key]) {
        const yl = ys[i] - step / 2 - step * 0.3;
        svg.append("line").attr("class", "baseline").attr("x1", 8).attr("x2", W - 8).attr("y1", yl).attr("y2", yl).style("opacity", 0.6);
      }
    });
    const g = svg.append("g").selectAll("g").data(rows).join("g").attr("transform", (d, i) => `translate(0,${ys[i]})`);
    g.append("text").attr("class", d => "row-label" + (d.key === "main" ? " em" : "")).attr("x", m.l - 14).attr("dy", "0.35em")
      .attr("text-anchor", "end").text(d => SHORT[d.key]);
    IDX.filter(i => i !== NQ).forEach(idx => {
      g.append("line").attr("class", "tick-other").attr("x1", d => x(d[idx].gap)).attr("x2", d => x(d[idx].gap)).attr("y1", -5).attr("y2", 5);
    });
    g.append("line").attr("class", "ci-nq").attr("x1", d => x(d[NQ].lo)).attr("x2", d => x(d[NQ].hi));
    g.append("circle").attr("class", "dot-nq").attr("cx", d => x(d[NQ].gap)).attr("r", 5.5);
    g.filter(d => LABELED.has(d.key)).append("text").attr("class", "val").attr("x", d => x(d[NQ].hi) + 8).attr("dy", "0.35em")
      .text(d => num(d[NQ].gap));
    hoverable(g.append("rect").attr("class", "hit").attr("x", 0).attr("width", W).attr("y", -step / 2).attr("height", step), (e, d) => {
      showTip(e, `${SHORT[d.key]}: week after, returns held fixed`, [
        { v: sgn(d[NQ].gap), l: `Nasdaq-100 (${ivl(d[NQ].lo, d[NQ].hi)}), ${d[NQ].n} spikes`, key: C("blue") },
        ...IDX.filter(i => i !== NQ).map(i => ({ v: sgn(d[i].gap), l: i, key: C("gray-line") }))]);
    });
    function update(state, dur) {
      const t = svg.transition().duration(dur);
      g.transition(t).style("opacity", d => (state === "era" ? (ERA.has(d.key) ? 1 : 0.28) : (ERA.has(d.key) ? 0.28 : 1)));
    }
    function legend() {
      return [{ kind: "dotline", label: "Nasdaq-100 with 95% interval" },
        { kind: "tick", label: "S&P 500, Dow, Russell 2000 (estimate)" }];
    }
    return { update, legend };
  }

  // ------------------------------------------------------------ legend (HTML, textContent only)
  function renderLegend(el, items) {
    el.replaceChildren();
    items.forEach(it => {
      const s = document.createElement("span");
      s.className = "item";
      if (it.kind !== "text") {
        const k = document.createElement("span");
        k.className = { bar: "key-bar", line: "key-line", dot: "key-dot", wash: "key-wash", tick: "key-tick", dotline: "key-dotline" }[it.kind];
        if (it.color) k.style.background = it.color;
        s.appendChild(k);
      }
      const l = document.createElement("span");
      l.textContent = it.label;
      if (it.kind === "text") l.style.color = C("muted");
      s.appendChild(l);
      el.appendChild(s);
    });
  }

  // ------------------------------------------------------------ scroll steps
  const MAKERS = { bars: makeBars, scatter: makeScatter, path: makePath, forest: makeForest };
  const mounted = [];

  function mountScrolly(section) {
    const kind = section.dataset.chart;
    const fig = section.querySelector(".graphic .frame");
    const chartEl = fig.querySelector(".chart"), legendEl = fig.querySelector(".legend");
    const steps = [...section.querySelectorAll(".step")];
    let state = steps[0].dataset.state, chart;
    const build = () => {
      chartEl.replaceChildren();
      chart = MAKERS[kind](chartEl);
      chart.update(state, 0);
      renderLegend(legendEl, chart.legend(state));
    };
    build();
    steps[0].classList.add("is-active");
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        if (!e.isIntersecting) return;
        steps.forEach(s => s.classList.toggle("is-active", s === e.target));
        const next = e.target.dataset.state;
        if (next !== state) {
          state = next;
          hideTip();
          chart.update(state, DUR);
          renderLegend(legendEl, chart.legend(state));
        }
      });
    }, { rootMargin: "-50% 0px -49% 0px" });
    steps.forEach(s => io.observe(s));
    mounted.push(build);
  }

  function mountStatic(section) {
    const kind = section.dataset.chart;
    const fig = section.querySelector(".graphic .frame");
    section.querySelectorAll(".step").forEach(step => {
      const wrapEl = document.createElement("div");
      wrapEl.className = "static-fig" + (kind === "scatter" || kind === "forest" ? " tall" : "");
      const clone = fig.cloneNode(true);
      clone.querySelector(".chart").replaceChildren();
      clone.querySelector(".legend").replaceChildren();
      wrapEl.appendChild(clone);
      step.appendChild(wrapEl);
      const chart = MAKERS[kind](clone.querySelector(".chart"));
      chart.update(step.dataset.state, 0);
      renderLegend(clone.querySelector(".legend"), chart.legend(step.dataset.state));
    });
  }

  // ------------------------------------------------------------ tables (the charts' table view)
  function table(title, head, body, note) {
    const det = document.createElement("details");
    if (STATIC) det.open = true;
    const sum = document.createElement("summary");
    sum.textContent = title;
    det.appendChild(sum);
    const wrapEl = document.createElement("div");
    wrapEl.className = "table-scroll";
    const t = document.createElement("table");
    const tr = document.createElement("tr");
    head.forEach(h => { const th = document.createElement("th"); th.textContent = h; tr.appendChild(th); });
    const th = document.createElement("thead");
    th.appendChild(tr);
    t.appendChild(th);
    const tb = document.createElement("tbody");
    body.forEach(r => {
      const row = document.createElement("tr");
      r.forEach(c => { const td = document.createElement("td"); td.textContent = c; row.appendChild(td); });
      tb.appendChild(row);
    });
    t.appendChild(tb);
    wrapEl.appendChild(t);
    det.appendChild(wrapEl);
    if (note) { const p = document.createElement("p"); p.textContent = note; p.style.margin = "8px 0 0"; p.style.color = "var(--ink-2)"; det.appendChild(p); }
    return det;
  }
  function buildTables() {
    const host = document.getElementById("tables");
    const sw = IDX.map(i => D.spike_week.find(r => r.index === i));
    host.appendChild(table("Sections 1 and 3: spike week, as reported and with price held fixed",
      ["Index", "As reported (95% interval)", "Price held fixed (95% interval)", "Gap removed", "Spike weeks down"],
      sw.map(d => [d.index, `${sgn(d.raw)} (${ivl(d.raw_lo, d.raw_hi)})`, `${sgn(d.ctrl)} (${ivl(d.ctrl_lo, d.ctrl_hi)})`,
        Math.round(d.explained_pct) + "%", `${Math.round(d.share_down)}% of ${d.n_spike}`]),
      "Points of open interest, spike weeks minus an ordinary week."));
    const S = D.scatter, spk = S.points.filter(p => p.s);
    host.appendChild(table("Section 2: Nasdaq-100 weekly scatter, summary",
      ["Group", "Weeks", "Average change (pts)", "Average QQQ return"],
      [["All weeks", String(S.points.length), sgn(mean(S.points.map(p => p.y))), sgn(mean(S.points.map(p => p.r))) + "%"],
        ["Spike weeks", String(spk.length), sgn(mean(spk.map(p => p.y))), sgn(mean(spk.map(p => p.r))) + "%"],
        ["Spike weeks with QQQ down", String(spk.filter(p => p.r < 0).length), sgn(mean(spk.filter(p => p.r < 0).map(p => p.y))), sgn(mean(spk.filter(p => p.r < 0).map(p => p.r))) + "%"]],
      `Fitted curve: change = ${sgn(S.coef.a)} ${sgn(S.coef.spike)} x spike + ${S.coef.ret.toFixed(3)} x return ${sgn(S.coef.ret2, 4)} x return squared. Every week is in story_data.json.`));
    host.appendChild(table("Section 2: spike weeks matched to ordinary weeks with similar QQQ returns",
      ["Match window (QQQ return within)", "Spike weeks matched", "Spike minus matched ordinary weeks (95% interval)"],
      Object.entries(D.matched).map(([w, v]) => [`${w} points`, `${v.n} of ${S.n_spike}`, `${sgn(v.diff)} (${ivl(v.lo, v.hi)})`]),
      "Each spike week is compared with the average of the ordinary weeks whose QQQ return was within the window; spike weeks with fewer than three such weeks (the most extreme crashes) are left out."));
    const body = [];
    IDX.forEach(i => [-2, -1, 0, 1, 2, 3, 4].forEach(h => {
      const p = D.path.find(q => q.index === i && q.h === h);
      body.push([`${i}, ${h === 0 ? "spike week" : "week " + sgn(h, 0)}`, `${sgn(p.raw)} (${ivl(p.raw_lo, p.raw_hi)})`, `${sgn(p.ctrl)} (${ivl(p.ctrl_lo, p.ctrl_hi)})`]);
    }));
    const nSp = IDX.map(i => `${i} ${D.path.find(q => q.index === i && q.h === 0).n_spike}`).join(", ");
    host.appendChild(table("Section 4: weeks around a spike",
      ["Index and week", "As reported (95% interval)", "Returns held fixed (95% interval)"], body,
      `Spikes not followed by another spike (${nSp}). Away from the spike week, the held-fixed model also holds the spike week's own return fixed.`));
    host.appendChild(table("Section 5: week after, returns held fixed, under other choices",
      ["Choice", "Nasdaq-100 (95% interval)", "Spikes", "S&P 500", "Dow", "Russell 2000"],
      D.forest.map(r => [r.label, `${sgn(r[NQ].gap)} (${ivl(r[NQ].lo, r[NQ].hi)})`, String(r[NQ].n), sgn(r["S&P 500"].gap), sgn(r.Dow.gap), sgn(r["Russell 2000"].gap)])));
    const lbl = { main: "As in this story", vix: "Same VIX spike weeks for all four", pre2020: "2006 to 2019 only", post2020: "2020 to 2026 only" };
    host.appendChild(table("Section 5: Nasdaq-100 minus S&P 500, week after, returns held fixed",
      ["Choice", "Difference (95% interval)", "Bootstrap p"],
      Object.entries(D.nq_minus_spx).map(([k, v]) => [lbl[k], `${sgn(v.diff)} (${ivl(v.lo, v.hi)})`, v.p.toFixed(3)]),
      "Interval from resampling whole report dates, so each date's pair of index values stays together."));
  }

  // ------------------------------------------------------------ go
  document.querySelectorAll(".scrolly").forEach(STATIC ? mountStatic : mountScrolly);
  buildTables();
  if (!STATIC) {
    let lastW = innerWidth, timer;
    addEventListener("resize", () => {
      if (Math.abs(innerWidth - lastW) < 40) return;   // ignore mobile toolbar resizes
      lastW = innerWidth;
      clearTimeout(timer);
      timer = setTimeout(() => mounted.forEach(b => b()), 200);
    });
  }
  window.__storyReady = true;
})();
