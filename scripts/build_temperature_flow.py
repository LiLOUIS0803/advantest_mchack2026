"""Export measurement-suite order from the supplied SmarTest program (not test IDs)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'SmarTest/Case_Smt870/src/TestCase1'


def build():
    steps = []

    def visit(filename, prefix):
        text = (SOURCE / (filename + '.flow')).read_text()
        children = dict(re.findall(r'flow\s+(\w+)\s+calls\s+TestCase1\.(\w+)', text))
        for name in re.findall(r'\b(\w+)\.execute\(\)', text):
            if name in children:
                visit(children[name], prefix + '.' + name)
            elif name not in ('lotidTest', 'waferidTest') and not name.startswith('receive_temp_predict'):
                steps.append({'position': len(steps) + 1, 'suite': prefix + '.' + name})

    visit('Main', 'Main')
    targets = []
    for step in steps:
        match = re.fullmatch(r'Main.sensor([1-6])', step['suite'])
        if match:
            k = int(match[1])
            targets.append(dict(step, sensor=k, test_number=80 + 20*k,
                                pin=['CP', 'DS0', 'IO4', 'IO1', 'IO2', 'IO3'][k-1]))
    assert len(targets) == 6
    return {'source': 'TestCase1/Main.flow and referenced subflows',
            'distance_unit': 'measurement suites', 'steps': steps, 'targets': targets}


if __name__ == '__main__':
    path = ROOT / 'artifacts/scene2/test_flow.json'
    path.write_text(json.dumps(build(), separators=(',', ':')) + '\n', encoding='utf-8')
