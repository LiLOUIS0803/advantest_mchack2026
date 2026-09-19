"""Causal engine. Only received measurements and completed outcomes enter state."""
from collections import deque
import json
import math
import numpy as np
from .data import ROOT
from .metrics import window_statistics, FORMAL_LABELS

LABELS = {'point_outlier': '測項數值偏離（輔助預警）', 'mean_trend_up': '平均值上升',
          'mean_trend_down': '平均值下降', 'stdev_trend_up': '標準差上升',
          'stdev_trend_down': '標準差下降', 'low_yield': '低良率'}


class Engine:
    def __init__(self):
        with np.load(ROOT / 'artifacts/normal_model.npz') as model:
            self.model = {k: model[k].copy() for k in model.files}
        self.info = json.loads((ROOT / 'artifacts/model_info.json').read_text(encoding='utf-8'))
        self.columns = self.model['columns'].tolist()
        self.lookup = {c:i for i,c in enumerate(self.columns)}
        self.reset()

    def reset(self, wafer='', lot='', total_devices=None, mode='replay'):
        if str(wafer).lstrip('Ww0') == '2':
            raise ValueError('W2 is excluded')
        self.wafer, self.lot, self.mode = str(wafer), str(lot), mode
        self.total_devices = total_devices
        self.histories = [deque(maxlen=16) for _ in self.columns]
        self.test_counts = np.zeros(len(self.columns), dtype=int)
        self.support = {kind:np.zeros(len(self.columns),dtype=int) for kind in FORMAL_LABELS if kind!='low_yield'}
        self.current, self.sites, self.pids = {}, {}, {}
        self.devices = {}
        self.series = [[] for _ in self.columns]
        self.completed_keys = set()
        self.completed = self.passed = self.batch = self.event_count = self.measured = 0
        self.stage = '等待資料'
        self.alerts, self.timeline = [], []
        self.latest, self.seen_events = {}, set()
        self.ended = False
        self.latency_ms = None

    def start_batch(self, batch, devices):
        if self.ended:
            raise ValueError('Wafer has ended')
        if self.current:
            raise ValueError('Previous batch must finish first')
        self.batch = batch
        for device in devices:
            key = str(device['key'])
            if key in self.completed_keys or key in self.current:
                raise ValueError('Duplicate device key')
            self.current[key] = np.full(len(self.columns), np.nan)
            self.sites[key] = device.get('site')
            self.devices[key] = {'key': key, 'site': device.get('site'), 'batch': batch,
                                 'pid': None, 'x': None, 'y': None, 'passed': None,
                                 'completed': False, 'point_tests': []}
            self._coordinates(key, device)
        self.stage = 'TestStart'

    def _coordinates(self, key, data):
        x, y = data.get('x'), data.get('y')
        if (isinstance(x, (int, float)) and isinstance(y, (int, float))
                and math.isfinite(x) and math.isfinite(y) and x != -32768 and y != -32768):
            self.devices[key].update(x=x, y=y)

    def _alert(self, kind, evidence, keys, score, sample_count, stage):
        # Coalesce one event per type per wafer; recovery is not asserted without a rule.
        first = kind not in self.latest
        if first:
            alert = {'id': len(self.alerts)+1, 'type': kind, 'label': LABELS[kind],
                     'formal_label': FORMAL_LABELS.get(kind),
                     'scope': 'device' if kind == 'point_outlier' else 'population',
                     'first_batch': self.batch, 'first_stage': stage,
                     'completed_at_detection': self.completed,
                     'potential_unstarted_devices': max(0, self.total_devices-self.completed-len(self.current)) if self.total_devices else None,
                     'updates': 0, 'last_batch': None, 'distinct_batches': 0, 'observations': []}
            self.alerts.append(alert)
            self.latest[kind] = alert
        alert = self.latest[kind]
        if alert['last_batch'] != self.batch:
            alert['distinct_batches'] += 1
        alert.update(last_batch=self.batch, stage=stage, evidence=evidence[:8],
                     device_keys=list(keys), sample_count=sample_count,
                     severity_ratio=round(float(min(score, 1e6)), 3))
        alert['updates'] += 1
        alert['observations'].append({'batch':self.batch,'stage':stage,'device_keys':list(keys),
                                      'evidence':evidence[:8], 'sample_count':sample_count})
        high = sample_count >= 16 and alert['distinct_batches'] >= 3
        alert['confidence'] = {'level': 'high' if high else 'medium' if sample_count >= 16 else 'low',
                               'reason': f'{sample_count} 筆可用樣本；{alert["distinct_batches"]} 個批次出現證據；非機率'}
        alert['recommended_action'] = 'review_pause' if high else 'warning'

    def measurement(self, keys, indices, values, stage='測項結果'):
        indices = np.asarray(indices, dtype=int)
        values = np.asarray(values, dtype=float)
        if values.shape != (len(keys), len(indices)) or not np.isfinite(values).all():
            raise ValueError('Expected finite measurement matrix [devices, tests]')
        if len(set(indices.tolist())) != len(indices) or np.any(indices < 0) or np.any(indices >= len(self.columns)):
            raise ValueError('Invalid or duplicate test indices')
        for key in keys:
            if key not in self.current or np.isfinite(self.current[key][indices]).any():
                raise ValueError('Unknown device or repeated result; explicit retest handling required')
        self.event_count += 1
        self.stage = stage
        m = self.model
        for key, row in zip(keys, values):
            self.current[key][indices] = row
            self.measured += len(indices)
            ratios = abs((row-m['center'][indices])/m['scale'][indices])/m['point'][indices]
            hits = np.where((ratios > 1) & m['active'][indices])[0]
            if len(hits):
                self.devices[key]['point_tests'].extend(int(indices[h]) for h in hits)
                hits = hits[np.argsort(ratios[hits])[::-1]]
                evidence = [self.evidence(int(indices[h]), float(row[h]), 'value',
                            float(m['center'][indices[h]]-m['point'][indices[h]]*m['scale'][indices[h]]),
                            float(m['center'][indices[h]]+m['point'][indices[h]]*m['scale'][indices[h]]), 1) for h in hits[:8]]
                self._alert('point_outlier', evidence, [key], ratios[hits[0]], 1, stage)
            for j, value in zip(indices, row):
                self.histories[j].append((key, float(value)))
                self.series[j].append((key, float(value)))
                self.test_counts[j] += 1
        available = [int(j) for j in indices if len(self.histories[j]) == 16 and self.test_counts[j] % 4 == 0 and m['active'][j]]
        if not available:
            return
        a = np.asarray([[v for _,v in self.histories[j]] for j in available])
        ids = np.asarray(available)
        stats = window_statistics(a.T, m['scale'][ids])
        delta, spread = stats['delta'], stats['spread']
        initial = np.asarray([[v for _,v in self.series[j][:8]] for j in available])
        anchor_mean = initial.mean(axis=1)
        anchor_std = np.maximum(initial.std(axis=1,ddof=1), m['scale'][ids]*1e-6)
        mean_departing = abs(stats['after_mean']-anchor_mean) > abs(stats['before_mean']-anchor_mean)
        std_departing = abs(np.log(np.maximum(stats['after_std'],1e-12)/anchor_std)) > abs(np.log(np.maximum(stats['before_std'],1e-12)/anchor_std))
        mean_stable = (delta <= m['up'][ids]) & (-delta <= m['down'][ids])
        metrics = [('mean_trend_up',delta,m['up'][ids],False),
                   ('mean_trend_down',-delta,m['down'][ids],False),
                   ('stdev_trend_up',spread,m['spread_hi'][ids],False),
                   ('stdev_trend_down',spread,m['spread_lo'][ids],True)]
        for kind, values_, limits, below in metrics:
            ratios = limits/np.maximum(values_,1e-9) if below else values_/limits
            candidate = ratios > 1
            if kind.startswith('mean_'):
                candidate &= mean_departing
            else:
                # Do not rename a mean ramp's dispersion or a return to its initial
                # baseline as a new independent standard-deviation trend.
                candidate &= std_departing & mean_stable
            self.support[kind][ids] = np.where(candidate, self.support[kind][ids]+1, 0)
            hits = np.where(candidate & (self.support[kind][ids] >= 2))[0]
            if len(hits) < 5:
                continue
            hits = hits[np.argsort(ratios[hits])[::-1]]
            evidence = [self.evidence(int(ids[h]),float(values_[h]),
                        'sample_std_ratio_last8_previous8' if 'stdev' in kind else 'directional_mean_delta_z',
                        float(limits[h]) if below else None, None if below else float(limits[h]), 16) for h in hits[:8]]
            affected = list(dict.fromkeys(k for h in hits for k,_ in self.histories[int(ids[h])]))
            for record, h in zip(evidence, hits[:8]):
                record.update({k:float(stats[k][h]) for k in
                               ('before_mean','after_mean','before_std','after_std')})
            self._alert(kind,evidence,affected,ratios[hits[0]],16,stage)

    def evidence(self, j, value, metric, low, high, n):
        return {'test':self.columns[j], 'value':value, 'metric':metric, 'low':low, 'high':high,
                'normal_center':float(self.model['center'][j]), 'sample_count':n}

    def finish_batch(self, outcomes):
        if set(str(r['key']) for r in outcomes) != set(self.current) or len(outcomes) != len(self.current):
            raise ValueError('Outcomes must cover exactly the active batch')
        if any(not isinstance(row['passed'], bool) for row in outcomes):
            raise ValueError('passed must be boolean; decode PartFlag in the adapter')
        for row in outcomes:
            key = str(row['key'])
            self.pids[key] = str(row['pid']) if row.get('pid') is not None else None
            self.devices[key].update(pid=self.pids[key], completed=True, passed=row['passed'])
            self.devices[key].update(pf=row.get('pf'),sbin=row.get('sbin'),hbin=row.get('hbin'))
            self._coordinates(key, row)
            self.completed += 1
            self.passed += int(row['passed'])
            self.completed_keys.add(key)
        self.current.clear()
        self.stage = 'TestEnd'
        n = self.completed
        p = self.passed/n
        # One-sided 95% Wilson bound; conservative evidence for yield below 80%.
        z = 1.645
        upper = (p+z*z/(2*n)+z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
        if n >= 16 and upper < .8:
            self._alert('low_yield', [{'metric':'cumulative_yield','value':p,'high':None,
                        'low':.8,'upper_bound':upper,'sample_count':n}],
                        list(self.completed_keys), .8/max(p,.001), n, 'TestEnd')
        batch_failed = sum(not row['passed'] for row in outcomes)
        self.timeline.append({'batch':self.batch,'completed':n,'yield':round(p,4),
                              'failed':n-self.passed, 'batch_completed':len(outcomes),
                              'batch_failed':batch_failed, 'batch_fail_rate':batch_failed/len(outcomes),
                              'alert_count':len(self.alerts)})

    def test_chart(self, index):
        if not 0 <= index < len(self.columns):
            raise ValueError('Unknown test index')
        m = self.model
        points, windows = [], []
        received = self.series[index]
        for n, (key, value) in enumerate(received, 1):
            d = self.devices[key]
            points.append({'n':n, 'key':key, 'pid':d['pid'], 'batch':d['batch'], 'value':value,
                           'outlier':index in d['point_tests']})
            if n >= 16 and n % 4 == 0:
                block = np.asarray([v for _,v in received[n-16:n]])
                stats = window_statistics(block, m['scale'][index])
                windows.append({'n':n, **{k:float(v) for k,v in stats.items()}})
        return {'index':index, 'test':self.columns[index], 'points':points, 'windows':windows,
                'center':float(m['center'][index]),
                'low':float(m['center'][index]-m['point'][index]*m['scale'][index]),
                'high':float(m['center'][index]+m['point'][index]*m['scale'][index]),
                'up':float(m['up'][index]), 'down':float(-m['down'][index]),
                'spread_low':float(m['spread_lo'][index]), 'spread_high':float(m['spread_hi'][index])}

    def snapshot(self, test_index=None):
        alerts = []
        for a in self.alerts:
            item = dict(a)
            item['devices'] = [{'key':k,'pid':self.pids.get(k),'site':self.sites.get(k)} for k in a['device_keys']]
            alerts.append(item)
        result = {'mode':self.mode,'wafer':self.wafer,'lot':self.lot,'batch':self.batch,
                'predicted_labels': [a['formal_label'] for a in alerts if a['formal_label']]
                    or (['Normal'] if self.completed >= 16 else []),
                'prediction_basis': 'labels observed so far; auxiliary warnings excluded',
                'formal_alert_count': sum(a['scope']=='population' for a in alerts),
                'auxiliary_warning_count': sum(a['updates'] for a in alerts if a['scope']=='device'),
                'stage':self.stage,'completed':self.completed,'total_devices':self.total_devices,
                'passed':self.passed,'failed':self.completed-self.passed,
                'failed_devices':[dict(d) for d in self.devices.values() if d['completed'] and d['passed'] is False],
                'yield':self.passed/self.completed if self.completed else None,
                'status':'anomaly' if any(a['scope']=='population' for a in alerts) else 'warning' if alerts else 'normal' if self.completed >= 16 else 'insufficient_data',
                'alerts':alerts,'timeline':self.timeline,'ended':self.ended,
                'devices':list(self.devices.values()),
                'measurements_received':self.measured,'analysis_ms':self.latency_ms,
                'estimated_saved_seconds':None,'pause_executed':False,
                'limitations':['信心等級非機率','正式類型依平均值與樣本標準差變化判斷；額外類型另計誤報',
                               '無機台停止動作；未開始 device 數僅為當時潛在可避免工作量']}
        if test_index is not None:
            result['test_chart'] = self.test_chart(test_index)
        return result
