"""Restore into an isolated database and rehearse champion rollback with recovery."""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values


def command(args, data=None):
    result = subprocess.run(['docker','compose','exec','-T','postgres',*args],input=data,capture_output=True,timeout=120)
    if result.returncode:
        raise RuntimeError('PostgreSQL drill command failed; diagnostic output withheld')
    return result.stdout


def backup_restore(config):
    user, database = config.get('POSTGRES_USER','biometric'), config.get('POSTGRES_DB','biometric')
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',s) for s in (user,database)):
        raise ValueError('Invalid PostgreSQL identifier')
    clone = 'ddm501_restore_drill_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    tables = ['people','biometric_samples','verification_events','verification_feedback','tenants','verify_sessions','webhook_deliveries','audit_logs']
    query = ' UNION ALL '.join("SELECT '" + t + "',count(*) FROM " + t for t in tables)
    def counts(db):
        output = command(['psql','-U',user,'-d',db,'-At','-c',query]).decode()
        return dict(line.split('|') for line in output.strip().splitlines())
    original = counts(database)
    archive = command(['pg_dump','-U',user,'-d',database,'-Fc'])
    folder = Path('data/backups')
    folder.mkdir(parents=True,exist_ok=True)
    path = folder / (clone + '.dump')
    path.write_bytes(archive)
    command(['createdb','-U',user,clone])
    try:
        command(['pg_restore','-U',user,'-d',clone,'--no-owner','--exit-on-error'],archive)
        restored = counts(clone)
        assert original == restored, 'Restored row counts differ'
        return {'status':'pass','backup':str(path),'bytes':len(archive),'isolated_database':clone,
                'row_counts':restored,'isolated_database_removed':True}
    finally:
        # Only the explicit database created by this drill is removed.
        command(['dropdb','-U',user,clone])


def rollback(config):
    session = requests.Session()
    session.trust_env = False
    base = 'http://127.0.0.1:15030/api/2.0/mlflow'
    model = config.get('MLFLOW_MODEL_NAME','face-voice-risk-bundle')
    def get(path, **kwargs):
        r = session.get(base+path,timeout=20,**kwargs)
        r.raise_for_status()
        return r.json()
    current = get('/registered-models/alias',params={'name':model,'alias':'champion'})['model_version']['version']
    versions = get('/model-versions/search',params={'filter':"name='"+model+"'"})['model_versions']
    previous = max((v for v in versions if int(v['version']) < int(current) and v['status']=='READY'),key=lambda v:int(v['version']))['version']
    headers = {'X-API-Key':config['API_KEY']}
    def switch(version):
        r = session.post(base+'/registered-models/alias',json={'name':model,'alias':'champion','version':version},timeout=20)
        r.raise_for_status()
        r = session.post('http://127.0.0.1:18100/v1/admin/reload-model',headers=headers,timeout=60)
        r.raise_for_status()
        assert r.json()['version'] == version
        r = session.get('http://127.0.0.1:18100/ready',timeout=15)
        r.raise_for_status()
        assert r.json()['model_version'] == version
    try:
        switch(previous)
    finally:
        switch(current)
    return {'status':'pass','original_champion':current,'rollback_version':previous,
            'restored_champion':current,'readiness_verified':True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rollback',action='store_true',help='Briefly switch serving to an earlier model, then restore champion')
    args = parser.parse_args()
    config = dotenv_values('.env')
    report = {'checked_at':datetime.now(timezone.utc).isoformat(),'backup_restore':backup_restore(config)}
    if args.rollback:
        report['rollback'] = rollback(config)
    Path('reports').mkdir(exist_ok=True)
    Path('reports/recovery-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
