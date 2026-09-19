"""Create a reproducible wafer-level development split using only stdlib."""

import csv
import json
import random
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data"
OUTPUT = SOURCE / "splits"
SEED = 20260919
EXCLUDED = {2}


def main():
    labels = {}
    for line in (SOURCE / "TrainDataInfo.txt").read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            match = re.fullmatch(r"W(\d+):\s*(.+?)\s*", line)
            if not match:
                raise ValueError(f"Invalid label: {line!r}")
            labels[int(match[1])] = match[2]
    if set(labels) != set(range(1, 26)):
        raise ValueError("Expected labels for wafers 1 through 25")

    normal = sorted(w for w, label in labels.items() if label == "Normal" and w not in EXCLUDED)
    random.Random(SEED).shuffle(normal)
    groups = {
        "train_normal": sorted(normal[:12]),
        "validation_normal": sorted(normal[12:]),
        "validation_anomaly": sorted(w for w, label in labels.items() if label != "Normal" and w not in EXCLUDED),
    }
    assert [len(v) for v in groups.values()] == [12, 5, 7]
    assigned = [w for wafers in groups.values() for w in wafers]
    assert len(assigned) == len(set(assigned)) == 24
    assert set(assigned) == set(labels) - EXCLUDED

    # Validate every included source before writing any output. W2 is never read.
    loaded = {}
    reference_header = None
    for wafer in sorted(assigned):
        source = SOURCE / f"A12345_W{wafer:02d}_RawResult.csv"
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            metadata = [next(reader) for _ in range(4)]
            rows = list(reader)
        assert [row[0] for row in metadata] == ["Pin", "Test Num", "High Limit", "Low Limit"]
        assert len(header) == 3046 and len(rows) == 80
        assert all(len(row) == len(header) for row in metadata + rows)
        assert all(row[1] == "A12345" and int(row[2]) == wafer for row in rows)
        assert len({row[0] for row in rows}) == 80
        assert len({(row[4], row[5]) for row in rows}) == 80
        assert all(sum(row[3] == str(site) for row in rows) == 20 for site in range(1, 5))
        if reference_header is None:
            reference_header = header
        assert header == reference_header
        loaded[wafer] = (source, header, metadata, rows)

    manifest = []
    for group, wafers in groups.items():
        (OUTPUT / group).mkdir(parents=True, exist_ok=True)
        (OUTPUT / "metadata").mkdir(parents=True, exist_ok=True)
        for wafer in wafers:
            source, header, metadata, rows = loaded[wafer]
            destination = OUTPUT / group / source.name
            meta_path = OUTPUT / "metadata" / f"A12345_W{wafer:02d}_metadata.csv"
            for path, records in [(destination, [header] + rows), (meta_path, [header] + metadata)]:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    csv.writer(handle).writerows(records)
                with path.open(newline="", encoding="utf-8") as handle:
                    assert list(csv.reader(handle)) == records
            manifest.append({
                "wafer": wafer, "split": group, "label": labels[wafer],
                "n_devices": len(rows), "source": source.relative_to(ROOT).as_posix(),
                "csv": destination.relative_to(ROOT).as_posix(),
                "metadata": meta_path.relative_to(ROOT).as_posix(),
            })
    manifest.append({
        "wafer": 2, "split": "excluded", "label": labels[2], "n_devices": "",
        "source": "data/A12345_W02_RawResult.csv", "csv": "", "metadata": "",
    })
    manifest.sort(key=lambda item: item["wafer"])
    with (OUTPUT / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    summary = {
        "seed": SEED, "unit": "wafer", "excluded_wafers": sorted(EXCLUDED),
        "groups": groups, "device_counts": {key: 80 * len(value) for key, value in groups.items()},
        "independent_test_set": False,
        "row_order": "Unchanged from source; actual event order must be confirmed before replay.",
    }
    (OUTPUT / "split_info.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Verified: disjoint wafers, W2 excluded, 1920 devices, matching schemas, exact cell preservation.")


if __name__ == "__main__":
    main()
