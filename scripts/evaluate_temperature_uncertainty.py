"""Empirical out-of-wafer error reference, not calibrated live probabilities."""
import sys,json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scene2'))
from train_temp_models import load_all,feature_plan,leave_wafer_out,META

def main():
    full,_=load_all(str(ROOT/'data'));full=full[full.W!=2].copy()
    plan=feature_plan([c for c in full.columns if c not in META+['W']]);sensors={}
    with threadpool_limits(limits=2):
        for k in range(1,7):
            target=plan[k]['target'];pred=leave_wafer_out(full,plan[k]['features'],target)
            errors=np.abs(pred-full[target].values)
            sensors[str(k)]={'mae':float(errors.mean()),'absolute_error_p95':float(np.quantile(errors,.95,method='higher')),'samples':len(errors)}
            print(k,sensors[str(k)],flush=True)
    report={'method':'Five wafer-group folds; excludes W2; raw one-step model, all preceding features available',
            'calibrated_live_probability':False,'recursive_forecast_validated':False,'sensors':sensors}
    (ROOT/'artifacts/scene2/uncertainty.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
