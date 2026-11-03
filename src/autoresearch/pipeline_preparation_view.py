"""Publish source-bound, explicitly unexecuted CellProfiler pipeline input."""
import copy
import hashlib
import tempfile
from pathlib import Path

from . import evidence_submission as submission, knowledge_sources as guard
from .contracts import canonical, fingerprint
from .diagnostic_view import read_diagnostic_artifacts
from .handoff_view import read_handoff_artifacts
from .pipeline_source import PROJECT, read_pipeline_evidence
from .returned_evidence import validate_packet

LIMITS={'pipeline-input.json':1_000_000,'pipeline-input.md':100_000}
GROUPS=[
 {'id':'channels','title':'图像命名','module_numbers':[3],'summary':'配置按 C0–C3 命名 OrigBF、OrigBlue、OrigGreen、OrigRed。'},
 {'id':'illumination_crop','title':'照明与裁剪','module_numbers':[5,6,7,8,9,10],'summary':'三个照明除法模块标记为禁用；裁剪配置选择 Orig 图像。'},
 {'id':'objects','title':'对象配置','module_numbers':[12,13,16],'summary':'配置识别 Nuclei、CellsGreen 和 CellsRed。'},
 {'id':'mask_branch','title':'掩膜与阈值','module_numbers':[14,15,17],'summary':'配置使用 CellsGreen 掩膜 CropRed；阈值及内存移除设置见原文。'},
 {'id':'intensity','title':'强度测量','module_numbers':[20],'summary':'配置图像 CropRed、CropGreen 与对象 CellsRed、CellsGreen。'},
 {'id':'export','title':'导出设置','module_numbers':[21],'summary':'配置逗号分隔输出、对象每图汇总和 NaN 表示。'}]
GAPS=[{'id':'actual_run','question':'实际运行版本和批次是否对应此保存管线？'},
      {'id':'antibody_dye','question':'抗体、染料与通道如何由作者材料对应？'},
      {'id':'export_workbook','question':'实际 CellsGreen、CellsRed、Image CSV 的列如何对应工作簿？'},
      {'id':'zero_aggregation','question':'Count 为零及 NaN 在导出和聚合时如何处理？'}]


def _require(condition,message): submission._require(condition,message)
def _digest(value): return hashlib.sha256(value).hexdigest()


def _capture(pipeline_directory,intake_directory,handoff):
    submission._handoff(handoff)
    original=read_pipeline_evidence(pipeline_directory)
    pipeline=guard._json(original['pipeline-source.json'])
    root=submission._root(intake_directory)
    receipt=submission.read_submission(root/'receipt',handoff)
    packet=guard._json(guard._read(root,'packet.json',4_000_000)); validate_packet(packet)
    _require(packet['submission_snapshot_sha256']==receipt['snapshot_sha256'] and packet['handoff_snapshot_sha256']==handoff['snapshot_sha256'] and packet['task_id']==receipt['task_id']==handoff['selected_task']['id'],'Receipt, packet and task differ.')
    sources={s['id']:s for s in receipt['sources']}
    _require(set(sources)=={'project','pipeline-settings','pipeline-raw'} and len(receipt['sources'])==3,'Unexpected submission sources.')
    _require(packet['sources']==[{k:copy.deepcopy(s[k]) for k in ('id','sha256','url','media_type','license_note','bytes')} for s in receipt['sources']],'Packet sources differ from receipt.')
    payloads={key:guard._read(root/'receipt',v['path'],submission.MAX_FILE,expected_sha=v['sha256'],expected_bytes=v['bytes']) for key,v in sources.items()}
    _require(_digest(payloads['project'])==PROJECT[1] and len(payloads['project'])==PROJECT[2] and payloads['pipeline-settings']==original['pipeline-source.json'] and payloads['pipeline-raw']==original['original-pipeline.txt'],'Receipt bytes differ from exact source project or pipeline.')
    claims={c['id']:c for c in packet['submission_claims']}; findings={f['id']:f for f in receipt['findings']}; chunks={c['id']:c for c in packet['chunks']}
    _require(len(findings)==len(receipt['findings'])==len(claims) and all({k:v for k,v in c.items() if k not in {'chunk_ids','interpretation_status'}}==findings.get(c['id']) for c in claims.values()),'Packet claims differ from receipt.')
    modules=[]
    for index,excerpt in enumerate(pipeline['selected_excerpts']):
        fid='saved-module-'+str(excerpt['module_number']); claim=claims.get(fid)
        _require(claim is not None and claim['source_id']=='pipeline-settings' and claim['locator']=={'kind':'json_pointer','value':'/selected_excerpts/'+str(index)},'Module source pointer differs.')
        selected=[chunks[key] for key in claim['chunk_ids']]
        _require(bool(selected) and ''.join(c['text'] for c in sorted(selected,key=lambda c:c['start_char']))==canonical(excerpt),'Module chunks differ from exact original excerpt.')
        modules.append({**copy.deepcopy(excerpt),'finding_id':fid,'chunk_ids':list(claim['chunk_ids'])})
    _require(len(pipeline['modules'])==26 and len(modules)==18 and len(receipt['findings'])==20 and len(packet['chunks'])==21,'Unexpected complete source counts.')
    numbers={m['module_number'] for m in modules}
    _require(all(set(g['module_numbers'])<=numbers for g in GROUPS),'Missing group source excerpt.')
    view={'schema_version':'p02-pipeline-preparation-view-v1','handoff_snapshot_sha256':handoff['snapshot_sha256'],
          'task_id':receipt['task_id'],'source_pipeline_snapshot_sha256':pipeline['snapshot_sha256'],
          'receipt_snapshot_sha256':receipt['snapshot_sha256'],'packet_snapshot_sha256':packet['snapshot_sha256'],
          'source':copy.deepcopy(pipeline['source']),'header_lines':copy.deepcopy(pipeline['header_lines']),
          'module_index':copy.deepcopy(pipeline['modules']),'modules':modules,
          'counts':{'sources':len(sources),'findings':len(findings),'chunks':len(chunks),'modules':len(pipeline['modules']),'selected_modules':len(modules)},
          'groups':copy.deepcopy(GROUPS),'groups_origin':'operator_curated_from_saved_settings',
          'gaps':copy.deepcopy(GAPS),'gaps_origin':'operator_curated_questions',
          'configured_settings_only':True,'execution_proven':False,'model_read_performed':False,
          'scientific_validation':False,'biological_endpoint_eligible':False,'model_calls':0,'new_fits':0,'status':'prepared'}
    view['snapshot_sha256']=fingerprint(view)
    return view


def _markdown(view):
    lines=['# 已准备的 CellProfiler 管线材料','','保存的配置不证明运行、导出结果、ALP 身份或科学验证；模型尚未读取。','','## 模块组（操作员整理）','']
    for g in view['groups']:lines.append('- '+g['title']+'（'+', '.join(map(str,g['module_numbers']))+'）：'+g['summary'])
    lines+=['','## 待核对（操作员提出）','']
    for g in view['gaps']:lines.append('- '+g['question'])
    lines+=['','完整原文、启用状态和来源坐标见 JSON。模型调用 0，新增拟合 0。','']
    return '\n'.join(lines).encode('utf-8')


def _manifest(view,files):
    return {'schema_version':'p02-pipeline-preparation-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
            'handoff_snapshot_sha256':view['handoff_snapshot_sha256'],
            'files':{k:{'sha256':_digest(v),'bytes':len(v)} for k,v in files.items()}}


def read_pipeline_preparation_artifacts(directory,handoff):
    submission._handoff(handoff); root=submission._root(directory)
    manifest=guard._json(guard._read(root,'manifest.json',100_000)); files={k:guard._read(root,k,n) for k,n in LIMITS.items()}
    view=guard._json(files['pipeline-input.json'])
    _require(view.get('schema_version')=='p02-pipeline-preparation-view-v1' and view.get('snapshot_sha256')==fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}) and view.get('handoff_snapshot_sha256')==handoff['snapshot_sha256'] and view.get('task_id')==handoff['selected_task']['id'] and view.get('status')=='prepared' and view.get('configured_settings_only') is True and all(view.get(k) is False for k in ('execution_proven','model_read_performed','scientific_validation','biological_endpoint_eligible')) and type(view.get('model_calls')) is int and view['model_calls']==0 and type(view.get('new_fits')) is int and view['new_fits']==0 and view.get('groups')==GROUPS and view.get('gaps')==GAPS and view.get('groups_origin')=='operator_curated_from_saved_settings' and view.get('gaps_origin')=='operator_curated_questions' and view.get('counts')=={'sources':3,'findings':20,'chunks':21,'modules':26,'selected_modules':18} and len(view.get('modules',[]))==18 and len(view.get('module_index',[]))==26,'Prepared pipeline identity or boundary changed.')
    _require(manifest==_manifest(view,files) and files['pipeline-input.md']==_markdown(view),'Prepared pipeline artifacts changed.')
    return files


def export_pipeline_preparation(pipeline_directory,intake_directory,handoff_directory,diagnostic_directory,output):
    target=submission._root(output); _require(not target.exists(),'Use a fresh output directory.')
    for value in (pipeline_directory,intake_directory,handoff_directory,diagnostic_directory):
        source=submission._root(value)
        _require(not(target==source or target.is_relative_to(source) or source.is_relative_to(target)),'Output overlaps input.')
    diagnostic_root=submission._root(diagnostic_directory)
    diagnostic=guard._json(guard._read(diagnostic_root,'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(diagnostic_root,{'snapshot_sha256':diagnostic['iteration_snapshot_sha256']})
    handoff=guard._json(read_handoff_artifacts(submission._root(handoff_directory),diagnostic)['handoff.json'])
    view=_capture(pipeline_directory,intake_directory,handoff)
    files={'pipeline-input.json':(canonical(view)+'\n').encode('utf-8'),'pipeline-input.md':_markdown(view)}
    _require(all(len(raw)<=LIMITS[name] for name,raw in files.items()),'Pipeline view exceeds size bounds.')
    target.parent.mkdir(parents=True,exist_ok=True);submission._root(target.parent)
    with tempfile.TemporaryDirectory(prefix='.pipeline-input-',dir=target.parent) as temporary:
        staged=Path(temporary)/'view';staged.mkdir()
        for name,raw in files.items():
            with (staged/name).open('xb') as stream:stream.write(raw)
        with (staged/'manifest.json').open('xb') as stream:stream.write((canonical(_manifest(view,files))+'\n').encode('utf-8'))
        read_pipeline_preparation_artifacts(staged,handoff)
        _require(not target.exists(),'Output appeared during sealing.')
        staged.rename(target)
    return {'snapshot_sha256':view['snapshot_sha256'],'handoff_snapshot_sha256':view['handoff_snapshot_sha256'],'counts':view['counts'],'status':view['status']}
