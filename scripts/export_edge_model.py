"""Export pure numeric inference and validate every available completed prefix."""
import json
import sys
from pathlib import Path
import joblib
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from realtime.data import manifest, read_wafer
from realtime.classifier_features import extract
from realtime.portable_model import PortableClassifier


def main():
    folder=ROOT/'artifacts/wafer_classifier'
    bundle=joblib.load(folder/'model.joblib')
    pipeline=bundle['model'];scaler,model=pipeline.steps[0][1],pipeline.steps[1][1]
    if len(pipeline.steps)!=2 or type(model).__name__!='LogisticRegression' or len(model.classes_)<3:
        raise ValueError('Exporter supports the current multinomial logistic pipeline only')
    np.savez_compressed(folder/'model.npz',format_version=np.array(1),
        mean=scaler.mean_,scale=scaler.scale_,coef=model.coef_,intercept=model.intercept_,
        classes=np.asarray(model.classes_,dtype=str),features=np.asarray(bundle['feature_names'],dtype=str),
        columns=np.asarray(bundle['columns'],dtype=str))
    portable=PortableClassifier(folder/'model.npz');count=0;maximum=0.;vectors=[];probabilities=[]
    for entry in manifest():
        columns,rows,x=read_wafer(entry)
        for end in range(16,len(rows)+1,4):
            f=extract(columns,rows[:end],x[:end]);v=[[f[k] for k in bundle['feature_names']]]
            expected=pipeline.predict_proba(v);actual=portable.predict_proba(v)
            np.testing.assert_allclose(actual,expected,atol=1e-12,rtol=1e-10)
            assert np.argmax(actual)==np.argmax(expected)
            maximum=max(maximum,float(np.max(np.abs(actual-expected))));count+=1
            vectors.append(v[0]);probabilities.append(expected[0])
    np.savez_compressed(folder/'portable_cases.npz',features=np.asarray(vectors),probabilities=np.asarray(probabilities))
    report={'prefixes_compared':count,'max_probability_error':maximum,'labels_identical':True,
            'note':'Local numerical parity; native ONEAPI and Linux Python 3.10 require target verification.'}
    (folder/'portable_validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
