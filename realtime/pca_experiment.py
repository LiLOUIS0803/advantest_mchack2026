"""Stage-local normal-only PCA with disjoint wafer-level threshold calibration."""
import hashlib
import json
from collections import deque

import numpy as np
from sklearn.decomposition import PCA
from threadpoolctl import threadpool_limits

from .data import ROOT, manifest, read_wafer, stage_indices
from .replay import events

DEST = ROOT / 'reports' / 'pca_experiment'


def features(x, model):
    z = (x-model['center']) / model['scale']
    if 'encoder' in model:
        hidden = np.tanh(z @ model['encoder'] + model['encoder_bias'])
        residual = z-(hidden @ model['decoder'] + model['decoder_bias'])
        latent = hidden-model['latent_center']
    else:
        latent = z @ model['components'].T
        residual = z-latent @ model['components']
    q = np.mean(residual**2, axis=1)
    t = np.mean(latent**2/model['variance'], axis=1)
    return q, t, latent, residual


def group_features(latent, variance, temporal=False):
    block = latent[-16:] / np.sqrt(variance)
    if temporal:
        before, after = block[:8], block[8:]
        return np.array([np.mean((after.mean(axis=0)-before.mean(axis=0))**2),
                         (np.mean(after.var(axis=0, ddof=1))+1e-6) /
                         (np.mean(before.var(axis=0, ddof=1))+1e-6)])
    return np.array([np.mean(block.mean(axis=0)**2), np.mean(block.var(axis=0, ddof=1))])


def fit():
    entries = sorted([e for e in manifest() if e['split']=='train_normal'], key=lambda e: int(e['wafer']))
    if len(entries) != 12:
        raise ValueError('This protocol requires the existing 12 normal training wafers')
    names, arrays, hashes = None, [], {}
    for e in entries:
        cols, _, x = read_wafer(e)
        if names is not None and names != cols:
            raise ValueError('Column mismatch')
        names = cols
        arrays.append(x)
        hashes[e['csv']] = hashlib.sha256((ROOT/e['csv']).read_bytes()).hexdigest()
    models = []
    for indices in stage_indices(names):
        train = np.concatenate([x[:, indices] for x in arrays[:8]])
        center, scale = train.mean(axis=0), np.maximum(train.std(axis=0, ddof=1), 1e-6)
        z = (train-center)/scale
        # Fixed capacity, no anomaly-label tuning; at least one residual dimension.
        rank = min(16, z.shape[1]-1, z.shape[0]-1)
        pca = PCA(n_components=rank, svd_solver='randomized', random_state=2026).fit(z)
        model = dict(indices=indices, center=center, scale=scale, components=pca.components_,
                     variance=np.maximum(pca.explained_variance_, 1e-6))
        cal_scores, cal_groups = [], []
        for x in arrays[8:]:
            q, t, latent, _ = features(x[:, indices], model)
            cal_scores.extend(np.column_stack([q, t]).tolist())
            cal_groups.extend(group_features(latent[end-16:end], model['variance'])
                              for end in range(16, len(x)+1, 4))
        cal_scores, cal_groups = np.array(cal_scores), np.array(cal_groups)
        model['die_limits'] = np.maximum(cal_scores.max(axis=0)*1.2, 1e-9)
        model['group_high'] = np.maximum(cal_groups.max(axis=0)*1.2, 1e-9)
        model['group_low'] = max(float(cal_groups[:, 1].min()*.8), 1e-9)
        models.append(model)
    info = {'method': 'stage_local_PCA_v1', 'fit_wafers': [int(e['wafer']) for e in entries[:8]],
            'calibration_wafers': [int(e['wafer']) for e in entries[8:]], 'excluded': [2],
            'source_sha256': hashes, 'columns': names,
            'thresholds': 'Max normal calibration score x1.2; low variance min x0.8. No validation tuning.',
            'trigger': 'Same stage/mechanism exceeds limit in two consecutive 16-die windows; stride 4. Die route requires >=3 high-score dies in window.',
            'type_output': 'Unknown: no supervised anomaly type training',
            'attribution': 'Suspicious evidence only; no die-level ground truth or calibrated confidence probability'}
    target = ROOT/'artifacts'/'pca_experiment'
    target.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target/'model.npz', **{f's{s}_{k}':v for s,m in enumerate(models) for k,v in m.items()})
    (target/'info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    return names, models, info


class PCAStream:
    def __init__(self, columns, models):
        self.columns, self.models = columns, models
        self.reset()

    def reset(self):
        self.devices, self.alerts, self.frames = {}, {}, []
        self.seen = set()
        self.history = [deque(maxlen=16) for _ in self.models]
        self.streak = [np.zeros(5 if 'residual_low' in m else 4, dtype=int) for m in self.models]
        self.batch = self.completed = 0
        self.total = None

    def consume(self, event):
        kind = event['type']
        if kind == 'wafer_start':
            if int(event['wafer']) == 2:
                raise ValueError('W2 excluded')
            self.reset()
            self.total = event['total_devices']
        elif kind == 'test_start':
            self.batch = event['batch']
            for d in event['devices']:
                self.devices[d['key']] = {'key': d['key'], 'pid': None, 'x': None, 'y': None,
                                         'score': 0., 'evidence': [], 'mechanism': None}
        elif kind == 'measurement':
            ids = np.array(event['indices'])
            stage = next((s for s,m in enumerate(self.models) if np.array_equal(ids, m['indices'])), None)
            if stage is None:
                raise ValueError('Experiment requires a complete simulated stage event')
            m = self.models[stage]
            values = np.asarray(event['values'])
            keys = event['keys']
            if (len(keys)!=4 or len(set(keys))!=4 or values.shape!=(4,len(ids))
                    or not np.isfinite(values).all()
                    or any(k not in self.devices or (k,stage) in self.seen for k in keys)):
                raise ValueError('Expected four known devices with unique finite stage results')
            self.seen.update((k,stage) for k in keys)
            q, t, latent, residual = features(values, m)
            scores = np.maximum(q/m['die_limits'][0], t/m['die_limits'][1])
            for i, key in enumerate(event['keys']):
                d = self.devices[key]
                if scores[i] >= d['score']:
                    # Residual attribution only explains Q, not latent T2 or causality.
                    top = np.argsort(residual[i]**2)[-5:][::-1]
                    d.update(score=float(scores[i]), mechanism='Q residual' if q[i]/m['die_limits'][0]>=t[i]/m['die_limits'][1] else 'latent T2',
                             evidence=[{'test': self.columns[int(ids[j])], 'value': float(event['values'][i][j]),
                                        'standardized_residual_squared': float(residual[i,j]**2)} for j in top])
                self.history[stage].append((key, float(scores[i]), latent[i], residual[i]))
            hist = self.history[stage]
            if len(hist)==16:
                g = group_features(np.array([r[2] for r in hist]), m['variance'], m.get('temporal', False))
                ratios = np.array([sum(r[1]>1 for r in hist)/3, g[0]/m['group_high'][0],
                                   g[1]/m['group_high'][1], m['group_low']/max(g[1], 1e-12)])
                mechanisms = ['multiple_suspicious_dies','latent_mean_shift','latent_spread_high','latent_spread_low']
                residual_evidence = None
                if 'residual_low' in m:
                    block = np.array([r[3] for r in hist])
                    before_var, after_var = block[:8].var(axis=0,ddof=1), block[8:].var(axis=0,ddof=1)
                    residual_ratio = (after_var.mean()+1e-6)/(before_var.mean()+1e-6)
                    ratios = np.append(ratios, m['residual_low']/max(residual_ratio,1e-12))
                    mechanisms.append('residual_spread_low')
                    top = np.argsort(before_var-after_var)[-5:][::-1]
                    residual_evidence = {'ratio':float(residual_ratio),'threshold':float(m['residual_low']),
                        'tests':[{'test':self.columns[int(m['indices'][j])],
                                  'before_residual_variance':float(before_var[j]),
                                  'after_residual_variance':float(after_var[j])} for j in top]}
                hit = ratios > 1
                hit[0] = ratios[0] >= 1
                self.streak[stage] = np.where(hit, self.streak[stage]+1, 0)
                for j, mechanism in enumerate(mechanisms):
                    alert_key = f'{stage}:{mechanism}'
                    if self.streak[stage][j] >= 2 and alert_key not in self.alerts:
                        self.alerts[alert_key] = {'batch': self.batch, 'stage': event['stage'], 'mechanism': mechanism,
                            'anomaly_type': '未確定', 'completed': self.completed,
                            'potential_unstarted_devices': max(0, self.total-len(self.devices)),
                            'estimated_saved_seconds': None, 'window_keys': [r[0] for r in hist],
                            'suspect_keys': [r[0] for r in hist if r[1]>1] if j==0 else [],
                            'ratio': float(ratios[j])}
                        if mechanism == 'residual_spread_low':
                            self.alerts[alert_key]['residual_evidence'] = residual_evidence
        elif kind == 'test_end':
            for row in event['outcomes']:
                self.devices[row['key']].update(pid=row['pid'], x=row.get('x'), y=row.get('y'))
                self.completed += 1
        if kind in ('measurement', 'test_end'):
            # Frozen snapshots: PID and coordinates are unavailable until TestEnd.
            self.frames.append(json.loads(json.dumps({'batch': self.batch, 'stage': event.get('stage', 'TestEnd'),
                'completed': self.completed, 'abnormal': bool(self.alerts),
                'first_alert': next(iter(self.alerts.values()), None),
                'ranking': sorted(self.devices.values(), key=lambda d: -d['score'])[:8],
                'map': [{k:d[k] for k in ('key','pid','x','y','score')} for d in self.devices.values() if d['x'] is not None]})))


def run():
    with threadpool_limits(limits=2):
        columns, models, info = fit()
        DEST.mkdir(parents=True, exist_ok=True)
        results = []
        for entry in manifest():
            if not entry['split'].startswith('validation') or entry['label']=='Site unbalance':
                continue
            stream = PCAStream(columns, models)
            for event in events(entry):
                stream.consume(event)
            row = {'wafer': int(entry['wafer']), 'label': entry['label'], 'predicted_abnormal': bool(stream.alerts),
                   'alerts': list(stream.alerts.values()), 'frames': stream.frames}
            results.append(row)
            print(f'W{entry["wafer"]}: abnormal={bool(stream.alerts)}, alerts={len(stream.alerts)}', flush=True)
    normal = [r for r in results if r['label']=='Normal']
    abnormal = [r for r in results if r['label']!='Normal']
    summary = {'normal_false_alerts': sum(r['predicted_abnormal'] for r in normal), 'normal_count':len(normal),
               'anomaly_detected': sum(r['predicted_abnormal'] for r in abnormal), 'anomaly_count':len(abnormal)}
    payload = {'info': info, 'summary': summary, 'results': results}
    (DEST/'results.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    template = (ROOT/'realtime/web/pca_experiment.html').read_text(encoding='utf-8')
    (DEST/'report.html').write_text(template.replace('__PAYLOAD__', json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('</', '<\\/')), encoding='utf-8')
    lines = ['# PCA 階段模型開發實驗', '', f'正常誤報 {summary["normal_false_alerts"]}/5；異常偵測 {summary["anomaly_detected"]}/6。',
             '', '8 片正常 fit PCA，另外 4 片正常校準門檻。W2 排除；沒有逐 die 標籤，也沒有使用異常標籤訓練。',
             '固定最多 16 主成分；階段各自建模。使用重建誤差、潛在空間距離與 16 顆視窗群體變化。',
             '目前只評估正常／異常，不宣稱已學會原始異常種類。潛在變異縮小不等於原始 Stdev Down 標籤。',
             'PID 排名不是根因；重建誤差只解釋 residual Q，不解釋 T2。群體事件不強迫指定單一來源 die。',
             '階段需完整四顆輸入；這是同一 CSV 重播協議的實驗，尚未接機台。',
             '對照既有 reports/evaluation.json：原模型正常誤報 0/5、異常偵測 5/6；PCA 本輪未優於原模型。', '',
             '| Wafer | 原始 label | ML 判斷 | 首次告警 | 未開始顆數上限 |', '|---|---|---|---|---|']
    for r in results:
        first = r['alerts'][0] if r['alerts'] else None
        lines.append(f'| W{r["wafer"]} | {r["label"]} | {"異常／類型未確定" if first else "未觸發"} | {str(first["batch"])+" / "+first["stage"] if first else "—"} | {first["potential_unstarted_devices"] if first else "—"} |')
    lines += ['', '開發資料非獨立測試。沒有 onset/PID 真值，無法評估定位準確度；分數不是信心機率。',
              '比較現有模型時僅比較 binary detection，不把未知類型計為原始類別正確。',
              '互動報表：開啟 report.html，播放或拖動時間軸；尚未揭露的 PID、座標及後續測項不顯示。']
    (DEST/'README.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    run()
