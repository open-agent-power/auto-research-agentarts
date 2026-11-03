"""Build a task-bound teammate evidence collection folder and ZIP."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from autoresearch import evidence_submission as submission, knowledge_sources as guard
from autoresearch.contracts import canonical
from autoresearch.diagnostic_view import read_diagnostic_artifacts
from autoresearch.evidence_draft import prepare_draft
from autoresearch.handoff_view import read_handoff_artifacts
from autoresearch.pipeline_preparation_view import read_pipeline_preparation_artifacts
from autoresearch.tabular_preparation_view import read_tabular_preparation_artifacts

README='''# P02 队友取证包

本包分两层：`context/` 是已封存的任务和已有证据，只读；`return/` 是绑定同一任务的空白填写包，可编辑。空白表不是已取得的证据，也不是模型评议或科学批准。

1. 阅读 `docs/teammate-pipeline-brief.md`、`context/handoff.md` 和现有准备材料；按原始来源寻找实际导出、运行记录、染色与映射。未找到则如实写未知。
2. 在 `return/` 按其 README 填写提交者、来源、发现、摘要和未决问题；将来源原件放入 `return/sources/`。`mapping-templates/` 是辅助空表，填写后也放入 `return/sources/` 并在 `sources.csv` 登记；它们不替代任务所需附件或作者原件。
3. 将填写后的整个 `return/` 文件夹交回主团队。主团队按现有 `scripts/intake_evidence.py` 入口封存收据并准备片段；本包不自动调用模型或拟合。

`context/` 已包含完整绑定的管线和表格准备 JSON/MD，不需要重新下载这些已有上下文；它们不替代缺失的作者实际导出。`manifest.json` 记录交付时的文件字节与 SHA-256；编辑回传目录后哈希变化属于预期。
'''


def _files_under_docs():
    root=ROOT/'docs'
    pending=['teammate-pipeline-brief.md','evidence-return.md','evidence-intake.md','pipeline-evidence.md','tabular-evidence.md']
    found={}
    while pending:
        name=pending.pop()
        if name in found: continue
        raw=guard._read(root,name,1_000_000);found[name]=raw
        for link in re.findall(r'\]\(([^)]+)\)',raw.decode('utf-8-sig')):
            target=link.split('#',1)[0]
            if not target or ':' in target or target.startswith('/') or '?' in target: continue
            relative=(Path(name).parent/target)
            if relative.suffix.lower()!='.md':continue
            candidate=(root/relative).resolve()
            if candidate.is_relative_to(root.resolve()) and candidate.is_file():
                pending.append(candidate.relative_to(root.resolve()).as_posix())
    return found


def build(handoff_directory,diagnostic_directory,pipeline_input_directory,prepared_input_directory,output):
    inputs=[submission._root(x) for x in (handoff_directory,diagnostic_directory,pipeline_input_directory,prepared_input_directory)]
    target=submission._root(output);archive=target.with_name(target.name+'.zip')
    submission._require(not target.exists() and not archive.exists(),'Output folder and ZIP must both be fresh.')
    for source in inputs:
        for result in (target,archive):
            submission._require(not(result==source or result.is_relative_to(source) or source.is_relative_to(result)),'Output overlaps sealed input.')
    diagnostic=guard._json(guard._read(inputs[1],'diagnostic.json',3_000_000))
    read_diagnostic_artifacts(inputs[1],{'snapshot_sha256':diagnostic['iteration_snapshot_sha256']})
    handoff_files=read_handoff_artifacts(inputs[0],diagnostic);handoff=guard._json(handoff_files['handoff.json'])
    pipeline_files=read_pipeline_preparation_artifacts(inputs[2],handoff)
    prepared_files=read_tabular_preparation_artifacts(inputs[3],handoff)
    pipeline=guard._json(pipeline_files['pipeline-input.json']);prepared=guard._json(prepared_files['prepared-input.json'])
    target.parent.mkdir(parents=True,exist_ok=True);submission._root(target.parent)
    with tempfile.TemporaryDirectory(prefix='.collection-pack-',dir=target.parent) as temp:
        stage=Path(temp)/'pack';stage.mkdir()
        (stage/'README.md').write_text(README,encoding='utf-8',newline='\n')
        (stage/'context').mkdir()
        for name,raw in {**handoff_files,**pipeline_files,**prepared_files}.items(): (stage/'context'/name).write_bytes(raw)
        (stage/'context'/'README.md').write_text('这些文件是封存任务及已准备材料的只读副本；保留原快照身份，不代表作者确认、模型评议或实际执行。\n',encoding='utf-8')
        prepare_draft(inputs[0],inputs[1],stage/'return')
        for name,raw in _files_under_docs().items():
            dest=stage/'docs'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        for name in ('run-export.csv','channel-antibody.csv','export-workbook.csv','zero-aggregation.csv'):
            raw=guard._read(ROOT/'docs','templates/p02-mapping/'+name,100_000)
            for dest in (stage/'mapping-templates'/name,stage/'docs'/'templates'/'p02-mapping'/name):
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        files={p.relative_to(stage).as_posix():p.read_bytes() for p in sorted(stage.rglob('*')) if p.is_file()}
        manifest={'schema_version':'p02-evidence-collection-pack-v1','source_snapshots':{
            'diagnostic':diagnostic['snapshot_sha256'],'handoff':handoff['snapshot_sha256'],
            'pipeline_input':pipeline['snapshot_sha256'],'prepared_input':prepared['snapshot_sha256']},
            'files':{name:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)} for name,raw in files.items()}}
        (stage/'manifest.json').write_text(canonical(manifest)+'\n',encoding='utf-8',newline='\n')
        tempzip=Path(temp)/'pack.zip'
        with zipfile.ZipFile(tempzip,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(stage.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(stage).as_posix())
        submission._require(not target.exists() and not archive.exists(),'Output appeared during preparation.')
        with archive.open('xb') as dest, tempzip.open('rb') as src:
            for part in iter(lambda:src.read(1024*1024),b''):dest.write(part)
        try:stage.rename(target)
        except Exception:
            archive.unlink(missing_ok=True)
            raise
    return {'schema_version':manifest['schema_version'],'source_snapshots':manifest['source_snapshots'],
            'files':len(files),'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'model_calls':0,'new_fits':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('handoff-directory','diagnostic-directory','pipeline-input-directory','prepared-input-directory','output'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args()
    print(json.dumps(build(a.handoff_directory,a.diagnostic_directory,a.pipeline_input_directory,a.prepared_input_directory,a.output),ensure_ascii=False))

if __name__=='__main__':main()
