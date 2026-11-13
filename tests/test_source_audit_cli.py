from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from hadis_web.config import Settings
from scripts import audit_sources


def setup_audit(tmp_path,monkeypatch):
    path=tmp_path/'source.sqlite';path.write_bytes(b'fixture source')
    search=tmp_path/'search.sqlite';search.write_bytes(b'fixture index')
    settings=replace(Settings.load(),source_db=path,search_db=search,project_root=tmp_path)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(audit_sources,'reader_audit',lambda _:dict(ok=True,findings=[],counts={},fingerprints={'source_sha256':digest,'expected_source_sha256':digest}))
    monkeypatch.setattr(audit_sources,'audit_working',lambda *a,**k:dict(ok=True,scan_complete=True,findings=[],counts={}))
    return settings,digest


def test_combined_report_has_fresh_fingerprints_and_no_semantic_approval(tmp_path,monkeypatch):
    settings,digest=setup_audit(tmp_path,monkeypatch)
    report=audit_sources.run_audit(settings)
    assert report['ok'] and report['scan_complete']
    assert report['fingerprints']['source_sha256_after']==digest
    assert report['source_inventory_unchanged']
    assert not report['meaning_reviewed'] and not report['expert_approval']


def test_audit_detects_source_change_during_working_scan(tmp_path,monkeypatch):
    settings,_=setup_audit(tmp_path,monkeypatch)
    def change(*args,**kwargs):
        settings.source_db.write_bytes(b'changed fixture')
        return dict(ok=True,scan_complete=True,findings=[],counts={})
    monkeypatch.setattr(audit_sources,'audit_working',change)
    report=audit_sources.run_audit(settings)
    assert not report['ok']
    assert 'source_changed_during_audit' in {f['code'] for f in report['findings']}


def test_incomplete_working_scan_cannot_pass_and_does_not_leak_secret(tmp_path,monkeypatch):
    settings,_=setup_audit(tmp_path,monkeypatch)
    def broken(*args,**kwargs):raise ValueError('postgresql://user:SECRET@private/db')
    monkeypatch.setattr(audit_sources,'audit_working',broken)
    report=audit_sources.run_audit(settings)
    assert not report['ok'] and not report['scan_complete']
    assert 'SECRET' not in json.dumps(report)


def test_report_is_created_exclusively_and_previous_evidence_is_preserved(tmp_path):
    path=tmp_path/'report.json'
    audit_sources.write_report(path,{'version':1})
    before=path.read_bytes()
    with pytest.raises(FileExistsError):audit_sources.write_report(path,{'version':2})
    assert path.read_bytes()==before


def test_changed_search_index_cannot_be_certified_after_the_scan(tmp_path,monkeypatch):
    settings,_=setup_audit(tmp_path,monkeypatch)
    def change(*args,**kwargs):
        settings.search_db.write_bytes(b'new fixture index')
        return dict(ok=True,scan_complete=True,findings=[],counts={})
    monkeypatch.setattr(audit_sources,'audit_working',change)
    report=audit_sources.run_audit(settings)
    assert not report['ok']
    assert 'search_changed_during_audit' in {f['code'] for f in report['findings']}


@pytest.mark.parametrize('which,suffix',[('source_db',''),('source_db','-wal'),('source_db','-shm'),('search_db','-journal')])
def test_output_cannot_create_a_source_or_index_sidecar(tmp_path,monkeypatch,which,suffix):
    settings,_=setup_audit(tmp_path,monkeypatch)
    path=Path(str(getattr(settings,which))+suffix)
    with pytest.raises(ValueError):audit_sources.validate_report_path(settings,path)
    audit_sources.validate_report_path(settings,tmp_path/'reports/result.json')
