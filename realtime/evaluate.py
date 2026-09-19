"""Strict set comparison against supplied wafer labels (development only)."""
import json
from .data import ROOT, manifest
from .engine import Engine
from .replay import events, apply_event
from .metrics import FORMAL_LABELS


def compare_labels(expected, predicted, supported=True):
    if not supported:
        return {'exact_match':None, 'missed_labels':None, 'extra_labels':None}
    expected = set() if expected == 'Normal' else {expected}
    predicted = set(predicted) - {'Normal'}
    return {'exact_match':predicted == expected, 'missed_labels':sorted(expected-predicted),
            'extra_labels':sorted(predicted-expected)}


def evaluate():
    results = []
    target=ROOT/'reports'; target.mkdir(exist_ok=True)
    for entry in manifest():
        if not entry['split'].startswith('validation'):
            continue
        engine=Engine()
        for event in events(entry):
            apply_event(engine,event)
        snapshot=engine.snapshot()
        formal=[a for a in snapshot['alerts'] if a['formal_label']]
        predicted=[a['formal_label'] for a in formal] or ['Normal']
        supported=entry['label']=='Normal' or entry['label'] in FORMAL_LABELS.values()
        row={'wafer':int(entry['wafer']), 'split':entry['split'], 'label':entry['label'],
             'supported':supported, 'predicted_labels':predicted, 'detected':bool(formal),
             'device_warnings':snapshot['auxiliary_warning_count'],
             'first_batch':min((a['first_batch'] for a in formal),default=None),
             'type_hit':entry['label'] in predicted if entry['label']!='Normal' and supported else None,
             'first_correct_batch':min((a['first_batch'] for a in formal if a['formal_label']==entry['label']),default=None),
             **compare_labels(entry['label'],predicted,supported)}
        results.append(row)
        (target/f'W{int(entry["wafer"]):02d}.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    normals=[r for r in results if r['label']=='Normal']
    anomalies=[r for r in results if r['label']!='Normal' and r['supported']]
    scored=[r for r in results if r['supported']]
    per_class={}
    for label in FORMAL_LABELS.values():
        tp=sum(r['label']==label and label in r['predicted_labels'] for r in scored)
        fp=sum(r['label']!=label and label in r['predicted_labels'] for r in scored)
        fn=sum(r['label']==label and label not in r['predicted_labels'] for r in scored)
        per_class[label]={'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,
                          'recall':tp/(tp+fn) if tp+fn else None}
    summary={'model':engine.info['model'],
             'normal_false_alert_wafers':sum(r['detected'] for r in normals),'normal_wafers':len(normals),
             'in_scope_anomaly_detected':sum(r['detected'] for r in anomalies),'in_scope_anomaly_wafers':len(anomalies),
             'in_scope_type_hits':sum(bool(r['type_hit']) for r in anomalies),
             'exact_match_wafers':sum(r['exact_match'] for r in scored),'scored_wafers':len(scored),
             'missed_label_count':sum(len(r['missed_labels']) for r in scored),
             'extra_label_count':sum(len(r['extra_labels']) for r in scored),
             'per_class':per_class,
             'metric_definition':'Exact set comparison of all formal labels ever emitted; extra labels penalized. Normal means empty anomaly set.',
             'note':'Development data inspected during revision; not independent test. W1 unsupported, W2 excluded. No PID/onset truth. Extra labels are disagreements with supplied labels, not proof the phenomenon never occurred.',
             'results':results}
    (target/'evaluation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# V2 開發驗證（原始標籤對齊）','',
           f'- 完全符合標籤：{summary["exact_match_wafers"]}/{len(scored)} 片。',
           f'- 漏報標籤 {summary["missed_label_count"]} 個；額外標籤 {summary["extra_label_count"]} 個。',
           f'- 正常片正式誤報 {summary["normal_false_alert_wafers"]}/{len(normals)}；異常片包含正確類型 {summary["in_scope_type_hits"]}/{len(anomalies)}。','',
           '| Wafer | 原始標籤 | 模型正式標籤 | 漏報 | 額外標籤 | 完全符合 |',
           '|---|---|---|---|---|---|']
    for r in results:
        lines.append(f'| W{r["wafer"]} | {r["label"]} | {", ".join(r["predicted_labels"])} | {", ".join(r["missed_labels"] or []) or "—"} | {", ".join(r["extra_labels"] or []) or "—"} | {r["exact_match"] if r["supported"] else "不評分"} |')
    lines+=['','正式 label 不含單顆預警。此處比較整片曾輸出的類型，不以事後挑選最佳類型美化結果。',
            'W1 的 Site unbalance 暫不支援；W2 排除。資料已用於開發分析，非獨立測試。',
            '瞬時低良率或異常恢復可能造成額外類型；仍照原始單一標籤計入不一致。沒有 PID 或異常開始點真值。']
    (target/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__': evaluate()
