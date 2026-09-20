"""Shared training and runtime feature extraction; NumPy only."""
import numpy as np
import warnings
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


def extract_partial(columns, rows, x):
    """Observed-only statistics; unavailable features remain absent for mean fallback.

    Missing measurements are never converted to normal measurements. Temporal
    statistics still require 16 completed dies and two observations per half.
    """
    if not len(rows):return {}
    x=np.asarray(x,dtype=float).copy();x[~np.isfinite(x)]=np.nan
    fail=np.array([int(r[6])==8 for r in rows])
    sites=np.array([r[3] for r in rows],dtype=object)
    known=[s for s in set(sites) if s is not None]
    out={'fail_fraction':float(fail.mean())}
    if len(known)>=2:
        out['site_fail_range']=float(np.ptp([fail[sites==s].mean() for s in known]))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        for stage,idx in enumerate(stage_indices(columns)):
            a=x[:,idx];scale=np.maximum(np.nanstd(a,axis=0,ddof=1),1e-6)
            changes=[];spreads=[]
            for end in range(16,len(a)+1,4):
                before,after=a[end-16:end-8],a[end-8:end]
                valid=(np.isfinite(before).sum(axis=0)>=2)&(np.isfinite(after).sum(axis=0)>=2)
                change=(np.nanmean(after,axis=0)-np.nanmean(before,axis=0))/scale
                spread=np.log((np.nanvar(after,axis=0,ddof=1)+scale**2*1e-6)/(np.nanvar(before,axis=0,ddof=1)+scale**2*1e-6))
                changes.extend(change[valid]);spreads.extend(spread[valid])
            gap=[]
            if len(known)>=2:
                means=np.array([np.nanmean(a[sites==s],axis=0) for s in known])
                valid=(np.isfinite(means).sum(axis=0)>=2)
                gap=((np.nanmax(means,axis=0)-np.nanmin(means,axis=0))/scale)[valid]
            for name,values,q,sign in (
                ('mean_up',changes,.99,1),('mean_down',changes,.01,-1),
                ('spread_up',spreads,.99,1),('spread_down',spreads,.01,-1),
                ('site_mean_gap',gap,.95,1),('site_mean_max',gap,1,1)):
                values=np.asarray(values);values=values[np.isfinite(values)]
                if len(values):out[f's{stage}_{name}']=float(sign*np.quantile(values,q))
    return out

