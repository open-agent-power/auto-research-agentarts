"""Bounded read-only inventory of the pinned ChemoTopoChip HDF5 project."""
from io import BytesIO
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
import re

import h5py
import numpy as np

from .chemotopo_data import _captured
from .chemotopo_rebuild import PROJECT

MAX_NODES=500
MAX_DEPTH=20
MAX_SAMPLES=4
MAX_TEXT_BYTES=1024
BUILTIN_FILTERS={1,2,3,5,6}
MEASUREMENT='2017-08-22-09-08-29'
_SAMPLE=re.compile(r'^/Measurements/2017-08-22-09-08-29/(?:Experiment/(?:CellProfiler_Version|Run_Timestamp|ChannelType_[A-Za-z]+)|Image/(?:Channel_[A-Za-z]+|Frame_[A-Za-z]+|Series_[A-Za-z]+|FileName_[A-Za-z]+|ImageNumber))/(?:data|index)$')


def _storage(dataset):
    plist=dataset.id.get_create_plist()
    filters=[int(plist.get_filter(i)[0]) for i in range(plist.get_nfilters())]
    virtual=plist.get_layout()==h5py.h5d.VIRTUAL
    external=plist.get_external_count()>0
    allowed=not virtual and not external and all(i in BUILTIN_FILTERS for i in filters)
    return {'virtual':virtual,'external_storage':external,'filters':filters,'safe_to_read':allowed}


def _samples(dataset,path,storage):
    if not storage['safe_to_read'] or not (path=='/Version' or _SAMPLE.fullmatch(path)):
        return None
    shape=dataset.shape
    if shape is None or not 1 <= len(shape) <= 2 or shape[0]>MAX_SAMPLES or any(n>MAX_SAMPLES for n in shape):
        return None
    dtype=dataset.dtype
    string=h5py.check_string_dtype(dtype)
    if string is None and dtype.kind not in 'iu': return None
    if string is not None and string.encoding not in ('utf-8','ascii'): return None
    values=dataset[...]
    def convert(value):
        if isinstance(value,(bytes,np.bytes_)):
            if len(value)>MAX_TEXT_BYTES: raise ValueError('selected string exceeds bound')
            return bytes(value).decode('utf-8','strict')
        if isinstance(value,str):
            if len(value.encode('utf-8'))>MAX_TEXT_BYTES: raise ValueError('selected string exceeds bound')
            return value
        if isinstance(value,(int,np.integer)): return int(value)
        raise ValueError('unexpected selected value type')
    if len(shape)==1: result=[convert(v) for v in values]
    else: result=[[convert(v) for v in row] for row in values]
    return {'classification':'stored_measurement' if path.startswith('/Measurements/') else 'stored_project_version',
            'values':result,'index_basis':'dataset offsets; feature index dataset stored separately'}


def _inventory(content):
    objects=[]; skipped=[]; seen=set(); node_count=0
    with h5py.File(BytesIO(content),'r') as handle:
        def walk(group,path,depth):
            nonlocal node_count
            if depth>MAX_DEPTH: raise ValueError('project exceeds depth bound')
            for name in sorted(group.keys()):
                node_count+=1
                if node_count>MAX_NODES: raise ValueError('project exceeds node bound')
                child=path+'/'+name
                link=group.get(name,getlink=True)
                if not isinstance(link,h5py.HardLink):
                    skipped.append({'path':child,'kind':type(link).__name__}); continue
                obj=group[name]
                address=int(h5py.h5o.get_info(obj.id).addr)
                if address in seen:
                    skipped.append({'path':child,'kind':'hardlink_already_seen'}); continue
                seen.add(address)
                if isinstance(obj,h5py.Group):
                    objects.append({'path':child,'kind':'group'})
                    walk(obj,child,depth+1)
                elif isinstance(obj,h5py.Dataset):
                    storage=_storage(obj)
                    sample=_samples(obj,child,storage)
                    item={'path':child,'kind':'dataset','shape':list(obj.shape) if obj.shape is not None else None,
                          'dtype':str(obj.dtype),'storage':storage,
                          'classification':('selected_stored_values' if sample is not None else
                          'bounded_filelist_ome_source' if child in {FILELIST+'/data',FILELIST+'/index',FILELIST+'/metadata/data',FILELIST+'/metadata/index'}
                          else 'metadata_only')}
                    if sample is not None: item['sample']=sample
                    objects.append(item)
                else: skipped.append({'path':child,'kind':'unsupported_object'})
        seen.add(int(h5py.h5o.get_info(handle['/'].id).addr))
        walk(handle,'',1)
    groups={o['path'] for o in objects if o['kind']=='group'}
    datasets={o['path'] for o in objects if o['kind']=='dataset'}
    prefix='/Measurements/'+MEASUREMENT
    measurements=[]
    if prefix in groups:
        categories=sorted(p[len(prefix)+1:] for p in groups if p.startswith(prefix+'/') and '/' not in p[len(prefix)+1:])
        features={}
        for category in categories:
            base=prefix+'/'+category+'/'
            features[category]=sorted(p[len(base):] for p in groups if p.startswith(base) and '/' not in p[len(base):] and p+'/data' in datasets)
        measurements.append({'name':MEASUREMENT,'groups':categories,'features':features})
    return {'object_count':len(objects),'link_count':node_count,'objects':objects,'skipped_links':skipped,
            'measurements':measurements}


FILELIST='/FileList/Default/file/\\2f\\2f\\2fR\\3a/NGBD/RC3/Mahi%20Amer/CTCs/26032018-ALP-B10'
OME_NS='http://www.openmicroscopy.org/Schemas/OME/2015-01'
MAX_METADATA_BYTES=3_000_000
MAX_XML_BYTES=600_000
MAX_XML_ELEMENTS=15_000


def _indexed_spans(data,index):
    if len(data)>MAX_METADATA_BYTES or getattr(index,'shape',None)!=(4,2) or index.dtype.kind not in 'iu':
        raise ValueError('invalid indexed metadata dimensions')
    spans=[(int(a),int(b)) for a,b in index]
    if any(a<0 or a>=b or b>len(data) for a,b in spans):
        raise ValueError('metadata index outside data')
    ordered=sorted(spans)
    if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):
        raise ValueError('overlapping metadata ranges')
    return spans


def _ome_document(raw):
    if len(raw)>MAX_XML_BYTES or b'\x00' in raw or re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b',raw,re.I):
        raise ValueError('unsafe or oversized OME XML')
    raw.decode('utf-8','strict')
    root=None; count=0
    for event,element in ET.iterparse(BytesIO(raw),events=('start','end')):
        if event=='start':
            count+=1
            if count>MAX_XML_ELEMENTS: raise ValueError('too many OME XML elements')
        else: root=element
    tag=lambda name: '{'+OME_NS+'}'+name
    if root is None or root.tag!=tag('OME'): raise ValueError('unexpected OME namespace')
    images=root.findall(tag('Image'))
    if len(images)!=1: raise ValueError('one OME image required')
    image=images[0]; pixels=image.find(tag('Pixels'))
    if pixels is None: raise ValueError('OME image lacks pixels metadata')
    channels=pixels.findall(tag('Channel'))
    if len(channels)>32: raise ValueError('too many channels')
    pixel_fields=('SizeX','SizeY','SizeZ','SizeC','SizeT','Type','SignificantBits','DimensionOrder')
    channel_fields=('ID','Name','Fluor','ExcitationWavelength','ExcitationWavelengthUnit','EmissionWavelength','EmissionWavelengthUnit')
    return {'image_name':image.get('Name'), 'dimensions':{key:pixels.get(key) for key in pixel_fields},
            'channels':[{key:c.get(key) for key in channel_fields if c.get(key) is not None} for c in channels],
            'xml_element_count':count}


def _decode_filelist(filename_data, filename_index, metadata_data, metadata_index):
    names=_indexed_spans(filename_data,filename_index)
    docs=_indexed_spans(metadata_data,metadata_index)
    results=[]; used=set()
    for row,((a,b),(c,d)) in enumerate(zip(names,docs)):
        name=filename_data[a:b].decode('utf-8','strict')
        if not name or len(name.encode('utf-8'))>MAX_TEXT_BYTES or '/' in name or '\\' in name:
            raise ValueError('filename must be a bounded basename')
        document=metadata_data[c:d]; info=_ome_document(document)
        if not info['image_name'] or re.sub(r' #\d+$','',info['image_name'])!=name or name in used:
            raise ValueError('filelist and OME image name do not match')
        used.add(name)
        results.append({'filelist_row':row,'filename':name,
            'filename_source':{'dataset':FILELIST+'/data','index_dataset':FILELIST+'/index','span':[a,b],
                               'sha256':hashlib.sha256(filename_data[a:b]).hexdigest()},
            'metadata_source':{'dataset':FILELIST+'/metadata/data','index_dataset':FILELIST+'/metadata/index','span':[c,d],
                               'sha256':hashlib.sha256(document).hexdigest()}, **info})
    return results


def _filelist_metadata(content):
    def dataset(root,path):
        current=root
        for part in path.strip('/').split('/'):
            if not isinstance(current,h5py.Group) or not isinstance(current.get(part,getlink=True),h5py.HardLink):
                raise ValueError('expected hard-linked filelist dataset')
            current=current[part]
        if not isinstance(current,h5py.Dataset) or not _storage(current)['safe_to_read']:
            raise ValueError('unsafe filelist storage')
        return current
    with h5py.File(BytesIO(content),'r') as f:
        def read_data(path):
            item=dataset(f,path)
            if len(item.shape)!=1 or item.shape[0]>MAX_METADATA_BYTES or item.dtype.kind!='S' or item.dtype.itemsize!=1:
                raise ValueError('invalid filelist byte array')
            return item[:].tobytes()
        def read_index(path):
            item=dataset(f,path)
            if item.shape!=(4,2) or item.dtype.kind not in 'iu' or item.dtype.itemsize>8:
                raise ValueError('invalid filelist index')
            return item[:]
        return _decode_filelist(read_data(FILELIST+'/data'),read_index(FILELIST+'/index'),
                                read_data(FILELIST+'/metadata/data'),read_index(FILELIST+'/metadata/index'))

def inspect_project(path):
    name,sha,size=PROJECT
    content=_captured(Path(path),sha,size)
    inventory=_inventory(content)
    return {'schema_version':'chemotopo-project-inventory-v1','source':{'file':name,'sha256':sha,'bytes':size},
            'inventory':inventory,'ome_filelist':_filelist_metadata(content),
            'limits':{'max_nodes':MAX_NODES,'max_depth':MAX_DEPTH,'max_sample_elements_per_axis':MAX_SAMPLES,'max_string_bytes':MAX_TEXT_BYTES},
            'limitations':['Only the pinned file is accepted; selected values are stored HDF5 measurements, not execution of the pipeline.',
                'Only bounded indexed OME XML is parsed; embedded pipeline and ZIP metadata remain metadata only and are not deserialized.',
                'HDF5 variable-length strings are read as strings only for a short fixed allowlist in this pinned file; no pickle is deserialized.',
                'Soft/external links, repeated hard links, virtual datasets, external storage and non-builtin filters are not read.',
                'File or channel names and channel numbers do not prove a biological marker, original export mapping, ALP endpoint or zero-object convention.']}
