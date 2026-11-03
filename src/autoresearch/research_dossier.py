"""Extract a source-bound research dossier from an already sealed workbench."""
import hashlib
from pathlib import Path

from .contracts import fingerprint
from . import snapshot_viewer as viewer


def _fields(value,keys):
    return {key:value[key] for key in keys if key in value}


def dossier_data(bundle_path):
    """Return structured published evidence; no inference, model call, or fit."""
    root=Path(bundle_path).absolute()
    before=viewer._read(root/'bundle-manifest.json',viewer.MAX_MANIFEST)
    files=viewer.load_bundle(root)
    after=viewer._read(root/'bundle-manifest.json',viewer.MAX_MANIFEST)
    if before!=after:raise ValueError('Bundle manifest changed during dossier capture')
    manifest=viewer._json(before)
    def load(name):
        raw=files.get('data/'+name+'.json')
        return viewer._json(raw) if raw is not None else None
    baseline=load('research');iteration=load('iteration');diagnostic=load('diagnostic');handoff=load('handoff')
    continuation=load('source-continuation');pipeline=load('pipeline-research');tabular=load('tabular-research')
    pipeline_input=load('pipeline-input');prepared=load('prepared-input');postrun=load('postrun');progress=load('source-progress')
    sections=[]
    def add(id,title,value,keys):
        if value is not None:sections.append({'id':id,'title':title,'data':_fields(value,keys)})
    add('baseline','基线与预测协议',baseline,('goal','status','scope','endpoint_gate','execution','prediction','comparison','actions','scientific_validation'))
    add('iteration','模型选择的数值迭代',iteration,('goal','status','controller_status','task_origin','execution','protocol','comparisons','actions','limits','interpretation_notice','scientific_validation','llm_weight_training'))
    add('diagnostic','分组误差诊断',diagnostic,('goal','study_status','controller_status','controller_reason','execution','candidate_facts','prior_diagnostics','topography','assessment','actions','limitations','terminal_control_applied','incomplete_notice'))
    add('handoff','取证任务',handoff,('selected_task','selected_action_id','cited_facts','model_reason_unreviewed','study_status','controller_status','execution','waiting_for_external_input','external_task_executed','scientific_validation'))
    add('source_progress','早期资料评议进度',progress,('study_status','controller_status','controller_reason','execution','read_aliases','read_source_ids','unfinished_requests','automatic_retry','notice','task_complete'))
    add('source_continuation','未知请求与续接',continuation,('status','disposition','budget','profile','prior','response','schema_diagnostics','accepted_assessment','needed_questions','automatic_retry','notice','task_complete','scientific_validation'))
    add('pipeline_research','管线配置读取',pipeline,('goal','study_status','controller_status','controller_reason','execution','read_groups','read_aliases','read_modules','actions','revision','operator_note','notice','execution_proven','scientific_validation'))
    add('tabular_research','表格来源评议',tabular,('goal','study_status','controller_status','controller_reason','execution','contributor','read_source_ids','read_aliases','alias_map','chunks','actions','answers','assessment_action_id','interpretation_status','operator_notes','submission_claims_unverified','unresolved_questions','notice','task_complete','scientific_validation','biological_endpoint_eligible'))
    add('prior_postrun','先前提案与修订',postrun,('goal','study_status','controller_status','controller_reason','actions','execution','assessment','scientific_validation'))
    sources={'baseline_manifest':baseline.get('source_manifest',[]),'baseline_citations':baseline.get('citations',[]),
             'iteration_citations':iteration.get('citations',[]) if iteration else [],
             'handoff_source_snapshots':handoff.get('source_snapshots',{}) if handoff else {},
             'pipeline_origin':pipeline_input.get('source') if pipeline_input else None,
             'tabular_sources':tabular.get('sources',[]) if tabular else [],
             'prepared_selections':prepared.get('selections',[]) if prepared else []}
    result={'schema_version':'p02-research-dossier-v1','bundle_manifest_sha256':hashlib.sha256(before).hexdigest(),
            'source_snapshots':{k:v for k,v in manifest.items() if k.endswith('_snapshot_sha256') and k!='dossier_snapshot_sha256'},
            'sections':sections,'sources':sources,
            'limitations':['封存记录提供一致性和可追溯性，不代表作者签名或新增科学验证。',
                           '模型原文与操作员核对分开；来源配置、已读取材料和实际执行各有不同边界。',
                           '数值探索不等于独立盲测或 LLM 权重训练；生物终点资格以封存记录为准。'],
            'scientific_validation':False}
    result['snapshot_sha256']=fingerprint(result)
    return result
