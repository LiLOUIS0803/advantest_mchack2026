"""Run inside the official Linux Python 3.10 image during build."""
import sys
import numpy as np
from pathlib import Path
from realtime.classifier_engine import ClassifierEngine


def main():
    if sys.version_info[:2]!=(3,10):raise RuntimeError('Python 3.10 is required by the native SDK')
    from oneapi import Interface
    from libACSAction import ActionManager
    engine=ClassifierEngine()
    from realtime.scene2_runtime import TemperatureRuntime
    import json
    temperature=TemperatureRuntime(json.loads((Path(__file__).parent/'adapter_config.json').read_text()))
    assert temperature.tp.bundle['excluded_wafers']==[2]
    for k in range(1,7):
        value,_=temperature.tp.predict_site(k,1)
        assert np.isfinite(value)
    with np.load(Path(__file__).parent/'artifacts/wafer_classifier/portable_cases.npz',allow_pickle=False) as data:
        actual=engine.classifier.predict_proba(data['features'])
        np.testing.assert_allclose(actual,data['probabilities'],rtol=1e-10,atol=1e-12)
        assert np.array_equal(actual.argmax(axis=1),data['probabilities'].argmax(axis=1))
        count=len(actual)
    if 'sklearn' in sys.modules or 'joblib' in sys.modules:raise RuntimeError('Unexpected training dependency')
    print('Runtime OK: native SDK imports, model loads, %s probability vectors match.' % count)
    print('This verifies imports and inference, not an active Nexus connection or live field mapping.')


if __name__=='__main__':main()
