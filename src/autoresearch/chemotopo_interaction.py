"""Fixed exploratory chemistry-by-geometry interaction diagnostic, offline only."""
import csv
import hashlib
import math
import os
from pathlib import Path
import platform
import statistics

import numpy as np
import sklearn
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import chemotopo_data as data, chemotopo_rebuild as rebuild, chemotopo_prediction as baseline_code
from . import chemotopo_experiment_evidence as evidence
from .contracts import canonical, fingerprint

BASELINE_MANIFEST_SHA256='b6d788ad46745efb86a0a4a5a6eced26750f2aa106a29d98dcecc316d0b33e83'
MAX_FITS=140


def _prepare(source,baseline):
    checked=evidence.inspect_experiment(baseline,source,BASELINE_MANIFEST_SHA256)
    if checked['manifest_sha256']!=BASELINE_MANIFEST_SHA256 or checked['summary']['prediction_refit'] is not False:
        raise ValueError('unexpected baseline identity or verification')
    features,geometry=baseline_code._descriptors(source)
    protocol={'schema_version':'chemotopo-interaction-protocol-v1',
        'origin':'operator-proposed exploratory follow-up after R54; not model-selected or preregistered before R54',
        'hypothesis':'The relationship between geometry and the raw-red proxy may differ by chemistry, which a shared additive geometry slope cannot express.',
        'baseline':{'manifest_sha256':checked['manifest_sha256'],'protocol_sha256':checked['protocol_sha256'],
                    'recipes':['chemistry_ridge','chemistry_geometry_ridge'],'refit':False,'verification':'original targets, grouped folds and metric arithmetic rechecked'},
        'source_manifest':checked['sources'],'geometry_features':features,
        'population':'Same 870 common three-batch material keys selected post hoc across four fixed policies; not all 980 materials.',
        'target':'Same-section measured flat-control normalized raw-red proxy, not confirmed ALP.',
        'split':'35 leave-one-topography-out folds with all held-out chemistries represented in training; same fixed folds as R54.',
        'features':'Training-only OneHotEncoder chemistry and StandardScaler ten geometry fields; concatenate chemistry and geometry main effects and all chemistry-onehot times standardized-geometry products. No topography ID.',
        'model':'Ridge(alpha=1.0, solver=svd, fit_intercept=True); encoder handle_unknown=ignore and dense output; no tuning.',
        'policies':[{'name':name,'positive_count_only':positive,'repeat_aggregation':agg} for name,positive,agg in rebuild.POLICIES],
        'fit_budget':{'policies':4,'folds':35,'new_fits':140,'maximum_new_fits':MAX_FITS,'baseline_refits':0},
        'primary_rule':'Compare pooled MAE interaction vs saved additive baseline per policy, lower is better: all four lower supports this fixed representation, all four not lower does not support it, otherwise mixed/no winner.',
        'secondary':'Pooled Spearman midrank is secondary; report separately and do not infer causal or within-chemistry ranking.',
        'limits':['Exploratory follow-up informed by R54; same data and measured controls, not a blind final test, future laboratory test or independent biological validation.',
                  'Full one-hot interactions alongside geometry main effects create redundant columns under Ridge. Any gain belongs to this complete representation and penalty configuration, not isolated evidence for a chemical interaction mechanism.',
                  'No ALP endpoint approval, materials recommendation, extrapolation claim, model calls, tuning, posthoc recipe selection or baseline refit.'],
        'versions':{'python':platform.python_version(),'numpy':np.__version__,'scikit_learn':sklearn.__version__},
        'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(evidence.__file__),Path(baseline_code.__file__),Path(rebuild.__file__),Path(data.__file__))}}
    return protocol,checked,geometry


def build_protocol(source,baseline):
    return _prepare(source,baseline)[0]


def grouped_interactions(rows):
    if len(rows)<3 or len({(r['topography'],r['chemistry']) for r in rows})!=len(rows): raise ValueError('unique material rows required')
    groups=np.asarray([r['topography'] for r in rows],dtype=int)
    X=np.asarray([[r['chemistry'],*r['geometry']] for r in rows],dtype=float)
    y=np.asarray([r['target'] for r in rows],dtype=float)
    if X.shape!=(len(rows),11) or not np.isfinite(X).all() or not np.isfinite(y).all(): raise ValueError('finite ten-feature inputs required')
    for r in rows:
        if any(type(r[k]) not in (int,float) or not math.isfinite(r[k]) for k in ('chemistry_prediction','additive_prediction')): raise ValueError('finite saved baseline predictions required')
    prediction=np.empty(len(rows));folds=[];fold_ids=np.zeros(len(rows),dtype=int)
    for fold,(train,test) in enumerate(LeaveOneGroupOut().split(X,y,groups),1):
        if set(groups[train])&set(groups[test]): raise ValueError('topography leakage')
        if not set(X[test,0])<=set(X[train,0]): raise ValueError('held-out chemistry absent from training')
        if any(rows[i]['fold']!=fold for i in test): raise ValueError('saved baseline fold differs')
        encoder=OneHotEncoder(handle_unknown='ignore',sparse_output=False).fit(X[train,:1]); scaler=StandardScaler().fit(X[train,1:])
        def transform(indices):
            chemical=encoder.transform(X[indices,:1]); geometry=scaler.transform(X[indices,1:])
            interaction=(chemical[:,:,None]*geometry[:,None,:]).reshape(len(indices),-1)
            return np.concatenate((chemical,geometry,interaction),axis=1)
        model=Ridge(alpha=1.0,solver='svd',fit_intercept=True).fit(transform(train),y[train])
        prediction[test]=model.predict(transform(test));fold_ids[test]=fold
        categories=encoder.categories_[0].tolist()
        folds.append({'fold':fold,'held_out_topography':int(groups[test[0]]),
            'train_keys':[[int(groups[i]),int(X[i,0])] for i in train], 'test_keys':[[int(groups[i]),int(X[i,0])] for i in test],
            'train_topographies':sorted(int(x) for x in set(groups[train])),'test_topographies':sorted(int(x) for x in set(groups[test])),
            'chemistry_categories':categories,'geometry_scaler':{'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()},
            'feature_counts':{'chemistry_main':len(categories),'geometry_main':10,'interactions':10*len(categories),'total':len(categories)+10+10*len(categories)}})
    out=[{'topography':int(groups[i]),'chemistry':int(X[i,0]),'fold':int(fold_ids[i]),'target':float(y[i]),
          'interaction_prediction':float(prediction[i]),'chemistry_prediction':rows[i]['chemistry_prediction'],
          'additive_prediction':rows[i]['additive_prediction']} for i in range(len(rows))]
    metrics={}
    for name,key in [('interaction','interaction_prediction'),('chemistry','chemistry_prediction'),('additive','additive_prediction')]:
        pred=[r[key] for r in out]; target=y.tolist(); errors=[abs(a-b) for a,b in zip(target,pred)]; ry=rebuild._ranks(target);rp=rebuild._ranks(pred)
        metrics[name]={'pooled_mae':statistics.mean(errors),'pooled_rmse':math.sqrt(statistics.mean((a-b)**2 for a,b in zip(target,pred))),
            'pooled_spearman_midrank':statistics.correlation(ry,rp) if len(set(ry))>1 and len(set(rp))>1 else None,
            'macro_fold_mae':statistics.mean(statistics.mean(errors[i] for i in range(len(rows)) if fold_ids[i]==f['fold']) for f in folds)}
    paired=[]
    for f in folds:
        subset=[r for r in out if r['fold']==f['fold']]
        mae=lambda key:statistics.mean(abs(r['target']-r[key]) for r in subset)
        actual=mae('interaction_prediction'); additive=mae('additive_prediction'); chemical=mae('chemistry_prediction')
        paired.append({'fold':f['fold'],'held_out_topography':f['held_out_topography'],'n':len(subset),'interaction_mae':actual,
                       'additive_mae':additive,'chemistry_mae':chemical,'delta_vs_additive':actual-additive,'delta_vs_chemistry':actual-chemical})
    return {'records':out,'folds':folds,'metrics':metrics,'paired_fold_mae':paired}


def _baseline_rows(checked,geometry,policy):
    selected={}
    for row in checked['verified_predictions']:
        if row['policy']!=policy or row['recipe'] not in {'chemistry_ridge','chemistry_geometry_ridge'}: continue
        key=(int(row['topography']),int(row['chemistry'])); d=selected.setdefault(key,{})
        if row['recipe'] in d:raise ValueError('duplicate baseline row')
        d[row['recipe']]=row
    rows=[]
    for (t,c),values in sorted(selected.items()):
        if set(values)!={'chemistry_ridge','chemistry_geometry_ridge'}:raise ValueError('incomplete baseline rows')
        chem,add=values['chemistry_ridge'],values['chemistry_geometry_ridge']
        if int(chem['fold'])!=int(add['fold']) or float(chem['target'])!=float(add['target']):raise ValueError('baseline key, fold or target mismatch')
        rows.append({'topography':t,'chemistry':c,'geometry':geometry[t],'target':float(chem['target']),
                     'fold':int(chem['fold']),'chemistry_prediction':float(chem['prediction']),'additive_prediction':float(add['prediction'])})
    if len(rows)!=870: raise ValueError('unexpected baseline cohort')
    return rows


def _protected_output(output,source,baseline):
    target=Path(os.path.abspath(output))
    for part in (target,*target.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('redirected output path')
    for protected in (Path(source).absolute().resolve(),Path(baseline).absolute().resolve()):
        if target==protected or target.is_relative_to(protected) or protected.is_relative_to(target):raise ValueError('output must be separate from sources')
    return target


def run_interaction(source,baseline,output,expected_protocol_sha256=None):
    target=_protected_output(output,source,baseline)
    if target.exists():raise FileExistsError('output directory already exists')
    protocol,checked,geometry=_prepare(source,baseline)
    if expected_protocol_sha256 is not None and fingerprint(protocol)!=expected_protocol_sha256:raise ValueError('frozen protocol differs')
    target.mkdir(parents=False,exist_ok=False)
    def write_json(name,value):
        with (target/name).open('x',encoding='utf-8') as out:out.write(canonical(value)+'\n')
    write_json('protocol.json',protocol)
    all_rows={policy:_baseline_rows(checked,geometry,policy) for policy,_,_ in rebuild.POLICIES}
    keysets=[{(r['topography'],r['chemistry']) for r in rows} for rows in all_rows.values()]
    if any(keys!=keysets[0] for keys in keysets):raise ValueError('baseline policies have different material keys')
    for policy,rows in all_rows.items():
        reference=checked['verified_folds'][policy]
        if len(reference)!=35:raise ValueError('unexpected baseline fold count')
        for number,topography in enumerate(sorted({r['topography'] for r in rows}),1):
            test=[[r['topography'],r['chemistry']] for r in rows if r['topography']==topography]
            train=[[r['topography'],r['chemistry']] for r in rows if r['topography']!=topography]
            fold=reference[number-1]
            if fold['fold']!=number or fold['test_keys']!=test or fold['train_keys']!=train or any(r['fold']!=number for r in rows if r['topography']==topography):raise ValueError('fold keys differ from baseline')
    if len(rebuild.POLICIES)*35>MAX_FITS:raise ValueError('fit budget exceeded')
    records=[];folds={};metrics={};paired={}
    for policy,_,_ in rebuild.POLICIES:
        rows=all_rows[policy];result=grouped_interactions(rows)
        if len(result['folds'])!=35:raise ValueError('unexpected fold count')
        records.extend({'policy':policy,**r} for r in result['records']);folds[policy]=result['folds'];metrics[policy]=result['metrics'];paired[policy]=result['paired_fold_mae']
    if len(records)!=3480 or len(folds)*35>MAX_FITS:raise ValueError('unexpected result or fit count')
    improved=sum(v['interaction']['pooled_mae']<v['additive']['pooled_mae'] for v in metrics.values())
    verdict='supports_fixed_representation' if improved==4 else 'no_support' if improved==0 else 'mixed_no_winner'
    write_json('folds.json',folds)
    write_json('summary.json',{'schema_version':'chemotopo-interaction-results-v1','protocol_sha256':fingerprint(protocol),
        'metrics':metrics,'paired_fold_mae':paired,'primary_rule':{'improved_policies':improved,'policy_count':4,'result':verdict},
        'new_operator_fits':140,'baseline_refits':0,'model_calls':0,'scientific_validation':False,'ALP_approved':False})
    with (target/'results.csv').open('x',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=['policy','topography','chemistry','fold','target','interaction_prediction','chemistry_prediction','additive_prediction']);writer.writeheader();writer.writerows(records)
    files={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(target.iterdir())}
    write_json('manifest.json',{'schema_version':'chemotopo-interaction-manifest-v1','complete':True,'files':files})
    return {'output':str(target),'protocol_sha256':fingerprint(protocol),'manifest':files}
