"""Single-label wafer classifier benchmark; no die pseudo-labels or random-window CV."""
import json
import hashlib
from collections import Counter
import numpy as np
import joblib
import sklearn
from sklearn.base import clone
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from threadpoolctl import threadpool_limits
from .data import ROOT, manifest, read_wafer, stage_indices


def official_labels():
    return {int(line.split(':',1)[0].strip()[1:]):line.split(':',1)[1].strip()
            for line in (ROOT/'data/TrainDataInfo.txt').read_text(encoding='utf-8-sig').splitlines() if ':' in line}


from .classifier_features import extract


def candidates():
    return {
        'logistic_l2':make_pipeline(StandardScaler(),LogisticRegression(C=.1,class_weight='balanced',max_iter=2000,random_state=2026)),
        'random_forest':RandomForestClassifier(n_estimators=200,max_depth=3,max_features=.7,class_weight='balanced',random_state=2026,n_jobs=1),
        'extra_trees':ExtraTreesClassifier(n_estimators=200,max_depth=3,max_features=.7,class_weight='balanced',random_state=2026,n_jobs=1)}


def run():
    labels=official_labels();entries=sorted(manifest(),key=lambda e:int(e['wafer']))
    dataset=[];fingerprints={}
    for e in entries:
        columns,rows,x=read_wafer(e)
        dataset.append((e,columns,rows,x,extract(columns,rows,x)))
        fingerprints[e['csv']]=hashlib.sha256((ROOT/e['csv']).read_bytes()).hexdigest()
    names=list(dataset[0][4]);X=np.array([[d[4][k] for k in names] for d in dataset]);y=np.array([labels[int(d[0]['wafer'])] for d in dataset]);counts=Counter(y)
    results={}
    with threadpool_limits(limits=2):
        for name,base in candidates().items():
            folds=[]
            for i,d in enumerate(dataset):
                mask=np.arange(len(y))!=i;model=clone(base).fit(X[mask],y[mask]);prediction=str(model.predict(X[i:i+1])[0])
                folds.append({'wafer':int(d[0]['wafer']),'expected':str(y[i]),'predicted_label':prediction,
                              'class_present_in_training':bool(y[i] in y[mask]),'correct':prediction==y[i]})
            supported=[r for r in folds if r['class_present_in_training']]
            recalls={c:sum(r['correct'] for r in supported if r['expected']==c)/sum(r['expected']==c for r in supported)
                     for c,n in counts.items() if n>1}
            results[name]={'correct':sum(r['correct'] for r in folds),'total':len(folds),
                          'supported_macro_recall':float(np.mean(list(recalls.values()))),
                          'supported_recalls':recalls,'normal_false_alerts':sum(r['predicted_label']!='Normal' for r in folds if r['expected']=='Normal'),
                          'folds':folds}
            print(name,{k:v for k,v in results[name].items() if k!='folds'},flush=True)
        # Fixed criterion; ties prefer the simpler regularized linear model.
        selected=max(results,key=lambda n:(results[n]['supported_macro_recall'],-results[n]['normal_false_alerts']))
        final=clone(candidates()[selected]).fit(X,y)
        prefix=[]
        for e,columns,rows,x,_ in dataset:
            trace=[]
            for end in range(16,len(rows)+1,4):
                f=extract(columns,rows[:end],x[:end]);v=np.array([[f[k] for k in names]])
                trace.append({'completed':end,'predicted_label':str(final.predict(v)[0])})
            prefix.append({'wafer':int(e['wafer']),'expected':labels[int(e['wafer'])],'trace':trace})
    target=ROOT/'artifacts/wafer_classifier';target.mkdir(parents=True,exist_ok=True)
    joblib.dump({'model':final,'feature_names':names,'columns':columns,'labels':sorted(counts)},target/'model.joblib')
    report={'selected':selected,'selection_basis':'LOO macro recall over classes with >=2 wafers; then lower normal false alarms; fixed candidate order breaks ties.',
            'class_counts':dict(counts),'excluded_wafers':[2],'site_features_enabled':True,
            'feature_names':names,'source_sha256':fingerprints,'sklearn_version':sklearn.__version__,
            'models':results,'prefix_replay_in_sample':prefix,
            'limitations':['Five anomaly classes have one wafer each and disappear from their held-out training fold.',
                           'Selection and evaluation use same development CV; no independent performance estimate.',
                           'Final model fits all 24 wafers including former validation; original split files unchanged.',
                           'Prefix replay is causal but in-sample and trained on full-wafer features; not verified early detection.',
                           'One official label only. No calibrated confidence or die-level root-cause labels.']}
    (target/'info.json').write_text(json.dumps({k:v for k,v in report.items() if k not in ('models','prefix_replay_in_sample')},ensure_ascii=False,indent=2),encoding='utf-8')
    dest=ROOT/'reports/wafer_classifier';dest.mkdir(parents=True,exist_ok=True)
    (dest/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Wafer 單一分類器基準','',f'候選選擇：{selected}；44 個摘要特徵；W2 排除，Site 差異已啟用。',
           '每片只有一個訓練樣本；固定參數比較三個模型，留一片驗證。沒有將視窗隨機拆分。','',
           '| 模型 | LOO 正確 / 24 | Normal 誤報 / 17 | 可學類別平均召回 |','|---|---|---|---|']
    for name,r in results.items():lines.append(f'| {name} | {r["correct"]} | {r["normal_false_alerts"]} | {r["supported_macro_recall"]:.3f} |')
    lines+=['','可學類別只有 Normal（17 片）和 Low yield（2 片）。其餘 5 類各只有 1 片，留出後訓練集根本沒有該類，不能驗證七類泛化。',
            '選擇結果僅為開發候選，不代表已證明適合所有七類。分數不可宣稱為七類準確率。',
            '最終候選使用全部 24 片標籤重新訓練；原 validation 不再是此模型的獨立驗證。原切分檔不變。',
            'comparison.json 的 prefix_replay_in_sample 僅展示測完每批後的单一預測；沒有給早期視窗套入最終異常標籤來訓練。',
            '尚未替換即時服務：完整 wafer 分類與中途預測的分布不同，仍需事件重播與額外標註驗證。','',
            '| Wafer | 官方 label | 留一片預測 | 訓練集含該類 |','|---|---|---|---|']
    for r in results[selected]['folds']:lines.append(f'| W{r["wafer"]} | {r["expected"]} | {r["predicted_label"]} | {r["class_present_in_training"]} |')
    (dest/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Selected:',selected)


if __name__=='__main__':run()
