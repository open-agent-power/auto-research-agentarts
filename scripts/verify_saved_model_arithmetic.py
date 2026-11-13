#!/usr/bin/env python3
"""Independent arithmetic application of archived saved Ridge parameters; never fit.

Only captured CSV raw values and declared selected-column log1p are supported.
Saved predictions are comparison outputs, never inputs to reconstruction.
"""
import argparse
import base64
import copy
from contextlib import ExitStack
import csv
import hashlib
import importlib.abc
import io
import json
import math
from pathlib import Path, PurePosixPath
import socket
import sqlite3
import sys
import unicodedata
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = 'e320404532fe80fd085ec1dbe07cf6e1abda6d8212a00f8295baa3c9371a1a58'
MANIFEST_SHA = '6c35932e8a9170c868b89e198479b4c7b52670b366720bda39ee6e9ebf40f1e1'
ABS_TOL, REL_TOL = 1e-10, 1e-12
CASES = {'concrete': ('repo/runs/cloud-concrete-local-20261113-01', 1030, 2, 8),
         'real-estate': ('repo/runs/g3-local-transfer-20261113-01/real-estate', 414, 2, 6),
         'slump': ('repo/runs/g3-local-transfer-20261113-01/slump', 103, 1, 7)}
PARAMS = {'alpha':1.0,'copy_X':True,'fit_intercept':True,'max_iter':None,
          'positive':False,'random_state':None,'solver':'auto','tol':0.0001}


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return digest(canonical(value).encode('utf-8'))


def parse(raw):
    def members(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'Duplicate JSON key')
            result[key]=value
        return result
    def reject(value):
        raise AssertionError('Nonfinite JSON constant '+value)
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=members,parse_constant=reject)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write('\n')


def file_identity(path):
    require(path.is_file() and not path.is_symlink(),'Expected regular file '+str(path))
    with path.open('rb') as stream:
        hashed=hashlib.file_digest(stream,'sha256').hexdigest()
    return {'bytes':path.stat().st_size,'sha256':hashed}


def checked_absolute(path):
    path=Path(path)
    require('..' not in path.parts,'Parent traversal is not an output/input path')
    path=path.absolute()
    require(all(not p.is_symlink() for p in (path,*path.parents)),'Input/output path cannot use symlinks')
    return path


def output_boundaries(archive):
    prefix='repo/runs/g5-native-cases-20261113-01/'
    freeze=archive.json(prefix+'retrieval/freeze.json')
    require(freeze['protected']==archive.json(prefix+'scheduling/freeze.json')['protected'],'Common original protection list')
    trees=[Path(p) for p in freeze['protected_tree_roots']]
    trees += [REPO/'runs/g5-native-cases-20261113-01'/kind for kind in ('retrieval','scheduling')]
    files=[Path(p) for p in freeze['protected']]
    files += [Path(row['source_path']) for name,row in archive.entries.items() if name.startswith(prefix)]
    trees += [REPO/name for name in ('src','scripts','docs','frontend','tests','examples','deploy','.agent','.git','work')]
    return trees,files


def checked_output(path, archive_path, trees, files):
    path=checked_absolute(path)
    forbidden=[checked_absolute(p) for p in [archive_path,*trees,*files]]
    require(not any(path==p or path.is_relative_to(p) or p.is_relative_to(path) for p in forbidden),
            'Output overlaps original archive, protected evidence or source tree')
    require(not path.exists(),'Fresh arithmetic output required')
    require(not any((parent/name).exists() for parent in (path,*path.parents)
                    for name in ('project.sqlite','workbench.sqlite')),'Output outside project/manager')
    return path


def number(value):
    require(type(value) in (int,float) and math.isfinite(value),'Finite real number required')
    return value


def comparison(actual, saved):
    number(actual);number(saved)
    limit=max(ABS_TOL, REL_TOL*max(abs(actual),abs(saved)))
    error=abs(actual-saved)
    return {'actual':actual,'saved':saved,'signed_diff':actual-saved,'abs_diff':error,
            'actual_limit':limit,'passed':error<=limit}


def unpack(asset, maximum):
    require(type(asset) is dict and set(asset)=={'file_name','sha256','bytes','bytes_base64'},'Captured asset shape')
    require(type(asset['bytes']) is int and 0<asset['bytes']<=maximum,'Captured asset bound')
    require(type(asset['bytes_base64']) is str and len(asset['bytes_base64'])<=4*((maximum+2)//3),'Base64 bound')
    require(type(asset['file_name']) is str and PurePosixPath(asset['file_name']).name==asset['file_name'] and '\\' not in asset['file_name'],'Single source filename')
    raw=base64.b64decode(asset['bytes_base64'],validate=True)
    require(len(raw)==asset['bytes'] and digest(raw)==asset['sha256'],'Captured asset byte/SHA identity')
    return raw


def captured_source(raw):
    require(len(raw)<=12*1024**2,'Source packet bound')
    packet=parse(raw)
    require(set(packet)=={'schema_version','source','spec_source','spec','scope','snapshot_sha256'}
            and packet['schema_version']=='tabular-quality-source-v1','Captured tabular source schema')
    require(packet['snapshot_sha256']==fingerprint({k:v for k,v in packet.items() if k!='snapshot_sha256'}),'Source canonical snapshot')
    data=unpack(packet['source'],8*1024**2);spec=parse(unpack(packet['spec_source'],64*1024))
    require(canonical(spec)==canonical(packet['spec']) and packet['spec_source']['file_name']=='spec.json'
            and packet['source']['file_name']==spec['file'],'Original spec echo/names')
    require(spec['schema_version']=='tabular-quality-spec-v1' and spec['delimiter'] in (',','\t'),'CSV spec')
    for key in ('numeric_columns','group_columns','key_columns','missing_tokens'):
        require(type(spec[key]) is list and len(set(spec[key]))==len(spec[key]) and all(type(v) is str for v in spec[key]),'Distinct string declarations')
    require('' in spec['missing_tokens'] and spec['target_column'] in spec['numeric_columns'],'Declared target/missing tokens')
    scope={'domain':'data','contract':'tabular-quality-v1','dataset_label':spec['dataset_label'],
           'sample_unit':spec['sample_unit'],'target_column':spec['target_column'],'target_unit':spec['target_unit'],
           'source_sha256':digest(data),'group_columns':spec['group_columns'],'key_columns':spec['key_columns'],
           'numeric_columns':spec['numeric_columns'],'target_status':'declared_unconfirmed'}
    require(canonical(packet['scope'])==canonical(scope),'Original typed scope')
    text=data.decode('utf-8-sig');require('\x00' not in text,'NUL in captured CSV')
    reader=csv.reader(io.StringIO(text,newline=''),delimiter=spec['delimiter'],strict=True)
    header=next(reader);require(1<=len(header)<=128 and all(v and v==v.strip() for v in header),'CSV header')
    require(len(set(unicodedata.normalize('NFKC',v).casefold() for v in header))==len(header),'Ambiguous CSV header')
    require(set(spec['numeric_columns']+spec['group_columns']+spec['key_columns'])<=set(header),'Declared source columns')
    records=[]
    for index,values in enumerate(reader,1):
        require(index<=50000 and len(values)==len(header),'CSV logical row bound/width')
        records.append({'logical_record':index,'physical_line_end':reader.line_num,'values':dict(zip(header,values))})
    return packet,spec,records


def training_rows(spec, records, training):
    require(set(training) in ({'feature_columns','split_group_columns','fit_limit'},
                             {'feature_columns','split_group_columns','fit_limit','input_transforms'}),'Only direct raw or selected log1p training')
    features,groups=training['feature_columns'],training['split_group_columns']
    require(type(features) is list and 1<=len(features)<=16 and len(set(features))==len(features)
            and set(features)<=set(spec['numeric_columns']) and spec['target_column'] not in features,'Declared feature inputs')
    require(type(groups) is list and groups and len(set(groups))==len(groups)
            and set(groups)<=set(spec['group_columns']) and not set(features)&set(spec['group_columns']),'Declared group inputs')
    require(type(training['fit_limit']) is int and training['fit_limit']>=0,'Original declared fit limit')
    transforms=training.get('input_transforms',{})
    require(type(transforms) is dict and ('input_transforms' not in training or bool(transforms))
            and set(transforms)<=set(features) and all(v=='log1p' for v in transforms.values()),'Only declared selected-column log1p')
    missing=set(spec['missing_tokens']);rows={};excluded=[]
    def finite(token):
        if token in missing:return None
        try:value=float(token)
        except (ValueError,OverflowError):return None
        return value if math.isfinite(value) else None
    for row in records:
        values=row['values'];target=finite(values[spec['target_column']]);inputs=[finite(values[name]) for name in features]
        labels=[values[name] for name in groups];reasons=[]
        if target is None:reasons.append('target_missing_or_nonfinite')
        if any(value is None for value in inputs):reasons.append('feature_missing_or_nonfinite')
        if any(label in missing for label in labels):reasons.append('split_group_missing')
        loc={k:row[k] for k in ('logical_record','physical_line_end')}
        if reasons:excluded.append({**loc,'reasons':reasons})
        else:rows[row['logical_record']]={**loc,'observed':target,'features':inputs,'groups':labels}
    return rows,excluded


def reconstruct(features, training, fold):
    columns=training['feature_columns'];require(len(features)==len(columns),'Raw input dimension')
    values=[number(v) for v in features]
    for index,name in enumerate(columns):
        if name in training.get('input_transforms',{}):
            require(training['input_transforms'][name]=='log1p' and values[index]>-1,'log1p input domain')
            values[index]=math.log1p(values[index])
    means,scales,coefficients=(fold[k] for k in ('scaler_mean','scaler_scale','ridge_coefficients'))
    require(all(type(v) is list and len(v)==len(columns) for v in (means,scales,coefficients)),'Saved parameter dimension')
    require(all(number(v)>0 for v in scales),'Positive saved scale')
    standardized=[(value-number(mean))/scale for value,mean,scale in zip(values,means,scales)]
    result=math.fsum(z*number(coef) for z,coef in zip(standardized,coefficients))+number(fold['ridge_intercept'])
    return number(result)


def verify_analysis(packet, spec, records, analysis):
    binding=analysis['design_binding'];training=binding['training'];rows,excluded=training_rows(spec,records,training)
    require(analysis['schema_version']=='ridge-validation-v1' and analysis['check']=='group_cv','Saved grouped Ridge schema')
    require(analysis['source_snapshot_sha256']==binding['source_snapshot_sha256']==packet['snapshot_sha256']
            and analysis['target_column']==binding['target_column']==spec['target_column'] and analysis['target_unit']==spec['target_unit'],'Source/target/binding identity')
    protocol=analysis['protocol'];folds=analysis['folds']
    require(2<=len(folds)<=5 and all(type(f['fold']) is int for f in folds)
            and [f['fold'] for f in folds]==list(range(1,len(folds)+1)),'Ordered complete saved folds')
    required={'splitter':'GroupKFold','n_splits':len(folds),'shuffle':False,'random_state':None,'ridge_alpha':1.0,
              'preprocessing':'StandardScaler.fit on training rows only','reference':'training-fold target mean',
              'feature_columns':training['feature_columns'],'split_group_columns':training['split_group_columns'],
              'grouping_semantics':'operator-declared source columns'}
    if 'input_transforms' in training:
        selected=[name for name in training['feature_columns'] if name in training['input_transforms']]
        required.update(input_basis={'kind':'log1p','source_columns':training['feature_columns'],'transformed_columns':selected,
                                     'order':'raw_log1p_then_fold_standardization'},
                        model_input_terms=['log1p('+name+')' if name in selected else name for name in training['feature_columns']])
    require(canonical(protocol)==canonical(required),'Exact original transform/protocol declaration')
    require(excluded==analysis['exclusions'],'Exact complete-case exclusions')
    oof=analysis['oof'];saved={row['logical_record']:row for row in oof}
    require(all(type(row['logical_record']) is int for row in oof) and len(saved)==len(oof)==len(rows)
            and set(saved)==set(rows) and [row['logical_record'] for row in oof]==sorted(rows),'Complete unique ordered OOF coverage')
    all_ids=set(rows);tested=set();out=[];fold_results=[]
    for fold in folds:
        require(canonical(fold['model_params'])==canonical(PARAMS),'Saved fixed Ridge hyperparameters')
        train,test=fold['train_records'],fold['test_records']
        require(all(type(v) is list and v and all(type(i) is int for i in v) and v==sorted(set(v)) for v in (train,test)),'Exact unique sorted row IDs')
        require(set(train).isdisjoint(test) and set(train)|set(test)==all_ids and set(test).isdisjoint(tested),'Train/test complement and OOF coverage')
        require({tuple(rows[i]['groups']) for i in train}.isdisjoint({tuple(rows[i]['groups']) for i in test}),'No source-declared group leakage')
        tested.update(test)
        reference=math.fsum(rows[i]['observed'] for i in train)/len(train)
        ref_check=comparison(reference,fold['reference_prediction']);fold_rows=[]
        for identifier in test:
            row=rows[identifier];prior=saved[identifier]
            require(type(prior['fold']) is int and type(prior['physical_line_end']) is int
                    and prior['fold']==fold['fold'] and prior['physical_line_end']==row['physical_line_end']
                    and prior['groups']==row['groups'] and number(prior['observed'])==row['observed'],'Saved source row/target/group/fold identity')
            # Saved predicted/reference fields are read only after both reconstructions.
            predicted=reconstruct(row['features'],training,fold)
            pred_check=comparison(predicted,prior['predicted']);reference_check=comparison(reference,prior['reference_prediction'])
            value={k:row[k] for k in ('logical_record','physical_line_end','groups','observed')}
            value.update(fold=fold['fold'],prediction=pred_check,reference=reference_check,
                         candidate_abs_error=abs(row['observed']-predicted),reference_abs_error=abs(row['observed']-reference),
                         negative_prediction=predicted<0,saved_negative_prediction=prior['predicted']<0)
            value['passed']=pred_check['passed'] and reference_check['passed'] and value['negative_prediction']==value['saved_negative_prediction']
            out.append(value);fold_rows.append(value)
        fold_results.append({'fold':fold['fold'],'train_rows':len(train),'test_rows':len(test),
                             'reference':ref_check,'max_prediction_abs_diff':max(r['prediction']['abs_diff'] for r in fold_rows),
                             'max_prediction_actual_limit':max(r['prediction']['actual_limit'] for r in fold_rows),
                             'passed':ref_check['passed'] and all(r['passed'] for r in fold_rows)})
    require(tested==all_ids,'Each complete source row held out exactly once')
    out.sort(key=lambda row:row['logical_record']);summary=analysis['summary'];n=len(out)
    require(summary['n']==n and summary['input_n']==len(records) and summary['excluded']==len(excluded)
            and summary['group_count']==len({tuple(row['groups']) for row in rows.values()}),'Original complete-case/group counts')
    candidate=math.fsum(row['candidate_abs_error'] for row in out)/n
    reference=math.fsum(row['reference_abs_error'] for row in out)/n
    improvement=1-candidate/reference if reference else None
    metrics={'candidate_mae':comparison(candidate,summary['candidate_mae']),'reference_mae':comparison(reference,summary['reference_mae'])}
    require(improvement is not None,'This scope requires a nonzero reference MAE')
    metrics['improvement']=comparison(improvement,summary['improvement'])
    require(summary['status']=='computed' and summary['reason'] is None and summary['outperforms_reference']==(improvement>0),'Saved metric interpretation')
    return {'passed':all(r['passed'] for r in fold_results) and all(r['passed'] for r in metrics.values()),
            'rows':out,'folds':fold_results,'metrics':metrics,'negative_rows':[r['logical_record'] for r in out if r['negative_prediction']],
            'max_prediction_abs_diff':max(r['prediction']['abs_diff'] for r in out),'model_rows':n,'model_dimensions':len(training['feature_columns']),
            'saved_partition_sha256':fingerprint([{k:f[k] for k in ('fold','train_records','test_records')} for f in folds])}


class Guards(importlib.abc.MetaPathFinder):
    def __init__(self):self.calls={};self.stack=ExitStack()
    def deny(self,label):
        self.calls[label]=self.calls.get(label,0)+1
        raise AssertionError('Forbidden arithmetic verifier operation: '+label)
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] not in sys.stdlib_module_names:
            self.deny('import:'+fullname)
        return None
    def __enter__(self):
        require(not any(n.split('.')[0] in ('autoresearch','sklearn','numpy','scipy') for n in sys.modules),'Start independent stdlib-only process')
        sys.meta_path.insert(0,self)
        for obj,name in ((socket.socket,'connect'),(socket.socket,'connect_ex'),(socket.socket,'sendto'),
                         (socket,'create_connection'),(socket,'getaddrinfo')):
            self.stack.enter_context(patch.object(obj,name,side_effect=lambda *a,_label=name,**k:self.deny('socket:'+_label)))
        return self
    def __exit__(self,*args):
        self.stack.close();sys.meta_path.remove(self)


def protected_snapshot(archive):
    native='repo/runs/g5-native-cases-20261113-01/'
    manifest=archive.json('archive-manifest.json');entries={r['path']:r for r in manifest['entries']}
    freeze=archive.json(native+'retrieval/freeze.json');expected=dict(freeze['protected'])
    for name,row in entries.items():
        if name.startswith(native):expected[row['source_path']]={'bytes':row['bytes'],'sha256':row['sha256']}
    require(len(expected)==494,'Exact original 369 plus 125 native file inventory')
    actual={name:file_identity(Path(name)) for name in expected}
    require(actual==expected,'Original live 494 identities differ from archived protection')
    roots=freeze['protected_tree_roots']+[str(REPO/'runs/g5-native-cases-20261113-01'/kind) for kind in ('retrieval','scheduling')]
    for root in map(Path,roots):
        paths=list(root.rglob('*'));require(all(not p.is_symlink() for p in paths),'Protected tree contains links')
        observed={str(p) for p in paths if p.is_file()}
        require(observed=={p for p in expected if p.startswith(str(root)+'/')},'Protected tree complete inventory')
    return actual


class Archive:
    def __init__(self,path):
        path=checked_absolute(path)
        self.path=path;self.identity=file_identity(path)
        require(self.identity['sha256']==ARCHIVE_SHA,'Exact predeclared archive SHA')
        self.zip=zipfile.ZipFile(path)
        names=self.zip.namelist();require(len(names)==len(set(names))==930,'Original unique archive member count')
        require(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in names),'Safe member paths')
        raw=self.zip.read('archive-manifest.json');require(digest(raw)==MANIFEST_SHA,'Original manifest identity')
        self.entries={r['path']:r for r in parse(raw)['entries']}
        require(set(self.entries)|{'archive-manifest.json'}==set(names),'Archive manifest inventory')
        self.reads=set()
    def raw(self,name):
        require(name in self.entries and self.entries[name]['bytes']<=16*1024**2,'Bounded manifested input')
        info=self.zip.getinfo(name);require(not info.flag_bits&1 and info.file_size==self.entries[name]['bytes'],'Regular unencrypted input size')
        raw=self.zip.read(name);require(digest(raw)==self.entries[name]['sha256'],'Archive member original SHA')
        self.reads.add(name);return raw
    def json(self,name):
        if name=='archive-manifest.json':return parse(self.zip.read(name))
        return parse(self.raw(name))
    def project(self,prefix):
        names=[n for n in self.entries if n.startswith(prefix+'/manager/projects/') and n.endswith('/project.sqlite')]
        require(len(names)==1,'One archived original project')
        database=sqlite3.connect(':memory:');database.deserialize(self.raw(names[0]));database.execute('PRAGMA query_only=ON')
        state=parse(database.execute('SELECT record FROM project').fetchone()[0].encode())
        actions=[parse(r[0].encode()) for r in database.execute('SELECT record FROM actions ORDER BY rowid')]
        database.close();return names[0].rsplit('/',1)[0],state,actions


def verify(archive_path, output):
    archive=Archive(archive_path)
    try:
        output=checked_output(output,archive.path,*output_boundaries(archive))
        output.mkdir(parents=True)
    except BaseException:
        archive.zip.close()
        raise
    results={};result={'status':'failed_closed','abs_tolerance':ABS_TOL,'relative_tolerance':REL_TOL}
    try:
        save(output/'protected-before.json',protected_snapshot(archive))
        with Guards() as guard:
            for case,(prefix,count,versions,dimensions) in CASES.items():
                project,state,actions=archive.project(prefix);packet_raw=archive.raw(project+'/source.json')
                packet,spec,records=captured_source(packet_raw)
                require(digest(packet_raw)==state['registration']['source_sha256'] and packet['snapshot_sha256']==state['source_snapshot_sha256'],'Registered source packet identity')
                require(canonical(packet['scope'])==canonical(state['source_scope']),'Registered source scope')
                cv=[a for a in actions if a['command']=='data.ridge-group-validation'];require(len(cv)==versions,'Original model count')
                case_models=[]
                for action in cv:
                    require(action['status']=='completed' and action['source_snapshot_sha256']==packet['snapshot_sha256'] and action['project_id']==state['id'] and action['run_id']==state['run_id'] and action['code_identity']==state['code_identity'],'Action project/source/code identity')
                    request={k:action[k] for k in ('project_id','command','dimension','source_snapshot_sha256','parameters','evaluation_ref','design_binding')}
                    require(fingerprint(request)==action['request_sha256'],'Original exact request identity')
                    member=project+'/'+action['artifact'];envelope=archive.json(member)
                    require(envelope['sha256']==action['result_sha256']==fingerprint({k:v for k,v in envelope.items() if k!='sha256'}),'Canonical original result envelope')
                    require(all(envelope[k]==action[k] for k in ('code_identity','request_sha256','source_snapshot_sha256')) and envelope['action_id']==action['id'],'Action artifact linkage')
                    tool=envelope['tool_result'];analysis=tool['result']['analysis'];binding=analysis['design_binding']
                    require(binding in state['design_revisions'] and canonical(binding)==canonical(action['design_binding']) and binding['project_id']==state['id'],'Original frozen design revision')
                    require(analysis['predecessor']==action['parameters'],'Quality predecessor linkage')
                    predecessor=next(a for a in actions if a['id']==action['parameters']['based_on_action_id'])
                    require(predecessor['result_sha256']==action['parameters']['based_on_result_sha256'],'Original predecessor result')
                    require(tool['tool_id']==action['command'] and tool['adapter_version']=='2' and tool['status']=='completed' and tool['model_calls']==0 and tool['new_fits']==5 and tool['scientific_validation'] is False,'Original producer metadata')
                    require(analysis['usage']=={'ridge_fit_attempts':5,'preprocessing_fit_attempts':5,'fit_attempts':10}
                            and 'group_cv' in binding['resource']['checks'],'Original protocol usage/design permission')
                    instance=action['method_instance'];inputs=instance['input_bindings']
                    require(instance['definition_ref']=={'id':action['command'],'version':'2'}
                            and instance['evaluation_ref']==action['evaluation_ref']=='ridge-validation-group_cv-v1'
                            and instance['parameters']==action['parameters'] and inputs['training']==binding['training']
                            and inputs['design_revision']==binding['version'] and inputs['resource_id']==binding['resource']['id']
                            and inputs['resource_version']==binding['resource']['version']
                            and inputs['source_snapshot_sha256']==packet['snapshot_sha256'],'Original method-instance inputs')
                    scope={**packet['scope'],'contract':'ridge-group_cv-v1','input_contract':packet['scope']['contract']}
                    require(canonical(analysis['scope'])==canonical(tool['result']['scope'])==canonical(scope)
                            and tool['result']['source_snapshot_sha256']==packet['snapshot_sha256']
                            and tool['result']['predecessor']==action['parameters'],'Result source/group scope')
                    refs=tool['evidence_refs'];require(len(refs)==1 and refs[0]['source_snapshot_sha256']==packet['snapshot_sha256']
                            and refs[0]['source_sha256']==packet['source']['sha256'] and refs[0]['file_name']==spec['file']
                            and refs[0]['locator']['kind']=='csv_logical_records' and refs[0]['locator']['first']==1
                            and refs[0]['locator']['last']==count,'Original complete source evidence locator')
                    require(action['fit_reservation']==10 and action['fit_events']==[{'estimator':name,'fold':fold,'index':2*fold-1+offset,'status':'completed'} for fold in range(1,6) for offset,name in enumerate(('scaler','ridge'))],'Original 10 completed estimator records')
                    model=verify_analysis(packet,spec,records,analysis)
                    require(len(records)==model['model_rows']==count and not analysis['exclusions']
                            and model['model_dimensions']==dimensions and len(model['folds'])==5,'Predeclared row/dimension/fold inventory')
                    label=case+'-v'+str(binding['resource']['version']);rowfile=output/(label+'-rows.jsonl')
                    with rowfile.open('x') as stream:
                        for row in model.pop('rows'):stream.write(canonical(row)+'\n')
                    model.update(action_id=action['id'],artifact_member=member,artifact_sha256=archive.entries[member]['sha256'],
                                 result_sha256=action['result_sha256'],source_snapshot_sha256=packet['snapshot_sha256'],
                                 captured_csv_sha256=packet['source']['sha256'],training=binding['training'],design_binding=binding,
                                 row_output=rowfile.name,row_output_identity=file_identity(rowfile))
                    save(output/(label+'-summary.json'),model);case_models.append(model)
                require([m['design_binding']['resource']['version'] for m in case_models]==list(range(1,versions+1)),'Ordered original resource versions')
                if versions==2:
                    require(case_models[1]['design_binding']['resource']['parent_version']==1 and case_models[0]['design_binding']['resource']['id']==case_models[1]['design_binding']['resource']['id'],'Original CV parent-child resource identity')
                    require(case_models[0]['saved_partition_sha256']==case_models[1]['saved_partition_sha256'],'Raw/candidate exact saved partition')
                results[case]={'project_id':state['id'],'run_id':state['run_id'],'original_budget_record':state['budget'],'models':case_models}
            require(sum(m['model_rows'] for c in results.values() for m in c['models'])==2991,'All 2991 saved predictions covered')
            require(not guard.calls,'No prohibited operation attempted')
        result.update(status='saved_model_arithmetic_verified' if all(m['passed'] for c in results.values() for m in c['models']) else 'arithmetic_mismatch',
                      cases=results,archive=archive.identity,archive_members_read=sorted(archive.reads),
                      verifier_sha256=digest(Path(__file__).read_bytes()),forbidden_call_counts=guard.calls,
                      reconstructed_rows=2991,saved_models=25,new_fits=0,new_predictions_via_estimator=0,model_api_calls=0,
                      scope='Independent fixed saved-parameter application only; no training, scaler re-estimation, coefficient optimality or unseen evaluation')
        require(file_identity(archive_path)==archive.identity,'Original archive unchanged')
        save(output/'protected-after.json',protected_snapshot(archive))
        require(parse((output/'protected-before.json').read_bytes())==parse((output/'protected-after.json').read_bytes()),'Original 494 protection unchanged')
        save(output/'result.json',result)
        require(result['status']=='saved_model_arithmetic_verified','Arithmetic mismatch; fixed tolerance not widened')
    except BaseException as error:
        if not (output/'result.json').exists():
            result.update(error={'type':type(error).__name__,'message':str(error)},cases=results)
            save(output/'result.json',result)
        raise
    finally:
        archive.zip.close()
        if not (output/'protected-after.json').exists():
            reopened=Archive(archive_path)
            try:save(output/'protected-after.json',protected_snapshot(reopened))
            finally:reopened.zip.close()
        save(output/'manifest.json',{p.name:file_identity(p) for p in output.iterdir() if p.is_file()})
    return result


def self_test():
    checks=0
    def check(value):
        nonlocal checks
        checks+=1;require(value,'Hand fixture '+str(checks))
    training={'feature_columns':['a','age'],'split_group_columns':['group'],'fit_limit':4}
    fold={'scaler_mean':[2,4],'scaler_scale':[2,2],'ridge_coefficients':[3,-1],'ridge_intercept':.5}
    check(reconstruct([4,8],training,fold)==1.5);check(reconstruct([0,8],training,fold)==-4.5)
    log={**training,'input_transforms':{'age':'log1p'}}
    logfold={**fold,'scaler_mean':[2,0],'scaler_scale':[2,1],'ridge_coefficients':[3,-2]}
    check(comparison(reconstruct([4,math.e-1],log,logfold),1.5)['passed'])
    for features,config in (([4,-1],logfold),([4,-2],logfold),([4,8],{**fold,'scaler_scale':[0,2]}),
                             ([4,8],{**fold,'scaler_mean':[float('nan'),4]}),([4],fold)):
        try:reconstruct(features,log,config)
        except AssertionError:check(True)
        else:check(False)
    check(comparison(1+1e-11,1)['passed']);check(not comparison(1+1e-8,1)['passed'])
    check(comparison(1e6+5e-7,1e6)['passed']);check(not comparison(1e6+2e-6,1e6)['passed'])
    try:parse(b'{"x":1,"x":2}')
    except AssertionError:check(True)
    else:check(False)
    with Guards() as guard:
        try:__import__('autoresearch')
        except AssertionError:check(True)
        else:check(False)
        check(guard.calls=={'import:autoresearch':1})
    # Fully hand-computed, deliberately non-trained two-fold example.
    spec={'schema_version':'tabular-quality-spec-v1','file':'fixture.csv','dataset_label':'Hand fixture',
          'source_url':'local://hand','license_note':'Own hand fixture','sample_unit':'one row',
          'numeric_columns':['x','y'],'group_columns':['group'],'key_columns':[],
          'target_column':'y','target_unit':'units','delimiter':',','missing_tokens':[''],
          'provenance':{'origin_sha256':'0'*64,'description':'Constructed arithmetic, not a fit'}}
    def asset(name,raw):return {'file_name':name,'bytes':len(raw),'sha256':digest(raw),'bytes_base64':base64.b64encode(raw).decode()}
    data=b'x,y,group\n0,1,A\n2,3,B\n4,5,C\n6,7,D\n'
    scope={'domain':'data','contract':'tabular-quality-v1','dataset_label':'Hand fixture','sample_unit':'one row',
           'target_column':'y','target_unit':'units','source_sha256':digest(data),'group_columns':['group'],
           'key_columns':[],'numeric_columns':['x','y'],'target_status':'declared_unconfirmed'}
    payload={'schema_version':'tabular-quality-source-v1','source':asset('fixture.csv',data),
             'spec_source':asset('spec.json',canonical(spec).encode()),'spec':spec,'scope':scope}
    payload['snapshot_sha256']=fingerprint(payload)
    packet,spec,records=captured_source(canonical(payload).encode());check(len(records)==4 and records[-1]['physical_line_end']==5)
    train={'feature_columns':['x'],'split_group_columns':['group'],'fit_limit':4}
    binding={'training':train,'source_snapshot_sha256':packet['snapshot_sha256'],'target_column':'y'}
    proto={'splitter':'GroupKFold','n_splits':2,'shuffle':False,'random_state':None,'ridge_alpha':1.0,
           'preprocessing':'StandardScaler.fit on training rows only','reference':'training-fold target mean',
           'feature_columns':['x'],'split_group_columns':['group'],'grouping_semantics':'operator-declared source columns'}
    folds=[{'fold':i,'train_records':tr,'test_records':te,'reference_prediction':ref,
            'model_params':copy.deepcopy(PARAMS),'scaler_mean':[mean],'scaler_scale':[1],
            'ridge_coefficients':[2],'ridge_intercept':1} for i,tr,te,ref,mean in
           ((1,[1,2],[3,4],2,1),(2,[3,4],[1,2],6,5))]
    oof=[{'logical_record':i,'physical_line_end':i+1,'observed':y,'predicted':p,'groups':[g],
          'fold':f,'reference_prediction':r} for i,y,p,g,f,r in
         ((1,1,-9,'A',2,6),(2,3,-5,'B',2,6),(3,5,7,'C',1,2),(4,7,11,'D',1,2))]
    analysis={'schema_version':'ridge-validation-v1','check':'group_cv','design_binding':binding,'protocol':proto,
              'source_snapshot_sha256':packet['snapshot_sha256'],'target_column':'y','target_unit':'units',
              'folds':folds,'oof':oof,'exclusions':[],
              'summary':{'n':4,'input_n':4,'excluded':0,'group_count':4,'candidate_mae':6,'reference_mae':4,
                         'improvement':-.5,'outperforms_reference':False,'status':'computed','reason':None}}
    reconstructed=verify_analysis(packet,spec,records,analysis)
    check(reconstructed['passed'] and reconstructed['negative_rows']==[1,2])
    check(reconstructed['metrics']['candidate_mae']['actual']==6 and reconstructed['metrics']['reference_mae']['actual']==4)
    wrong=copy.deepcopy(analysis);wrong['oof'][0]['predicted']+=1e-7
    check(not verify_analysis(packet,spec,records,wrong)['passed'])
    for wrong in ({**analysis,'folds':[dict(folds[0],train_records=[1,1]),folds[1]]},
                  {**analysis,'oof':oof[:-1]},
                  {**analysis,'protocol':dict(proto,ridge_alpha=2.0)}):
        try:verify_analysis(packet,spec,records,wrong)
        except AssertionError:check(True)
        else:check(False)
    for invalid in ({**train,'input_basis':'univariate_cubic'}, {**train,'input_transforms':{'x':'sqrt'}}):
        try:training_rows(spec,records,invalid)
        except AssertionError:check(True)
        else:check(False)
    broken=copy.deepcopy(packet);broken['source']['sha256']='0'*64
    broken['snapshot_sha256']=fingerprint({k:v for k,v in broken.items() if k!='snapshot_sha256'})
    try:captured_source(canonical(broken).encode())
    except AssertionError:check(True)
    else:check(False)
    # These calls only validate names; no target directory is ever created.
    oldcase=REPO/'runs/cloud-concrete-local-20261113-01'
    archive_name=REPO/'runs/sprint-005-delivery/native-cpu-reproduction-evidence.zip'
    scratch=REPO.parent/'work'/'saved-model-arithmetic-preflight-only-uncreated'
    forbidden_trees=[oldcase,REPO/'src',REPO/'work']
    for target in (oldcase/'arithmetic-preflight-must-not-exist',
                   REPO/'src/autoresearch/arithmetic-preflight-must-not-exist',
                   REPO/'work/study-source-0ceb274/arithmetic-preflight-must-not-exist',
                   archive_name/'nested-output',scratch/'..'/'escaped-output'):
        require(not target.exists(),'Preflight fixture target must start absent')
        try:checked_output(target,archive_name,forbidden_trees,[])
        except AssertionError:check(True)
        else:check(False)
        check(not target.exists())
    check(checked_output(scratch,archive_name,forbidden_trees,[])==scratch)
    check(not scratch.exists())
    return {'status':'hand_fixtures_passed','checks':checks,'real_case_reconstructions':0,'new_fits':0,'abs_tolerance':ABS_TOL,'relative_tolerance':REL_TOL}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    fixture=sub.add_parser('self-test');fixture.add_argument('--output',type=Path)
    actual=sub.add_parser('verify');actual.add_argument('--archive',type=Path,required=True);actual.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='self-test':
        result=self_test()
        if args.output:save(args.output,result)
    else:result=verify(args.archive,args.output)
    print(canonical({k:v for k,v in result.items() if k not in ('cases','archive_members_read')}))


if __name__=='__main__':
    main()
