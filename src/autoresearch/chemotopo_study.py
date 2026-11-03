"""Evidence-bound P02 tools and conditional numerical observations, no inference.

Reuses the existing guarded research SQLite access and research-memory storage.
The domain validator never sends P02 records through the C01 numerical verifier.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import uuid

from . import archive_inventory, c01, chemotopo_data as data, chemotopo_rebuild as rebuild
from . import chemotopo_project, chemotopo_experiment_evidence as experiment
from .c01_research import C01Research, ACTION_FIELDS
from .contracts import ResearchError, canonical, fingerprint, identifier
from .research_memory import ResearchMemory, observation_id


ACTIONS = {'inspect_source','inspect_project','inspect_prediction','compare_policies','review_evidence','review_prediction','remember_evidence','recall_evidence','check_training_gate','pause','stop'}
GATE = {'fit_eligible':False,'ALP_eligible':False,
        'reason_codes':['ALP_CHANNEL_UNCONFIRMED','OBJECT_EXPORT_MAPPING_UNCONFIRMED','ZERO_OBJECT_CONVENTION_UNCONFIRMED'],
        'scope':'P02 source-policy study only; no fit tool or scientific approval'}


class MemoryImportPending(RuntimeError):
    """Action already committed; this is not an invalid model decision."""
    def __init__(self,original_code):
        super().__init__('Committed memory action has an unfinished idempotent import.')
        self.original_code=original_code


def analysis_identity():
    return hashlib.sha256(b''.join(Path(m.__file__).read_bytes() for m in
        (data,rebuild,c01,archive_inventory,chemotopo_project,experiment))+Path(__file__).read_bytes()).hexdigest()


def source_manifest(with_prediction=False):
    sha,size=data.SOURCES['hiMSC_Raw_Data.xlsx']
    name,psha,psize=rebuild.PROJECT
    files=[{'file':'hiMSC_Raw_Data.xlsx','sha256':sha,'bytes':size}, {'file':name,'sha256':psha,'bytes':psize}]
    if with_prediction:
        dsha,dsize=data.SOURCES['Modelling_Descriptors.xlsx']; files.append({'file':'Modelling_Descriptors.xlsx','sha256':dsha,'bytes':dsize})
    return {'dataset':'10.17632/57nrc49stj.1','files':files}


def source_bytes(directory):
    return {s['file']:data._captured(Path(directory)/s['file'],s['sha256'],s['bytes'])
            for s in source_manifest()['files']}


def scope_for_source(attachment_identity=None,research_focus='source_policy'):
    manifest=source_manifest(bool(attachment_identity))
    return {'source_manifest_sha256':fingerprint(manifest),
            'inputs_sha256':fingerprint({'manifest':manifest,'policy_sha256':fingerprint(rebuild.PROTOCOL),
                                       'endpoint':'raw_red_proxy_unresolved_ALP', **({'prediction_attachment':attachment_identity} if attachment_identity else {}), **({'research_focus':research_focus} if research_focus!='source_policy' else {})}),
            'analysis_code_sha256':analysis_identity(),
            'protocol':rebuild.PROTOCOL['id']+'|source-qualification-v1'}


def inspect_source(directory):
    payload=source_bytes(directory)
    book=data.read_workbook(payload['hiMSC_Raw_Data.xlsx'])
    reports,_=data.audit_sections(book,rebuild.SECTIONS,himsc=True)
    keys=sum(r['checks']['keys'] for r in reports)
    conflicts=sum(r['checks']['count_sd_over_flat_base_count_sd_matches'] for r in reports)
    example=next(r for r in reports[0]['records'] if (r['topography'],r['chemistry'])==(10,0))
    pipeline=rebuild.static_pipeline(payload[rebuild.PROJECT[0]])
    manifest=source_manifest()
    citations=[{'citation_id':'p02-workbook','source_sha256':manifest['files'][0]['sha256'],
                'source_file':'hiMSC_Raw_Data.xlsx','url':'https://data.mendeley.com/datasets/57nrc49stj/1',
                'location':'B8S1_Normalised!E2 and B8S1_SNR!E2/E82; all12 sections rechecked',
                'evidence_type':'recomputed author-table observation, not author prose',
                'finding':f'{conflicts}/{keys} normalized values labeled red match cell-count SD / flat-base cell-count SD; biological identity not established.'},
               {'citation_id':'p02-pipeline','source_sha256':manifest['files'][1]['sha256'],
                'source_file':rebuild.PROJECT[0],'url':'https://data.mendeley.com/datasets/57nrc49stj/1',
                'location':'static embedded ASCII copies at offsets475730 and507314',
                'evidence_type':'static source settings, not an executed author pipeline',
                'finding':'Two object sets and two images are measured; export field/object mapping and ALP channel remain unresolved.'}]
    return {'source_manifest':manifest,'normalized_keys':keys,'red_role_conflicts':conflicts,
            'example':example,'pipeline_evidence':pipeline,'endpoint_gate':copy.deepcopy(GATE),
            'citations':citations,'scientific_validation':False}


def comparison_summary(result):
    value={key:copy.deepcopy(result[key]) for key in ('schema_version','protocol_sha256','raw_summary','comparison','endpoint_gate','limits')}
    keys=value['comparison'].pop('common_three_batch_keys')
    value['comparison']['common_keys_sha256']=fingerprint(keys)
    value['comparison_axis']='processing_rules'
    value['protocol']=copy.deepcopy(result['protocol'])
    value['policies']={}
    for name,positive,aggregation in rebuild.POLICIES:
        policy=result['policies'][name]
        counts={str(n):sum(len(r['available_batches'])==n for r in policy['combinations']) for n in (1,2,3)}
        examples=[]
        for section in policy['section_audits']:
            if section['section'] not in {'B8S1','B10S1'}:continue
            group=next(r for r in section['groups'] if (r['topography'],r['chemistry'])==(10,0))
            examples.append({'section':section['section'],'control':section['control'],'group10_0':group})
        value['policies'][name]={'positive_count_only':positive,'repeat_aggregation':aggregation,
                                'available_combinations':policy['coverage']['available_combinations'],
                                'batch_coverage_counts':counts,'source_control_examples':examples}
    return value


class ChemoTopoMemory(ResearchMemory):
    def derive_actions(self, config, actions):
        inspect=next((a for a in actions if a['action']=='inspect_source'),None)
        compare=next((a for a in actions if a['action']=='compare_policies'),None)
        prediction=next((a for a in actions if a['action']=='inspect_prediction'),None)
        data._require(inspect is not None and (prediction is not None or compare is not None),'NO_EVIDENCE','Execute source and prediction inspection or policy comparison before remembering.')
        checked_source=inspect_source(config['source_directory'])
        data._require(checked_source==inspect['result'],'EVIDENCE_CHANGED','Saved source differs from recomputation.')
        refs=checked_source['citations']
        payloads=[(inspect,{'type':'source_qualification','normalized_keys':checked_source['normalized_keys'],
                           'red_role_conflicts':checked_source['red_role_conflicts'],'endpoint_gate':GATE,
                           'interpretation':'Column-role conflict; no copying direction or biological error adjudicated.'})]
        if prediction:
            checked_prediction=experiment.inspect_experiment(config['prediction_directory'],config['source_directory'],config['prediction_attachment']['manifest_sha256'])
            data._require({**checked_prediction['summary'],'manifest_sha256':checked_prediction['manifest_sha256'],'protocol_sha256':checked_prediction['protocol_sha256']}==prediction['result']['summary'],'EVIDENCE_CHANGED','Saved prediction differs from arithmetic recheck.')
            checked_comparison=None
            payloads.append((prediction,{'type':'prediction_diagnostic',**checked_prediction['summary'],
                'manifest_sha256':checked_prediction['manifest_sha256'],'protocol_sha256':checked_prediction['protocol_sha256'],
                'sources':checked_prediction['sources'],'endpoint_gate':GATE}))
            dsha,_=data.SOURCES['Modelling_Descriptors.xlsx']
            refs=[*refs,{'citation_id':'p02-descriptors','source_sha256':dsha,'source_file':'Modelling_Descriptors.xlsx','finding':'Pinned geometry descriptors; not a biological endpoint.'}]
        else:
            checked_comparison=comparison_summary(rebuild.run_reconstruction(config['source_directory']))
            data._require(checked_comparison==compare['result']['summary'],'EVIDENCE_CHANGED','Saved policy comparison differs from recomputation.')
            payloads.append((compare,{'type':'policy_sensitivity','comparison_axis':'processing_rules','protocol_sha256':checked_comparison['protocol_sha256'],
                'protocol':checked_comparison['protocol'],
                'policy_definitions':{n:{k:v for k,v in p.items() if k!='source_control_examples'} for n,p in checked_comparison['policies'].items()},
                'common_combinations':checked_comparison['comparison']['common_combinations'],
                'pairs':checked_comparison['comparison']['pairs'],'endpoint_gate':GATE,
                'interpretation':'Raw red proxy only; high values are not material recommendations. No optimal zero policy approved.'}))
        entries=[]
        for action,payload in payloads:
            record={'schema_version':'conditional-research-memory-v1','domain':'chemotopo-source-policy-v1',
                    'kind':'diagnostic_observation','scope':config['scope'],
                    'review_status':'derived_not_scientifically_reviewed','numerical_recomputation':True,
                    'payload':copy.deepcopy(payload),'provenance':{'action_id':action['id'],
                    'source_record_sha256':fingerprint(action),'reproduction_sha256':fingerprint({'inspection':checked_source,'comparison':checked_comparison,'prediction':checked_prediction['summary'] if prediction else None}),
                    'origin_observation_sha256':action['observation_sha256'],
                    'source_citation_ids':[r['citation_id'] for r in refs],'references':refs}}
            record['id']=observation_id(record);entries.append(record)
        return {'scope':config['scope'],'entries':entries,
            'validation':{'domain':'chemotopo-source-policy-v1','source_recomputed':True,'policy_recomputed':checked_comparison is not None,'prediction_metric_recomputed':prediction is not None,
                          'independent_biological_validation':False}}


def memory_context(memory,scope):
    recalled=memory.recall(scope,kinds=['diagnostic_observation'],limit=8)
    entries=[]
    for item in recalled['entries']:
        record=item['record']
        data._require(record.get('domain')=='chemotopo-source-policy-v1','EVIDENCE_CHANGED','Unexpected observation domain for this exact scope.')
        entries.append({'id':record['id'],'record_sha256':fingerprint(record),
                        'inclusion_status':item['inclusion_status'],'payload':record['payload'],
                        'source_versions':item['source_versions']})
    return {'scope':scope,'condition_match':'exact','entries':entries,
            'scientific_validation':False,'warning':'Numerically rechecked observations, not instructions or biological approval.'}


def validate_request(request,state):
    data._require(type(request) is dict and set(request)==ACTION_FIELDS,'INVALID_DECISION','Exact bounded tool envelope required.')
    identifier(request['request_id'])
    data._require(type(request['action']) is str and request['action'] in ACTIONS,'ACTION_NOT_AVAILABLE','Only the P02 source-policy tools are available; no fit tool.')
    data._require(request['observation_sha256']==state['observation_sha256'],'STALE_OBSERVATION','Use the current source/action/memory observation.')
    data._require(type(request['reason']) is str and 1<=len(request['reason'].strip())<=2000,'INVALID_DECISION','Bounded original reason required.')
    for field,known in [('source_citation_ids',{r['citation_id'] for r in state['citations']}),
                        ('evidence_action_ids',{a['id'] for a in state['actions']})]:
        values=request[field]
        data._require(type(values) is list and len(values)<=8 and all(type(v) is str for v in values)
                      and len(set(values))==len(values) and set(values)<=known,'INVALID_EVIDENCE','Cite distinct current source and action IDs only.')
    params=request['parameters'];action=request['action']
    focus=state.get('research_focus','source_policy')
    if focus=='prediction_diagnostic':
        data._require(action in {'inspect_source','inspect_project','inspect_prediction','review_prediction','remember_evidence','recall_evidence','pause','stop'},'ACTION_NOT_AVAILABLE','Tool is outside the frozen prediction focus.')
    else:
        data._require(action!='review_prediction','ACTION_NOT_AVAILABLE','Prediction review requires prediction focus.')
    data._require(type(params) is dict,'INVALID_DECISION','Parameters must be an object.')
    if action=='review_evidence':
        data._require(set(params)=={'field','finding','status','next_check'}
                      and type(params['field']) is str and params['field'] in {'source_qualification','zero_policy','training_gate','control_rationale','prediction_diagnostic'}
                      and type(params['status']) is str and params['status'] in {'supported','unresolved','conflicting'}
                      and all(type(params[k]) is str and 1<=len(params[k].strip())<=2000 for k in ('finding','next_check')),
                      'INVALID_REVIEW','A bounded unapproved finding and next check are required.')
    elif action=='review_prediction':
        data._require(set(params)=={'fact_ids','decision','hypothesis','next_check'} and type(params['fact_ids']) is list and 1<=len(params['fact_ids'])<=6 and all(type(v) is str for v in params['fact_ids']) and len(set(params['fact_ids']))==len(params['fact_ids']) and type(params['decision']) is str and params['decision'] in {'continue','revise','pause'} and all(type(params[k]) is str and 1<=len(params[k].strip())<=2000 for k in ('hypothesis','next_check')),'INVALID_REVIEW','Bounded prediction review fields required.')
        inspected=next((a for a in state['actions'] if a['action']=='inspect_prediction'),None)
        data._require(inspected is not None,'INVALID_EVIDENCE','Inspect prediction before review.')
        facts=inspected['result']['summary']['prediction_facts']['facts']; known={f['id'] for f in facts}; primary=next(f['id'] for f in facts if f['kind']=='primary_aggregate')
        data._require(set(params['fact_ids'])<=known and primary in params['fact_ids'] and inspected['id'] in request['evidence_action_ids'],'INVALID_EVIDENCE','Use checked prediction facts including primary aggregate and cite the prediction action.')
    else:data._require(not params,'INVALID_REQUEST','This action has no model-selected parameters or paths.')
    if action in {'inspect_project','inspect_prediction','compare_policies','remember_evidence','review_evidence','review_prediction'}:
        relevant=[a for a in state['actions'] if a['action'] in {'inspect_source','inspect_project','inspect_prediction','compare_policies'}]
        data._require(relevant and request['source_citation_ids'] and relevant[-1]['id'] in request['evidence_action_ids'],
                      'INVALID_EVIDENCE','Cite retrieved sources and the latest source/numerical feedback.')


def parse_decision(content,state,request_id):
    value=json.loads(content)
    data._require(type(value) is dict and 'request_id' not in value,'INVALID_DECISION','Request identity is runner-owned.')
    request={'request_id':request_id,**value}
    validate_request(request,state)
    return request


class ChemoTopoStudy(C01Research):
    """Own P02 schema/tools, reusing guarded SQLite access without C01 data."""
    def create(self,directory,goal,*,memory_workspace=None,max_actions=12,prediction_directory=None,research_focus='source_policy'):
        data._require(type(goal) is str and 1<=len(goal.strip())<=2000 and type(max_actions) is int and 3<=max_actions<=16,
                      'INVALID_REQUEST','Bounded goal and action budget required.')
        data._require(research_focus in {'source_policy','prediction_diagnostic'} and (research_focus!='prediction_diagnostic' or prediction_directory is not None),'INVALID_REQUEST','Prediction focus requires a fixed prediction attachment.')
        self._guard()
        data._require(not self.root.exists() or not any(self.root.iterdir()),'ALREADY_EXISTS','Use a new study workspace.')
        source_bytes(directory)
        identity=None
        if prediction_directory is not None:
            attached=experiment.attachment(prediction_directory,directory)
            identity={'manifest_sha256':attached['manifest_sha256'],'protocol_sha256':attached['protocol_sha256'],
                      'reader_sha256':hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest()}
        config={'schema':'chemotopo-source-study-v1','goal':goal,'source_directory':str(Path(directory).absolute()),
                'source_manifest':source_manifest(bool(identity)),'scope':scope_for_source(identity,research_focus),'research_focus':research_focus,'max_actions':max_actions,
                **({'prediction_directory':str(Path(prediction_directory).absolute()),'prediction_attachment':identity} if identity else {}),
                'memory_workspace':str(Path(memory_workspace).absolute() if memory_workspace else self.root/'observation-memory')}
        self.root.mkdir(parents=True,exist_ok=True)
        with self.db.open('xb'):pass
        with self._connect(True) as con:
            con.executescript('CREATE TABLE meta(config TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL);CREATE TABLE actions(ordinal INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,request_id TEXT UNIQUE NOT NULL,request_sha256 TEXT NOT NULL,record TEXT NOT NULL);')
            con.execute('INSERT INTO meta VALUES(?,?,?)',(canonical(config),fingerprint(config),'active'))
        return self.observe()

    def _artifact(self,reference):
        data._require(type(reference) is dict and set(reference)=={'sha256','bytes'}
                      and re.fullmatch('[0-9a-f]{64}',reference['sha256']) and type(reference['bytes']) is int
                      and 0<reference['bytes']<=25000000,'EVIDENCE_CHANGED','Invalid bounded result artifact reference.')
        return data._captured(self.root/'artifacts'/(reference['sha256']+'.json'),reference['sha256'],reference['bytes'])

    def _state(self,con):
        row=con.execute('SELECT * FROM meta').fetchone();config=json.loads(row['config'])
        data._require(fingerprint(config)==row['sha256'],'INPUT_CHANGED','Study configuration changed.')
        data._require(config['scope']==scope_for_source(config.get('prediction_attachment'),config.get('research_focus','source_policy')),'CODE_CHANGED','Frozen source/protocol/analysis identity changed.')
        source_bytes(config['source_directory'])
        if config.get('prediction_attachment'):
            identity=config['prediction_attachment']; attached=experiment.attachment(config['prediction_directory'],config['source_directory'],identity['manifest_sha256'])
            data._require(attached['protocol_sha256']==identity['protocol_sha256'] and hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest()==identity['reader_sha256'],'EVIDENCE_CHANGED','Frozen prediction identity changed.')
        actions=[]
        for item in con.execute('SELECT * FROM actions ORDER BY ordinal'):
            action=json.loads(item['record'])
            data._require(action['id']==item['id'] and action['request_id']==item['request_id']
                          and action['ordinal']==len(actions)+1 and fingerprint(action['result'])==action['result_sha256']
                          and fingerprint({k:action[k] for k in ACTION_FIELDS})==item['request_sha256'],
                          'EVIDENCE_CHANGED','Stored P02 action or result changed.')
            if action['action'] in {'compare_policies','inspect_project','inspect_prediction'}:self._artifact(action['result']['artifact'])
            actions.append(action)
        citations=next((a['result']['citations'] for a in actions if a['action']=='inspect_source'),[])
        if any(a['action']=='inspect_prediction' for a in actions):
            sha,_=data.SOURCES['Modelling_Descriptors.xlsx']; citations=[*citations,{'citation_id':'p02-descriptors','source_sha256':sha,'source_file':'Modelling_Descriptors.xlsx','finding':'Pinned geometry descriptors; not a biological endpoint.'}]
        memory=memory_context(ChemoTopoMemory(config['memory_workspace']),config['scope'])
        state={'schema_version':config['schema'],'configuration_sha256':row['sha256'],'goal':config['goal'],'status':row['status'],
               'budget':{'actions_used':len(actions),'max_actions':config['max_actions'],'fits_used':0,'max_fits':0},
               'source_manifest':config['source_manifest'],'research_focus':config.get('research_focus','source_policy'),'scope':config['scope'],'endpoint_gate':copy.deepcopy(GATE),
               'actions':actions,'citations':citations,'prediction_attachment':config.get('prediction_attachment'),'memory_context':memory,'scientific_validation':False}
        state['observation_sha256']=fingerprint(state)
        return config,state,actions

    def observe(self):
        with self._connect() as con:return self._state(con)[1]

    def apply(self,request):
        with self._connect(True) as con:
            con.execute('BEGIN IMMEDIATE')
            config,state,actions=self._state(con)
            old=con.execute('SELECT * FROM actions WHERE request_id=?',(request.get('request_id'),)).fetchone()
            if old:
                data._require(fingerprint(request)==old['request_sha256'],'IDEMPOTENCY_CONFLICT','Request ID already binds different original arguments.')
                return self._finish(json.loads(old['record']),True,config)
            validate_request(request,state)
            data._require(state['status']=='active' and len(actions)<config['max_actions'],'NOT_ACTIVE','Study inactive or action budget exhausted.')
            action=request['action']
            data._require(action not in {'inspect_source','inspect_project','inspect_prediction','compare_policies','remember_evidence'} or not any(a['action']==action for a in actions),
                          'DUPLICATE_ANALYSIS','Use existing verified feedback instead of repeating this operation.')
            if action=='inspect_source':result=inspect_source(config['source_directory'])
            elif action in {'compare_policies','inspect_project','inspect_prediction'}:
                data._require(any(a['action']=='inspect_source' for a in actions),'NO_EVIDENCE','Inspect source first.')
                if action=='compare_policies': full=rebuild.run_reconstruction(config['source_directory']); summary=comparison_summary(full)
                elif action=='inspect_project':
                    full=chemotopo_project.inspect_project(Path(config['source_directory'])/rebuild.PROJECT[0])
                    measurements=full['inventory']['measurements']; files=full['ome_filelist']
                    channels=[item['channels'] for item in files]; dimensions=[item['dimensions'] for item in files]
                    summary={'object_count':full['inventory']['object_count'],
                             'measurement_groups':[{'name':m['name'],'groups':m['groups'],'features':m['features']} for m in measurements],
                             'ome_files':[item['filename'] for item in files],
                             'common_channels':channels[0] if channels and all(v==channels[0] for v in channels) else None,
                             'common_dimensions':dimensions[0] if dimensions and all(v==dimensions[0] for v in dimensions) else None,
                             'limitations':full['limitations'],'scientific_validation':False}
                else:
                    data._require(bool(config.get('prediction_attachment')),'ACTION_NOT_AVAILABLE','No prediction attachment configured.')
                    full=experiment.inspect_experiment(config['prediction_directory'],config['source_directory'],config['prediction_attachment']['manifest_sha256']); summary={**full['summary'],'manifest_sha256':full['manifest_sha256'],'protocol_sha256':full['protocol_sha256']}
                payload=canonical(full).encode('utf-8');sha=hashlib.sha256(payload).hexdigest()
                target=self.root/'artifacts'/(sha+'.json')
                for parent in (target.parent,*target.parent.parents):
                    data._require(not parent.is_symlink() and not getattr(parent,'is_junction',lambda:False)(),'UNSAFE_PATH','Artifact directories cannot redirect.')
                target.parent.mkdir(exist_ok=True)
                if not target.exists():
                    with target.open('xb') as stream:stream.write(payload)
                reference={'sha256':sha,'bytes':len(payload)};self._artifact(reference)
                result={'summary':summary,'artifact':reference,'scientific_validation':False}
            elif action=='remember_evidence':result={'derived':ChemoTopoMemory(config['memory_workspace']).derive_actions(config,actions),
                                                     'persistence':'memory imported idempotently after this action commits'}
            elif action=='recall_evidence':result=memory_context(ChemoTopoMemory(config['memory_workspace']),config['scope'])
            elif action=='review_prediction':
                pred=next(a for a in actions if a['action']=='inspect_prediction'); facts=pred['result']['summary']['prediction_facts']['facts']; chosen=set(request['parameters']['fact_ids'])
                result={'verified_metric_facts':[copy.deepcopy(f) for f in facts if f['id'] in chosen],
                        'comparison_axis':'model_inputs','prediction_action_id':pred['id'],
                        'model_assertion':{k:request['parameters'][k] for k in ('decision','hypothesis','next_check')},
                        'assertion_verified':False,'scientific_approval':False}
            elif action=='review_evidence':result={**request['parameters'],'interpretation_verified':False,'scientific_approval':False}
            else:result={'endpoint_gate':copy.deepcopy(GATE),'fits_executed':0,'reason':request['reason']}
            record={**copy.deepcopy(request),'id':'p02-'+uuid.uuid4().hex,'ordinal':len(actions)+1,'result':result,'result_sha256':fingerprint(result)}
            con.execute('INSERT INTO actions VALUES(?,?,?,?,?)',(record['ordinal'],record['id'],request['request_id'],fingerprint(request),canonical(record)))
            if action in {'pause','stop'}:con.execute('UPDATE meta SET status=?',('paused' if action=='pause' else 'stopped',))
        return self._finish(record,False,config)

    def _finish(self,record,replayed,config):
        reply={'action':record,'replayed':replayed}
        if record['action']=='remember_evidence':
            # Study commitment precedes the second database side effect. A crash
            # on either side resumes this same recorded action before freshness.
            try:reply['memory_import']=ChemoTopoMemory(config['memory_workspace'])._import_derived(record['result']['derived'])
            except Exception as error:
                # Any ordinary exception here is an execution-side failure after
                # durable commitment, including malformed stored JSON/structure.
                # Process interrupts (BaseException) still escape unchanged.
                raise MemoryImportPending(getattr(error,'code','MEMORY_IO_FAILED')) from None
        return reply
