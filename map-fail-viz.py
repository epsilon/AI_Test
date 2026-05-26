#!/usr/bin/env python3
"""
map_fail_viz.py  —  DRAM die wafer fail visualizer

Usage:
    python map_fail_viz.py input.csv
    python map_fail_viz.py input.csv --out report.html
    python map_fail_viz.py input.csv --wafer LOT123:5     # single wafer only
    python map_fail_viz.py input.csv --top 24             # cap cols per group
    python map_fail_viz.py input.csv --fail-pattern '^(fail|fmat|mat)'

Expected CSV:
    - xdiepos, ydiepos                (die coords on wafer; case-insensitive)
    - many numeric fail_* columns     (fail counts per die-internal location)
    - optional: LOTID, waferseq       (multi-wafer aggregation / filter)

Output:
    A single self-contained HTML with embedded PNG plots:
      1. Overview wafer map (sum of all fail cols, log scale)
      2. Pareto bar chart (top columns by total fail)
      3. Per-group small-multiple wafer maps  (one figure per prefix group)
"""

import sys, re, argparse, base64
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ---------- helpers ----------

def parse_group(col: str):
    """
    Map a column name to (group_name, index).
      fail_cnt_bank0    -> ('bank', 0)
      fail_cn_bank12    -> ('bank', 12)
      fail_mat_5        -> ('mat', 5)
      fail_fmat_row_3   -> ('fmat_row', 3)
      fail_total        -> ('total', None)
    """
    s = col.lower()
    s = re.sub(r"^fail_?(cn|cnt)?_?", "", s)        # strip fail / fail_cnt / fail_cn
    m = re.match(r"^([a-z][a-z_]*?)_?(\d+)$", s)
    if m:
        g = m.group(1).strip("_") or "misc"
        return g, int(m.group(2))
    return (s or "misc"), None


def fig_to_b64(fig) -> str:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def wafer_map(ax, xs, ys, values, title, vmax_log=None, point_size=18):
    """Scatter wafer map with log1p color scale. Zeros stay at the floor."""
    v = np.log1p(np.asarray(values, dtype=float))
    if vmax_log is None:
        vmax_log = float(v.max()) if v.size and v.max() > 0 else 1.0
    sc = ax.scatter(
        xs, ys, c=v, s=point_size, marker="s", cmap="inferno",
        vmin=0.0, vmax=vmax_log, edgecolors="none",
    )
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)
    ax.set_xticks([]); ax.set_yticks([])
    return sc


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="input CSV path")
    ap.add_argument("--out", default="wafer_report.html", help="output HTML")
    ap.add_argument("--wafer", default=None,
                    help='filter to one wafer: "LOTID:waferseq" (default: aggregate all)')
    ap.add_argument("--top", type=int, default=48,
                    help="max columns per group to plot (default 48)")
    ap.add_argument("--fail-pattern", default=r"^fail",
                    help="regex (case-insensitive) for fail column names. default ^fail")
    ap.add_argument("--point-size", type=int, default=18,
                    help="scatter marker size. increase for sparse wafers, decrease for dense (default 18)")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"ERROR: file not found: {csv_path}")

    print(f"reading {csv_path} ...")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  rows: {len(df):,}   cols: {len(df.columns)}")

    # case-insensitive column lookup
    cmap = {c.lower(): c for c in df.columns}
    def col(name, required=True):
        c = cmap.get(name.lower())
        if c is None and required:
            sys.exit(f"ERROR: required column '{name}' not found. "
                     f"have: {list(df.columns)[:20]} ...")
        return c

    x_col = col("xdiepos")
    y_col = col("ydiepos")
    lot_col = col("LOTID", required=False)
    wseq_col = col("waferseq", required=False)

    # detect fail columns
    pat = re.compile(args.fail_pattern, re.IGNORECASE)
    fail_cols = [c for c in df.columns
                 if pat.search(c) and pd.api.types.is_numeric_dtype(df[c])]
    print(f"  fail columns detected: {len(fail_cols)}")
    if not fail_cols:
        sys.exit("ERROR: no numeric fail columns found. "
                 "try a different --fail-pattern, e.g. '^(fail|fmat|mat|row)'")

    # filter to one wafer, or aggregate across wafers
    if args.wafer and lot_col and wseq_col:
        lot, wseq = args.wafer.split(":", 1)
        mask = (df[lot_col].astype(str) == lot) & (df[wseq_col].astype(str) == wseq)
        df = df.loc[mask].copy()
        print(f"  filtered to wafer {args.wafer}: {len(df):,} rows")
    elif lot_col and wseq_col:
        nw = df.groupby([lot_col, wseq_col]).ngroups
        if nw > 1:
            print(f"  {nw} wafers in file -> aggregating (sum) by die position")
            df = df.groupby([x_col, y_col], as_index=False)[fail_cols].sum()

    if len(df) == 0:
        sys.exit("ERROR: no rows after filtering")

    # group fail columns by prefix
    groups: dict[str, list[tuple[int, str]]] = {}
    for c in fail_cols:
        g, idx = parse_group(c)
        groups.setdefault(g, []).append((idx if idx is not None else 10**9, c))
    for g in groups:
        groups[g].sort()
    summary = ", ".join(f"{g}({len(v)})" for g, v in
                        sorted(groups.items(), key=lambda kv: -len(kv[1])))
    print(f"  groups: {summary}")

    # ---------- build HTML ----------
    html = ["""<!doctype html><html><head><meta charset="utf-8">
<title>Wafer Fail Report</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0c1118;color:#e6edf3;
     margin:0;padding:20px;max-width:1400px;margin-left:auto;margin-right:auto}
h1{font-size:18px;border-bottom:1px solid #2c3645;padding-bottom:10px;
   color:#ffb000;letter-spacing:.05em}
h2{font-size:13px;color:#ffb000;margin-top:32px;letter-spacing:.05em;
   text-transform:uppercase}
.meta{color:#8b949e;font-size:12px;margin-bottom:8px;
      font-family:ui-monospace,SFMono-Regular,monospace;line-height:1.6}
img{display:block;max-width:100%;background:#fff;border-radius:4px;margin:6px 0}
.note{color:#8b949e;font-size:11px;margin:4px 0 12px}
</style></head><body>"""]
    html.append("<h1>WAFER FAIL VISUALIZATION</h1>")
    html.append(
        f"<div class='meta'>file: {csv_path.name}<br>"
        f"rows: {len(df):,} &middot; fail cols: {len(fail_cols)} &middot; "
        f"groups: {len(groups)} &middot; "
        f"x range: {int(df[x_col].min())}..{int(df[x_col].max())} &middot; "
        f"y range: {int(df[y_col].min())}..{int(df[y_col].max())}"
        f"{('<br>filter: wafer ' + args.wafer) if args.wafer else ''}</div>"
    )

    xs, ys = df[x_col].values, df[y_col].values

    # 1. Overview
    print("[1/3] overview ...")
    total = df[fail_cols].sum(axis=1).values
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    sc = wafer_map(ax, xs, ys, total,
                   f"TOTAL FAIL  (sum of {len(fail_cols)} cols)",
                   point_size=args.point_size)
    plt.colorbar(sc, ax=ax, shrink=0.75, label="log1p(fail)")
    html.append("<h2>1. Overview &mdash; total fail per die</h2>")
    html.append("<div class='note'>color = log(1 + total fail). zero stays at the floor.</div>")
    html.append(f"<img src='data:image/png;base64,{fig_to_b64(fig)}'>")

    # 2. Pareto
    print("[2/3] pareto ...")
    totals = df[fail_cols].sum().sort_values(ascending=False)
    top_n = min(40, len(totals))
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.bar(range(top_n), totals.head(top_n).values, color="#ffb000")
    ax.set_xticks(range(top_n))
    ax.set_xticklabels(totals.head(top_n).index, rotation=70, fontsize=7, ha="right")
    ax.set_ylabel("total fail (log)")
    ax.set_yscale("log")
    ax.set_title(f"Top {top_n} of {len(totals)} fail columns")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    html.append("<h2>2. Pareto &mdash; top columns by total fail</h2>")
    html.append(f"<img src='data:image/png;base64,{fig_to_b64(fig)}'>")

    # 3. Per-group small multiples
    print("[3/3] per-group small multiples ...")
    for g, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        cols_in_group = [c for _, c in items]
        n_all = len(cols_in_group)
        plotted = cols_in_group[: args.top]
        n = len(plotted)

        ncols = min(6, max(3, int(np.ceil(np.sqrt(n)))))
        nrows = (n + ncols - 1) // ncols
        print(f"  group '{g}': plotting {n}/{n_all}  ({nrows}x{ncols})")

        # shared log-color scale across the whole group
        gmax = df[plotted].to_numpy().max() if n else 0
        gvmax = float(np.log1p(gmax if gmax > 0 else 1))

        fig, axes = plt.subplots(nrows, ncols,
                                 figsize=(ncols * 2.2, nrows * 2.4))
        axes = np.atleast_2d(axes).reshape(nrows, ncols)
        last_sc = None
        for i, c in enumerate(plotted):
            r, cc = divmod(i, ncols)
            last_sc = wafer_map(axes[r, cc], xs, ys, df[c].values, c,
                                vmax_log=gvmax, point_size=args.point_size)
        for j in range(n, nrows * ncols):
            r, cc = divmod(j, ncols)
            axes[r, cc].axis("off")
        if last_sc is not None:
            fig.colorbar(last_sc, ax=axes.ravel().tolist(),
                         shrink=0.6, label="log1p(fail)")
        fig.suptitle(
            f"group: {g}  -  showing {n} of {n_all}  -  shared color scale",
            fontsize=10, y=0.995,
        )

        html.append(f"<h2>Group '{g}' &mdash; {n_all} columns</h2>")
        if n < n_all:
            html.append(f"<div class='note'>showing first {n}; "
                        f"raise with <code>--top {n_all}</code></div>")
        html.append(f"<img src='data:image/png;base64,{fig_to_b64(fig)}'>")

    html.append("</body></html>")
    Path(args.out).write_text("".join(html), encoding="utf-8")
    print(f"\nDONE  ->  {args.out}")


if __name__ == "__main__":
    main()
