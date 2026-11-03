"""Verify immutable R59 interaction evidence against R54 and original sources, without fits."""
import csv
import hashlib
from io import StringIO
import json
import math
from pathlib import Path
import statistics

from . import chemotopo_data as data, chemotopo_interaction as interaction, chemotopo_rebuild as rebuild
from .chemotopo_experiment_evidence import _safe_file
from .contracts import ResearchError, fingerprint

R59_MANIFEST='8e955ed98e055c30363229115cfc6c5e90639358adf2d3256d2c1c4d06001852'
LIMITS={'protocol.json':100000,'summary.json':200000,'folds.json':3000000,'results.csv':3000000}


def checked_files(directory,expected=R59_MANIFEST):
    root=Path(directory).absolute();raw=_safe_file(root/'manifest.json',100000);digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected:raise ResearchError('EVIDENCE_CHANGED','Frozen R59 manifest changed.')
    manifest=json.loads(raw)
    if manifest.get('schema_version')!='chemotopo-interaction-manifest-v1' or manifest.get('complete') is not True or set(manifest.get('files',{}))!=set(LIMITS):
        raise ResearchError('EVIDENCE_CHANGED','R59 manifest is incomplete.')
    files={}
    for name,limit in LIMITS.items():
        row=manifest['files'][name]
        if type(row.get('bytes')) is not int or not 0<row['bytes']<=limit:raise ResearchError('EVIDENCE_CHANGED','R59 artifact exceeds bounds.')
        files[name]=data._captured(root/name,row['sha256'],row['bytes'])
    return {'manifest_sha256':digest,'files':files}


def inspect(source,baseline,directory,expected=R59_MANIFEST):
    captured=checked_files(directory,expected)
    protocol,base,geometry=interaction._prepare(source,baseline)
    stored=json.loads(captured['files']['protocol.json']);summary=json.loads(captured['files']['summary.json']);folds=json.loads(captured['files']['folds.json'])
    if stored!=protocol or summary.get('protocol_sha256')!=fingerprint(protocol) or summary.get('new_operator_fits')!=140 or summary.get('baseline_refits')!=0 or summary.get('model_calls')!=0 or summary.get('ALP_approved') is not False or summary.get('scientific_validation') is not False:
        raise ResearchError('EVIDENCE_CHANGED','R59 protocol or execution identity changed.')
    policies=[p[0] for p in rebuild.POLICIES]
    rows=list(csv.DictReader(StringIO(captured['files']['results.csv'].decode('utf-8'))))
    if len(rows)!=3480 or set(folds)!=set(policies):raise ResearchError('EVIDENCE_CHANGED','R59 row or fold count changed.')
    grouped={p:[] for p in policies}; seen=set()
    for row in rows:
        if set(row)!={'policy','topography','chemistry','fold','target','interaction_prediction','chemistry_prediction','additive_prediction'}:raise ResearchError('EVIDENCE_CHANGED','R59 row schema changed.')
        try:
            p=row['policy'];t=int(row['topography']);c=int(row['chemistry']);f=int(row['fold'])
            nums={k:float(row[k]) for k in ('target','interaction_prediction','chemistry_prediction','additive_prediction')}
        except (ValueError,TypeError):raise ResearchError('EVIDENCE_CHANGED','Invalid R59 numeric record.') from None
        if p not in grouped or (p,t,c) in seen or not all(math.isfinite(v) for v in nums.values()):raise ResearchError('EVIDENCE_CHANGED','Invalid R59 row identity.')
        seen.add((p,t,c));grouped[p].append({'topography':t,'chemistry':c,'fold':f,**nums})
    computed={}
    for policy in policies:
        actual=sorted(grouped[policy],key=lambda r:(r['topography'],r['chemistry']))
        expected_rows=interaction._baseline_rows(base,geometry,policy)
        if len(actual)!=870 or len(folds[policy])!=35:raise ResearchError('EVIDENCE_CHANGED','R59 coverage changed.')
        for a,b in zip(actual,expected_rows):
            if any(a[k]!=b[k] for k in ('topography','chemistry','fold','target','chemistry_prediction','additive_prediction')):
                raise ResearchError('EVIDENCE_CHANGED','R59 records differ from verified R54 baseline.')
        for i,(f,b) in enumerate(zip(folds[policy],base['verified_folds'][policy]),1):
            if f['fold']!=i or f['train_keys']!=b['train_keys'] or f['test_keys']!=b['test_keys'] or f['held_out_topography']!=b['held_out_topography']:
                raise ResearchError('EVIDENCE_CHANGED','R59 grouped folds changed.')
        computed[policy]={}
        for name,key in (('interaction','interaction_prediction'),('additive','additive_prediction'),('chemistry','chemistry_prediction')):
            y=[r['target'] for r in actual]; pred=[r[key] for r in actual]; errs=[abs(x-z) for x,z in zip(y,pred)]
            ry=rebuild._ranks(y);rp=rebuild._ranks(pred)
            calc={'pooled_mae':statistics.mean(errs),'pooled_rmse':math.sqrt(statistics.mean((x-z)**2 for x,z in zip(y,pred))),
                  'pooled_spearman_midrank':statistics.correlation(ry,rp) if len(set(ry))>1 and len(set(rp))>1 else None,
                  'macro_fold_mae':statistics.mean(statistics.mean(errs[j] for j,r in enumerate(actual) if r['fold']==i) for i in range(1,36))}
            stated=summary['metrics'][policy][name]
            if set(calc)!=set(stated) or any(not ((v is None and stated[k] is None) or (v is not None and type(stated[k]) in (int,float) and math.isfinite(stated[k]) and math.isclose(v,stated[k],rel_tol=1e-10,abs_tol=1e-12))) for k,v in calc.items()):
                raise ResearchError('EVIDENCE_CHANGED','R59 metric arithmetic differs.')
            computed[policy][name]=calc
        for i,record in enumerate(summary['paired_fold_mae'][policy],1):
            subset=[r for r in actual if r['fold']==i]
            if not subset or record['fold']!=i or record['held_out_topography']!=subset[0]['topography'] or record['n']!=len(subset):raise ResearchError('EVIDENCE_CHANGED','R59 paired fold identity changed.')
            maes={k:statistics.mean(abs(r['target']-r[k+'_prediction']) for r in subset) for k in ('interaction','additive','chemistry')}
            values={**{k+'_mae':v for k,v in maes.items()},'delta_vs_additive':maes['interaction']-maes['additive'],'delta_vs_chemistry':maes['interaction']-maes['chemistry']}
            if any(not math.isclose(record[k],v,rel_tol=1e-10,abs_tol=1e-12) for k,v in values.items()):raise ResearchError('EVIDENCE_CHANGED','R59 paired fold arithmetic changed.')
        if len(summary['paired_fold_mae'][policy])!=35:raise ResearchError('EVIDENCE_CHANGED','R59 paired fold count changed.')
    improved=sum(m['interaction']['pooled_mae']<m['additive']['pooled_mae'] for m in computed.values())
    verdict='supports_fixed_representation' if improved==4 else 'no_support' if improved==0 else 'mixed_no_winner'
    if summary.get('primary_rule')!={'improved_policies':improved,'policy_count':4,'result':verdict}:raise ResearchError('EVIDENCE_CHANGED','R59 verdict differs from metrics.')
    return {'manifest_sha256':captured['manifest_sha256'],'protocol_sha256':fingerprint(protocol),'metrics':computed,'primary_rule':summary['primary_rule'],
            'baseline_manifest_sha256':base['manifest_sha256'],'rows_by_policy':grouped,'baseline_verified':base,'geometry':geometry,
            'limits':protocol['limits'],'r59_operator_fits':140,'recomputed_fit':False}
