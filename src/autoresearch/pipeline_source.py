"""Extract the pinned CellProfiler pipeline as inert, source-bound text."""
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

import h5py

from .chemotopo_data import _captured
from .chemotopo_project import PROJECT, _storage
from .chemotopo_experiment_evidence import _safe_file
from .contracts import canonical, fingerprint

EXTRACTOR_VERSION = 'p02-pipeline-source-v1'
DATA = '/Measurements/2017-08-22-09-08-29/Experiment/Pipeline_Pipeline/data'
INDEX = '/Measurements/2017-08-22-09-08-29/Experiment/Pipeline_Pipeline/index'
SELECTED = frozenset({'NamesAndTypes','ImageMath','Crop','IdentifyPrimaryObjects','IdentifySecondaryObjects',
                      'MeasureObjectIntensity','ExportToSpreadsheet','ApplyThreshold','CorrectIlluminationApply','MaskImage','ConserveMemory'})
HEADING = re.compile(r'^([A-Za-z][A-Za-z0-9]*):\[module_num:(\d+)\|')
ENABLED = re.compile(r'(?:^|\|)enabled:(True|False)(?=\||\])')


def _enabled(heading):
    matches=ENABLED.findall(heading)
    if len(matches)!=1: raise ValueError('Missing or ambiguous module enabled state')
    return matches[0]=='True'


def _extractor_identity():
    root=Path(__file__).parent
    files=('pipeline_source.py','chemotopo_project.py','chemotopo_data.py')
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
    return {'extractor_code_sha256':fingerprint(hashes),'extractor_component_sha256':hashes,'h5py_version':h5py.__version__}


def _dataset(handle, path):
    current = handle
    for part in path.strip('/').split('/'):
        if not isinstance(current, h5py.Group) or not isinstance(current.get(part, getlink=True), h5py.HardLink):
            raise ValueError('Expected only hard links for pipeline datasets')
        current = current[part]
    if not isinstance(current, h5py.Dataset) or not _storage(current)['safe_to_read']:
        raise ValueError('Unsafe pipeline dataset storage')
    return current


def extract_pipeline(project_path, *, source_url, license_note):
    """Return the complete escaped ASCII bytes and source-bound typed projection."""
    if not all(isinstance(v, str) and 0 < len(v) <= 2048 for v in (source_url, license_note)):
        raise ValueError('Explicit source URL and license note required')
    name, sha, size = PROJECT
    content = _captured(Path(project_path), sha, size)
    with h5py.File(BytesIO(content), 'r') as handle:
        data, index = _dataset(handle, DATA), _dataset(handle, INDEX)
        info = h5py.check_string_dtype(data.dtype)
        if data.shape != (2,) or info is None or info.encoding != 'ascii' or info.length is not None:
            raise ValueError('Unexpected pipeline text datatype or shape')
        if index.shape != (1, 3) or index.dtype.kind not in 'iu' or index.dtype.itemsize > 8:
            raise ValueError('Unexpected pipeline index datatype or shape')
        rows = index[:].tolist()
        if rows != [[0, 1, 2]]:
            raise ValueError('Unexpected stored pipeline index')
        values = data[:]
        if any(not isinstance(x, bytes) or len(x) > 100_000 for x in values):
            raise ValueError('Pipeline entries exceed bounds or are not bytes')
        entries = [{'element_index':i,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()}
                   for i,value in enumerate(values)]
        if values[0] != values[1]:
            raise ValueError('Stored pipeline entries are not identical')
        raw = values[0]
    text = raw.decode('ascii', 'strict')
    lines = text.split('\\n')
    if len(lines) > 5000 or any(len(line) > 10000 for line in lines):
        raise ValueError('Pipeline line bounds exceeded')
    starts=[]
    for i,line in enumerate(lines):
        match=HEADING.match(line)
        if match: starts.append((i,match.group(1),int(match.group(2))))
    if len(starts) != 26 or [x[2] for x in starts] != list(range(1,27)):
        raise ValueError('Unexpected pipeline module order')
    origin={'project_file':name,'project_sha256':sha,'source_url':source_url,'license_note':license_note,
            'hdf5_data_path':DATA,'hdf5_index_path':INDEX,'element_index':0,
            'raw_sha256':entries[0]['sha256'],'extractor_version':EXTRACTOR_VERSION,**_extractor_identity()}
    modules=[]; excerpts=[]
    for i,(start,module,number) in enumerate(starts):
        end=starts[i+1][0] if i+1<len(starts) else len(lines)
        while end>start+1 and lines[end-1]=='': end-=1
        row={'module':module,'module_number':number,'enabled':_enabled(lines[start]),'line_start':start+1,'line_end':end}
        modules.append(row)
        if module in SELECTED:
            excerpts.append({**row,'origin':{**origin,'line_range':[start+1,end]},
                             'heading':lines[start], 'raw_settings_lines':lines[start+1:end]})
    result={'schema_version':EXTRACTOR_VERSION,'source':origin,'entries':entries,'stored_index':rows,
            'logical_line_count':len(lines),'header_lines':lines[:starts[0][0]],'modules':modules,'selected_excerpts':excerpts,
            'selected_module_names':sorted(SELECTED),'line_split':'literal backslash followed by n only; other escapes untouched',
            'configured_settings_only':True,'execution_proven':False,'scientific_validation':False,
            'notice':'Stored pipeline settings do not establish execution, output measurements, antibody identity, or biological endpoint.'}
    result['snapshot_sha256']=fingerprint(result)
    return raw,result


def export_pipeline_evidence(project_path, output_directory, *, source_url, license_note):
    """Write a fresh immutable-by-convention artifact set; never alter the source."""
    output=Path(output_directory).absolute()
    for part in (output,*output.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():
            raise ValueError('Output path redirects')
    resolved_output=output.resolve(); resolved_source=Path(project_path).absolute().resolve()
    if resolved_output==resolved_source or resolved_output.is_relative_to(resolved_source) or resolved_source.is_relative_to(resolved_output):
        raise ValueError('Output and source project cannot overlap')
    if output.exists(): raise ValueError('Output directory must be fresh')
    raw,projection=extract_pipeline(project_path,source_url=source_url,license_note=license_note)
    files={'original-pipeline.txt':raw,'pipeline-source.json':(canonical(projection)+'\n').encode('utf-8')}
    manifest={'schema_version':'p02-pipeline-source-artifacts-v1','snapshot_sha256':projection['snapshot_sha256'],
              'files':{k:{'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for k,v in files.items()}}
    output.mkdir(parents=True,exist_ok=False)
    for name,value in files.items():
        with (output/name).open('xb') as stream: stream.write(value)
    with (output/'manifest.json').open('xb') as stream: stream.write((canonical(manifest)+'\n').encode('utf-8'))
    return manifest


def read_pipeline_evidence(directory):
    """Verify artifact bytes, self-hash, stored source identity, and excerpt coordinates."""
    root=Path(directory).absolute()
    manifest=json.loads(_safe_file(root/'manifest.json',100_000)); raw=_safe_file(root/'original-pipeline.txt',100_000); data=_safe_file(root/'pipeline-source.json',500_000); view=json.loads(data)
    expected={'schema_version':'p02-pipeline-source-artifacts-v1','snapshot_sha256':view['snapshot_sha256'],
              'files':{k:{'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for k,v in {'original-pipeline.txt':raw,'pipeline-source.json':data}.items()}}
    if manifest!=expected or view.get('snapshot_sha256')!=fingerprint({k:v for k,v in view.items() if k!='snapshot_sha256'}):raise ValueError('Artifact identity changed')
    lines=raw.decode('ascii','strict').split('\\n'); digest=hashlib.sha256(raw).hexdigest()
    if view['source']['project_sha256']!=PROJECT[1] or any(e['sha256']!=digest or e['bytes']!=len(raw) for e in view['entries']):raise ValueError('Source identity changed')
    for item in view['modules']:
        a=item['line_start']
        if not 1<=a<=len(lines) or _enabled(lines[a-1]) is not item['enabled']:raise ValueError('Module enabled state changed')
    for item in view['selected_excerpts']:
        a,b=item['line_start'],item['line_end']
        if not (1<=a<=b<=len(lines)) or item['heading']!=lines[a-1] or _enabled(lines[a-1]) is not item['enabled'] or item['raw_settings_lines']!=lines[a:b] or item['origin']!={**view['source'],'line_range':[a,b]}:raise ValueError('Excerpt coordinates changed')
    return {'original-pipeline.txt':raw,'pipeline-source.json':data}
