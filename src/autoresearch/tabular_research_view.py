"""Seal the actual tabular assessment with separate operator fact checks."""
import copy
import hashlib
import json
import tempfile
from pathlib import Path

from . import evidence_submission as submission, knowledge_sources as guard, source_assessment_view
from .contracts import canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts
from .tabular_preparation_view import read_tabular_preparation_artifacts
from .tabular_research import TabularResearchCloudLoop

LIMITS={'tabular-research.json':3_000_000,'tabular-research.md':200_000}
OPERATOR_NOTES=[
 {'origin':'operator_assistant_inspection','text':'模型回答没有给出所选单元格的算术对照；该核对为操作员补充，不是模型自我修正。'},
 {'origin':'operator_assistant_inspection','text':'B8S1_Normalised!E2 = 0.6756492790031468，与 B8S1_SNR!E2/E82 同值；B8S1_SNR!G2/G82 = 1.3365449385299482。这是指定坐标的算术核对，不证明作者公式或 ALP 身份。'},
 {'origin':'operator_assistant_inspection','text':'B2 的 0 是 Chemistry 编号，不是 Count；来源已有 B8S1 表名，因此称没有批次标识过宽，完整批次及导出映射仍未确认。'}]


def _require(condition,message):submission._require(condition,message)
def _hash(raw):return hashlib.sha256(raw).hexdigest()


def _operator_notes(view):
    # These checks were made for this exact response and source; do not attach
    # them to a future workbook or another model's answer.
    if (view.get('source_snapshot_sha256')=='2d89a33eb998fe371b31c79d6b194415c6d0931be4ca00a5a009a904a249d512'
        and view.get('assessment_action_id')=='p02sourceassessment-3d11ce393abfcf8a8145d2e3633f9d41'):
        return copy.deepcopy(OPERATOR_NOTES)
    return []


def capture_tabular_research(workspace,prepared_input):
    _require(type(prepared_input) is dict and prepared_input.get('schema_version')=='p02-tabular-preparation-view-v1' and prepared_input.get('snapshot_sha256')==fingerprint({k:v for k,v in prepared_input.items() if k!='snapshot_sha256'}),'Intact prepared tabular view required.')
    base=source_assessment_view._capture(workspace,controller_class=TabularResearchCloudLoop)
    loop=TabularResearchCloudLoop(workspace)
    with loop.study._connect() as con:config,state,_=loop.study._state(con)
    _require(base['source_snapshot_sha256']==prepared_input['packet_snapshot_sha256'] and base['handoff_snapshot_sha256']==prepared_input['handoff_snapshot_sha256'] and state['source_snapshot_sha256']==base['source_snapshot_sha256'],'Assessment and prepared input differ.')
    prior=json.loads(config['prior_attempt']);private=prior.pop('private_sources')
    _require(type(private) is dict and prior['prepared_input_snapshot_sha256']==prepared_input['snapshot_sha256'] and prior['packet_snapshot_sha256']==base['source_snapshot_sha256'] and prior['handoff_snapshot_sha256']==base['handoff_snapshot_sha256'],'Frozen prepared input and prior history differ.')
    view={**{k:copy.deepcopy(v) for k,v in base.items() if k!='snapshot_sha256'},'schema_version':'p02-tabular-research-view-v1',
          'prepared_input_snapshot_sha256':prepared_input['snapshot_sha256'],'prior_budget_history':prior,'operator_notes':_operator_notes(base)}
    view['snapshot_sha256']=fingerprint(view);return view


def _markdown(view):
    base=source_assessment_view._markdown(view).decode('utf-8')
    return (base+'\n## 操作员独立核对（不是模型回答）\n\n'+'\n'.join('- '+n['text'] for n in view['operator_notes'])+'\n').encode('utf-8')


def _manifest(view,files):
    return {'schema_version':'p02-tabular-research-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
            'prepared_input_snapshot_sha256':view['prepared_input_snapshot_sha256'],'source_snapshot_sha256':view['source_snapshot_sha256'],
            'handoff_snapshot_sha256':view['handoff_snapshot_sha256'],
            'files':{k:{'sha256':_hash(v),'bytes':len(v)} for k,v in files.items()}}


def read_tabular_research_artifacts(directory,prepared_input):
    root=submission._root(directory);manifest=guard._json(guard._read(root,'manifest.json',100_000));files={k:guard._read(root,k,n) for k,n in LIMITS.items()};view=guard._json(files['tabular-research.json'])
    _require(type(prepared_input) is dict and prepared_input.get('snapshot_sha256')==fingerprint({k:v for k,v in prepared_input.items() if k!='snapshot_sha256'}) and view.get('schema_version')=='p02-tabular-research-view-v1' and view.get('snapshot_sha256')==fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}) and view.get('prepared_input_snapshot_sha256')==prepared_input['snapshot_sha256'] and view.get('source_snapshot_sha256')==prepared_input['packet_snapshot_sha256'] and view.get('handoff_snapshot_sha256')==prepared_input['handoff_snapshot_sha256'] and view.get('operator_notes')==_operator_notes(view) and view.get('scientific_validation') is False and view.get('biological_endpoint_eligible') is False and view.get('task_complete') is False and view.get('execution',{}).get('new_fits')==0 and 'private_sources' not in view.get('prior_budget_history',{}),'Tabular assessment identity or boundary changed.')
    _require(manifest==_manifest(view,files) and files['tabular-research.md']==_markdown(view),'Tabular assessment artifacts changed.')
    return files


def export_tabular_research(workspace,prepared_input_directory,handoff_directory,diagnostic_directory,output):
    target=submission._root(output);_require(not target.exists(),'Use a fresh publication directory.')
    for item in (workspace,prepared_input_directory,handoff_directory,diagnostic_directory):
        source=submission._root(item)
        _require(not(target==source or target.is_relative_to(source) or source.is_relative_to(target)),'Output overlaps source.')
    droot=submission._root(diagnostic_directory);diagnostic=guard._json(guard._read(droot,'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(droot,{'snapshot_sha256':diagnostic['iteration_snapshot_sha256']})
    handoff=guard._json(read_handoff_artifacts(handoff_directory,diagnostic)['handoff.json'])
    prepared=guard._json(read_tabular_preparation_artifacts(prepared_input_directory,handoff)['prepared-input.json'])
    view=capture_tabular_research(workspace,prepared);files={'tabular-research.json':(canonical(view)+'\n').encode('utf-8'),'tabular-research.md':_markdown(view)}
    _require(all(len(v)<=LIMITS[k] for k,v in files.items()),'Tabular research view exceeds bounds.')
    target.parent.mkdir(parents=True,exist_ok=True);submission._root(target.parent)
    with tempfile.TemporaryDirectory(prefix='.tabular-research-',dir=target.parent) as temp:
        stage=Path(temp)/'view';stage.mkdir()
        for k,v in files.items():
            with (stage/k).open('xb') as f:f.write(v)
        with (stage/'manifest.json').open('xb') as f:f.write((canonical(_manifest(view,files))+'\n').encode('utf-8'))
        read_tabular_research_artifacts(stage,prepared);_require(not target.exists(),'Output appeared during sealing.');stage.rename(target)
    return _manifest(view,files)
