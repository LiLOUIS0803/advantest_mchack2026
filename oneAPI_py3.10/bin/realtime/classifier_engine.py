"""Single wafer label from completed-device prefixes; legacy signals are evidence only."""
import json
import numpy as np
from .data import ROOT
from .engine import Engine
from .classifier_features import extract
from .portable_model import PortableClassifier


class ClassifierEngine(Engine):
    def __init__(self):
        portable=ROOT/'artifacts/wafer_classifier/model.npz'
        if portable.exists():
            self.classifier=PortableClassifier(portable)
            self.feature_names=self.classifier.features.tolist()
            self.classifier_columns=self.classifier.columns.tolist()
            self.class_labels=self.classifier.classes.tolist()
        else:
            import joblib
            bundle=joblib.load(ROOT/'artifacts/wafer_classifier/model.joblib')
            self.classifier=bundle['model']
            self.feature_names=bundle['feature_names']
            self.classifier_columns=bundle['columns']
            self.class_labels=bundle['labels']
        super().__init__()
        if self.columns!=self.classifier_columns:
            raise ValueError('Classifier measurement schema differs from engine')
        metadata=json.loads((ROOT/'artifacts/wafer_classifier/info.json').read_text(encoding='utf-8'))
        self.info.update(model='wafer_logistic_l2',training_devices=sum(metadata['class_counts'].values())*80,
            classifier=metadata,labels=self.class_labels,site_features_enabled=True,
            training_wafers=[i for i in range(1,26) if i!=2],
            development_note='All 24 wafers used to fit; prefix replay is in-sample, not independent validation.')

    def reset(self,*args,**kwargs):
        super().reset(*args,**kwargs)
        self.class_rows=[];self.class_values=[];self.predicted_label=None
        self.classification_history=[];self.classification_reason='minimum_16_completed_devices'
        self.classification_confidence=None

    def finish_batch(self,outcomes):
        # Capture received values before base engine clears the active batch.
        # Sort by TestStart order, not arbitrary TestEnd transport order.
        indexed={str(r['key']):r for r in outcomes}
        ordered=[(key,self.current[key].copy(),self.sites[key],indexed.get(key)) for key in self.current]
        super().finish_batch(outcomes)
        for key,values,site,row in ordered:
            self.class_values.append(values)
            self.class_rows.append(['','','',site,'','',0 if row['passed'] else 8])
        self.predicted_label=None
        self.classification_confidence=None
        if len(self.class_rows)<16:
            self.classification_reason='minimum_16_completed_devices'
        elif any(r[3] is None for r in self.class_rows) or not np.isfinite(self.class_values).all():
            self.classification_reason='missing_measurements_or_site'
        else:
            f=extract(self.columns,self.class_rows,np.asarray(self.class_values))
            probabilities=self.classifier.predict_proba([[f[k] for k in self.feature_names]])[0]
            best=int(np.argmax(probabilities))
            label=str(self.classifier.classes_[best])
            if label not in self.class_labels:raise ValueError('Unexpected classifier label')
            self.predicted_label=label;self.classification_reason=None
            self.classification_confidence={'score':float(probabilities[best]),'calibrated':False,'method':'predict_proba'}
        self.classification_history.append({'batch':self.batch,'completed':self.completed,
            'predicted_label':self.predicted_label,'reason':self.classification_reason,'confidence':self.classification_confidence})

    def snapshot(self,test_index=None):
        state=super().snapshot(test_index)
        for alert in state['alerts']:
            alert['diagnostic_label']=alert['formal_label']
            alert['formal_label']=None
            alert['scope']='device' if alert['type']=='point_outlier' else 'diagnostic'
            alert['recommended_action']='warning'
        state.update(predicted_label=self.predicted_label,
            classification_confidence=self.classification_confidence,
            predicted_labels=[self.predicted_label] if self.predicted_label else [],
            status='insufficient_data' if self.predicted_label is None else 'normal' if self.predicted_label=='Normal' else 'anomaly',
            formal_alert_count=int(self.predicted_label is not None and self.predicted_label!='Normal'),
            classification_history=list(self.classification_history),classification_reason=self.classification_reason,
            prediction_basis='Single classifier output from received completed devices; official answers not read at inference.',
            classifier_model='wafer_logistic_l2',
            limitations=['All 24 available wafers used for training; replay is in-sample.',
                         'Five anomaly classes have one wafer each; early predictions are not independently validated.',
                         'Diagnostic signals are not wafer class labels; PF remains observed outcome.'])
        return state
