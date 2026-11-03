import hashlib
import io
import os
from pathlib import Path
import statistics
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from autoresearch import chemotopo_data as module
from autoresearch.contracts import ResearchError


NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def workbook(sheets, extras=(), external=False):
    """Tiny real OOXML caches; no Excel library or expression evaluation."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        book = ET.Element('workbook', xmlns=NS)
        listing = ET.SubElement(book, 'sheets')
        rels = ET.Element('Relationships', xmlns='http://schemas.openxmlformats.org/package/2006/relationships')
        for i, (name, cells) in enumerate(sheets.items(), 1):
            ET.SubElement(listing, 'sheet', {'name': name, module.REL: f'r{i}'})
            attrs = {'Id': f'r{i}', 'Target': f'worksheets/sheet{i}.xml'}
            if external: attrs['TargetMode'] = 'External'
            ET.SubElement(rels, 'Relationship', attrs)
            sheet = ET.Element('worksheet', xmlns=NS)
            data = ET.SubElement(sheet, 'sheetData')
            rows = {}
            for ref, value in cells.items():
                row = int(''.join(c for c in ref if c.isdigit()))
                if row not in rows: rows[row] = ET.SubElement(data, 'row', r=str(row))
                cell = ET.SubElement(rows[row], 'c', r=ref)
                if isinstance(value, tuple):
                    ET.SubElement(cell, 'f').text = value[0]
                    ET.SubElement(cell, 'v').text = str(value[1])
                elif isinstance(value, str):
                    cell.set('t','inlineStr')
                    ET.SubElement(ET.SubElement(cell,'is'),'t').text = value
                elif value is not None: ET.SubElement(cell, 'v').text = str(value)
            archive.writestr(f'xl/worksheets/sheet{i}.xml', ET.tostring(sheet))
        archive.writestr('xl/workbook.xml', ET.tostring(book))
        archive.writestr('xl/_rels/workbook.xml.rels', ET.tostring(rels))
        for name, payload in extras: archive.writestr(name, payload)
    return buffer.getvalue()


def cells(headers, rows):
    return {module._column(c)+str(r): value for r, row in enumerate([headers, *rows], 1)
            for c, value in enumerate(row, 1)}


def fixture():
    # Same chemistry, explicit flat and textured keys; the labeled normalized
    # signal is deliberately a count-SD ratio, different from the signal ratio.
    raw = [[1,0,'1_0',1,2,3], [1,0,'1_0',5,4,3],
           [2,0,'2_0',6,10,3], [2,0,'2_0',10,14,3]]
    snr, norm = [], []
    for topo in (1,2):
        rows = [r for r in raw if r[0] == topo]
        count, red = [r[3] for r in rows], [r[4] for r in rows]
        mc, sc, mr, sr = statistics.mean(count), statistics.stdev(count), statistics.mean(red), statistics.stdev(red)
        snr.append([topo,0,f'{topo}_0',mc,sc,mc/sc,mr,sr,mr/sr])
        norm.append([topo,0,f'{topo}_0',mc,sc/statistics.stdev([1,5])])
    return {
        'B1S1': cells(['Topo','Chem','Coordinate','Count','Mean_Red_Intensity','Mean_Green_Intensity'], raw),
        'B1S1_SNR': cells(['Topography','Chemistry','Topo_Chem','Avg Cell Count','Std Cell Count','SNR Cell Count',
                          'Avg Red Intensity','Std Red Intensity','SNR Red Intensity'],snr),
        'B1S1_Normalised': cells(['Topography','Chemistry','Topo_Chem','Avg Cell Count','Avg Red Intensity'],norm),
    }


class ChemoTopoDataTests(unittest.TestCase):
    def test_formula_is_cached_reference_not_executed_and_sources_are_exact(self):
        payload = workbook({'Sheet1': {'A1': 'header', 'A2': ('HYPERLINK("https://invalid/","no execution")', 7),
                                      'A3': float('nan'), 'A4': None, 'A5': 'nan'}})
        with patch('socket.create_connection', side_effect=AssertionError('offline')):
            book = module.read_workbook(payload)
        point = module._point(book,'Sheet1','A2')
        self.assertEqual((point['sheet'],point['cell'],point['value']),('Sheet1','A2',7))
        self.assertTrue(point['formula_present'])
        self.assertIn('HYPERLINK',point['formula'])
        self.assertEqual(book['Sheet1']['A3']['status'],'nonfinite_or_invalid')
        self.assertEqual(book['Sheet1']['A4']['status'],'missing')
        self.assertEqual(book['Sheet1']['A5']['status'],'text')

    def test_unsafe_zip_external_links_macro_and_entities_fail_closed(self):
        for extras, external in [([('../escape',b'no')],False),([('xl/vbaProject.bin',b'no')],False),
                                 ([('xl/externalLinks/externalLink1.xml',b'no')],False),([],True),
                                 ([('xl/sharedStrings.xml',b'<!DOCTYPE x [<!ENTITY a "boom">]><sst/>')],False)]:
            with self.subTest(extras=extras,external=external):
                with self.assertRaises(ResearchError): module.read_workbook(workbook({'S':{'A1':1}},extras,external))

    def test_corrupt_workbook_is_structured_error(self):
        with self.assertRaises(ResearchError): module.read_workbook(b'not zip')
        with self.assertRaises(ResearchError): module.read_workbook(workbook({'S':{'A1':1}}, [('xl/sharedStrings.xml',b'<invalid')]))

    def test_count_variability_is_not_relabelled_as_biological_signal(self):
        book = module.read_workbook(workbook(fixture()))
        reports, _ = module.audit_sections(book,['B1S1'],himsc=True)
        checks = reports[0]['checks']
        self.assertEqual(checks['count_sd_over_flat_base_count_sd_matches'],2)
        self.assertEqual(checks['signal_mean_over_flat_base_signal_mean_matches'],1)  # flat itself only
        row = reports[0]['records'][1]
        self.assertEqual(row['normalized_labeled_signal']['cell'],'E3')
        self.assertEqual(row['candidate_comparisons']['signal_mean_over_flat_base_signal_mean']['expected'],4)
        self.assertEqual(row['normalized_labeled_signal']['value'],1)
        self.assertEqual(row['raw_rows'],[4,5])

    def test_missing_signal_is_retained_and_never_imputed_as_zero(self):
        data = fixture(); data['B1S1']['E4'] = None
        report, _ = module.audit_sections(module.read_workbook(workbook(data)),['B1S1'],himsc=True)
        self.assertEqual(report[0]['checks']['raw_signal_nonfinite_or_missing_rows'],1)
        self.assertEqual(report[0]['checks']['raw_mean_signal_matches_snr'],1)
        self.assertEqual(report[0]['records'][1]['raw_signal_nonfinite_or_missing'][0]['cell'],'E4')

    def test_zero_denominator_is_explicit_not_infinite_or_zero_filled(self):
        data = fixture();data['B1S1_SNR']['G2'] = 0
        report, _ = module.audit_sections(module.read_workbook(workbook(data)),['B1S1'],himsc=True)
        checks = report[0]['checks']
        self.assertEqual(checks['signal_mean_over_flat_base_signal_mean_zero_denominators'],2)
        self.assertIsNone(report[0]['records'][1]['candidate_comparisons']['signal_mean_over_flat_base_signal_mean']['expected'])

    def test_duplicate_and_disagreeing_keys_are_not_paired_by_row_position(self):
        for change, code in [('duplicate','DUPLICATE_KEY'),('label','KEY_MISMATCH'),('unmatched','KEY_MISMATCH')]:
            data = fixture()
            if change == 'duplicate': data['B1S1_Normalised']['A3'] = 1; data['B1S1_Normalised']['C3'] = '1_0'
            elif change == 'label': data['B1S1_Normalised']['C3'] = '2_1'
            else: data['B1S1_Normalised']['A3'] = 3; data['B1S1_Normalised']['C3'] = '3_0'
            with self.subTest(change=change):
                with self.assertRaises(ResearchError) as error:
                    module.audit_sections(module.read_workbook(workbook(data)),['B1S1'],himsc=True)
                self.assertEqual(error.exception.code,code)

    def test_missing_flat_control_and_changed_header_fail_closed(self):
        data = fixture();data['B1S1_Normalised']['E1'] = 'ALP definitive'
        with self.assertRaises(ResearchError) as error: module.audit_sections(module.read_workbook(workbook(data)),['B1S1'],himsc=True)
        self.assertEqual(error.exception.code,'SCHEMA_MISMATCH')
        data = fixture()
        for sheet in data.values():
            for ref in list(sheet):
                if ref.endswith('2'): del sheet[ref]
        with self.assertRaises(ResearchError): module.audit_sections(module.read_workbook(workbook(data)),['B1S1'],himsc=True)

    def test_changed_capture_and_linked_file_are_rejected_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'author.xlsx';payload=workbook(fixture());path.write_bytes(payload)
            sha=hashlib.sha256(payload).hexdigest()
            self.assertEqual(module._captured(path,sha,len(payload)),payload)
            with self.assertRaises(ResearchError):module._captured(path,'0'*64,len(payload))
            with self.assertRaises(ResearchError):module._captured(path,sha,len(payload)+1)
            self.assertEqual(path.read_bytes(),payload)
            link=path.with_name('linked.xlsx');os.link(path,link)
            with self.assertRaises(ResearchError):module._captured(path,sha,len(payload))

    def test_macro_ratio_cache_and_missing_fields_are_checked_without_zero_fill(self):
        raw=[[1,0,'1_0',1,2,4,2],[1,0,'1_0',5,4,16,4],
             [2,0,'2_0',6,2,10,5],[2,0,'2_0',10,'nan','nan',None]]
        sd=statistics.stdev([1,5]);sr=statistics.stdev([2,4])
        snr=[[1,0,'1_0',3,sd,3/sd,3,sr,3/sr],[2,0,'2_0',8,sd,8/sd,5,0,0]]
        norm=[[1,0,'1_0',3,1],[2,0,'2_0',8,5/3]]
        data={
            'B1S1':cells(['Topography','Chemistry','Topo_Chem','Cell_Count','546_MFI','647_MFI','M2/M1_Ratio'],raw),
            'B1S1_SNR':cells(['Topography','Chemistry','Topo_Chem','Avg Cell Count','Std Cell Count','SNR Cell Count',
                             'Avg M2M1','Std M2M1','SNR M2M1'],snr),
            'B1S1_Normalised':cells(['Topography','Chemistry','Topo_Chem','Avg Cell Count','Avg M2M1'],norm)}
        report,_=module.audit_sections(module.read_workbook(workbook(data)),['B1S1'],himsc=False)
        checks=report[0]['checks']
        self.assertEqual(checks['raw_ratio_comparable_rows'],3)
        self.assertEqual(checks['raw_ratio_F_over_E_matches'],3)
        self.assertEqual(checks['raw_ratio_not_comparable_rows'],1)
        self.assertEqual(checks['raw_signal_nonfinite_or_missing_rows'],1)
        self.assertEqual(checks['signal_mean_over_flat_base_signal_mean_matches'],2)

    def test_aggregate_joins_use_explicit_keys_and_preserve_unequal_sections(self):
        data=fixture()
        data['CellCountAllBatches']=cells(['Topo_Chem','Topography','Chemistry','B1S1'],[['2_0',2,0,8],['1_0',1,0,3]])
        data['RedIntensityAllBatches']=cells(['Topo_Chem','Topography','Chemistry','B1S1'],[['1_0',1,0,1],['2_0',2,0,1]])
        data['DataForClustering']=cells(['Topo_Chem','Polymer','Topography','Chemistry','AVG Cell Count','STD Cell Count',
                                       'SNR Cell Count','AVG Red Intensity','STD Red Intensity','SNR Red Intensity'],
                                      [['2_0','Base',2,0,8,0,0,1,0,0]])
        book=module.read_workbook(workbook(data));_, normalized=module.audit_sections(book,['B1S1'],himsc=True)
        keys,polymers,reports,records=module.audit_aggregate(book,normalized,himsc=True)
        self.assertEqual(set(keys),{(2,0)})
        self.assertEqual(polymers[2,0],'Base')
        self.assertEqual(reports[0]['checks']['mapped_equal'],2)
        self.assertEqual(reports[0]['keys_excluded_from_clustering'],[[1,0]])
        self.assertEqual(records[2,0]['CellCountAllBatches']['available_sections_by_batch'],{'B1':1})
        # A value attached to a nonexistent material/section is not structural absence.
        data['CellCountAllBatches']['A3']='3_0';data['CellCountAllBatches']['B3']=3
        with self.assertRaises(ResearchError):module.audit_aggregate(module.read_workbook(workbook(data)),normalized,himsc=True)


if __name__ == '__main__': unittest.main()
