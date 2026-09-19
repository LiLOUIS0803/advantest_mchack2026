"""Audit missed variance reduction without using anomaly labels for thresholds."""
import json
import hashlib
import numpy as np
from threadpoolctl import threadpool_limits
from .data import ROOT, manifest, read_wafer
from .pca_experiment import features, group_features


def variance_ratio(before, after):
    return (np.mean(after.var(axis=0, ddof=1))+1e-6)/(np.mean(before.var(axis=0, ddof=1))+1e-6)


def window_scores(x, model):
    _,_,latent,residual = features(x,model)
    z=(x-model['center'])/model['scale']
    # Original latent signal, discarded-subspace signal, and sparse feature changes.
    result=[]
    for end in range(16,len(x)+1,4):
        before,after=z[end-16:end-8],z[end-8:end]
        ratios=(after.var(axis=0,ddof=1)+1e-6)/(before.var(axis=0,ddof=1)+1e-6)
        # Active dimensions must be learned from fit data, not this wafer.
        active=model['active']
        result.append([group_features(latent[end-16:end],model['variance'],True)[1],
                       variance_ratio(residual[end-16:end-8],residual[end-8:end]),
                       float(np.quantile(ratios[active],.2)) if active.any() else 1.])
    return np.asarray(result)


def run():
    source=ROOT/'artifacts/ml_comparison/pca_temporal'
    info=json.loads((source/'info.json').read_text(encoding='utf-8'))
    for path,digest in info['source_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Training data fingerprint changed')
    entries=manifest(); arrays={}; columns=None
    for e in entries:
        names,_,x=read_wafer(e)
        if names!=info['columns']: raise ValueError('Columns differ')
        columns=names; arrays[int(e['wafer'])]=x
    with np.load(source/'model.npz') as saved:
        models=[{k.split('_',1)[1]:saved[k].copy() for k in saved.files if k.startswith(f's{s}_')} for s in range(7)]
    thresholds=[]
    with threadpool_limits(limits=2):
        for m in models:
            fit=np.concatenate([arrays[w][:,m['indices']] for w in info['fit_wafers']])
            m['active']=fit.var(axis=0)>1e-12
            cal=np.concatenate([window_scores(arrays[w][:,m['indices']],m) for w in info['calibration_wafers']])
            limits=np.maximum(cal.min(axis=0)*.8,1e-9)
            # Exact original low-variance threshold, not recalibrated on validation.
            limits[0]=float(m['group_low'])
            thresholds.append(limits)
        results=[]
        for e in entries:
            if not e['split'].startswith('validation') or e['label']=='Site unbalance': continue
            x=arrays[int(e['wafer'])]; traces=[]
            for s,m in enumerate(models):
                scores=window_scores(x[:,m['indices']],m)
                evidence=thresholds[s]/np.maximum(scores,1e-12)
                for j,name in enumerate(('latent_variance','residual_variance','feature_lower_quintile')):
                    paired=np.minimum(evidence[:-1,j],evidence[1:,j])
                    hits=np.flatnonzero(paired>1)
                    traces.append({'stage':s,'mechanism':name,'threshold':float(thresholds[s][j]),
                        'minimum_observed_ratio':float(scores[:,j].min()),
                        'peak_single_evidence':float(evidence[:,j].max()),
                        'peak_two_window_evidence':float(paired.max()),
                        'first_batch':int((16+4*(hits[0]+1))/4) if len(hits) else None})
            results.append({'wafer':int(e['wafer']),'label':e['label'],'traces':traces})
    dest=ROOT/'reports/variance_audit';dest.mkdir(parents=True,exist_ok=True)
    payload={'fit_wafers':info['fit_wafers'],'calibration_wafers':info['calibration_wafers'],
        'source_sha256':info['source_sha256'],'results':results,
        'protocol':'Lower bound = calibration minimum x0.8. Two consecutive windows, stride4. Thresholds not fitted to W25.',
        'limitation':'Exploratory after observing validation failures; no independent test or official PID/onset truth.'}
    (dest/'audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 變異下降漏報診斷','',
           '比較 PCA 保留空間、PCA 重建殘差與原始標準化測項中第 20 百分位的前後視窗變異比。',
           '新增兩種訊號僅為候選；門檻只用既有 4 片正常校準資料，不調整目前模型。',
           '證據比 > 1 才越界；連續兩視窗證據比取兩次較小值。', '',
           '| Wafer | 訊號 | 最大單視窗證據比 | 最大連續兩視窗證據比 | 最早觸發批次 |',
           '|---|---|---|---|---|']
    for r in results:
        for name in ('latent_variance','residual_variance','feature_lower_quintile'):
            rows=[t for t in r['traces'] if t['mechanism']==name]
            first=min((t['first_batch'] for t in rows if t['first_batch'] is not None),default=None)
            lines.append(f'| W{r["wafer"]} | {name} | {max(t["peak_single_evidence"] for t in rows):.3f} | {max(t["peak_two_window_evidence"] for t in rows):.3f} | {first or "—"} |')
    lines+=['','分數不足不代表原始標籤錯誤，只表示這些觀測與模型不足以辨識。',
            '這是整片回溯診斷，非新增即時正式告警。實際候選訊號只依前後 16 顆與已揭露階段計算。',
            '群體低變異不能據此認定某個 PID 是主要異常來源。']
    (dest/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(line for line in lines if 'W25' in line))


if __name__=='__main__': run()
