from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np

from autoresearch import chemotopo_project as module
from autoresearch.contracts import ResearchError


class ProjectTests(unittest.TestCase):
    def fixture(self):
        buffer=BytesIO()
        with h5py.File(buffer,'w') as f:
            image=f.create_group('Measurements/2017-08-22-09-08-29/Image')
            image.create_dataset('Channel_OrigRed/data',data=np.array([-1,-1,-1,-1],dtype='i4'))
            image.create_dataset('Channel_OrigRed/index',data=np.array([[4,0,1],[3,1,2],[2,2,3],[1,3,4]],dtype='i4'))
            image.create_dataset('ImageNumber/data',data=np.arange(5,dtype='i4'))
            image.create_dataset('FileName_OrigRed/data',data=np.array(['a.czi','b.czi'],dtype=h5py.string_dtype('utf-8')))
            f.create_dataset('opaque',data=np.array([1,2],dtype='u1'))
            f['soft']=h5py.SoftLink('/opaque')
            f['external']=h5py.ExternalLink('not-read.h5','/data')
            f['cycle']=f['/']
            layout=h5py.VirtualLayout(shape=(2,),dtype='i4')
            layout[:]=h5py.VirtualSource('missing.h5','/data',shape=(2,))
            f.create_virtual_dataset('virtual',layout)
        return buffer.getvalue()

    def test_link_storage_and_measurement_classification(self):
        result=module._inventory(self.fixture())
        skipped={x['path']:x['kind'] for x in result['skipped_links']}
        self.assertEqual(skipped['/soft'],'SoftLink')
        self.assertEqual(skipped['/external'],'ExternalLink')
        self.assertEqual(skipped['/cycle'],'hardlink_already_seen')
        objects={x['path']:x for x in result['objects']}
        self.assertFalse(objects['/virtual']['storage']['safe_to_read'])
        self.assertEqual(objects['/opaque']['classification'],'metadata_only')
        base='/Measurements/2017-08-22-09-08-29/Image/'
        self.assertEqual(objects[base+'Channel_OrigRed/data']['sample']['values'],[-1]*4)
        self.assertEqual(objects[base+'Channel_OrigRed/index']['sample']['values'][0],[4,0,1])
        self.assertEqual(objects[base+'FileName_OrigRed/data']['sample']['values'],['a.czi','b.czi'])
        self.assertEqual(objects[base+'ImageNumber/data']['classification'],'metadata_only')
        self.assertEqual(result['measurements'][0]['features']['Image'],['Channel_OrigRed','FileName_OrigRed','ImageNumber'])

    def test_unknown_filter_and_external_storage_are_never_read(self):
        buffer=BytesIO(self.fixture())
        with h5py.File(buffer,'r') as f:
            ds=f['Measurements/2017-08-22-09-08-29/Image/Channel_OrigRed/data']
            path='/Measurements/2017-08-22-09-08-29/Image/Channel_OrigRed/data'
            self.assertIsNone(module._samples(ds,path,{'safe_to_read':False,'filters':[32000],'external_storage':False,'virtual':False}))
            self.assertIsNone(module._samples(ds,path,{'safe_to_read':False,'filters':[],'external_storage':True,'virtual':False}))

    def test_bounds_and_pinned_source_reject_tampering(self):
        with patch.object(module,'MAX_NODES',2):
            with self.assertRaises(ValueError): module._inventory(self.fixture())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bad.cpproj'; path.write_bytes(b'bad')
            with self.assertRaises(ResearchError): module.inspect_project(path)

    def test_ome_indexed_rows_align_names_not_offset_order(self):
        def xml(name):
            return (f'<OME xmlns="{module.OME_NS}"><Image Name="{name} #1"><Pixels SizeX="1500" SizeC="1"><Channel Name="DAPI"/></Pixels></Image></OME>').encode()
        names=[b'one.czi',b'two.czi',b'three.czi',b'four.czi']
        docs=[xml(x.decode()) for x in names]
        def reordered(parts):
            positions={}; blob=b''
            for i in (3,0,2,1):
                positions[i]=(len(blob),len(blob)+len(parts[i])); blob+=parts[i]
            return blob,np.array([positions[i] for i in range(4)],dtype='i4')
        nameblob,nameindex=reordered(names); docblob,docindex=reordered(docs)
        values=module._decode_filelist(nameblob,nameindex,docblob,docindex)
        self.assertEqual([v['filename'] for v in values],[x.decode() for x in names])
        self.assertEqual(values[0]['channels'][0]['Name'],'DAPI')
        self.assertEqual(values[0]['filename_source']['span'],list(nameindex[0]))
        with self.assertRaises(ValueError): module._decode_filelist(nameblob,nameindex,docblob,docindex[[1,0,2,3]])

    def test_ome_rejects_dtd_entities_and_bad_spans(self):
        with self.assertRaises(ValueError): module._ome_document(b'<!DoCtYpE x [<!ENTITY a "bad">]><x/>')
        with self.assertRaises(ValueError): module._ome_document(b'x'*(module.MAX_XML_BYTES+1))
        for index in (np.array([[0,2],[1,3],[3,4],[4,5]]), np.array([[0,2],[2,3],[3,4],[4,9]])):
            with self.assertRaises(ValueError): module._indexed_spans(b'12345',index)

    def test_real_pinned_project_measurements_and_metadata(self):
        source=Path(__file__).resolve().parents[3]/'references/auto-research/10-chemotopochip/2026-10-31/hMSC_Analysis.cpproj'
        result=module.inspect_project(source)
        inventory=result['inventory']; self.assertEqual(inventory['object_count'],247)
        measurements=inventory['measurements']; self.assertEqual(len(measurements),1)
        self.assertEqual(set(measurements[0]['groups']),{'Experiment','Image'})
        self.assertIn('Channel_OrigRed',measurements[0]['features']['Image'])
        objects={x['path']:x for x in inventory['objects']}
        prefix='/Measurements/2017-08-22-09-08-29/'
        self.assertEqual(objects[prefix+'Image/ImageNumber/data']['sample']['values'],[1,2,3,4])
        self.assertEqual(objects[prefix+'Experiment/Pipeline_Pipeline/data']['classification'],'metadata_only')
        self.assertEqual(objects[prefix+'Experiment/ImageSet_Zip_Dictionary/data']['classification'],'metadata_only')
        self.assertEqual(len(objects[prefix+'Image/Channel_OrigRed/index']['sample']['values']),4)


if __name__=='__main__': unittest.main()
