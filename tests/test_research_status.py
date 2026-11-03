import hashlib
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


spec=importlib.util.spec_from_file_location('research_status',Path(__file__).parents[1]/'scripts'/'research_status.py')
status=importlib.util.module_from_spec(spec);spec.loader.exec_module(status)


class ResearchStatusTests(unittest.TestCase):
    def test_one_workspace_readonly_counts_actual_fields_and_preserves_ledgers(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);study=root/'configured-study.sqlite';controller=root/'configured-cloud.sqlite'
            with closing(sqlite3.connect(study)) as con, con:
                con.executescript('CREATE TABLE meta(config TEXT,status TEXT);CREATE TABLE actions(ordinal INTEGER,record TEXT);')
                con.execute('INSERT INTO meta VALUES(?,?)',(json.dumps({'protocol':{'max_requests':6,'max_fits':280}}),'paused'))
                for number,record in enumerate([{'id':'fit','ordinal':1,'action':'run_candidate','parameters':{'candidate_id':'alpha3'},'result':{'summary':{'fit_count':140}}},
                                                {'id':'control','ordinal':2,'action':'pause','parameters':{},'reason':'PRIVATE_TEXT_NOT_OUTPUT'}],1):
                    con.execute('INSERT INTO actions VALUES(?,?)',(number,json.dumps(record)))
            with closing(sqlite3.connect(controller)) as con, con:
                con.executescript('CREATE TABLE project(spec_json TEXT,status TEXT,reason TEXT);CREATE TABLE calls(status TEXT);')
                con.execute('INSERT INTO project VALUES(?,?,?)',(json.dumps({'schema':'p02-compact-native-cloud-v1','max_requests':6}),'active','RECEIVED_PENDING'))
                con.executemany('INSERT INTO calls VALUES(?)',[(s,) for s in ('applied','invalid','sending','received','applied')])
            original={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            value=status.inspect_workspace(root)
            self.assertEqual(value['kind'],'compact');self.assertEqual(value['requests'],{'used':5,'max':6,'applied':2,'invalid':1,'sending':1,'received':1})
            self.assertEqual(value['last_action'],{'id':'control','ordinal':2,'action':'pause'})
            self.assertEqual(value['fits'],{'completed':140,'reserved':None,'max':280})
            self.assertEqual(value['applied_actions'],2);self.assertFalse(value['resumed'])
            self.assertNotIn('PRIVATE_TEXT_NOT_OUTPUT',json.dumps(value))
            self.assertEqual(original,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()})
            connection=status.readonly(study)
            try:
                with self.assertRaises(sqlite3.OperationalError):connection.execute("UPDATE meta SET status='changed'")
            finally:connection.close()


if __name__=='__main__':unittest.main()
