"""Isolated P02 iteration ledger: two bounded model-selected numeric candidates."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import uuid

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import chemotopo_iteration_evidence as evidence, chemotopo_experiment_evidence, chemotopo_interaction, chemotopo_prediction, chemotopo_rebuild, chemotopo_data
from .c01_research import C01Research, ACTION_FIELDS
from .contracts import ResearchError, canonical, fingerprint, identifier

CANDIDATES={'fit_alpha10':10.0,'fit_alpha100':100.0}


def code_identity():
    modules=(evidence,chemotopo_experiment_evidence,chemotopo_interaction,chemotopo_prediction,chemotopo_rebuild,chemotopo_data)
    return hashlib.sha256(b''.join(Path(m.__file__).read_bytes() for m in modules)+Path(__file__).read_bytes()).hexdigest()


def candidate_predictions(rows,alpha):
    """R59 feature representation, with a caller-fixed Ridge penalty."""
    x=np.asarray([[r['chemistry'],*r['geometry']] for r in rows],dtype=float)
    y=np.asarray([r['target'] for r in rows],dtype=float);groups=np.asarray([r['topography'] for r in rows],dtype=int)
    if x.shape!=(len(rows),11) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('finite input required')
    output=np.empty(len(rows));folds=[]
    for number,(train,test) in enumerate(LeaveOneGroupOut().split(x,y,groups),1):
        if set(groups[train])&set(groups[test]) or not set(x[test,0])<=set(x[train,0]) or any(rows[i]['fold']!=number for i in test):raise ValueError('R59 grouped split mismatch')
        encoder=OneHotEncoder(handle_unknown='ignore',sparse_output=False).fit(x[train,:1]);scaler=StandardScaler().fit(x[train,1:])
        def transform(ids):
            chem=encoder.transform(x[ids,:1]);geo=scaler.transform(x[ids,1:])
            return np.concatenate((chem,geo,(chem[:,:,None]*geo[:,None,:]).reshape(len(ids),-1)),axis=1)
        model=Ridge(alpha=alpha,solver='svd',fit_intercept=True).fit(transform(train),y[train]);output[test]=model.predict(transform(test))
        folds.append({'fold':number,'held_out_topography':int(groups[test[0]]),'chemistry_categories':encoder.categories_[0].tolist(),
                      'geometry_scaler':{'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist()},
                      'train_keys':[[int(groups[i]),int(x[i,0])] for i in train], 'test_keys':[[int(groups[i]),int(x[i,0])] for i in test]})
    return output.tolist(),folds


def _calculate(config,request):
    from .chemotopo_rebuild import POLICIES, _ranks
    verified=evidence.inspect(config['source'],config['baseline'],config['interaction'],config['r59_manifest'])
    alpha=CANDIDATES[request['action']];results=[];folds={};metrics={}
    for policy,_,_ in POLICIES:
        rows=chemotopo_interaction._baseline_rows(verified['baseline_verified'],verified['geometry'],policy)
        prediction,ledger=candidate_predictions(rows,alpha)
        if len(rows)!=870 or len(ledger)!=35:raise ResearchError('EVIDENCE_CHANGED','Unexpected fit coverage.')
        old=sorted(verified['rows_by_policy'][policy],key=lambda r:(r['topography'],r['chemistry']))
        if any((r['topography'],r['chemistry'],r['fold'],r['target'])!=(o['topography'],o['chemistry'],o['fold'],o['target']) for r,o in zip(rows,old)):
            raise ResearchError('EVIDENCE_CHANGED','Candidate inputs differ from R59.')
        errors=[abs(r['target']-v) for r,v in zip(rows,prediction)]; target=[r['target'] for r in rows]
        ry=_ranks(target);rp=_ranks(prediction)
        metrics[policy]={'pooled_mae':statistics.mean(errors),'pooled_rmse':float(np.sqrt(np.mean(np.square(errors)))),
            'pooled_spearman_midrank':statistics.correlation(ry,rp) if len(set(ry))>1 and len(set(rp))>1 else None,
            'macro_fold_mae':statistics.mean(statistics.mean(errors[i] for i,r in enumerate(rows) if r['fold']==f) for f in range(1,36)),
            'r59_alpha1_mae':verified['metrics'][policy]['interaction']['pooled_mae'],
            'r54_additive_mae':verified['metrics'][policy]['additive']['pooled_mae'],
            'r54_chemistry_mae':verified['metrics'][policy]['chemistry']['pooled_mae']}
        for r,v in zip(rows,prediction):results.append({'policy':policy,'topography':r['topography'],'chemistry':r['chemistry'],'fold':r['fold'],'target':r['target'],'prediction':v})
        folds[policy]=ledger
    if len(results)!=3480:raise ResearchError('EVIDENCE_CHANGED','Incomplete numeric output.')
    return {'schema_version':'p02-iteration-candidate-v1','request_sha256':fingerprint(request),'action':request['action'],'alpha':alpha,
            'r59_manifest':config['r59_manifest'],'configuration_sha256':config['configuration_sha256'],
            'summary':{'alpha':alpha,'metrics':metrics,'fit_count':140,'model_weight_training':False,'scientific_validation':False,
                       'limits':['Exploratory fixed penalty comparison on reused sources and measured controls; not independent biological validation.',
                                 'ALP endpoint unconfirmed; no causal, clinical, extrapolation, or LLM-weight-training claim.']},
            'predictions':results,'folds':folds}


def _verify_complete(value,config):
    """Recheck artifact identity, inputs and metric arithmetic without refitting."""
    action=value.get('action'); summary=value.get('summary',{}); rows=value.get('predictions');folds=value.get('folds')
    if action not in CANDIDATES or value.get('alpha')!=CANDIDATES[action] or value.get('r59_manifest')!=config['r59_manifest'] or type(rows) is not list or len(rows)!=3480 or type(folds) is not dict:
        raise ResearchError('EVIDENCE_CHANGED','Candidate artifact shape differs.')
    if summary.get('alpha')!=CANDIDATES[action] or summary.get('fit_count')!=140 or summary.get('model_weight_training') is not False or summary.get('scientific_validation') is not False:
        raise ResearchError('EVIDENCE_CHANGED','Candidate execution summary differs.')
    verified=evidence.inspect(config['source'],config['baseline'],config['interaction'],config['r59_manifest'])
    policies=[x[0] for x in chemotopo_rebuild.POLICIES]
    if set(folds)!=set(policies) or set(summary.get('metrics',{}))!=set(policies):raise ResearchError('EVIDENCE_CHANGED','Candidate policies differ.')
    seen=set()
    for policy in policies:
        actual=sorted((r for r in rows if r.get('policy')==policy),key=lambda r:(r['topography'],r['chemistry']))
        original=chemotopo_interaction._baseline_rows(verified['baseline_verified'],verified['geometry'],policy)
        if len(actual)!=870 or len(folds[policy])!=35:raise ResearchError('EVIDENCE_CHANGED','Candidate row or fold count differs.')
        predictions=[];targets=[]
        for a,b in zip(actual,original):
            key=(policy,a['topography'],a['chemistry'])
            if key in seen or any(a[k]!=b[k] for k in ('topography','chemistry','fold','target')) or type(a.get('prediction')) not in (int,float) or not math.isfinite(a['prediction']):raise ResearchError('EVIDENCE_CHANGED','Candidate target, key, fold or prediction differs.')
            seen.add(key);predictions.append(a['prediction']);targets.append(a['target'])
        for f,reference in zip(folds[policy],verified['baseline_verified']['verified_folds'][policy]):
            if any(f[k]!=reference[k] for k in ('fold','held_out_topography','train_keys','test_keys')):raise ResearchError('EVIDENCE_CHANGED','Candidate grouped folds differ.')
        errors=[abs(a-b) for a,b in zip(targets,predictions)];ry=chemotopo_rebuild._ranks(targets);rp=chemotopo_rebuild._ranks(predictions)
        calculated={'pooled_mae':statistics.mean(errors),'pooled_rmse':math.sqrt(statistics.mean((a-b)**2 for a,b in zip(targets,predictions))),
            'pooled_spearman_midrank':statistics.correlation(ry,rp) if len(set(ry))>1 and len(set(rp))>1 else None,
            'macro_fold_mae':statistics.mean(statistics.mean(errors[i] for i,r in enumerate(actual) if r['fold']==f) for f in range(1,36)),
            'r59_alpha1_mae':verified['metrics'][policy]['interaction']['pooled_mae'],
            'r54_additive_mae':verified['metrics'][policy]['additive']['pooled_mae'],
            'r54_chemistry_mae':verified['metrics'][policy]['chemistry']['pooled_mae']}
        stated=summary['metrics'][policy]
        if set(stated)!=set(calculated) or any(not ((v is None and stated[k] is None) or (v is not None and type(stated[k]) in (int,float) and math.isfinite(stated[k]) and math.isclose(v,stated[k],rel_tol=1e-10,abs_tol=1e-12))) for k,v in calculated.items()):raise ResearchError('EVIDENCE_CHANGED','Candidate metric arithmetic differs.')
    if len(seen)!=3480:raise ResearchError('EVIDENCE_CHANGED','Candidate record identity differs.')


class IterationStudy(C01Research):
    def __init__(self,workspace):
        super().__init__(workspace);self.db=self.root/'iteration-study.sqlite'

    def create(self,source,baseline,interaction,goal):
        if type(goal) is not str or not 1<=len(goal.strip())<=2000:raise ResearchError('INVALID_REQUEST','Bounded goal required.')
        self._guard()
        if self.root.exists() and any(self.root.iterdir()):raise ResearchError('ALREADY_EXISTS','New workspace required.')
        for path in (source,baseline,interaction):
            fixed=Path(path).absolute().resolve()
            root=self.root.resolve()
            if root==fixed or root.is_relative_to(fixed) or fixed.is_relative_to(root):raise ResearchError('UNSAFE_PATH','Iteration workspace must not overlap evidence sources.')
        checked=evidence.inspect(source,baseline,interaction)
        config={'schema':'p02-native-iteration-v1','source':str(Path(source).absolute()),'baseline':str(Path(baseline).absolute()),
                'interaction':str(Path(interaction).absolute()),'goal':goal,'r59_manifest':checked['manifest_sha256'],
                'r59_protocol_sha256':checked['protocol_sha256'],'r54_manifest':checked['baseline_manifest_sha256'],
                'prior_metrics':checked['metrics'],'prior_primary_rule':checked['primary_rule'],'code_sha256':code_identity()}
        self.root.mkdir(parents=True,exist_ok=True)
        with self.db.open('xb'):pass
        with self._connect(True) as con:
            con.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE,request_id TEXT UNIQUE,request_sha256 TEXT,record TEXT);CREATE TABLE reservations(request_id TEXT PRIMARY KEY,request_sha256 TEXT NOT NULL,request_json TEXT NOT NULL,action TEXT UNIQUE NOT NULL, status TEXT NOT NULL);')
            con.execute('INSERT INTO meta VALUES(?,?,?)',(canonical(config),fingerprint(config),'active'))
        return self.observe()

    def _state(self,con):
        meta=con.execute('SELECT * FROM meta').fetchone();config=json.loads(meta['config'])
        if fingerprint(config)!=meta['sha256'] or config['code_sha256']!=code_identity():raise ResearchError('CODE_CHANGED','Frozen iteration configuration changed.')
        evidence.checked_files(config['interaction'],config['r59_manifest'])
        baseline=chemotopo_experiment_evidence.attachment(config['baseline'],config['source'],config['r54_manifest'])
        if baseline['protocol_sha256'] is None:raise ResearchError('EVIDENCE_CHANGED','Baseline protocol unavailable.')
        actions=[]
        for row in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            a=json.loads(row['record'])
            if a['ordinal']!=len(actions)+1 or a['ordinal']!=row['ordinal'] or a['id']!=row['id'] or a['request_id']!=row['request_id'] or fingerprint({k:a[k] for k in ACTION_FIELDS})!=row['request_sha256'] or fingerprint(a['result'])!=a['result_sha256']:
                raise ResearchError('EVIDENCE_CHANGED','Iteration action changed.')
            if a['action'] in CANDIDATES:
                verified=self._read_complete(a['request_id'],row['request_sha256'],config,a['action'])
                if verified['summary']!=a['result']['summary']:raise ResearchError('EVIDENCE_CHANGED','Candidate artifact differs from action.')
                payload=canonical(verified).encode('utf-8')
                if a['result']['artifact']!={'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}:
                    raise ResearchError('EVIDENCE_CHANGED','Candidate artifact reference differs from verified bytes.')
            actions.append(a)
        reservations=[dict(r) for r in con.execute('SELECT * FROM reservations ORDER BY rowid')]
        if len(reservations)>2 or any(r['status'] not in {'started','committed'} for r in reservations):raise ResearchError('EVIDENCE_CHANGED','Invalid candidate reservations.')
        for r in reservations:
            saved=json.loads(r['request_json'])
            linked=next((a for a in actions if a['request_id']==r['request_id']),None)
            if (fingerprint(saved)!=r['request_sha256'] or saved.get('request_id')!=r['request_id'] or saved.get('action')!=r['action'] or r['action'] not in CANDIDATES
                    or (r['status']=='committed')!=(linked is not None) or (linked is not None and (linked['action']!=r['action'] or fingerprint({k:linked[k] for k in ACTION_FIELDS})!=r['request_sha256']))):
                raise ResearchError('EVIDENCE_CHANGED','Candidate reservation binding changed.')
        state={'schema_version':config['schema'],'configuration_sha256':meta['sha256'],'status':meta['status'],'goal':config['goal'],
               'prior_evidence':{'r59_manifest_sha256':config['r59_manifest'],'r59_protocol_sha256':config['r59_protocol_sha256'],
                                 'r54_manifest_sha256':config['r54_manifest'],'metrics':config['prior_metrics'],'primary_rule':config['prior_primary_rule'],
                                 'provenance':'R54/R59 operator-run evidence, not model-selected; no independent biological validation.'},
               'citations':[{'citation_id':'p02-r54','source_sha256':config['r54_manifest']},{'citation_id':'p02-r59','source_sha256':config['r59_manifest']}],
               'actions':actions,'reservations':[{'action':r['action'],'status':r['status']} for r in reservations],
               'budget':{'fits_reserved':len(reservations)*140,'max_fits':280,'candidate_limit':2},
               'endpoint_gate':{'ALP_eligible':False,'biological_fit_eligible':False,'numerical_fit_eligible':True,'fit_scope':'fixed raw-red proxy numerical diagnostics only; no biological endpoint qualification'},'scientific_validation':False}
        state['observation_sha256']=fingerprint(state)
        return config,state,actions

    def observe(self):
        with self._connect() as con:return self._state(con)[1]

    def _path(self,request_id):
        path=self.root/'artifacts'/hashlib.sha256(request_id.encode('utf-8')).hexdigest()
        for item in (path,*path.parents):
            if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ResearchError('UNSAFE_PATH','Artifact path cannot redirect.')
        return path

    def _read_complete(self,request_id,request_sha,config,expected_action):
        root=self._path(request_id);manifest_path=root/'complete.json'
        try:
            raw=chemotopo_experiment_evidence._safe_file(manifest_path,10000);manifest=json.loads(raw)
            if manifest.get('complete') is not True or manifest.get('request_sha256')!=request_sha or manifest.get('configuration_sha256')!=fingerprint(config):raise ValueError('invalid completion identity')
            if type(manifest.get('bytes')) is not int or not 0<manifest['bytes']<=10000000:raise ValueError('invalid artifact size')
            payload=chemotopo_data._captured(root/'result.json',manifest['sha256'],manifest['bytes']);value=json.loads(payload)
            if value['request_sha256']!=request_sha or value['configuration_sha256']!=fingerprint(config) or value.get('action')!=expected_action:raise ValueError('invalid artifact binding')
            _verify_complete(value,config)
            return value
        except (OSError,ValueError,KeyError,TypeError,ResearchError):raise ResearchError('EVIDENCE_CHANGED','Candidate incomplete or invalid; no automatic rerun.') from None

    def _write_complete(self,request,value,config):
        root=self._path(request['request_id']);root.mkdir(parents=True,exist_ok=False)
        payload=canonical(value).encode('utf-8');digest=hashlib.sha256(payload).hexdigest()
        with (root/'result.tmp').open('xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.replace(root/'result.tmp',root/'result.json')
        manifest={'complete':True,'request_sha256':fingerprint(request),'configuration_sha256':fingerprint(config),'sha256':digest,'bytes':len(payload)}
        with (root/'complete.tmp').open('xb') as stream:stream.write(canonical(manifest).encode('utf-8'));stream.flush();os.fsync(stream.fileno())
        os.replace(root/'complete.tmp',root/'complete.json')
        return self._read_complete(request['request_id'],fingerprint(request),config,request['action'])

    def apply(self,request):
        digest=fingerprint(request);compute=False
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');config,state,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if old:
                if old['request_sha256']!=digest:raise ResearchError('IDEMPOTENCY_CONFLICT','Request differs from committed action.')
                return {'action':json.loads(old['record']),'replayed':True}
            reserved=con.execute('SELECT * FROM reservations WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if reserved:
                if reserved['request_sha256']!=digest:raise ResearchError('IDEMPOTENCY_CONFLICT','Request differs from reservation.')
                config_for_fit={**config,'configuration_sha256':fingerprint(config)}
            else:
                validate_request(request,state)
                if state['status']!='active':raise ResearchError('NOT_ACTIVE','Study is terminal.')
                if any(r['status']=='started' for r in state['reservations']):raise ResearchError('EVIDENCE_CHANGED','Previous candidate outcome unknown; no automatic rerun.')
                if request['action'] in CANDIDATES:
                    if any(r['action']==request['action'] for r in state['reservations']) or state['budget']['fits_reserved']>=280:raise ResearchError('BUDGET_EXHAUSTED','Candidate already reserved or budget exhausted.')
                    con.execute('INSERT INTO reservations VALUES(?,?,?,?,?)',(request['request_id'],digest,canonical(request),request['action'],'started'));compute=True
                    config_for_fit={**config,'configuration_sha256':fingerprint(config)}
                else:
                    result={'decision':request['action'],'scientific_validation':False,'model_weight_training':False}
                    record={**copy.deepcopy(request),'id':'p02i-'+uuid.uuid4().hex,'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
                    con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
                    con.execute('UPDATE meta SET status=?',('paused' if request['action']=='pause' else 'stopped',))
                    return {'action':record,'replayed':False}
        if compute:
            try:
                result=_calculate(config_for_fit,request)
                self._write_complete(request,result,config)
            except Exception as error:raise ResearchError('EVIDENCE_CHANGED','Candidate interrupted or failed; reservation retained and no automatic rerun.') from error
        complete=self._read_complete(request['request_id'],digest,config,request['action'])
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE');_,state,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request['request_id'],)).fetchone()
            if old:return {'action':json.loads(old['record']),'replayed':True}
            artifact={'sha256':hashlib.sha256(canonical(complete).encode('utf-8')).hexdigest(),'bytes':len(canonical(complete).encode('utf-8'))}
            result={'summary':complete['summary'],'artifact':artifact}
            record={**copy.deepcopy(request),'id':'p02i-'+uuid.uuid4().hex,'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
            con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],digest,canonical(record)))
            con.execute("UPDATE reservations SET status='committed' WHERE request_id=? AND status='started'",(request['request_id'],))
        return {'action':record,'replayed':False}


def validate_request(request,state):
    if type(request) is not dict or set(request)!=ACTION_FIELDS:raise ResearchError('INVALID_DECISION','Exact tool envelope required.')
    identifier(request['request_id'])
    if request['observation_sha256']!=state['observation_sha256']:raise ResearchError('STALE_OBSERVATION','Use the current observation.')
    if request['action'] not in set(CANDIDATES)|{'pause','stop'} or request['parameters']!={}:raise ResearchError('ACTION_NOT_AVAILABLE','Only fixed candidates and controls are offered.')
    if type(request['reason']) is not str or not 1<=len(request['reason'].strip())<=2000:raise ResearchError('INVALID_DECISION','Bounded reason required.')
    sources=request['source_citation_ids'];ids=request['evidence_action_ids']; known={a['id'] for a in state['actions']}
    if type(sources) is not list or len(sources)!=len(set(sources)) or set(sources)!={'p02-r54','p02-r59'}:raise ResearchError('INVALID_EVIDENCE','Cite both fixed source IDs.')
    if type(ids) is not list or len(ids)!=len(set(ids)) or not set(ids)<=known or (state['actions'] and state['actions'][-1]['id'] not in ids):raise ResearchError('INVALID_EVIDENCE','Cite exact latest action ID.')


def parse_decision(content,state,request_id):
    value=json.loads(content)
    if type(value) is not dict or 'request_id' in value:raise ResearchError('INVALID_DECISION','Runner owns request identity.')
    request={'request_id':request_id,**value};validate_request(request,state);return request
