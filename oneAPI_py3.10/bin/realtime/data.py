import csv
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / 'data' / 'splits'


def manifest():
    with (SPLITS / 'manifest.csv').open(encoding='utf-8', newline='') as f:
        return [r for r in csv.DictReader(f) if r['split'] != 'excluded' and int(r['wafer']) != 2]


def read_wafer(entry):
    if int(entry['wafer']) == 2:
        raise ValueError('W2 is excluded')
    with (ROOT / entry['csv']).open(encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header[10:], rows, np.asarray([r[10:] for r in rows], dtype=float)


def stage_indices(columns):
    # Explicit simulated checkpoints: before sensor1, then sensorN + subflowN.
    # This is a replay convention, not a claim about SDK delivery timing.
    groups = [[] for _ in range(7)]
    for j, name in enumerate(columns):
        stage = 0
        for n in range(1, 7):
            if f'.subflow{n}.' in name or f'.sensor{n}#' in name:
                stage = n
                break
        groups[stage].append(j)
    return [np.asarray(g, dtype=int) for g in groups]
