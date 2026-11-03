"""Start or resume the new tabular evidence task without resetting old budgets."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autoresearch import knowledge_sources as guard
from autoresearch.contracts import ResearchError, canonical, fingerprint
from autoresearch.diagnostic_view import read_diagnostic_artifacts
from autoresearch.handoff_view import read_handoff_artifacts
from autoresearch.local_ollama import file_info, parse_json, require
from autoresearch.pipeline_preparation_view import read_pipeline_preparation_artifacts
from autoresearch.pipeline_research_view import capture_pipeline_research
from autoresearch.pipeline_research_transport import OwnedPipelineResearchOllama
from autoresearch.returned_evidence import validate_packet
from autoresearch.source_assessment_continuation import SourceAssessmentContinuation
from autoresearch.tabular_preparation_view import read_tabular_preparation_artifacts
from autoresearch.tabular_research import SourceAssessmentStudy,TabularResearchCloudLoop


def history(prior_workflow,pipeline_workspace,pipeline_input_directory,handoff_directory,diagnostic_directory,prepared_input_directory,packet_path):
    controller=SourceAssessmentContinuation(prior_workflow);old=controller.status()
    require(old['status']=='completed' and old['budget']['total_reserved']==old['budget']['max_requests']==4 and old['budget']['old_unknown_reserved']==1 and old['new_outcome']['status']=='invalid','PRIOR_CHANGED','Old exhausted assessment and unknown reservation required.')
    receipt=controller.root/'history/transport-000002/cloud-003-sending.json';receipt_sha,_,raw=file_info(receipt,2*1024*1024);sending=parse_json(raw)
    require(sending.get('status')=='sending' and sending.get('request_sha256')==fingerprint(sending.get('request')),'PRIOR_CHANGED','Original sending receipt required.')
    droot=Path(diagnostic_directory).absolute();diagnostic=guard._json(guard._read(droot,'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(droot,{'snapshot_sha256':diagnostic['iteration_snapshot_sha256']})
    handoff=guard._json(read_handoff_artifacts(handoff_directory,diagnostic)['handoff.json'])
    pipeline=guard._json(read_pipeline_preparation_artifacts(pipeline_input_directory,handoff)['pipeline-input.json'])
    prepared=guard._json(read_tabular_preparation_artifacts(prepared_input_directory,handoff)['prepared-input.json'])
    packet=parse_json(file_info(Path(packet_path).absolute(),4_000_000)[2]);validate_packet(packet)
    require(packet['snapshot_sha256']==prepared['packet_snapshot_sha256'] and packet['handoff_snapshot_sha256']==handoff['snapshot_sha256'] and packet['snapshot_sha256']!=old['source_snapshot_sha256'],'SOURCE_CHANGED','Prepared tabular packet must be distinct from the old packet and bound to the same handoff.')
    prior_pipeline=capture_pipeline_research(pipeline_workspace,pipeline)
    require(prior_pipeline['study_status']=='paused' and prior_pipeline['controller_status']=='completed' and prior_pipeline['execution']['requests_reserved']==2 and prior_pipeline['execution']['max_requests']==4 and len(prior_pipeline['read_aliases'])==15 and prior_pipeline['revision'] is None,'PRIOR_CHANGED','The prior pipeline reading and pause must remain intact.')
    prior={'schema_version':'p02-tabular-research-prior-v1','prepared_input_snapshot_sha256':prepared['snapshot_sha256'],
           'packet_snapshot_sha256':packet['snapshot_sha256'],'handoff_snapshot_sha256':handoff['snapshot_sha256'],
           'old_assessment':{'requests_reserved':4,'max_requests':4,'unknown_requests':1,'outcome':'old_assessment_not_accepted',
             'source_snapshot_sha256':old['source_snapshot_sha256'],'continuation_outcome_sha256':old['new_outcome']['snapshot_sha256'],
             'unknown_request_sha256':sending['request_sha256'],'unknown_receipt_sha256':receipt_sha},
           'pipeline_research':{'snapshot_sha256':prior_pipeline['snapshot_sha256'],'study_configuration_sha256':prior_pipeline['study_configuration_sha256'],
             'requests_reserved':2,'max_requests':4,'read_modules':15,'study_status':'paused','revision':None},
           'private_sources':{key:str(Path(value).absolute()) for key,value in zip(('prior_workflow','pipeline_workspace','pipeline_input_directory','handoff_directory','diagnostic_directory','prepared_input_directory','packet_path'),(prior_workflow,pipeline_workspace,pipeline_input_directory,handoff_directory,diagnostic_directory,prepared_input_directory,packet_path))}}
    return prior,old['profile']['model_identity'],receipt,receipt_sha


def compact(value):
    study=value.get('study',value)
    result={k:value[k] for k in ('status','reason','budget','native_usage','unknown_cloud_send') if k in value}
    result.update({'study_status':study['status'],'source_snapshot_sha256':study['source_snapshot_sha256'],
        'read_source_ids':study['read_source_ids'],'read_aliases':study['read_aliases'],
        'actions':[{'id':a['id'],'action':a['action']} for a in study['actions']],
        'prior_attempt_recorded':study['prior_attempt_recorded'],'scientific_validation':False,'new_fits':0})
    if 'calls' in value:result['calls']=[{k:c[k] for k in ('ordinal','status','error_code')} for c in value['calls']]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['create','status','resume']);p.add_argument('--workspace',required=True)
    for name in ('prior-workflow','pipeline-workspace','pipeline-input-directory','handoff-directory','diagnostic-directory','prepared-input-directory','packet-path','goal','model-store'):p.add_argument('--'+name)
    p.add_argument('--max-new-requests',type=int,choices=range(4),default=0);p.add_argument('--port',type=int,default=11449)
    p.add_argument('--ollama-executable',default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    a=p.parse_args();client=None
    try:
        study=SourceAssessmentStudy(a.workspace);loop=TabularResearchCloudLoop(a.workspace)
        paths=(a.prior_workflow,a.pipeline_workspace,a.pipeline_input_directory,a.handoff_directory,a.diagnostic_directory,a.prepared_input_directory,a.packet_path)
        if a.action=='status':
            require(a.max_new_requests==0,'INVALID_REQUEST','Status never sends requests.')
            value=loop.status() if loop.db.exists() else study.observe()
        elif a.action=='create':
            require(all(paths),'INVALID_REQUEST','All frozen source and prior paths are required.')
            prior,identity,receipt,digest=history(*paths)
            require(a.max_new_requests==0 and a.goal,'INVALID_REQUEST','Creation requires goal and sends no request.')
            value=study.create(a.packet_path,a.goal,max_requests=3,prior_attempt=canonical(prior))
        else:
            with study._connect() as con:config,observed,_=study._state(con)
            frozen=json.loads(config['prior_attempt']);source=frozen['private_sources']
            keys=('prior_workflow','pipeline_workspace','pipeline_input_directory','handoff_directory','diagnostic_directory','prepared_input_directory','packet_path')
            require(set(source)==set(keys) and not any(paths),'INVALID_REQUEST','Resume uses frozen source paths; do not replace them.')
            prior,identity,receipt,digest=history(*(source[k] for k in keys))
            require(config['prior_attempt']==canonical(prior) and config['max_requests']==3 and observed['source_snapshot_sha256']==prior['packet_snapshot_sha256'],'PRIOR_CHANGED','Frozen prior or packet differs.')
            value=loop.run(max_new_requests=0) if loop.db.exists() else observed
            observed=value.get('study',value)
            if a.max_new_requests and value['status']=='active' and observed['status']=='active':
                require(a.model_store,'INVALID_REQUEST','Original model store required for a new request.')
                reserved=value.get('budget',{}).get('requests_reserved',0);output=study.root/'history'/f'transport-{reserved:06d}'
                with OwnedPipelineResearchOllama(a.ollama_executable,output.with_name(output.name+'-cache'),output,model_store=a.model_store,port=a.port,
                    original_identity=identity,unknown_receipt=receipt,unknown_sha256=digest,unknown_request_sha256=prior['old_assessment']['unknown_request_sha256']) as client:
                    acquired=client.acquire();loop.configure(acquired);value=loop.run(client,max_new_requests=a.max_new_requests,verified_weights=acquired)
                print(json.dumps({'transport_cleanup':{'owned_server_stopped':client.stopped,'key_metadata_unchanged':client.key_metadata_unchanged}}))
        print(json.dumps(compact(value),ensure_ascii=False));return 1 if value['status']=='needs_review' else 0
    except (ResearchError,OSError,ValueError) as error:
        result={'ok':False,'code':getattr(error,'code','TABULAR_RESEARCH_FAILED'),'automatic_retry':False,'new_fits':0}
        if client is not None:
            result['transport_cleanup']={'owned_server_stopped':client.stopped,'key_metadata_unchanged':client.key_metadata_unchanged}
        try:
            state=loop.status() if loop.db.exists() else None
            if state is not None:
                result.update(budget=state['budget'],native_outcome_unknown=state['unknown_cloud_send'],
                              last_native_status=state['calls'][-1]['status'] if state['calls'] else None)
        except (ResearchError,OSError,ValueError):pass
        print(json.dumps(result));return 1

if __name__=='__main__':raise SystemExit(main())
