"""Offline, predeclared leave-topography-out proxy diagnostics; no ALP approval."""
import csv
import hashlib
import json
import math
import platform
import statistics
from pathlib import Path

import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import chemotopo_data as data, chemotopo_rebuild as rebuild
from .contracts import canonical, fingerprint

RECIPES=('train_mean','chemistry_ridge','chemistry_geometry_ridge')
MAX_FITS=420


def _descriptors(directory):
    filename='Modelling_Descriptors.xlsx'; sha,size=data.SOURCES[filename]
    book=data.read_workbook(data._captured(Path(directory)/filename,sha,size))
    rows=data._table(book,'Sheet1',['Topography'])
    headers={cell['value']:ref[:-1] for ref,cell in book['Sheet1'].items() if ref.endswith('1') and ref[:-1].isalpha()}
    if any(name not in headers for name in data.GEOMETRY_CANDIDATES): raise ValueError('missing geometry feature')
    features=[]; values={}
    for name in data.GEOMETRY_CANDIDATES:
        col=headers[name]
        features.append({'name':name,'sheet':'Sheet1','header_cell':col+'1','value_cells':[]})
    for row in rows:
        topo=data._number(book,'Sheet1','A'+str(row))
        if not topo.is_integer() or int(topo) in values: raise ValueError('invalid descriptor key')
        key=int(topo); values[key]=[]
        for feature in features:
            cell=headers[feature['name']]+str(row)
            values[key].append(data._number(book,'Sheet1',cell))
            feature['value_cells'].append({'topography':key,'cell':cell,'key_cell':'A'+str(row)})
    if set(values)!=set(range(2,37)): raise ValueError('unexpected descriptor keys')
    return features,values


def build_protocol(directory):
    root=Path(directory)
    sources=[]
    for name,sha,size in [('hiMSC_Raw_Data.xlsx',*data.SOURCES['hiMSC_Raw_Data.xlsx']),
                          ('Modelling_Descriptors.xlsx',*data.SOURCES['Modelling_Descriptors.xlsx']),rebuild.PROJECT]:
        data._captured(root/name,sha,size)
        sources.append({'file':name,'sha256':sha,'bytes':size})
    features,_=_descriptors(root)
    return {'schema_version':'chemotopo-grouped-proxy-protocol-v1','sources':sources,'features':features,
        'policies':[{'name':n,'positive_count_only':p,'repeat_aggregation':a} for n,p,a in rebuild.POLICIES],
        'reconstruction_protocol':rebuild.PROTOCOL,'reconstruction_protocol_sha256':fingerprint(rebuild.PROTOCOL),
        'population':'870 material keys selected post hoc by common three-batch availability across all four policies; not a blind or final test and not all 980 materials. Topography 2..36 and Chemistry 0..27; control Topography 1 excluded.',
        'target':'Same-section-control-normalized original raw-red proxy, not confirmed ALP. Known measured batch controls are part of target construction.',
        'estimand':'Held-out whole topographies with represented chemistries under existing measured source and control conditions; not future laboratory performance.',
        'split':'35 LeaveOneGroupOut folds by topography; no held-out topography in training; every test chemistry must occur in training.',
        'fit_budget':{'policies':4,'folds':35,'recipes':3,'maximum':MAX_FITS},
        'recipes':[{'name':'train_mean','model':'DummyRegressor(strategy=mean)'},
                   {'name':'chemistry_ridge','model':'OneHotEncoder(handle_unknown=ignore, sparse_output=False) then Ridge(alpha=1.0, solver=svd)'},
                   {'name':'chemistry_geometry_ridge','model':'OneHotEncoder(handle_unknown=ignore, sparse_output=False) chemistry and StandardScaler ten geometry features, fit on train only; Ridge(alpha=1.0, solver=svd)'}],
        'rules':['No topography identifier as predictor; no tuning, outcome-based policy selection, clipping, log transform, p-values, or scientific endpoint approval.',
                 'OOF scoring reuses measured data and same-section measured flat controls; it is not an unbiased final test, future-batch test or independent biological validation.',
                 'No response-derived features; chemistry and ten predeclared geometry fields only. All means, encoder categories and scaling fit on training rows only.',
                 'Pooled Spearman may reflect differences between chemistries and does not establish within-chemistry topography ranking.',
                 'MAE skill is 1 minus pooled recipe MAE divided by pooled OOF train-mean MAE; it is not based on macro-fold MAE.'],
        'metrics':['pooled_mae','pooled_rmse','pooled_spearman_midrank','macro_fold_mae','skill_vs_oof_train_mean_mae'],
        'versions':{'python':platform.python_version(),'numpy':np.__version__,'scikit_learn':sklearn.__version__},
        'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path(data.__file__),Path(rebuild.__file__))}}


def _pipeline(recipe):
    if recipe=='train_mean': return DummyRegressor(strategy='mean')
    transforms=[('chemistry',OneHotEncoder(handle_unknown='ignore',sparse_output=False),[0])]
    if recipe=='chemistry_geometry_ridge': transforms.append(('geometry',StandardScaler(),list(range(1,11))))
    return Pipeline([('features',ColumnTransformer(transforms,remainder='drop')),('ridge',Ridge(alpha=1.0,solver='svd'))])


def grouped_predictions(rows):
    if len(rows)<3 or len({(r['topography'],r['chemistry']) for r in rows})!=len(rows): raise ValueError('invalid unique material rows')
    groups=np.array([r['topography'] for r in rows],dtype=int)
    X=np.array([[r['chemistry'],*r['geometry']] for r in rows],dtype=float)
    y=np.array([r['target'] for r in rows],dtype=float)
    if X.shape!=(len(rows),11) or not np.isfinite(X).all() or not np.isfinite(y).all(): raise ValueError('finite ten-feature inputs required')
    predictions={name:np.empty(len(rows)) for name in RECIPES}; folds=[]
    for fold,(train,test) in enumerate(LeaveOneGroupOut().split(X,y,groups),1):
        if set(groups[train]) & set(groups[test]): raise ValueError('group leakage')
        if not set(X[test,0]) <= set(X[train,0]): raise ValueError('held-out chemistry absent from training')
        detail={'fold':fold,'held_out_topography':int(groups[test[0]]),
                'train_keys':[[int(groups[i]),int(X[i,0])] for i in train],
                'test_keys':[[int(groups[i]),int(X[i,0])] for i in test],
                'train_topographies':sorted(int(v) for v in set(groups[train])),
                'test_topographies':sorted(int(v) for v in set(groups[test])),
                'training_target_bounds':{'min':float(y[train].min()),'max':float(y[train].max())},
                'training_geometry_bounds':[{'feature':name,'min':float(X[train,j+1].min()),'max':float(X[train,j+1].max())} for j,name in enumerate(data.GEOMETRY_CANDIDATES)]}
        for recipe in RECIPES:
            model=_pipeline(recipe); model.fit(X[train],y[train]); predictions[recipe][test]=model.predict(X[test])
            if recipe=='chemistry_geometry_ridge':
                transformer=model.named_steps['features']
                scaler=transformer.named_transformers_['geometry']
                detail['geometry_scaler']={'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()}
                detail['chemistry_categories']=transformer.named_transformers_['chemistry'].categories_[0].tolist()
        folds.append(detail)
    metrics={}; baseline=float(np.mean(np.abs(y-predictions['train_mean'])))
    for recipe in RECIPES:
        pred=predictions[recipe]; errors=np.abs(y-pred); ranks_y=rebuild._ranks(y.tolist()); ranks_p=rebuild._ranks(pred.tolist())
        corr=statistics.correlation(ranks_y,ranks_p) if len(set(ranks_y))>1 and len(set(ranks_p))>1 else None
        metrics[recipe]={'pooled_mae':float(np.mean(errors)),'pooled_rmse':float(np.sqrt(np.mean((y-pred)**2))),
                         'pooled_spearman_midrank':corr,'macro_fold_mae':float(np.mean([np.mean(errors[groups==f['held_out_topography']]) for f in folds])),
                         'skill_vs_oof_train_mean_mae':None if baseline==0 else float(1-np.mean(errors)/baseline)}
    records=[]
    fold_map={f['held_out_topography']:f['fold'] for f in folds}
    for i,row in enumerate(rows):
        for recipe in RECIPES:
            records.append({'topography':int(groups[i]),'chemistry':int(X[i,0]),'fold':fold_map[int(groups[i])],
                            'recipe':recipe,'target':float(y[i]),'prediction':float(predictions[recipe][i])})
    return {'records':records,'folds':folds,'metrics':metrics}


def run_diagnostic(directory,output):
    protocol=build_protocol(directory)
    output=Path(output); output.mkdir(parents=False,exist_ok=False)
    def write_json(name,value): (output/name).write_text(canonical(value)+'\n',encoding='utf-8')
    write_json('protocol.json',protocol)
    _,geometry=_descriptors(directory)
    reconstruction=rebuild.run_reconstruction(directory)
    keys=[tuple(x) for x in reconstruction['comparison']['common_three_batch_keys']]
    if len(keys)!=870 or len(set(keys))!=870 or {x[0] for x in keys}!=set(range(2,37)) or any(not 0<=x[1]<=27 for x in keys):
        raise ValueError('unexpected common coverage')
    if len(rebuild.POLICIES)*35*len(RECIPES)>MAX_FITS: raise ValueError('predeclared fit budget exceeded')
    records=[]; all_folds={}; metrics={}
    for policy,_,_ in rebuild.POLICIES:
        values={(r['topography'],r['chemistry']):r['value'] for r in reconstruction['policies'][policy]['combinations'] if r['complete_three_batch_coverage']}
        rows=[{'topography':t,'chemistry':c,'geometry':geometry[t],'target':values[t,c]} for t,c in keys]
        result=grouped_predictions(rows)
        if len(result['folds'])!=35: raise ValueError('unexpected topography folds')
        records.extend({'policy':policy,**r} for r in result['records']); all_folds[policy]=result['folds']; metrics[policy]=result['metrics']
    write_json('folds.json',all_folds)
    write_json('summary.json',{'schema_version':'chemotopo-grouped-proxy-results-v1','protocol_sha256':fingerprint(protocol),
                               'keys':len(keys),'folds':35,'metrics':metrics,'fits':420,'model_calls':0,'ALP_approved':False,'scientific_validation':False})
    with (output/'results.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['policy','topography','chemistry','fold','recipe','target','prediction']);writer.writeheader();writer.writerows(records)
    manifest={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(output.iterdir())}
    write_json('manifest.json',{'schema_version':'chemotopo-grouped-proxy-manifest-v1','complete':True,'files':manifest})
    return {'output':str(output),'manifest':manifest}
