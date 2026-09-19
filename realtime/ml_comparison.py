"""Fixed-protocol temporal PCA / small autoencoder development comparison."""
import json
import hashlib
import warnings
import numpy as np
from sklearn.decomposition import PCA
from sklearn.neural_network import MLPRegressor
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
from .data import ROOT, manifest, read_wafer, stage_indices
from .pca_experiment import features, group_features, PCAStream
from .replay import events

DEST = ROOT/'reports'/'ml_comparison'


def train(kind, columns, arrays):
    models, diagnostics = [], []
    for stage, indices in enumerate(stage_indices(columns)):
        x = np.concatenate([a[:, indices] for a in arrays[:8]])
        center, scale = x.mean(axis=0), np.maximum(x.std(axis=0, ddof=1), 1e-6)
        z = (x-center)/scale
        rank = min(16, z.shape[1]-1, z.shape[0]-1)
        m = dict(indices=indices, center=center, scale=scale, temporal=True)
        if kind == 'pca_temporal':
            net = PCA(n_components=rank, svd_solver='randomized', random_state=2026).fit(z)
            m.update(components=net.components_, variance=np.maximum(net.explained_variance_,1e-6))
            diagnostics.append({'stage':stage, 'components':rank})
        else:
            # Train x -> x; a single tanh bottleneck and linear reconstruction.
            # No randomly split die early stopping or anomaly labels.
            net = MLPRegressor(hidden_layer_sizes=(rank,), activation='tanh', solver='adam',
                alpha=.01, batch_size=64, learning_rate_init=.001, max_iter=200,
                early_stopping=False, n_iter_no_change=20, random_state=2026)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', ConvergenceWarning)
                net.fit(z,z)
            hidden = np.tanh(z @ net.coefs_[0]+net.intercepts_[0])
            m.update(encoder=net.coefs_[0], encoder_bias=net.intercepts_[0],
                     decoder=net.coefs_[1], decoder_bias=net.intercepts_[1],
                     latent_center=hidden.mean(axis=0), variance=np.maximum(hidden.var(axis=0,ddof=1),1e-6))
            diagnostics.append({'stage':stage,'bottleneck':rank,'iterations':net.n_iter_,
                                'training_loss':float(net.loss_),
                                'convergence_warning':any(issubclass(w.category,ConvergenceWarning) for w in caught)})
        scores, groups = [], []
        for a in arrays[8:]:
            q,t,latent,_ = features(a[:,indices],m)
            scores.extend(np.column_stack([q,t]))
            groups.extend(group_features(latent[end-16:end], m['variance'], True)
                          for end in range(16,len(a)+1,4))
        scores,groups = np.array(scores),np.array(groups)
        m['die_limits'] = np.maximum(scores.max(axis=0)*1.2,1e-9)
        m['group_high'] = np.maximum(groups.max(axis=0)*1.2,1e-9)
        m['group_low'] = max(float(groups[:,1].min()*.8),1e-9)
        models.append(m)
        print(f'{kind}: trained stage {stage}',flush=True)
    return models,diagnostics


def run():
    entries = sorted([e for e in manifest() if e['split']=='train_normal'],key=lambda e:int(e['wafer']))
    if len(entries)!=12:
        raise ValueError('Expected existing 12 training wafers')
    arrays, hashes, columns = [], {}, None
    for e in entries:
        names,_,x = read_wafer(e)
        if columns is not None and names!=columns: raise ValueError('Column mismatch')
        columns=names; arrays.append(x)
        hashes[e['csv']]=hashlib.sha256((ROOT/e['csv']).read_bytes()).hexdigest()
    info={'fit_wafers':[int(e['wafer']) for e in entries[:8]],
          'calibration_wafers':[int(e['wafer']) for e in entries[8:]],'excluded_wafers':[2],
          'source_sha256':hashes,'columns':columns,
          'protocol':'Fixed 16-dimensional bottleneck; two consecutive windows; 16 dies, stride 4; same threshold margins as PCA v1.',
          'group_change':'Mean difference between consecutive 8-die windows; ratio of average latent sample variances.',
          'scope':'Binary detection only. No learned anomaly type, PID truth, or calibrated confidence.',
          'development_note':'Temporal rule changed after diagnosing validation false alarms. This remains development data, not an independent test.'}
    DEST.mkdir(parents=True,exist_ok=True)
    reports={}
    with threadpool_limits(limits=2):
        for kind in ('pca_temporal','autoencoder_temporal'):
            models, diagnostics=train(kind,columns,arrays)
            target=ROOT/'artifacts'/'ml_comparison'/kind;target.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(target/'model.npz',**{f's{s}_{k}':v for s,m in enumerate(models) for k,v in m.items()})
            model_info={**info,'method':kind,'diagnostics':diagnostics}
            (target/'info.json').write_text(json.dumps(model_info,ensure_ascii=False,indent=2),encoding='utf-8')
            results=[]
            for e in manifest():
                if not e['split'].startswith('validation') or e['label']=='Site unbalance': continue
                stream=PCAStream(columns,models)
                for event in events(e): stream.consume(event)
                results.append({'wafer':int(e['wafer']),'label':e['label'],
                    'predicted_abnormal':bool(stream.alerts),'alerts':list(stream.alerts.values()),'frames':stream.frames})
            normal=[r for r in results if r['label']=='Normal']; anomaly=[r for r in results if r['label']!='Normal']
            summary={'normal_false_alerts':sum(r['predicted_abnormal'] for r in normal),'normal_count':len(normal),
                     'anomaly_detected':sum(r['predicted_abnormal'] for r in anomaly),'anomaly_count':len(anomaly)}
            payload={'info':model_info,'summary':summary,'results':results}
            (DEST/f'{kind}.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
            template=(ROOT/'realtime/web/pca_experiment.html').read_text(encoding='utf-8')
            template=template.replace('PCA', 'Temporal PCA' if kind=='pca_temporal' else 'Autoencoder')
            (DEST/f'{kind}.html').write_text(template.replace('__PAYLOAD__',json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('</','<\\/')),encoding='utf-8')
            reports[kind]={'summary':summary,'diagnostics':diagnostics,
                          'results':[{k:v for k,v in r.items() if k!='frames'} for r in results]}
            print(kind,summary,flush=True)
    old=json.loads((ROOT/'reports/pca_experiment/results.json').read_text(encoding='utf-8'))
    # Keep earlier run intact; compare source fingerprints before presenting it.
    if old['info']['source_sha256']!=hashes: raise ValueError('PCA v1 baseline sources differ')
    audit=[{'wafer':r['wafer'],'mechanisms':[a['mechanism'] for a in r['alerts']]}
           for r in old['results'] if r['label']=='Normal' and r['predicted_abnormal']]
    (DEST/'comparison.json').write_text(json.dumps({'info':info,'pca_v1_false_alarm_audit':audit,
        'pca_v1_summary':old['summary'],'models':reports},ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 時序 PCA 與 Autoencoder 開發比較','',
        '原 PCA 的正常誤報全部來自 latent_mean_shift：絕對基準偏移不等於同片內趨勢。',
        '本輪比較前後 8 顆視窗差異。模型/門檻仍只使用原訓練切分的 8/4 片正常 wafer。',
        '改法受先前驗證結果啟發，因此所有結果仍是開發驗證；未依本輪結果搜尋門檻。', '',
        '| 模型 | 正常誤報 / 5 | 異常偵測 / 6 |', '|---|---|---|',
        f'| PCA v1 | {old["summary"]["normal_false_alerts"]} | {old["summary"]["anomaly_detected"]} |']
    for name,r in reports.items():
        lines.append(f'| {name} | {r["summary"]["normal_false_alerts"]} | {r["summary"]["anomaly_detected"]} |')
    lines+=['','| Wafer / label | 模型 | 正式告警 | 首次告警 | 未開始顆數上限 |','|---|---|---|---|---|']
    for name,report in reports.items():
        for r in report['results']:
            a=r['alerts'][0] if r['alerts'] else None
            lines.append(f'| W{r["wafer"]} / {r["label"]} | {name} | {"異常／種類未確定" if a else "未觸發"} | {str(a["batch"])+" / "+a["stage"] if a else "—"} | {a["potential_unstarted_devices"] if a else "—"} |')
    lines+=['','Autoencoder 是標準化測項 → tanh 16 維瓶頸 → 線性重建；最多 200 epochs，固定 seed 2026。',
        '若未收斂警告存在，僅表示固定訓練預算內未達停止條件；詳見 comparison.json diagnostics。',
        '不輸出原始異常種類；低良率沒有另加 PF 規則。重建/latent 分數與原始 label 語意不相同。',
        'PID 為可疑證據，不是根因；群體事件不指定單一 die。分數不是機率。W2 排除，Site 不建模。',
        '原服務模型與 PCA v1 報表均保留。互動報表：pca_temporal.html、autoencoder_temporal.html。']
    (DEST/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__': run()
