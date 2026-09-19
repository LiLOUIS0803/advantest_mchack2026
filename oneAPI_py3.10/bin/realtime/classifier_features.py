"""Shared training and runtime feature extraction; NumPy only."""
import numpy as np
from .data import stage_indices


def extract(columns, rows, x):
    """Only supplied completed devices; identifiers never enter model features."""
    if len(x)<16 or len(rows)!=len(x) or not np.isfinite(x).all():
        raise ValueError('Require >=16 completed devices with finite measurements')
    sites=np.array([int(r[3]) for r in rows]);fail=np.array([int(r[6])==8 for r in rows])
    rates=[fail[sites==s].mean() for s in np.unique(sites)]
    out={'fail_fraction':float(fail.mean()),'site_fail_range':float(np.ptp(rates))}
    for stage,idx in enumerate(stage_indices(columns)):
        a=x[:,idx];scale=np.maximum(a.std(axis=0,ddof=1),1e-6)
        changes=[];spreads=[]
        for end in range(16,len(a)+1,4):
            before,after=a[end-16:end-8],a[end-8:end]
            changes.append((after.mean(axis=0)-before.mean(axis=0))/scale)
            spreads.append(np.log((after.var(axis=0,ddof=1)+scale**2*1e-6)/(before.var(axis=0,ddof=1)+scale**2*1e-6)))
        changes=np.array(changes);spreads=np.array(spreads)
        site_means=np.array([a[sites==s].mean(axis=0) for s in np.unique(sites)])
        for name,value in {
            'mean_up':np.quantile(changes,.99), 'mean_down':-np.quantile(changes,.01),
            'spread_up':np.quantile(spreads,.99),'spread_down':-np.quantile(spreads,.01),
            'site_mean_gap':np.quantile(np.ptp(site_means,axis=0)/scale,.95),
            'site_mean_max':np.max(np.ptp(site_means,axis=0)/scale),
        }.items():out[f's{stage}_{name}']=float(value)
    return out

