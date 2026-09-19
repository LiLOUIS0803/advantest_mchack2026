"""Same-stream development comparison; never loads hackathon's fitted artifacts."""
import hashlib
import json

import numpy as np

from hackathon.app.hierarchical import DieBaseline, HierarchicalAnalyzer
from .data import ROOT, manifest, read_wafer
from .engine import Engine
from .evaluate import compare_labels
from .metrics import FORMAL_LABELS
from .replay import events, apply_event


def fit_baseline():
    entries = [e for e in manifest() if e['split'] == 'train_normal']
    columns, arrays, hashes = None, [], {}
    for entry in entries:
        names, _, x = read_wafer(entry)
        if columns is not None and names != columns:
            raise ValueError('Inconsistent columns')
        columns = names
        arrays.append(x)
        hashes[entry['csv']] = hashlib.sha256((ROOT / entry['csv']).read_bytes()).hexdigest()
    pool = np.concatenate(arrays)
    center = np.median(pool, axis=0)
    mad = np.median(abs(pool-center), axis=0)*1.4826
    scale = np.where(mad > 1e-9, mad, pool.std(axis=0))
    scale = np.where(scale > 1e-9, scale, np.nan)
    return DieBaseline.from_arrays(columns, center, scale), hashes


def die_diagnosis(analyzer):
    """Original die thresholds/direction rule, with Site branch explicitly removed."""
    from hackathon.app.hierarchical import MIN_EXC_DICE, DIR_COHERENT
    exc = [r for r in analyzer.records if r.status == 'EXCURSION']
    if len(exc) < MIN_EXC_DICE:
        return None
    wide = analyzer._wafer_wide_mask()
    signs = np.concatenate([s[~wide] for r, s in zip(analyzer.records, analyzer._sign)
                            if r.status == 'EXCURSION'])
    positive = int((signs > 0).sum()) / max(1, int((signs != 0).sum()))
    kind = ('mean_trend_up' if positive >= DIR_COHERENT else
            'mean_trend_down' if positive <= 1-DIR_COHERENT else 'stdev_trend_up')
    return {'kind': kind, 'affected_pids': [r.pid for r in exc],
            'positive_fraction': positive,
            'evidence': [{'pid': r.pid, 'outlier_tests': r.k, 'top_tests': r.top_cols} for r in exc]}


def record_first(log, label, event_index, engine, **evidence):
    if label not in log:
        log[label] = {'event_index': event_index, 'batch': engine.batch,
                      'stage': engine.stage, 'completed': engine.completed,
                      'potential_unstarted_devices': max(0, engine.total_devices-engine.completed-len(engine.current)),
                      'estimated_saved_seconds': None, **evidence}


def replay(entry, baseline):
    engine, analyzer = Engine(), HierarchicalAnalyzer(baseline)
    logs = {name: {} for name in ('current', 'die_only', 'hybrid')}
    for index, event in enumerate(events(entry)):
        # Only completed devices enter the die detector. Never read future CSV rows here.
        if event['type'] == 'test_end':
            for outcome in event['outcomes']:
                values = engine.current[outcome['key']]
                analyzer.add_die({'pid': outcome['pid'], 'site': None},
                                 {c: float(v) for c, v in zip(engine.columns, values) if np.isfinite(v)})
        apply_event(engine, event)
        for alert in engine.alerts:
            label = alert['formal_label']
            if label:
                record_first(logs['current'], label, index, engine)
                if alert['type'] in ('low_yield', 'stdev_trend_down'):
                    record_first(logs['hybrid'], label, index, engine)
        if event['type'] == 'test_end':
            diagnosis = die_diagnosis(analyzer)
            if diagnosis:
                label = FORMAL_LABELS[diagnosis['kind']]
                for name in ('die_only', 'hybrid'):
                    record_first(logs[name], label, index, engine, **diagnosis)
    return logs


def evaluate():
    baseline, hashes = fit_baseline()
    engine = Engine()
    if engine.info['source_sha256'] != hashes or engine.columns != baseline.keys:
        raise ValueError('Current model sources differ; run python -m realtime.train first')
    result = {'training_wafers': engine.info['training_wafers'], 'source_sha256': hashes,
              'excluded_wafers': [2], 'site_classification': False,
              'protocol': 'All labels ever emitted; same four-device, seven-stage replay; first alerts retained even if later withdrawn.',
              'variants': {'current': 'Existing v2 unchanged',
                           'die_only': 'Hackathon die component only; no supervised statistics fallback',
                           'hybrid': 'Die component for Mean Up/Down and Stdev Up; current Low yield and Stdev Down'},
              'limitations': ['Development data, not an independent test.',
                             'Original hackathon thresholds retained; no validation threshold search.',
                             'No labeled anomaly feature selection or original fitted artifacts used.',
                             'Die-only does not support Low yield or Stdev Down; shown as an ablation, not the full hackathon model.',
                             'No PID/onset truth. Savings are unstarted-device upper bounds, not measured time.',
                             'CSV event order is simulated, not verified against machine logs.'],
              'results': [], 'summary': {}}
    for entry in manifest():
        if not entry['split'].startswith('validation') or entry['label'] == 'Site unbalance':
            continue
        logs = replay(entry, baseline)
        row = {'wafer': int(entry['wafer']), 'label': entry['label'], 'models': {}}
        for name, alerts in logs.items():
            predicted = list(alerts) or ['Normal']
            row['models'][name] = {'predicted_labels': predicted, 'alerts': alerts,
                                   'first_correct': alerts.get(entry['label']),
                                   **compare_labels(entry['label'], predicted)}
        result['results'].append(row)
    for name in result['variants']:
        rows = result['results']
        result['summary'][name] = {
            'exact_match': sum(r['models'][name]['exact_match'] for r in rows),
            'scored_wafers': len(rows),
            'normal_false_alerts': sum(bool(r['models'][name]['alerts']) for r in rows if r['label']=='Normal'),
            'correct_anomaly_types': sum(r['models'][name]['first_correct'] is not None for r in rows if r['label']!='Normal'),
            'extra_labels': sum(len(r['models'][name]['extra_labels']) for r in rows),
            'missed_labels': sum(len(r['models'][name]['missed_labels']) for r in rows)}
    target = ROOT / 'reports' / 'model_comparison'
    target.mkdir(parents=True, exist_ok=True)
    (target/'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 同切分、同串流模型比較', '',
             '排除 W2、W1 Site 類別；12 片正常訓練，5 片正常及 6 片異常驗證。所有曾發出的正式標籤均計分。', '',
             'hybrid 用 die 分支替代三種變化分類，保留原本 Low yield 與 Stdev Down；不是把兩邊告警全部聯集。',
             'die_only 只是元件消融，不包含 hackathon 需異常範例選特徵的統計備援，因此不代表完整原模型。', '',
             '| 版本 | 完全符合 / 11 | 正常誤報 / 5 | 正確異常類型 / 6 | 額外標籤 | 漏報標籤 |',
             '|---|---|---|---|---|---|']
    for name, s in result['summary'].items():
        lines.append(f'| {name} | {s["exact_match"]} | {s["normal_false_alerts"]} | {s["correct_anomaly_types"]} | {s["extra_labels"]} | {s["missed_labels"]} |')
    lines += ['', '| Wafer / 原始標籤 | 版本 | 全程正式預測 | 首次正確告警 | 當時尚未開始顆數上限 |', '|---|---|---|---|---|']
    for row in result['results']:
        for name, m in row['models'].items():
            first = m['first_correct']
            moment = f'批次 {first["batch"]} / {first["stage"]}' if first else '—'
            saving = first['potential_unstarted_devices'] if first else '—'
            lines.append(f'| W{row["wafer"]} / {row["label"]} | {name} | {", ".join(m["predicted_labels"])} | {moment} | {saving} |')
    lines += ['', '仍為開發驗證，不能當成未知 wafer 的準確率。原始門檻沒有依這次結果調整。',
              '同一批四顆 TestEnd 作為共同觀測點，不利用模擬批次內人為排序取得時間優勢。',
              '未提供真實時間、異常開始點及 PID 真值；尚未開始顆數不是實際節省，也不能證明定位準確。',
              '首次告警證據及所有額外類型保留於 comparison.json；現有報表模型未切換。']
    (target/'README.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    evaluate()
