"""Small read-only ledger summary for one explicitly selected research workspace.

Standard library only. Does not load source snapshots, run an adapter, recover a
request, infer, fit, rewrite budgets or scan neighboring/historical workspaces.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import stat


LEDGERS={
    'source_assessment':('source-assessment-study.sqlite','source-assessment-cloud.sqlite'),
    'evidence_assessment':('evidence-assessment-study.sqlite','evidence-assessment-cloud.sqlite'),
    'evidence_handoff':('evidence-handoff-study.sqlite','evidence-handoff-cloud.sqlite'),
    'configured':('configured-study.sqlite','configured-cloud.sqlite'),
    'postrun':('postrun-study.sqlite','postrun-cloud.sqlite'),
    'revision':('revision-study.sqlite','revision-cloud.sqlite'),
    'diagnostic':('diagnostic-study.sqlite','diagnostic-cloud.sqlite'),
    'diagnostic_followup':('diagnostic-followup-study.sqlite','diagnostic-followup-cloud.sqlite'),
    'iterative_diagnosis':('iterative-diagnosis-study.sqlite','iterative-diagnosis-cloud.sqlite'),
}
NONFITTING={'source_assessment','evidence_assessment','evidence_handoff','postrun','revision','diagnostic','diagnostic_followup','iterative_diagnosis'}


def readonly(path):
    for part in (path,*path.parents):
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise ValueError('redirected workspace or ledger is not accepted')
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('a regular unshared ledger is required')
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)
    connection.row_factory=sqlite3.Row;connection.execute('PRAGMA query_only=ON')
    return connection


def columns(connection,table):
    return {row['name'] for row in connection.execute('PRAGMA table_info('+table+')')}


def metadata(connection,table,column,limit):
    if column not in columns(connection,table):return {}
    row=connection.execute(f'SELECT {column} AS value FROM {table} LIMIT 1').fetchone()
    if row is None:return {}
    if type(row['value']) is not str or len(row['value'])>limit:raise ValueError('ledger metadata exceeds inspection bound')
    value=json.loads(row['value'])
    if type(value) is not dict:raise ValueError('ledger metadata is not an object')
    return value


def positive(value):return value if type(value) is int and value>=0 else None


def study_details(connection,kind):
    config=metadata(connection,'meta','config',1_000_000)
    meta_columns=columns(connection,'meta')
    row=connection.execute('SELECT status FROM meta LIMIT 1').fetchone() if 'status' in meta_columns else None
    status=row['status'] if row else None
    protocol=config.get('protocol',{})
    if type(protocol) is not dict:protocol={}
    maximum=positive(config.get('max_requests',protocol.get('max_requests')))
    fit_max=positive(config.get('max_fits',protocol.get('max_fits')))
    count=connection.execute('SELECT count(*) FROM actions').fetchone()[0] if columns(connection,'actions') else 0
    last=None;completed=0 if kind in NONFITTING or count==0 else None
    if count:
        # SQLite extracts only the requested fields; full diagnostic rows and
        # original model text are not copied into this small status result.
        try:
            row=connection.execute("SELECT json_extract(record,'$.id') AS id,json_extract(record,'$.ordinal') AS ordinal,"
                "json_extract(record,'$.action') AS action,json_extract(record,'$.parameters.candidate_id') AS candidate_id,"
                "json_extract(record,'$.parameters.dimension') AS dimension FROM actions ORDER BY ordinal DESC LIMIT 1").fetchone()
            last={key:row[key] for key in row.keys() if row[key] is not None}
            if kind not in NONFITTING:
                fits=[]
                for item in connection.execute("SELECT json_extract(record,'$.action') AS action,json_extract(record,'$.result.summary.fit_count') AS fit_count FROM actions"):
                    if item['action'] in {'run_candidate','fit_alpha10','fit_alpha100'}:
                        n=positive(item['fit_count'])
                        if n is None:fits=None;break
                        fits.append(n)
                completed=sum(fits) if fits is not None else None
        except sqlite3.OperationalError:
            # Older SQLite without JSON support cannot safely infer fit counts.
            last=None
    return config,status,maximum,{'completed':completed,'reserved':None,'max':fit_max},count,last


def inspect_workspace(workspace):
    root=Path(workspace).absolute()
    if not root.is_dir():raise ValueError('one existing research workspace is required')
    found=[(kind,names) for kind,names in LEDGERS.items() if (root/names[0]).is_file()]
    if len(found)!=1:raise ValueError('workspace must contain exactly one recognized study ledger')
    kind,(study_name,cloud_name)=found[0]
    con=readonly(root/study_name)
    try:config,study_status,maximum,fits,action_count,last=study_details(con,kind)
    finally:con.close()
    counts={name:0 for name in ('applied','invalid','sending','received')};used=0
    controller_status='not_started';controller_reason=None;spec={}
    if (root/cloud_name).is_file():
        con=readonly(root/cloud_name)
        try:
            spec=metadata(con,'project','spec_json',100_000)
            cols=columns(con,'project')
            if 'status' in cols:
                fields='status,reason' if 'reason' in cols else 'status'
                project=con.execute('SELECT '+fields+' FROM project LIMIT 1').fetchone()
                if project:
                    controller_status=project['status'];controller_reason=project['reason'] if 'reason' in cols else None
            if 'status' in columns(con,'calls'):
                for row in con.execute('SELECT status,count(*) AS n FROM calls GROUP BY status'):
                    used+=row['n'];counts[row['status']]=row['n']
        finally:con.close()
    if kind=='configured' and spec.get('schema')=='p02-compact-native-cloud-v1':kind='compact'
    spec_max=positive(spec.get('max_requests'));warnings=[]
    if maximum is not None and spec_max is not None and maximum!=spec_max:warnings.append('study_and_controller_request_caps_differ')
    if spec_max is not None:maximum=spec_max
    return {'schema_version':'research-status-v1','workspace':str(root),'kind':kind,
            'study_status':study_status,'controller_status':controller_status,'controller_reason':controller_reason,
            'requests':{'used':used,'max':maximum,**counts},'applied_actions':action_count,'last_action':last,
            'fits':fits,'warnings':warnings,'scope':'stored_ledger_status_only_not_source_or_scientific_validation',
            'resumed':False,'model_calls':0,'new_fits':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',required=True)
    args=parser.parse_args()
    try:print(json.dumps({'ok':True,**inspect_workspace(args.workspace)},ensure_ascii=False));return 0
    except (ValueError,OSError,sqlite3.Error,json.JSONDecodeError) as error:
        print(json.dumps({'ok':False,'error':str(error),'resumed':False,'model_calls':0,'new_fits':0},ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
