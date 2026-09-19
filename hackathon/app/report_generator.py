"""
待辦 5：異常報告呈現（評分佔比單項最高 25%）。

設計理念：
  - ACS Gemini 上的 Edge Server / Host Controller VM 多半沒有對外網路，
    所以報告一定要是「自包含」的純 HTML（inline CSS + inline SVG 圖表），
    不能依賴任何 CDN／外部字型／JS 套件，才能保證在 VM 裡直接雙擊打開就能看。
  - 每次 consumeData() 偵測到異常，除了照規定呼叫 ActionManager.set_message()
    送一則文字訊息給機台之外，額外在本機生成一份「可視化異常報告」：
      1. Wafer map：X/Y 座標 + PF/SBin 著色，一眼看出空間分布（site unbalance /
         低良率的空間聚集型態一目了然）。
      2. Site 比較長條圖：4 個 site 在「觸發異常的關鍵測項」上的平均值。
      3. 測試時序趨勢線：關鍵測項數值 vs. 測試順序（PID），可以看出
         mean/stdev trend 是從哪個時間點開始飄的。
      4. 關鍵測項 |z-score| 排行：讓工程師一眼知道「是哪些測項造成的」，
         而不是只給一句「異常」。
  - 這份報告存成靜態檔案（reports/live/wafer_XX_*.html），Host Controller
    上的瀏覽器打開就能看；同時也累積寫一份 reports/live/index.html 當作
    「歷史異常查詢介面」，滿足 md 5.3 節建議的「可查詢的報告介面」。
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_DIR = ROOT / "reports" / "live"

CATEGORY_LABELS = {
    "site_unbalance": "Site 不平衡 (Site Unbalance)",
    "low_yield": "低良率 (Low Yield)",
    "mean_trend_up": "均值上升趨勢 (Mean Trend Up)",
    "mean_trend_down": "均值下降趨勢 (Mean Trend Down)",
    "stdev_trend_up": "變異數上升趨勢 (Stdev Trend Up)",
    "stdev_trend_down": "變異數下降趨勢 (Stdev Trend Down)",
}

SEVERITY_COLOR = {
    "critical": "#dc2626",
    "warning": "#d97706",
    "info": "#2563eb",
}


@dataclass
class CategoryFinding:
    category: str
    score: float  # 觸發欄位比例 or 平均 |z|，越大越嚴重
    severity: str  # "critical" | "warning"
    triggered_columns: list[dict]  # [{key,label,z,direction,current,baseline_mu,baseline_sigma}]


@dataclass
class WaferReportContext:
    wafer_id: int
    lot: str
    tester_id: str
    timestamp: str
    n_devices: int
    yield_rate: float
    devices: list[dict]  # [{x,y,site,pid,pf,sbin,hbin}]
    findings: list[CategoryFinding]
    trend_series: dict  # category -> {"label": str, "pid": [...], "values": [...]}
    diagnosis: object | None = None  # hierarchical.WaferDiagnosis：三層式診斷結果（含 die 定位）


def _esc(s) -> str:
    return html.escape(str(s))


def _svg_bar_chart(items: list[tuple[str, float]], width=640, bar_h=22, color="#2563eb", unit="") -> str:
    if not items:
        return "<p style='color:#6b7280'>（無資料）</p>"
    max_v = max(abs(v) for _, v in items) or 1.0
    n = len(items)
    height = n * (bar_h + 6) + 10
    label_w = 260
    plot_w = width - label_w - 60
    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">']
    for i, (label, v) in enumerate(items):
        y = 10 + i * (bar_h + 6)
        bw = max(2, abs(v) / max_v * plot_w)
        svg.append(f'<text x="0" y="{y + bar_h*0.7:.1f}" font-size="12" fill="#374151">{_esc(label)}</text>')
        svg.append(
            f'<rect x="{label_w}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="3" fill="{color}" opacity="0.85"/>'
        )
        svg.append(
            f'<text x="{label_w + bw + 6:.1f}" y="{y + bar_h*0.7:.1f}" font-size="12" fill="#111827">'
            f"{v:+.3f}{unit}</text>"
        )
    svg.append("</svg>")
    return "".join(svg)


def _svg_die_timeline(records, k_thr: int, width=640, height=190) -> str:
    """每顆 die 的「離群測項數」依測試順序畫成長條圖；橘色 = 被判定為離群 die。"""
    if not records:
        return "<p style='color:#6b7280'>（無資料）</p>"
    pad_l, pad_b, pad_t = 34, 22, 10
    plot_w = width - pad_l - 8
    plot_h = height - pad_b - pad_t
    k_max = max(max(r.k for r in records), k_thr * 1.5)
    bw = plot_w / len(records)
    colors = {"PASS": "#16a34a", "FAIL": "#f87171", "EXCURSION": "#ea580c"}
    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">']
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f9fafb" rx="8"/>')
    for i, r in enumerate(records):
        h = r.k / k_max * plot_h
        x = pad_l + i * bw
        svg.append(
            f'<rect x="{x:.1f}" y="{pad_t + plot_h - h:.1f}" width="{max(bw - 1, 1):.1f}" height="{max(h, 1):.1f}" '
            f'fill="{colors.get(r.status, "#16a34a")}"><title>PID {r.pid} site{r.site} 離群測項 {r.k}</title></rect>'
        )
    ty = pad_t + plot_h - k_thr / k_max * plot_h
    svg.append(f'<line x1="{pad_l}" x2="{width - 8}" y1="{ty:.1f}" y2="{ty:.1f}" stroke="#374151" stroke-dasharray="4 3"/>')
    svg.append(f'<text x="2" y="{ty + 4:.1f}" font-size="10" fill="#374151">{k_thr}</text>')
    for i, r in enumerate(records):
        if r.pid % 10 == 0:
            svg.append(
                f'<text x="{pad_l + i * bw:.1f}" y="{height - 6}" font-size="10" fill="#6b7280">{r.pid}</text>'
            )
    svg.append("</svg>")
    return "".join(svg)


def _svg_wafer_map(
    devices: list[dict], width=360, height=360, highlight_site: int | None = None, status_by_pid: dict | None = None
) -> str:
    if not devices:
        return "<p style='color:#6b7280'>（無資料）</p>"
    xs = [d["x"] for d in devices]
    ys = [d["y"] for d in devices]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = 20
    span_x = max(xmax - xmin, 1)
    span_y = max(ymax - ymin, 1)

    def sx(x):
        return pad + (x - xmin) / span_x * (width - 2 * pad)

    def sy(y):
        return pad + (y - ymin) / span_y * (height - 2 * pad)

    r = max(4, min(10, (width - 2 * pad) / (span_x + 1) / 2.2))
    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">']
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f9fafb" rx="8"/>')
    labels = []
    for d in devices:
        pf_pass = d.get("pf") == 0 or d.get("sbin") == 1
        color = "#16a34a" if pf_pass else "#dc2626"
        stroke = "#111827" if highlight_site is not None and d.get("site") == highlight_site else "none"
        sw = 2 if stroke != "none" else 0
        rr = r
        status = (status_by_pid or {}).get(d.get("pid"))
        if status == "EXCURSION":
            color, stroke, sw, rr = "#ea580c", "#111827", 2.5, r * 1.3
            labels.append(
                f'<text x="{sx(d["x"]):.1f}" y="{sy(d["y"]) + 3:.1f}" font-size="8" font-weight="700" '
                f'text-anchor="middle" fill="white">{d.get("pid")}</text>'
            )
        svg.append(
            f'<circle cx="{sx(d["x"]):.1f}" cy="{sy(d["y"]):.1f}" r="{rr:.1f}" fill="{color}" '
            f'stroke="{stroke}" stroke-width="{sw}" opacity="0.9"><title>'
            f'PID{d.get("pid")} site{d.get("site")} X{d["x"]} Y{d["y"]} SBin{d.get("sbin")} {status or ""}</title></circle>'
        )
    svg.extend(labels)
    svg.append("</svg>")
    return "".join(svg)


def _svg_trend_line(pid: list[float], values: list[float], width=640, height=200, color="#2563eb") -> str:
    if not pid or not values:
        return "<p style='color:#6b7280'>（無資料）</p>"
    pad = 24
    xmin, xmax = min(pid), max(pid)
    ymin, ymax = min(values), max(values)
    span_x = max(xmax - xmin, 1)
    span_y = max(ymax - ymin, 1e-9)

    def sx(x):
        return pad + (x - xmin) / span_x * (width - 2 * pad)

    def sy(y):
        return height - pad - (y - ymin) / span_y * (height - 2 * pad)

    pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(pid, values))
    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">']
    svg.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f9fafb" rx="8"/>')
    svg.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>')
    for x, y in zip(pid, values):
        svg.append(f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.5" fill="{color}"/>')
    svg.append("</svg>")
    return "".join(svg)


def _render_pipeline_section(ctx: WaferReportContext) -> str:
    """三層式診斷區塊：二元判斷 → 原因 → 受影響 die（含 die 清單表格與離群分數時間軸）。"""
    diag = ctx.diagnosis
    if diag is None:
        return ""
    from hierarchical import K_EXC

    if diag.abnormal:
        s1 = '<span class="pill" style="background:#dc2626">ABNORMAL</span>'
        s1_txt = f"{diag.n_excursion} / {diag.n_dice} 顆 die 被判定為離群 die" if diag.n_excursion else "wafer 統計偵測觸發"
        s2 = f'<b>{_esc(diag.cause_label)}</b>'
        s2_txt = "<br>".join(_esc(e) for e in diag.evidence)
        if diag.die_localizable and diag.affected_dice:
            w = f"PID {diag.window[0]}~{diag.window[1]}，" if diag.window else ""
            site = f"site {diag.site}，" if diag.site else ""
            s3 = f"<b>{len(diag.affected_dice)} 顆 die</b>"
            s3_txt = f"{site}{w}明細見下表"
        else:
            s3 = "<b>無法定位到單顆 die</b>"
            s3_txt = "此類異常是整片 wafer 的變異數變化，沒有任何單顆離群 die"
    else:
        s1 = '<span class="pill" style="background:#16a34a">NORMAL</span>'
        s1_txt = f"{diag.n_excursion} / {diag.n_dice} 顆離群 die（未達判定門檻）"
        s2, s2_txt, s3, s3_txt = "—", "不需細分原因", "—", "無"

    steps = f"""
    <section class="card">
      <div class="steps">
        <div class="step"><div class="step-h">第 1 層 · 二元判斷</div>{s1}<div class="step-t">{s1_txt}</div></div>
        <div class="arrow">→</div>
        <div class="step"><div class="step-h">第 2 層 · 原因</div>{s2}<div class="step-t">{s2_txt}</div></div>
        <div class="arrow">→</div>
        <div class="step"><div class="step-h">第 3 層 · die 定位</div>{s3}<div class="step-t">{s3_txt}</div></div>
      </div>
    </section>
    <section class="card">
      <h4 style="margin-top:0">每顆 die 的離群測項數（依測試順序；虛線 = 判定門檻 {K_EXC}）</h4>
      {_svg_die_timeline(diag.dice, K_EXC)}
      <div class="legend">
        <span><i style="background:#16a34a"></i>正常 die</span>
        <span><i style="background:#f87171"></i>一般 bin-fail（背景良率損失）</span>
        <span><i style="background:#ea580c"></i>離群 die（異常）</span>
      </div>
    </section>"""

    if diag.die_localizable and diag.affected_dice:
        rows = []
        for d in diag.affected_dice[:60]:
            cols = ", ".join(f"{c}({z:+.1f})" for c, z in (d.get("top_cols") or [])[:2]) or "—"
            rows.append(
                f"<tr><td>{d['pid']}</td><td>{d['site']}</td><td>{d['x']:.0f}</td><td>{d['y']:.0f}</td>"
                f"<td>{d['sbin']}</td><td>{d['k']}</td><td>{_esc(cols)}</td></tr>"
            )
        more = f"<p>（僅列前 60 顆，共 {len(diag.affected_dice)} 顆）</p>" if len(diag.affected_dice) > 60 else ""
        steps += f"""
    <section class="card">
      <h4 style="margin-top:0">受影響的 die（{len(diag.affected_dice)} 顆）</h4>
      <table>
        <thead><tr><th>PID</th><th>Site</th><th>X</th><th>Y</th><th>SBin</th><th>離群測項數</th><th>主要離群測項 (z)</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>{more}
    </section>"""
    return steps


def render_wafer_report(ctx: WaferReportContext) -> str:
    diag = ctx.diagnosis
    if diag is not None:
        status_ok = not diag.abnormal
        status_text = "NORMAL" if status_ok else diag.cause_label
    else:
        status_ok = len(ctx.findings) == 0
        status_text = "NORMAL" if status_ok else f"{len(ctx.findings)} 項異常"
    status_color = "#16a34a" if status_ok else "#dc2626"
    status_by_pid = {r.pid: r.status for r in diag.dice} if diag is not None else None

    cards = []
    for f in ctx.findings:
        color = SEVERITY_COLOR.get(f.severity, "#2563eb")
        cat_label = CATEGORY_LABELS.get(f.category, f.category)
        bar_items = [(c["label"], c["z"]) for c in f.triggered_columns[:15]]
        col_rows = "".join(
            f"<tr><td>{_esc(c['label'])}</td><td>{c['z']:+.2f}</td>"
            f"<td>{c['current']:.4f}</td><td>{c['baseline_mu']:.4f} ± {c['baseline_sigma']:.4f}</td></tr>"
            for c in f.triggered_columns[:15]
        )
        trend_html = ""
        if f.category in ctx.trend_series:
            ts = ctx.trend_series[f.category]
            trend_html = f"""
            <h4>關鍵測項數值 vs. 測試順序 — {_esc(ts['label'])}</h4>
            {_svg_trend_line(ts['pid'], ts['values'], color=color)}
            """
        cards.append(f"""
        <section class="card" style="border-left:6px solid {color}">
          <h3><span class="dot" style="background:{color}"></span>{_esc(cat_label)}
              <span class="badge" style="background:{color}">{f.severity.upper()}</span></h3>
          <p>觸發分數 (score) = {f.score:.3f} ／ 觸發測項數 = {len(f.triggered_columns)}</p>
          <h4>最相關測項 |z-score| 排行</h4>
          {_svg_bar_chart(bar_items, color=color)}
          {trend_html}
          <details>
            <summary>詳細數據（前 15 項）</summary>
            <table>
              <thead><tr><th>測項</th><th>z</th><th>目前值</th><th>正常基準 (mu ± sigma)</th></tr></thead>
              <tbody>{col_rows}</tbody>
            </table>
          </details>
        </section>
        """)

    site_ids = sorted({d.get("site") for d in ctx.devices if d.get("site") is not None})
    wafer_maps = "".join(
        f'<div class="map-cell"><div class="map-title">全部 site</div>{_svg_wafer_map(ctx.devices)}</div>'
    )

    html_doc = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>Wafer {ctx.wafer_id} 異常報告</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Noto Sans TC", sans-serif; background:#f3f4f6; color:#111827; margin:0; padding:24px; }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .meta {{ color:#6b7280; font-size:13px; margin-bottom:20px; }}
  .status {{ display:inline-block; padding:4px 12px; border-radius:999px; color:white; font-weight:600; background:{status_color}; }}
  .card {{ background:white; border-radius:10px; padding:16px 20px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .card h3 {{ margin:0 0 6px; display:flex; align-items:center; gap:8px; font-size:16px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  .badge {{ margin-left:auto; color:white; font-size:11px; padding:2px 8px; border-radius:6px; }}
  table {{ border-collapse: collapse; width:100%; font-size:12px; margin-top:8px; }}
  th, td {{ border-bottom:1px solid #e5e7eb; padding:4px 8px; text-align:left; }}
  th {{ color:#6b7280; font-weight:600; }}
  .grid {{ display:flex; gap:16px; flex-wrap:wrap; }}
  .map-cell {{ background:white; border-radius:10px; padding:12px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .map-title {{ font-size:12px; color:#6b7280; margin-bottom:6px; }}
  .legend span {{ display:inline-flex; align-items:center; gap:4px; margin-right:14px; font-size:12px; color:#374151; }}
  .legend i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
  summary {{ cursor:pointer; color:#2563eb; font-size:13px; margin-top:8px; }}
  .steps {{ display:flex; align-items:stretch; gap:10px; flex-wrap:wrap; }}
  .step {{ flex:1; min-width:200px; background:#f9fafb; border-radius:8px; padding:10px 12px; }}
  .step-h {{ font-size:11px; color:#6b7280; margin-bottom:4px; }}
  .step-t {{ font-size:12px; color:#374151; margin-top:6px; line-height:1.5; }}
  .arrow {{ align-self:center; color:#9ca3af; font-size:20px; }}
  .pill {{ color:white; font-size:12px; font-weight:700; padding:2px 10px; border-radius:999px; }}
</style></head>
<body>
  <h1>Wafer {ctx.wafer_id} 即時異常報告 <span class="status">{status_text}</span></h1>
  <div class="meta">
    Lot {_esc(ctx.lot)} ・ Tester {_esc(ctx.tester_id)} ・ 產出時間 {_esc(ctx.timestamp)} ・
    已測 {ctx.n_devices} 顆 ・ 良率 {ctx.yield_rate*100:.1f}%
  </div>

  {_render_pipeline_section(ctx)}

  <div class="grid">
    <div class="map-cell">
      <div class="map-title">Wafer Map（綠=Pass，紅=一般 Fail，橘色+編號=離群 die）</div>
      {_svg_wafer_map(ctx.devices, status_by_pid=status_by_pid)}
      <div class="legend">
        <span><i style="background:#16a34a"></i>Pass</span>
        <span><i style="background:#dc2626"></i>Fail</span>
        <span><i style="background:#ea580c"></i>離群 die</span>
      </div>
    </div>
  </div>

  {"".join(cards) if cards else ('' if diag is not None else '<div class="card">目前未偵測到已知類型的 wafer 級異常。</div>')}
</body></html>"""
    return html_doc


def save_report(ctx: WaferReportContext) -> Path:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = ctx.timestamp.replace(":", "").replace(" ", "_").replace("-", "")
    out_path = LIVE_DIR / f"wafer_{ctx.wafer_id:02d}_{ts}.html"
    out_path.write_text(render_wafer_report(ctx), encoding="utf-8")
    _update_index()
    return out_path


def _update_index() -> None:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    reports = sorted(LIVE_DIR.glob("wafer_*.html"), reverse=True)
    rows = "".join(
        f'<tr><td><a href="{p.name}">{_esc(p.name)}</a></td>'
        f'<td>{datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M:%S}</td></tr>'
        for p in reports
    )
    index_html = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>異常報告查詢</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Noto Sans TC",sans-serif;background:#f3f4f6;padding:24px}}
 table{{border-collapse:collapse;background:white;border-radius:8px;overflow:hidden;width:100%;max-width:640px}}
 th,td{{padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:13px}}
 th{{background:#111827;color:white}}
 a{{color:#2563eb;text-decoration:none}}
</style></head><body>
<h2>異常報告查詢介面（{len(reports)} 筆）</h2>
<table><thead><tr><th>報告</th><th>產出時間</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    (LIVE_DIR / "index.html").write_text(index_html, encoding="utf-8")


def build_message_text(ctx: WaferReportContext, report_path: Path) -> str:
    """符合 md 5.3 節「規定要做的最低要求」：ActionManager.set_message() 的純文字內容。"""
    diag = ctx.diagnosis
    if diag is not None:
        if not diag.abnormal:
            return f"[Wafer {ctx.wafer_id}] 正常。良率 {ctx.yield_rate*100:.1f}%。詳細報告：{report_path}"
        lines = [
            f"[Wafer {ctx.wafer_id}] ABNORMAL → 原因：{diag.cause_label}",
            *(f"  - {e}" for e in diag.evidence),
        ]
        if diag.die_localizable and diag.affected_dice:
            shown = diag.affected_dice[:12]
            dies = "; ".join(f"PID{d['pid']}(site{d['site']},X{d['x']:.0f},Y{d['y']:.0f})" for d in shown)
            more = f" …共 {len(diag.affected_dice)} 顆" if len(diag.affected_dice) > len(shown) else ""
            lines.append(f"  問題 die：{dies}{more}")
        else:
            lines.append("  問題 die：此類異常無法定位到單顆 die（整片 wafer 的變異數變化）")
        lines.append(f"完整視覺化報告：{report_path}")
        return "\n".join(lines)
    if not ctx.findings:
        return f"[Wafer {ctx.wafer_id}] 正常。良率 {ctx.yield_rate*100:.1f}%。詳細報告：{report_path}"
    parts = [f"[Wafer {ctx.wafer_id}] 偵測到 {len(ctx.findings)} 項異常："]
    for f in ctx.findings:
        cat_label = CATEGORY_LABELS.get(f.category, f.category)
        top = f.triggered_columns[0] if f.triggered_columns else None
        top_txt = f"（主因測項：{top['label']}, z={top['z']:+.2f}）" if top else ""
        parts.append(f"  - {cat_label} [{f.severity}] score={f.score:.3f} {top_txt}")
    parts.append(f"完整視覺化報告：{report_path}")
    return "\n".join(parts)
