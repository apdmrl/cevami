"""Full read-only source/search/working audit; writes one new evidence file."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from hadis_web.config import Settings
from hadis_web.integrity import audit as reader_audit
from hadis_web.source_witnesses import digest_file
from hadis_web.working_integrity import audit_working,public_error


def inventory(path):
    return {p.name:{'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}
            for p in sorted(path.parent.glob(path.name+'*')) if p.is_file()}


def run_audit(settings,progress=None):
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'ok':False,'scan_complete':False,
            'meaning_reviewed':False,'expert_approval':False,'findings':[],'fingerprints':{}}
    findings=result['findings']
    try:
        before=inventory(settings.source_db)
        search_before=inventory(settings.search_db)
        search_sha=digest_file(settings.search_db) if settings.search_db.is_file() else None
        result['fingerprints']['search_sha256_before']=search_sha
        if progress:progress('source_and_search_started')
        source=reader_audit(settings);result['source_and_search']=source
        result['fingerprints'].update(source['fingerprints'])
        if progress:progress('source_and_search_completed')
        if source['ok']:
            try:result['working']=audit_working(settings,source['fingerprints']['source_sha256'],progress=progress)
            except Exception as error:
                result['working']={'ok':False,'scan_complete':False,'findings':[{'code':'working_scan_incomplete','severity':'error','count':1,'examples':[public_error(error)]}]}
        else:
            result['working']={'ok':False,'scan_complete':False,'findings':[{'code':'working_not_checked_due_to_source_error','severity':'error','count':1,'examples':[]}]}
        after_sha=digest_file(settings.source_db)
        result['fingerprints']['source_sha256_after']=after_sha
        after=inventory(settings.source_db)
        result['source_inventory_before']=before;result['source_inventory_after']=after
        result['source_inventory_unchanged']=before==after
        search_after=inventory(settings.search_db)
        search_after_sha=digest_file(settings.search_db) if settings.search_db.is_file() else None
        result['fingerprints']['search_sha256_after']=search_after_sha
        result['search_inventory_unchanged']=search_before==search_after
        if search_sha!=search_after_sha or search_before!=search_after:
            findings.append({'code':'search_changed_during_audit','severity':'error','count':1,'examples':[]})
        if after_sha!=source['fingerprints']['source_sha256'] or before!=after:
            findings.append({'code':'source_changed_during_audit','severity':'error','count':1,'examples':[]})
        result['scan_complete']=bool(result['working']['scan_complete'])
        findings.extend(source['findings']);findings.extend(result['working']['findings'])
        result['ok']=source['ok'] and result['working']['ok'] and not any(f['severity']=='error' for f in findings)
    except Exception as error:
        findings.append({'code':'source_audit_incomplete','severity':'error','count':1,'examples':[public_error(error)]})
    result['completed_at_utc']=datetime.now(timezone.utc).isoformat()
    result['status']='technical_error' if not result['ok'] else 'technical_checks_with_warnings' if findings else 'technical_checks_passed'
    return result


def write_report(path,report):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.write('\n')


def validate_report_path(settings,path):
    target=path.resolve()
    for source in (settings.source_db,settings.search_db):
        source=source.resolve()
        if target in {source,*(Path(str(source)+suffix) for suffix in ('-wal','-shm','-journal'))}:
            raise ValueError('Protected audit input or SQLite sidecar')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.exists():
        print(json.dumps({'ok':False,'error':'report_already_exists'}));return 2
    try:
        settings=Settings.load()
        validate_report_path(settings,args.output)
        report=run_audit(settings,progress=lambda stage:print(json.dumps({'stage':stage}),flush=True))
        write_report(args.output,report)
    except Exception as error:
        print(json.dumps({'ok':False,'error':'audit_or_report_unavailable',**public_error(error)}));return 2
    print(json.dumps({'ok':report['ok'],'status':report['status'],'scan_complete':report['scan_complete'],
        'source_counts':report.get('source_and_search',{}).get('counts',{}),'working_counts':report.get('working',{}).get('counts',{}),
        'findings':[{k:v for k,v in f.items() if k!='examples'} for f in report['findings']]}))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
