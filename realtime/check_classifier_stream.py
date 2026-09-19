"""Full event replay of deployed classifier; explicitly in-sample."""
import json
from .data import ROOT, manifest
from .classifier_engine import ClassifierEngine
from .replay import events, apply_event


def run():
    results=[]
    engine=ClassifierEngine()
    for entry in manifest():
        for event in events(entry):apply_event(engine,event)
        state=engine.snapshot()
        history=state['classification_history']
        labels=[h['predicted_label'] for h in history if h['predicted_label']]
        results.append({'wafer':int(entry['wafer']),'expected':entry['label'],
            'final_label':state['predicted_label'],'final_correct':state['predicted_label']==entry['label'],
            'label_changes':sum(a!=b for a,b in zip(labels,labels[1:])),
            'wrong_prefix_batches':sum(h['predicted_label'] is not None and h['predicted_label']!=entry['label'] for h in history),
            'history':history})
    report={'note':'All wafers used to train this classifier. Final label correctness and early traces are not held-out accuracy. Early wafer label truth is unavailable.',
            'final_correct':sum(r['final_correct'] for r in results),'total':len(results),'results':results}
    target=ROOT/'reports/wafer_classifier/stream_check.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))


if __name__=='__main__':run()
