"""Create/read/resume a new-source task; preserve the exhausted earlier assessment."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoresearch.contracts import ResearchError
from autoresearch.local_ollama import file_info, parse_json, require
from autoresearch.pipeline_research import PipelineResearchStudy, PipelineResearchCloudLoop
from autoresearch.source_assessment_continuation import SourceAssessmentContinuation


def prior(workflow):
    controller = SourceAssessmentContinuation(workflow)
    old = controller.status()
    require(old['status'] == 'completed' and old['budget']['total_reserved'] == 4
            and old['budget']['max_requests'] == 4 and old['budget']['old_unknown_reserved'] == 1
            and old['new_outcome']['status'] == 'invalid', 'PRIOR_CHANGED', 'Keep the exhausted prior assessment and unknown.')
    receipt = controller.root / 'history/transport-000002/cloud-003-sending.json'
    digest, _, raw = file_info(receipt, 2 * 1024 * 1024)
    sending = parse_json(raw)
    history = {'requests_reserved':4, 'max_requests':4, 'unknown_requests':1,
               'outcome':'old_assessment_not_accepted', 'old_source_snapshot_sha256':old['source_snapshot_sha256'],
               'continuation_outcome_sha256':old['new_outcome']['snapshot_sha256'],
               'unknown_request_sha256':sending['request_sha256']}
    return history, old['profile']['model_identity'], receipt, digest


def compact(value):
    study = value.get('study', value)
    result = {k:value[k] for k in ('status','reason','budget','native_usage','unknown_cloud_send') if k in value}
    result.update({'study_status':study['status'], 'source_snapshot_sha256':study['source_snapshot_sha256'],
                   'prior_budget_history':study['prior_budget_history'], 'read_groups':study['read_groups'],
                   'read_aliases':study['read_aliases'], 'actions':[{'id':a['id'],'action':a['action']} for a in study['actions']],
                   'scientific_validation':False,'new_fits':0})
    if 'calls' in value:
        result['calls'] = [{k:c[k] for k in ('ordinal','status','error_code')} for c in value['calls']]
    revisions = [a['result'] for a in study['actions'] if a['action']=='revise_collection']
    if revisions: result['revision'] = revisions[-1]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create','status','resume'])
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--prior-workflow')
    parser.add_argument('--pipeline-input-directory')
    parser.add_argument('--handoff-directory')
    parser.add_argument('--diagnostic-directory')
    parser.add_argument('--goal')
    parser.add_argument('--max-new-requests', type=int, choices=range(5), default=0)
    parser.add_argument('--model-store')
    parser.add_argument('--port', type=int, default=11448)
    parser.add_argument('--ollama-executable', default=str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'))
    args = parser.parse_args()
    try:
        study = PipelineResearchStudy(args.workspace)
        loop = PipelineResearchCloudLoop(args.workspace)
        if args.action=='create':
            require(args.max_new_requests==0 and all((args.prior_workflow,args.pipeline_input_directory,args.handoff_directory,args.diagnostic_directory,args.goal)),
                    'INVALID_REQUEST','Creation needs sources, prior history and goal; sends no requests.')
            history, _, _, _ = prior(args.prior_workflow)
            value = study.create(args.pipeline_input_directory,args.handoff_directory,args.diagnostic_directory,args.goal,history,max_requests=4)
        elif args.action=='status':
            require(args.max_new_requests==0,'INVALID_REQUEST','Status never sends requests.')
            value = loop.status() if loop.db.exists() else study.observe()
        else:
            # Consume captured responses and terminal state without starting a model server.
            value = loop.run(max_new_requests=0) if loop.db.exists() else study.observe()
            observed = value.get('study', value)
            if args.max_new_requests and value['status']=='active' and observed['status']=='active':
                require(args.prior_workflow and args.model_store,'INVALID_REQUEST','Original history and existing model store required.')
                history, identity, receipt, digest = prior(args.prior_workflow)
                require(history==observed['prior_budget_history'],'PRIOR_CHANGED','Original exhausted history changed.')
                from autoresearch.pipeline_research_transport import OwnedPipelineResearchOllama
                reserved = value.get('budget',{}).get('requests_reserved',0)
                output = study.root / 'history' / f'transport-{reserved:06d}'
                with OwnedPipelineResearchOllama(args.ollama_executable,output.with_name(output.name+'-cache'),output,
                        model_store=args.model_store,port=args.port,original_identity=identity,
                        unknown_receipt=receipt,unknown_sha256=digest,unknown_request_sha256=history['unknown_request_sha256']) as client:
                    acquired = client.acquire()
                    loop.configure(acquired)
                    value = loop.run(client,max_new_requests=args.max_new_requests,verified_weights=acquired)
                print(json.dumps({'transport_cleanup':{'owned_server_stopped':client.stopped,'key_metadata_unchanged':client.key_metadata_unchanged}}))
        print(json.dumps(compact(value),ensure_ascii=False))
        return 1 if value['status']=='needs_review' else 0
    except (ResearchError,OSError,ValueError) as error:
        print(json.dumps({'ok':False,'code':getattr(error,'code','PIPELINE_RESEARCH_FAILED'),'automatic_retry':False,'new_fits':0}))
        return 1


if __name__=='__main__': raise SystemExit(main())
