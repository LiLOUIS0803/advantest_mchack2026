"""Fit a robust normal-only statistical model; no validation data used."""
import hashlib
import json
import numpy as np
from .data import ROOT, manifest, read_wafer
from .metrics import window_statistics, FORMAL_LABELS


def train():
    entries = [r for r in manifest() if r['split'] == 'train_normal']
    arrays, hashes = [], {}
    columns = None
    for entry in entries:
        names, _, x = read_wafer(entry)
        if columns is not None and names != columns:
            raise ValueError('Inconsistent measurement columns')
        columns = names
        arrays.append(x)
        hashes[entry['csv']] = hashlib.sha256((ROOT / entry['csv']).read_bytes()).hexdigest()
    all_x = np.concatenate(arrays)
    center = np.mean(all_x, axis=0)
    # Typical within-wafer SAMPLE standard deviation; median only pools wafers.
    scale = np.median([x.std(axis=0, ddof=1) for x in arrays], axis=0)
    active = np.ptp(all_x, axis=0) > 1e-10
    scale = np.maximum(scale, 1e-6)
    window = 16
    deltas, spreads = [], []
    for x in arrays:
        for end in range(window, len(x) + 1, 4):
            block = x[end-window:end]
            stats = window_statistics(block, scale)
            deltas.append(stats['delta'])
            spreads.append(stats['spread'])
    deltas, spreads = np.asarray(deltas), np.asarray(spreads)
    # Envelopes learned on training wafers only; deliberately conservative first baseline.
    point = np.maximum(8., np.max(abs((all_x-center)/scale), axis=0) * 1.15)
    up = np.maximum(1.5, np.max(deltas, axis=0) * 1.2)
    down = np.maximum(1.5, -np.min(deltas, axis=0) * 1.2)
    spread_hi = np.maximum(2., np.max(spreads, axis=0) * 1.2)
    spread_lo = np.minimum(.45, np.min(spreads, axis=0) * .8)
    target = ROOT / 'artifacts'
    target.mkdir(exist_ok=True)
    np.savez_compressed(target / 'normal_model.npz', columns=np.asarray(columns), center=center,
                        scale=scale, active=active, point=point, up=up, down=down,
                        spread_hi=spread_hi, spread_lo=spread_lo)
    info = {'model': 'label_aligned_mean_std_v2', 'training_wafers': [int(e['wafer']) for e in entries],
            'training_devices': len(all_x), 'measurement_count': len(columns),
            'active_measurements': int(active.sum()), 'excluded_wafers': [2],
            'window_devices': window, 'minimum_affected_tests': 5,
            'consecutive_windows': 2,
            'recovery_gate': 'Moving away from first8 baseline; stdev also requires mean below change threshold.',
            'formal_labels': FORMAL_LABELS, 'unsupported_labels': ['Site unbalance'],
            'auxiliary_only': ['point_outlier'],
            'mean_metric': '(mean(last8)-mean(previous8))/training_scale',
            'stdev_metric': 'sample_std(last8)/sample_std(previous8), ddof=1',
            'development_note': 'Definitions revised after inspecting validation; not an untouched test set.',
            'confidence': 'Evidence heuristic, not calibrated probability',
            'normal_label_does_not_imply_all_devices_pass': True,
            'threshold_source': 'training only; observed envelopes with fixed safety margins',
            'source_sha256': hashes}
    (target / 'model_info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in info.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    train()
