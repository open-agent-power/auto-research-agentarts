"""Read and arithmetically verify a frozen P02 prediction experiment; never refit."""
import csv
import hashlib
from io import StringIO
import json
import math
import os
from pathlib import Path
import statistics

from . import chemotopo_data as data, chemotopo_prediction as prediction, chemotopo_rebuild as rebuild
from .contracts import ResearchError, fingerprint

FILES={'protocol.json':100000,'folds.json':3000000,'results.csv':3000000,'summary.json':100000}


def _safe_file(path,limit):
    before=data._regular(path)
    if not 0 < before.st_size <= limit: raise ResearchError('EVIDENCE_CHANGED','Experiment file exceeds bounds.')
    with path.open('rb') as stream:
        if data._stamp(os.fstat(stream.fileno())) != data._stamp(before):
            raise ResearchError('EVIDENCE_CHANGED','Experiment file changed before read.')
        payload=stream.read(limit+1)
        if (len(payload)!=before.st_size or len(payload)>limit or data._stamp(os.fstat(stream.fileno()))!=data._stamp(before)
                or data._stamp(data._regular(path))!=data._stamp(before)):
            raise ResearchError('EVIDENCE_CHANGED','Experiment file changed during read.')
    return payload


def attachment(directory,source_directory,expected_manifest_sha256=None):
    root=Path(directory).absolute(); raw=_safe_file(root/'manifest.json',100000)
    digest=hashlib.sha256(raw).hexdigest()
    if expected_manifest_sha256 is not None and digest!=expected_manifest_sha256: raise ResearchError('EVIDENCE_CHANGED','Pinned experiment manifest changed.')
    manifest=json.loads(raw)
    if manifest.get('schema_version')!='chemotopo-grouped-proxy-manifest-v1' or manifest.get('complete') is not True or set(manifest.get('files',{}))!=set(FILES):
        raise ResearchError('EVIDENCE_CHANGED','Incomplete or unexpected experiment manifest.')
    files={}
    for name,limit in FILES.items():
        item=manifest['files'][name]
        if type(item.get('bytes')) is not int or not 0<item['bytes']<=limit: raise ResearchError('EVIDENCE_CHANGED','Experiment file exceeds bounds.')
        files[name]=data._captured(root/name,item['sha256'],item['bytes'])
    protocol=json.loads(files['protocol.json'])
    if protocol!=prediction.build_protocol(source_directory): raise ResearchError('EVIDENCE_CHANGED','Experiment protocol, code, environment or sources differ.')
    return {'manifest_sha256':digest,'protocol_sha256':fingerprint(protocol),'manifest':manifest,'files':files}


def derived_prediction_facts(metrics,manifest_sha256,protocol_sha256):
    """Describe checked comparisons of model inputs; never infer scientific causes."""
    policies=[item[0] for item in rebuild.POLICIES]
    def make(value):
        return {'id':'p02-fact-'+fingerprint({'manifest_sha256':manifest_sha256,'protocol_sha256':protocol_sha256,'fact':value}),**value}
    def comparison(left,right):
        if left is None or right is None:return 'uncomparable'
        if math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-12):return 'tie'
        return 'higher' if right>left else 'lower'
    values=[]
    for policy in policies:
        chemical=metrics[policy]['chemistry_ridge']; geometry=metrics[policy]['chemistry_geometry_ridge']
        cm=chemical['pooled_mae']; gm=geometry['pooled_mae']
        cs=chemical['pooled_spearman_midrank']; gs=geometry['pooled_spearman_midrank']
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (cm,gm)) or any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in (cs,gs)):
            raise ResearchError('EVIDENCE_CHANGED','Invalid prediction comparison metrics.')
        values.append({'kind':'policy_model_inputs','policy':policy,'chemistry_pooled_mae':cm,
            'chemistry_geometry_pooled_mae':gm,'mae_delta_geometry_minus_chemistry':gm-cm,
            'mae_geometry_relation':comparison(cm,gm),
            'chemistry_pooled_spearman':cs,'chemistry_geometry_pooled_spearman':gs,
            'spearman_geometry_relation':comparison(cs,gs)})
    def counts(key):
        relations=[v[key] for v in values]
        return {'higher_count':relations.count('higher'),'lower_count':relations.count('lower'),
                'tie_count':relations.count('tie'),'uncomparable_count':relations.count('uncomparable')}
    primary=counts('mae_geometry_relation')
    aggregate={'kind':'primary_aggregate','geometry_worse_policy_count':primary['higher_count'],
               'geometry_better_policy_count':primary['lower_count'],'tie_count':primary['tie_count'],
               'uncomparable_count':primary['uncomparable_count'],'policy_count':len(values),'measure':'pooled_mae','direction':'lower_is_better'}
    secondary={'kind':'secondary_spearman_aggregate',**counts('spearman_geometry_relation'),
               'geometry_higher_policy_count':counts('spearman_geometry_relation')['higher_count'],
               'policy_count':len(values),'measure':'pooled_spearman_midrank','direction':'higher_is_better'}
    return {'comparison_axis':'model_inputs','primary_metric':'pooled_mae','comparison_tolerance':{'rel_tol':1e-12,'abs_tol':1e-12},
            'facts':[make(aggregate),*[make(v) for v in values],make(secondary)]}


def inspect_experiment(directory,source_directory,expected_manifest_sha256):
    attached=attachment(directory,source_directory,expected_manifest_sha256)
    protocol=json.loads(attached['files']['protocol.json']); summary=json.loads(attached['files']['summary.json']); folds=json.loads(attached['files']['folds.json'])
    if (summary.get('protocol_sha256')!=attached['protocol_sha256'] or summary.get('keys')!=870 or summary.get('folds')!=35
        or summary.get('fits')!=420 or summary.get('model_calls')!=0 or summary.get('ALP_approved') is not False or summary.get('scientific_validation') is not False):
        raise ResearchError('EVIDENCE_CHANGED','Experiment summary identity differs.')
    source=rebuild.run_reconstruction(source_directory); keys={tuple(k) for k in source['comparison']['common_three_batch_keys']}
    names=[p[0] for p in rebuild.POLICIES]; recipes=prediction.RECIPES
    if len(keys)!=870 or {k[0] for k in keys}!=set(range(2,37)) or set(folds)!=set(names): raise ResearchError('EVIDENCE_CHANGED','Invalid experiment cohort.')
    records=list(csv.DictReader(StringIO(attached['files']['results.csv'].decode('utf-8'))))
    if len(records)!=870*4*3: raise ResearchError('EVIDENCE_CHANGED','Unexpected prediction row count.')
    parsed={}; by_policy={}
    for row in records:
        if set(row)!={'policy','topography','chemistry','fold','recipe','target','prediction'}: raise ResearchError('EVIDENCE_CHANGED','Unexpected prediction row schema.')
        try:
            policy=row['policy']; recipe=row['recipe']; t=int(row['topography']); c=int(row['chemistry']); fold=int(row['fold']); target=float(row['target']); pred=float(row['prediction'])
        except (TypeError,ValueError): raise ResearchError('EVIDENCE_CHANGED','Invalid prediction row.') from None
        key=(policy,recipe,t,c)
        if policy not in names or recipe not in recipes or (t,c) not in keys or key in parsed or not all(map(math.isfinite,(target,pred))): raise ResearchError('EVIDENCE_CHANGED','Duplicate or invalid prediction.')
        parsed[key]={'fold':fold,'target':target,'prediction':pred}
    for policy in names:
        original={(r['topography'],r['chemistry']):r['value'] for r in source['policies'][policy]['combinations'] if r['complete_three_batch_coverage']}
        fset=folds[policy]
        if len(fset)!=35: raise ResearchError('EVIDENCE_CHANGED','Invalid fold count.')
        seen=set()
        for i,fold in enumerate(fset,1):
            test={tuple(v) for v in fold['test_keys']}; train={tuple(v) for v in fold['train_keys']}; topo=fold['held_out_topography']
            if (fold['fold']!=i or topo in seen or not test or len(test)!=len(fold['test_keys']) or len(train)!=len(fold['train_keys']) or train != keys-test or {k[0] for k in test}!={topo}
                or {k[0] for k in train}&{topo} or {k[1] for k in test}-{k[1] for k in train}
                or fold['test_topographies']!=[topo] or fold['train_topographies']!=sorted({k[0] for k in train})):
                raise ResearchError('EVIDENCE_CHANGED','Invalid grouped fold or chemistry scope.')
            seen.add(topo)
            train_mean=statistics.mean(original[t,c] for t,c in sorted(train))
            for t,c in test:
                for recipe in recipes:
                    record=parsed[policy,recipe,t,c]
                    if record['fold']!=i or not math.isclose(record['target'],original[t,c],rel_tol=1e-12,abs_tol=1e-12): raise ResearchError('EVIDENCE_CHANGED','Prediction target or fold differs from original reconstruction.')
                    if recipe=='train_mean' and not math.isclose(record['prediction'],train_mean,rel_tol=1e-12,abs_tol=1e-12): raise ResearchError('EVIDENCE_CHANGED','OOF train-mean baseline differs from its training targets.')
        if seen!=set(range(2,37)): raise ResearchError('EVIDENCE_CHANGED','Incomplete held-out topographies.')
        ordered=sorted(keys); computed={}
        for recipe in recipes:
            values=[parsed[policy,recipe,*key] for key in ordered]
            y=[v['target'] for v in values]; pred=[v['prediction'] for v in values]
            errors=[abs(a-b) for a,b in zip(y,pred)]
            ry=rebuild._ranks(y); rp=rebuild._ranks(pred)
            computed[recipe]={'pooled_mae':statistics.mean(errors),'pooled_rmse':math.sqrt(statistics.mean((a-b)**2 for a,b in zip(y,pred))),
                'pooled_spearman_midrank':statistics.correlation(ry,rp) if len(set(ry))>1 and len(set(rp))>1 else None,
                'macro_fold_mae':statistics.mean(statistics.mean(errors[j] for j,k in enumerate(ordered) if k[0]==t) for t in sorted(seen))}
        baseline=computed['train_mean']['pooled_mae']
        for recipe in recipes:
            computed[recipe]['skill_vs_oof_train_mean_mae']=None if baseline==0 else 1-computed[recipe]['pooled_mae']/baseline
            stated=summary['metrics'][policy][recipe]
            if set(stated)!=set(computed[recipe]) or any(not ((a is None and b is None) or (type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12))) for a,b in ((stated[k],v) for k,v in computed[recipe].items())):
                raise ResearchError('EVIDENCE_CHANGED','Experiment metric arithmetic differs.')
        by_policy[policy]=computed
    return {'schema_version':'chemotopo-prediction-inspection-v1','manifest_sha256':attached['manifest_sha256'],
            'protocol_sha256':attached['protocol_sha256'],'summary':{'keys':870,'folds':35,'prediction_rows':len(records),
            'metrics':by_policy,'prediction_facts':derived_prediction_facts(by_policy,attached['manifest_sha256'],attached['protocol_sha256']),'fits_actor':'operator_script','prior_fits':420,'model_calls':0,'metric_arithmetic_rechecked':True,
            'targets_recomputed':True,'prediction_refit':False,'scientific_validation':False,'ALP_approved':False,
            'limits':protocol['rules']+[protocol['population'],protocol['target'],protocol['estimand']]},
            'verified_folds':folds,'verified_predictions':records,'sources':protocol['sources']}
