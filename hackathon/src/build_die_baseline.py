"""
建立「die 層級」異常判斷用的正常基準：每個測項（canonical key）的
median 與 robust scale（MAD*1.4826，MAD 為 0 時退回 std）。

只用標記為 Normal 的 wafer 建立基準。輸出 reports/die_baseline.json，
runtime 端（app/hierarchical.py）用它算每一顆 die 的 robust z-score。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from data_loader import WAFER_STATUS, load_all_wafers

ROOT = Path(__file__).resolve().parent.parent


def main():
    wafers = load_all_wafers()
    cols = wafers[0].test_cols
    keys = [wafers[0].canonical_map[c] for c in cols]

    pool = np.vstack([w.df[cols].to_numpy(float) for w in wafers if WAFER_STATUS[w.wafer_id] == "Normal"])
    med = np.nanmedian(pool, axis=0)
    mad = np.nanmedian(np.abs(pool - med), axis=0) * 1.4826
    std = np.nanstd(pool, axis=0)
    scale = np.where(mad > 1e-9, mad, std)
    scale = np.where(scale > 1e-9, scale, np.nan)

    out = {
        "keys": keys,
        "median": [None if np.isnan(v) else float(v) for v in med],
        "scale": [None if np.isnan(v) else float(v) for v in scale],
        "n_normal_dice": int(pool.shape[0]),
    }
    path = ROOT / "reports" / "die_baseline.json"
    path.write_text(json.dumps(out), encoding="utf-8")
    usable = int(np.isfinite(scale).sum())
    print(f"saved {path}: {len(keys)} columns ({usable} usable), {pool.shape[0]} normal dice")


if __name__ == "__main__":
    main()
