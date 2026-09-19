"""Replay PCA plus normal-calibrated residual variance reduction candidate."""
import json
import hashlib
import numpy as np
from threadpoolctl import threadpool_limits
from .data import ROOT, manifest, read_wafer
from .pca_experiment import features, PCAStream
from .replay import events
from .variance_audit import variance_ratio


def run():
    source=ROOT/'artifacts/ml_comparison/pca_temporal'
    info=json.loads((source/'info.json').read_text(encoding='utf-8'))
    for path,digest in info['source_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest: raise ValueError('Training source changed')
    with np.load(source/'model.npz') as archive:
        models=[{k.split('_',1)[1]:archive[k].copy() for k in archive.files if k.startswith(f's{s}_')} for s in range(7)]
    entries=manifest()
    with threadpool_limits(limits=2):
        cal=[]
        for e in entries:
            if int(e['wafer']) in info['calibration_wafers']:
                names,_,x=read_wafer(e)
                if names!=info['columns']: raise ValueError('Columns differ')
                cal.append(x)
        for m in models:
            values=[]
            for x in cal:
                residual=features(x[:,m['indices']],m)[3]
                values.extend(variance_ratio(residual[end-16:end-8],residual[end-8:end])
                              for end in range(16,len(x)+1,4))
            m['residual_low']=max(min(values)*.8,1e-9)
        results=[]
        for e in entries:
            if not e['split'].startswith('validation') or e['label']=='Site unbalance':continue
            stream=PCAStream(info['columns'],models)
            for event in events(e):stream.consume(event)
            results.append({'wafer':int(e['wafer']),'label':e['label'],
                'predicted_abnormal':bool(stream.alerts),'alerts':list(stream.alerts.values()),'frames':stream.frames})
    info.update(method='pca_temporal_plus_residual',
        residual_rule='Ratio of mean residual sample variances last8/previous8; calibration minimum x0.8, two successive windows.',
        development_note='Residual branch selected after inspecting W25 and validation. Not independent validation; thresholds use normal calibration wafers only.')
    target=ROOT/'artifacts/residual_experiment';target.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(target/'model.npz',**{f's{s}_{k}':v for s,m in enumerate(models) for k,v in m.items()})
    (target/'info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    normals=[r for r in results if r['label']=='Normal']; anomalies=[r for r in results if r['label']!='Normal']
    summary={'normal_false_alerts':sum(r['predicted_abnormal'] for r in normals),'normal_count':len(normals),
             'anomaly_detected':sum(r['predicted_abnormal'] for r in anomalies),'anomaly_count':len(anomalies)}
    payload={'info':info,'summary':summary,'results':results}
    dest=ROOT/'reports/residual_experiment';dest.mkdir(parents=True,exist_ok=True)
    (dest/'results.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    template=(ROOT/'realtime/web/pca_experiment.html').read_text(encoding='utf-8').replace('PCA','PCA + 殘差變異')
    (dest/'report.html').write_text(template.replace('__PAYLOAD__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/')),encoding='utf-8')
    lines=['# PCA 加入殘差變異下降候選','',
        f'正常誤報 {summary["normal_false_alerts"]}/5；異常偵測 {summary["anomaly_detected"]}/6。',
        '原模型與 PCA 基準未切換；仍只輸出異常、類型未確定。',
        '沿用 8 片擬合／4 片正常校準資料，W2 排除，不建模 Site。新增訊號與既有事件逐階段重播。',
        '選擇殘差分支受 W25 分析啟發，屬開發驗證；正常門檻校準不能消除模型選擇造成的樂觀偏差。','',
        '| Wafer | 原始標籤 | 首次異常批次 | 新分支首次批次 |', '|---|---|---|---|']
    for r in results:
        a=r['alerts'][0] if r['alerts'] else None
        new=next((a for a in r['alerts'] if a['mechanism']=='residual_spread_low'),None)
        lines.append(f'| W{r["wafer"]} | {r["label"]} | {a["batch"] if a else "—"} | {new["batch"] if new else "—"} |')
    w25=next(r for r in results if r['wafer']==25)
    for a in w25['alerts']:
        lines+=['',f'W25 首次訊號：批次 {a["batch"]}，{a["stage"]}；已完成 {a["completed"]} 顆，尚未開始 {a["potential_unstarted_devices"]} 顆。',
            f'當次門檻比 {a["ratio"]:.4f}，證據偏弱；非信心機率。',
            '此為群體重建殘差變異縮小，不等於已證明原始 Stdev Down 的測項或原因；不指定單顆根因 PID。']
    lines+=['','W25 的部分前窗殘差變異很高，後窗回落；可能包含極端值離開視窗的效應。',
            '此命中只能計為 binary 異常偵測，尚不能判定找到了官方所指的標準差下降原因。']
    lines+=['','尚未開始顆數只是可避免工作量上限，不代表實際省時。缺少 onset/PID 真值。',
            '互動 report.html 支援時間軸與群體殘差證據；results.json 保留每個正式告警及首次視窗。']
    (dest/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary));print(json.dumps(w25['alerts'],ensure_ascii=False))


if __name__=='__main__':run()
