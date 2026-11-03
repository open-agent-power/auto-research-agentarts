"""Verify a pinned workbench recipe and publish only its selected snapshots."""
import hashlib
from pathlib import Path

from . import knowledge_sources as guard
from .chemotopo_bundle import build_handoff
from .chemotopo_experiment_evidence import _safe_file
from .contracts import ResearchError, fingerprint
from .current_workbench import select_bundle

PRODUCT_ROOT=Path(__file__).resolve().parents[2]
SOURCES={
 'baseline_directory':('research.json','baseline_snapshot_sha256'),
 'iteration_directory':('iteration.json','iteration_snapshot_sha256'),
 'postrun_directory':('postrun.json','postrun_snapshot_sha256'),
 'diagnostic_directory':('diagnostic.json','diagnostic_snapshot_sha256'),
 'handoff_directory':('handoff.json','handoff_snapshot_sha256'),
 'source_progress_directory':('progress.json','source_progress_snapshot_sha256'),
 'prepared_input_directory':('prepared-input.json','prepared_input_snapshot_sha256'),
 'source_continuation_directory':('continuation.json','source_continuation_snapshot_sha256'),
 'pipeline_input_directory':('pipeline-input.json','pipeline_input_snapshot_sha256'),
 'pipeline_research_directory':('pipeline-research.json','pipeline_research_snapshot_sha256'),
 'tabular_research_directory':('tabular-research.json','tabular_research_snapshot_sha256'),
 'dossier_directory':('research-dossier.json','dossier_snapshot_sha256')}
DEPENDENCIES={'postrun_directory':('iteration_directory',),'diagnostic_directory':('iteration_directory',),
 'handoff_directory':('diagnostic_directory',),'source_progress_directory':('handoff_directory','diagnostic_directory'),
 'prepared_input_directory':('handoff_directory',),'source_continuation_directory':('source_progress_directory',),
 'pipeline_input_directory':('handoff_directory',),'pipeline_research_directory':('pipeline_input_directory',),
 'tabular_research_directory':('prepared_input_directory',),
 'dossier_directory':('baseline_directory','iteration_directory','postrun_directory','diagnostic_directory','handoff_directory','source_progress_directory','prepared_input_directory','source_continuation_directory','pipeline_input_directory','pipeline_research_directory','tabular_research_directory')}


def _require(condition,message):
    if not condition:raise ResearchError('INVALID_RECIPE',message)


def _path(value):
    _require(type(value) is str and 0<len(value)<=4000 and '\x00' not in value,'Bounded path required.')
    path=Path(value);return path.absolute() if path.is_absolute() else (PRODUCT_ROOT/path).absolute()


def inspect_recipe(recipe_path='config/workbench-p02.json'):
    recipe=guard._json(_safe_file(_path(recipe_path),100_000))
    _require(type(recipe) is dict and set(recipe)=={'schema_version','label','sources'} and recipe['schema_version']=='p02-workbench-recipe-v1' and type(recipe['label']) is str and 1<=len(recipe['label'].strip())<=200 and all(ord(c)>=32 for c in recipe['label']),'Invalid recipe fields or label.')
    sources=recipe['sources'];_require(type(sources) is dict and 'baseline_directory' in sources and set(sources)<=set(SOURCES),'Baseline and known source keys required.')
    for name,required in DEPENDENCIES.items():
        if name in sources:_require(all(item in sources for item in required),'A selected source lacks its required dependency.')
    selected={};paths={}
    for key,descriptor in sources.items():
        _require(type(descriptor) is dict and set(descriptor)=={'directory','snapshot_sha256'} and guard._digest(descriptor['snapshot_sha256']),'Source path and SHA-256 required.')
        folder=_path(descriptor['directory']);filename,manifest_key=SOURCES[key]
        raw=_safe_file(folder/filename,3_000_000);value=guard._json(raw)
        _require(type(value) is dict and value.get('snapshot_sha256')==fingerprint({k:v for k,v in value.items() if k!='snapshot_sha256'})==descriptor['snapshot_sha256'],'Source snapshot mismatch.')
        manifest=guard._json(_safe_file(folder/'manifest.json',100_000))
        _require(manifest.get('snapshot_sha256')==descriptor['snapshot_sha256'] and manifest.get('files',{}).get(filename)=={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)},'Source manifest mismatch.')
        selected[key]={'snapshot_sha256':descriptor['snapshot_sha256'],'bundle_manifest_key':manifest_key}
        paths[key]=folder
    return {'schema_version':'p02-workbench-recipe-inspection-v1','label':recipe['label'],'sources':selected,'model_calls':0,'new_fits':0},paths


def publish_recipe(recipe_path,output,*,select=False):
    inspection,paths=inspect_recipe(recipe_path)
    target=_path(output)
    options={k:v for k,v in paths.items() if k not in {'baseline_directory','iteration_directory'}}
    publication=build_handoff(paths['baseline_directory'],paths.get('iteration_directory'),target,**options)
    manifest=guard._json(_safe_file(target/'bundle-manifest.json',100_000))
    expected={v['bundle_manifest_key']:v['snapshot_sha256'] for v in inspection['sources'].values()}
    if 'iteration_directory' not in paths:expected['iteration_snapshot_sha256']=None
    actual={k:v for k,v in manifest.items() if k.endswith('_snapshot_sha256')}
    _require(actual==expected,'Built bundle snapshots differ from recipe; existing bundle preserved and not selected.')
    result={'schema_version':'p02-workbench-recipe-publication-v1',**publication,'label':inspection['label'],'snapshots':expected,'selected':False,'model_calls':0,'new_fits':0}
    if select:
        select_bundle(target,label=inspection['label'],product_root=PRODUCT_ROOT);result['selected']=True
    return result
