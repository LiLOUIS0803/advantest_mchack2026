"""Refit the supplied scene2 design without W2; export JSON for Python 3.10."""
import sys,json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scene2'))
from train_temp_models import load_all,feature_plan,fit_lasso,leave_wafer_out,META

def main():
    full,limits=load_all(str(ROOT/'data'));full=full[full.W!=2].copy()
    plan=feature_plan([c for c in full.columns if c not in META+['W']])
    bundle={'version':2,'excluded_wafers':[2],'training_wafers':sorted(int(w) for w in full.W.unique()),'targets':{},'models':{}}
    report={}
    with threadpool_limits(limits=2):
        for k in range(1,7):
            target,feats=plan[k]['target'],plan[k]['features'];X=full[feats];y=full[target].values;med=X.median()
            model=fit_lasso(X.fillna(med).values,y)
            model.update(feature_names=feats,median=med.values,limit_lo=float(limits.loc[target,'lo']),limit_hi=float(limits.loc[target,'hi']))
            bundle['models'][str(k)]={n:v.tolist() if isinstance(v,np.ndarray) else v for n,v in model.items()}
            bundle['targets'][str(k)]=target
            p=leave_wafer_out(full,feats,target)
            report[str(k)]={'mae':float(np.abs(p-y).mean()),'rmse':float(np.sqrt(((p-y)**2).mean()))}
            print('sensor',k,report[str(k)],flush=True)
    out=ROOT/'artifacts/scene2';out.mkdir(exist_ok=True)
    (out/'temp_models.json').write_text(json.dumps(bundle),encoding='utf-8')
    (out/'evaluation.json').write_text(json.dumps({'excluded_wafers':[2],'evaluation':'5 wafer-group folds; no online correction','sensors':report},indent=2),encoding='utf-8')
if __name__=='__main__':main()
