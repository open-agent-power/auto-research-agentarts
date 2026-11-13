"""Independent saved-artifact checks for the two native CPU cases.

Never ranks/indexes, calls the production scheduling kernel, fits, times a solver,
replays requests or writes native projects. Retrieval metrics are recomputed from
saved rankings and original citation labels; scheduling optima use a separate
coordinate-compressed Fenwick recurrence. This is not independent reranking.
"""
import argparse
import base64
from bisect import bisect_left, bisect_right
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
from autoresearch.contracts import canonical, fingerprint
from autoresearch.research_project import ResearchProject

OLD = REPO/'runs/g5-local-cpu-20261113-01'
METRICS = ('recall@5','recall@10','recall@20','mrr@10','ndcg@10')
METHODS = ('tfidf_cosine','bm25')
PRIMARY = {'retrieval':'research.retrieval-fixed-pair','scheduling':'research.weighted-interval-fixed-pair'}
AUDIT = {'retrieval':'research.retrieval-saved-error-audit','scheduling':'research.weighted-interval-saved-audit'}
EVALUATION = {'research.retrieval-fixed-pair':'citation-retrieval-fixed-pair-v1',
              'research.retrieval-saved-error-audit':'citation-retrieval-saved-error-audit-v1',
              'research.weighted-interval-fixed-pair':'weighted-interval-fixed-pair-v1',
              'research.weighted-interval-saved-audit':'weighted-interval-saved-audit-v1'}


def read(path, maximum=64000000):
    assert path.is_file() and not path.is_symlink() and path.stat().st_size<=maximum, str(path)
    with path.open('rb') as stream:raw=stream.read(maximum+1)
    assert len(raw)<=maximum
    return raw


def sha(raw):return hashlib.sha256(raw).hexdigest()


def json_file(path):return json.loads(read(path))


def jsonl(path):return [json.loads(line) for line in read(path).split(b'\n') if line.strip()]


def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


class Checks:
    def __init__(self):self.count=0
    def __call__(self,condition,label):
        self.count+=1
        if not condition:raise AssertionError(label)


def identities(root):
    return {str(path.relative_to(root)):sha(read(path)) for path in sorted(root.rglob('*')) if path.is_file()}


def protected():
    vm=REPO/'runs/g4-local-group-20261113-01'
    baseline=json_file(vm/'baseline-manifest.json')
    original=json_file(vm/'integrity-before.json')
    current={name:identities(Path(item['path'])) for name,item in baseline['inputs'].items()}
    assert current==original,'Historical G1/G3 case changed from frozen G4 identities'
    native=json_file(REPO/'runs/g4-native-confirmation-20261113-01/freeze.json')
    controls={**baseline['controls'],**native['controls']}
    assert len(controls)==5 and all(sha(read(REPO/name))==digest for name,digest in controls.items()),'Frozen G4 control changed'
    old_manifest=json_file(OLD/'manifest.json')
    assert all(sha(read(OLD/name))==digest for name,digest in old_manifest['files'].items()),'Standalone CPU evidence changed'
    return {'cases':current,'controls':controls,'standalone':identities(OLD)}


def asset_bytes(value):
    raw=base64.b64decode(value['bytes_base64'],validate=True)
    assert len(raw)==value['bytes'] and sha(raw)==value['sha256']
    return raw


def native_case(root,kind,checks):
    manager=root/kind/'manager'
    databases=list((manager/'projects').glob('*/project.sqlite'))
    checks(len(databases)==1,'Exactly one completed native '+kind+' project is required')
    project=ResearchProject(databases[0].parent)
    before=identities(manager)
    state=project.status()
    checks(state['registration']['method_id']==PRIMARY[kind],'Native primary registration')
    source_raw=read(project.root/'source.json',16000000)
    packet=json.loads(source_raw)
    checks(sha(source_raw)==state['registration']['source_sha256'],'Registered original source bytes')
    checks(packet['snapshot_sha256']==state['source_snapshot_sha256']==fingerprint({k:v for k,v in packet.items() if k!='snapshot_sha256'}),'Canonical source identity')
    checks(canonical(packet['scope'])==canonical(state['source_scope']),'Source scope identity')
    expected=read(Path('/workspace/work/g5-native-'+kind+'-packet.json'),16000000)
    checks(source_raw==expected,'Registered packet equals preflight original bytes')
    originals={role:asset_bytes(value) for role,value in packet['assets'].items()}
    checks(canonical(json.loads(asset_bytes(packet['spec_source'])))==canonical(packet['spec']),'Original spec and typed echo')
    actions=state['actions']
    checks(len(actions)==2 and [a['command'] for a in actions]==[PRIMARY[kind],AUDIT[kind]],'One primary and one saved audit, no extra executions')
    tools=[]
    for action in actions:
        checks(action['status']=='completed' and action['project_id']==state['id'] and action['run_id']==state['run_id'],'Native completed project/run identity')
        checks(action['source_snapshot_sha256']==state['source_snapshot_sha256'] and action['code_identity']==state['code_identity'],'Native source and code identity')
        request={key:action[key] for key in ('project_id','command','dimension','source_snapshot_sha256')}
        if action['command']==AUDIT[kind]:request.update(parameters=action['parameters'],evaluation_ref=EVALUATION[action['command']])
        checks(fingerprint(request)==action['request_sha256'],'Exact native request fingerprint')
        checks(action['method_instance']['definition_ref']=={'id':action['command'],'version':'1'} and
               action['method_instance']['evaluation_ref']==EVALUATION[action['command']],'Method definition/evaluator identity')
        # Derive the actual artifact from the saved action, never a fixed filename.
        path=project._artifact(action)
        envelope=json_file(path)
        checks(envelope['sha256']==action['result_sha256']==fingerprint({k:v for k,v in envelope.items() if k!='sha256'}),'Canonical native result envelope')
        checks(all(envelope[k]==action[k] for k in ('code_identity','request_sha256','source_snapshot_sha256')) and envelope['action_id']==action['id'],'Action/envelope linkage')
        tool=envelope['tool_result']
        checks(tool['status']=='completed' and tool['tool_id']==action['command'] and all(type(tool[key]) is int and tool[key]==0 for key in ('model_calls','new_fits')) and tool['scientific_validation'] is False,'Tool scope and zero fit/model')
        checks(canonical(tool['result']['scope'])==canonical(packet['scope']) and tool['result']['source_snapshot_sha256']==state['source_snapshot_sha256'],'Tool source scope')
        tools.append(tool)
    predecessor={'based_on_action_id':actions[0]['id'],'based_on_result_sha256':actions[0]['result_sha256']}
    checks(actions[1]['parameters']==predecessor and tools[1]['result']['predecessor']==predecessor,'Saved audit binds real predecessor')
    checks(actions[1]['method_instance']['parameters']==predecessor,'Method instance predecessor identity')
    budget=state['budget']
    required={'local_tool_call_limit':2,'local_tool_calls_used':2,'local_tool_calls_reserved':0,'local_tool_dispatches':2,
        'evidence_read_limit':0,'evidence_reads_used':0,'evidence_reads_reserved':0,'fit_limit':0,'fit_attempts_used':0,'fits_reserved':0,
        'new_fits':0,'new_model_requests':0,'model_requests_allowed':0,'model_requests_reserved':0}
    for key,value in required.items():checks(type(budget.get(key)) is int and budget[key]==value,'Budget '+key)
    checks(not state['evidence_actions'] and not state.get('source_requests',[]) and not state.get('local_model_requests',[]),'No source/model execution records')
    checks(state['research_status']=='waiting' and state['execution_status']=='completed','Explicit completed execution and research wait')
    plans=state.get('plan_revisions',[])
    checks(len(plans)>=2 and [p['version'] for p in plans]==list(range(1,len(plans)+1)),'Native sequential research plans')
    checks(actions[0]['id'] in canonical(plans[1:]),'Plan revision cites fresh primary feedback')
    checks(any(plans[0][key]!=plans[1][key] for key in ('basis','steps','expected_feedback')),'Plan revision changes research content')
    reports=[]
    for path in (root/kind).rglob('manifest.json'):
        manifest=json_file(path)
        if manifest.get('schema_version')=='project-report-export-v1' and manifest.get('project_id')==state['id'] and manifest.get('project_snapshot_ref')==state['snapshot_ref']:
            reports.append((path.parent,manifest))
    checks(len(reports)==1,'Exactly one current native report manifest')
    report_root,manifest=reports[0]
    checks(set(manifest['files'])=={'report.json','report.md','report.pdf','input.json'},'Existing four-file report contract')
    for name,identity in manifest['files'].items():
        raw=read(report_root/name)
        checks(sha(raw)==identity['sha256'] and len(raw)==identity['bytes'],'Report original '+name)
    report=json_file(report_root/'report.json'); inputs=json_file(report_root/'input.json')
    checks(report['project_id']==state['id'] and report['project_snapshot_ref']==state['snapshot_ref'],'Report native snapshot')
    checks(canonical(inputs['source_packet'])==canonical(packet),'Report preserves complete source packet')
    for action,tool in zip(actions,tools):
        saved=next(row for row in report['action_results'] if row['action_id']==action['id'])
        checks(canonical(saved['tool_result'])==canonical(tool),'Report preserves complete original action result')
    checks(identities(manager)==before,'Read-only verifier leaves manager/project bytes unchanged')
    return state,packet,originals,tools,{'project_id':state['id'],'project_workspace':str(project.root),'project_snapshot_ref':state['snapshot_ref'],
        'source_snapshot_sha256':state['source_snapshot_sha256'],'source_packet_sha256':sha(source_raw),'code_identity':state['code_identity'],'actions':[a['id'] for a in actions],
        'result_hashes':[a['result_sha256'] for a in actions],'budget':budget,'report_manifest_sha256':sha(read(report_root/'manifest.json'))}


def independent_metrics(ranking,relevant):
    truth=set(relevant)
    recall={f'recall@{cutoff}':sum(doc in truth for doc in ranking[:cutoff])/len(truth) if truth else 0.0 for cutoff in (5,10,20)}
    reciprocal=0.0; gain=0.0
    for position,doc in enumerate(ranking[:10],1):
        if doc in truth:
            if reciprocal==0:reciprocal=1.0/position
            gain+=1.0/math.log2(position+1)
    ideal=sum(1.0/math.log2(position+1) for position in range(1,min(10,len(truth))+1))
    return {**recall,'mrr@10':reciprocal,'ndcg@10':gain/ideal if ideal else 0.0}


def verify_retrieval(packet,raw,tools,checks):
    corpus_lines={json.loads(line)['_id']:index for index,line in enumerate(raw['corpus'].split(b'\n'),1) if line.strip()}
    query_lines={json.loads(line)['_id']:index for index,line in enumerate(raw['queries'].split(b'\n'),1) if line.strip()}
    checks(len(corpus_lines)==5183 and len(query_lines)==1109,'Complete original corpus/query identities')
    qrels={}
    for split,role in (('train','train_qrels'),('test','test_qrels')):
        qrels[split]=defaultdict(set)
        for row in csv.DictReader(io.StringIO(raw[role].decode()),delimiter='\t'):
            checks(row['score']=='1','Citation qrel score')
            qrels[split][row['query-id']].add(row['corpus-id'])
    checks(len(qrels['train'])==809 and sum(map(len,qrels['train'].values()))==919 and len(qrels['test'])==300 and sum(map(len,qrels['test'].values()))==339,'Full original qrel coverage')
    freeze=json_file(OLD/'freeze.json')
    checks(packet['spec']['query_splits']==freeze['splits'],'Original 80/80/300 query IDs')
    body=tools[0]['result']; rows=body['rankings']; scored=body['per_query_metrics']
    checks(len(rows)==len(scored)==920,'Complete 460 x 2 arm/query coverage')
    checks(fingerprint(rows)==body['rankings_before_scoring_sha256'],'Complete pre-scoring ranking identity')
    key=lambda row:(row['split'],row['query_id'],row['method'])
    expected={(split,qid,method) for split,ids in freeze['splits'].items() for qid in ids for method in METHODS}
    indexed={key(row):row for row in rows}; scores={key(row):row for row in scored}
    checks(set(indexed)==set(scores)==expected and len(indexed)==len(scores)==920,'No duplicate/missing ranking/score row')
    old_ranks={key(row):row for row in jsonl(OLD/'retrieval-rankings.jsonl')}
    old_scores={key(row):row for row in jsonl(OLD/'retrieval-per-query.jsonl')}
    for identity,row in indexed.items():
        checks(row['ranking']==old_ranks[identity]['ranking'],'Exact saved standalone ranking '+str(identity))
        checks(row['query_line']==query_lines[row['query_id']] and row['ranked_doc_lines']==[corpus_lines[doc] for doc in row['ranking']],'Exact original JSONL query/document locators')
        relevant=qrels['test' if row['split']=='test' else 'train'][row['query_id']]
        independent=independent_metrics(row['ranking'],relevant)
        actual=scores[identity]['metrics']
        checks(canonical(actual)==canonical(old_scores[identity]['metrics']),'Exact standalone per-query score '+str(identity))
        for name,value in independent.items():checks(math.isclose(actual[name],value,rel_tol=1e-12,abs_tol=1e-12),'Independent saved-ranking metric '+name)
    old_summary=json_file(OLD/'summary.json')['retrieval']['splits']
    for split,summary in body['paired_summary']['splits'].items():
        for method in METHODS:
            checks(canonical(summary['arms'][method]['metrics'])==canonical(old_summary[split]['arms'][method]['metrics']),'Exact standalone macro scores')
            for metric in METRICS:
                values=[row['metrics'][metric] for row in scored if row['split']==split and row['method']==method]
                checks(math.isclose(statistics.mean(values),summary['arms'][method]['metrics'][metric],abs_tol=1e-12),'Independent macro metric')
        checks(canonical(summary['paired_candidate_minus_baseline'])==canonical(old_summary[split]['paired_candidate_minus_baseline']),'All paired wins/ties/losses preserved')
        for metric in METRICS:
            deltas=[scores[(split,qid,'bm25')]['metrics'][metric]-scores[(split,qid,'tfidf_cosine')]['metrics'][metric] for qid in freeze['splits'][split]]
            paired=summary['paired_candidate_minus_baseline'][metric]
            checks(math.isclose(paired['mean'],statistics.mean(deltas),abs_tol=1e-12) and paired['wins']==sum(d>1e-12 for d in deltas)
                and paired['ties']==sum(abs(d)<=1e-12 for d in deltas) and paired['losses']==sum(d< -1e-12 for d in deltas),'Independent paired metric outcomes')
    expected_bad=set()
    for split,ids in freeze['splits'].items():
        for qid in ids:
            base=scores[(split,qid,'tfidf_cosine')]['metrics'];candidate=scores[(split,qid,'bm25')]['metrics']
            if any(candidate[name]-base[name]< -1e-12 for name in METRICS) or min(candidate['recall@20'],base['recall@20'])<1:
                expected_bad.add((split,qid))
    bad=body['adverse_queries']
    checks(len(bad)==len(expected_bad) and {(r['split'],r['query_id']) for r in bad}==expected_bad,'Every coverage/difference adverse query retained')
    for row in bad:
        checks(row['baseline']==scores[(row['split'],row['query_id'],'tfidf_cosine')]['metrics'] and
               row['candidate']==scores[(row['split'],row['query_id'],'bm25')]['metrics'],'Adverse values preserve actual per-query scores')
    checks(canonical(tools[1]['result']['summary'])==canonical(body['paired_summary']),'Saved retrieval audit summary')
    checks(canonical(tools[1]['result']['adverse_queries'])==canonical(body['adverse_queries']),'All retrieval adverse cases preserved')
    checks(tools[1]['result']['usage']['index_builds']==tools[1]['result']['usage']['ranking_calls']==tools[1]['result']['usage']['scoring_calls']==0,'Audit no rerank or gold rescore')
    return {'rankings_compared':920,'per_query_scores_compared':920,'independent_metric_tolerance':1e-12,
            'scope':'Independent metric arithmetic over saved ranks; no independent reranking/index execution'}


def fenwick_optimum(jobs):
    ends=sorted({row['end'] for row in jobs});bit=[0]*(len(ends)+1)
    for job in sorted(jobs,key=lambda row:(row['end'],row['start'],row['id'])):
        cursor=bisect_right(ends,job['start']); best=0
        while cursor:
            best=max(best,bit[cursor]);cursor-=cursor&-cursor
        value=max(0,best+job['weight']);cursor=bisect_left(ends,job['end'])+1
        while cursor<len(bit):
            bit[cursor]=max(bit[cursor],value);cursor+=cursor&-cursor
    answer=0;cursor=len(ends)
    while cursor:
        answer=max(answer,bit[cursor]);cursor-=cursor&-cursor
    return answer


def schedule_checks(jobs,run,checks):
    lookup={row['id']:row for row in jobs};selected=run['schedule']
    checks(len(selected)==len(set(selected)) and set(selected)<=set(lookup),'Saved schedule unique known IDs')
    ordered=[lookup[job_id] for job_id in selected]
    checks(all(left['end']<=right['start'] for left,right in zip(ordered,ordered[1:])),'Saved schedule feasibility')
    checks(sum(row['weight'] for row in ordered)==run['objective'],'Saved selected-weight objective')
    checks(fingerprint(selected)==run['schedule_sha256'],'Saved schedule full identity')
    all_jobs=sorted(jobs,key=lambda row:(row['end'],row['start'],row['id']))
    checks(selected==[r['id'] for r in sorted(ordered,key=lambda row:(row['end'],row['start'],row['id']))],'Original schedule reconstruction order')
    n=len(jobs);scan=n*(n-1)//2 if run['method']=='quadratic_scan_dp' else 0
    ops=run['operations']
    checks(run['full_scan_comparisons']==ops['full_scan_comparisons']==scan,'Exact full-scan comparisons')
    checks(ops['dp_steps']==n and ops['bisect_calls']==(n if run['method']=='binary_search_dp' else 0) and ops['bisect_internal_comparisons'] is None,'DP/bisect operation meanings')
    ends=[row['end'] for row in all_jobs];chosen=set(selected);position=n;steps=0
    while position:
        steps+=1;row=all_jobs[position-1]
        position=bisect_right(ends,row['start'],0,position-1) if row['id'] in chosen else position-1
    checks(ops['reconstruction_steps']==steps,'Independent saved-path reconstruction steps')


def verify_scheduling(packet,raw,tools,checks):
    inputs=json.loads(raw['jobs'])['cases'];body=tools[0]['result']
    cases=body['cases'];checks(len(inputs)==len(cases)==16,'All 16 original synthetic workloads')
    source={case['case_id']:case for case in inputs}
    old_test={(r['split'],r['seed'],r['n'],r['repeat'],r['method']):r for r in jsonl(OLD/'algorithm-timings.jsonl')}
    old_other={(r['split'],r['seed'],r['n']):r for r in json_file(OLD/'algorithm-correctness.json') if r.get('split') in ('dev','validation')}
    checks(len(old_test)==72 and len(old_other)==4,'Original 72 test runs plus four dev/validation definitions')
    optima={};test_runs=0
    for case in cases:
        original=source[case['case_id']]
        checks(all(case[k]==original[k] for k in ('case_id','split','seed','jobs_sha256','jobs')),'Complete original jobs and input hash')
        jobs=case['jobs'];legacy=[[j['start'],j['end'],j['weight'],j['id']] for j in jobs]
        checks(fingerprint(legacy)==case['jobs_sha256'],'Legacy tuple workload hash')
        optimum=fenwick_optimum(jobs);optima[case['case_id']]=optimum
        runs=case['runs'];repetitions=3 if case['split']=='test' else 1
        checks(len(runs)==2*repetitions and {(r['repeat'],r['method']) for r in runs}=={(i,m) for i in range(repetitions) for m in ('quadratic_scan_dp','binary_search_dp')},'All exact paired repetitions')
        for run in runs:
            schedule_checks(jobs,run,checks)
            checks(run['objective']==optimum,'Independent Fenwick optimum')
            checks(run['objective']==runs[0]['objective'] and run['schedule']==runs[0]['schedule'],'All paired schedules and objectives identical')
            if case['split']=='test':
                prior=old_test[(case['split'],case['seed'],len(jobs),run['repeat'],run['method'])]
                checks(prior['input_sha256']==case['jobs_sha256'] and prior['schedule_sha256']==run['schedule_sha256'] and prior['objective']==run['objective'] and prior['full_scan_comparisons']==run['full_scan_comparisons'],'Exact original test definitions/objective/schedule/ops')
                test_runs+=1
            else:
                prior=old_other[(case['split'],case['seed'],len(jobs))]
                checks(prior['input_sha256']==case['jobs_sha256'] and prior['objective']==run['objective'],'Original dev/validation input and optimum')
        row=next(r for r in body['paired_summary']['per_case'] if r['case_id']==case['case_id'])
        for method in ('quadratic_scan_dp','binary_search_dp'):
            checks(row['median_seconds'][method]==statistics.median(r['seconds'] for r in runs if r['method']==method),'Saved timing median arithmetic, no re-timing')
        medians=row['median_seconds'];base=medians['quadratic_scan_dp'];candidate=medians['binary_search_dp']
        checks(row['candidate_minus_baseline_seconds']==candidate-base and row['speedup_baseline_over_candidate']==(base/candidate if candidate else None)
               and row['candidate_timing']==('faster' if candidate<base else 'slower' if candidate>base else 'tie'),'Saved scheduling timing differences and classifications')
    checks(test_runs==72 and body['usage']['solver_calls']==80,'All saved native runs preserved')
    checks(set(body['paired_summary']['adverse_cases'])=={r['case_id'] for r in body['paired_summary']['per_case'] if r['candidate_timing'] in ('slower','tie')},'All adverse/tied scheduling cases retained')
    checks(canonical(tools[1]['result']['summary'])==canonical(body['paired_summary']),'Saved scheduling audit summary')
    checks(all(type(tools[1]['result']['usage'][key]) is int and tools[1]['result']['usage'][key]==0 for key in ('solver_calls','bruteforce_calls','new_timing_calls','native_fits','model_calls')),'No solver or timing rerun reported by audit')
    return {'workloads':16,'workload_hashes':{case['case_id']:case['jobs_sha256'] for case in cases},
            'independent_fenwick_optima':optima,'old_test_runs_compared':test_runs,'old_dev_validation_cases_compared':4,
            'scope':'Independent saved schedule/operation/optimum verification; no original DP kernel or timing invoked'}


def verify(root,output):
    assert not output.exists(),'Use a fresh verifier output'
    assert root.is_dir(),'Native cases are missing; do not treat preparation as a completed run'
    output.mkdir(parents=True)
    before=protected();checks=Checks()
    write(output/'protected-before.json',before)
    result={'schema_version':'native-cpu-independent-verification-v1','status':'failed_closed','checks':0}
    try:
        cases={}
        for kind in ('retrieval','scheduling'):
            state,packet,raw,tools,identity=native_case(root,kind,checks)
            numeric=verify_retrieval(packet,raw,tools,checks) if kind=='retrieval' else verify_scheduling(packet,raw,tools,checks)
            cases[kind]={**identity,**numeric}
        after=protected();write(output/'protected-after.json',after)
        checks(before==after,'292 prior case files, five G4 controls and standalone data unchanged')
        result.update(status='saved_artifacts_verified_no_reexecution',checks=checks.count,cases=cases,
            verifier_sha256=sha(read(Path(__file__))),native_ranking_executions=0,production_solver_executions=0,
            fits=0,product_model_api_calls=0,requests_replayed=0,
            limitations=['No independent reranking or scientific support/refutation validation','No production scheduling kernel or new timing','Same-ID and relocation replay are separate checks'])
    except BaseException as error:
        result.update(checks=checks.count,error={'type':type(error).__name__,'message':str(error)})
        try:write(output/'protected-after.json',protected())
        except Exception as protection_error:result['protection_error']=str(protection_error)
        write(output/'verification.json',result)
        raise
    write(output/'verification.json',result)
    return result


def self_test():
    check=Checks()
    check(independent_metrics(['a','b','c'],{'b','c'})['mrr@10']==.5,'Manual reciprocal rank')
    check(independent_metrics([],{'a'})['recall@5']==0,'Empty saved ranking')
    for raw,expected in (([],0),([(0,2,3),(2,4,4),(0,4,6)],7),([(0,2,-3)],0),([(0,2,3),(0,2,4)],4),([(-3,-1,5),(-1,2,7)],12)):
        jobs=[{'id':i,'start':a,'end':b,'weight':w} for i,(a,b,w) in enumerate(raw)]
        check(fenwick_optimum(jobs)==expected,'Independent tiny Fenwick fixture')
    jobs=[{'id':0,'start':0,'end':2,'weight':3},{'id':1,'start':2,'end':4,'weight':4},{'id':2,'start':0,'end':4,'weight':6}]
    run={'method':'quadratic_scan_dp','schedule':[0,1],'objective':7,'schedule_sha256':fingerprint([0,1]),'full_scan_comparisons':3,
        'operations':{'dp_steps':3,'full_scan_comparisons':3,'bisect_calls':0,'bisect_internal_comparisons':None,'reconstruction_steps':2}}
    schedule_checks(jobs,run,check)
    try:schedule_checks(jobs,{**run,'schedule':[0,2]},Checks())
    except AssertionError:pass
    else:raise AssertionError('Infeasible saved schedule accepted')
    with tempfile.TemporaryDirectory() as temp:
        try:verify(Path(temp)/'missing',Path(temp)/'output')
        except AssertionError:pass
        else:raise AssertionError('Missing native runs accepted')
    return {'status':'small_saved_math_fixtures_passed','checks':check.count,'real_native_cases_checked':0,'ranking_executions':0,'production_solver_executions':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('self-test')
    command=sub.add_parser('verify');command.add_argument('--root',required=True);command.add_argument('--output',required=True)
    args=parser.parse_args()
    result=self_test() if args.command=='self-test' else verify(Path(args.root).resolve(),Path(args.output).resolve())
    print(json.dumps({'status':result['status'],'checks':result['checks']},indent=2))


if __name__=='__main__':main()
