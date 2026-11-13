"""Actual split-gzip/tar roundtrip and adversarial extraction in temporary paths."""
import hashlib
import io
import json
import tarfile
import os
from pathlib import Path

import pytest
from scripts.data_release import build_bundle,restore_bundle


def test_split_bundle_roundtrip_keeps_bytes_and_rejects_existing_target(tmp_path):
    source=tmp_path/'source';source.write_bytes(bytes(range(256))*64)
    release=tmp_path/'release'
    manifest=build_bundle({'references/source.db':source},release,part_size=128)
    assert len(manifest['archive']['parts'])>1
    target=tmp_path/'restored'
    previous=os.umask(0o077) if os.name!='nt' else None
    try:restore_bundle(release/'manifest.json',target)
    finally:
        if previous is not None:os.umask(previous)
    assert (target/'references/source.db').read_bytes()==source.read_bytes()
    if os.name!='nt':
        assert target.stat().st_mode&0o055==0o055
        assert (target/'references').stat().st_mode&0o055==0o055
        assert (target/'references/source.db').stat().st_mode&0o044==0o044
    with pytest.raises((ValueError,FileExistsError)):restore_bundle(release/'manifest.json',target)
    assert (target/'references/source.db').read_bytes()==source.read_bytes()


def test_changed_or_missing_lfs_part_never_installs_data(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'important data')
    release=tmp_path/'release';manifest=build_bundle({'source.db':source},release,part_size=128)
    part=release/manifest['archive']['parts'][0]['name'];part.write_bytes(b'git-lfs pointer is not data')
    with pytest.raises(ValueError):restore_bundle(release/'manifest.json',tmp_path/'target')
    assert not (tmp_path/'target').exists()


@pytest.mark.parametrize('name',['../escaped','/absolute','C:/drive','folder\\escaped','folder/.. /escaped','NUL.txt','folder/trailing.'])
def test_builder_rejects_unsafe_logical_paths(tmp_path,name):
    source=tmp_path/'source';source.write_text('safe',encoding='utf-8')
    with pytest.raises(ValueError):build_bundle({name:source},tmp_path/'release')


def archive_fixture(tmp_path,members,files):
    release=tmp_path/'release';release.mkdir()
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as archive:
        for name,value,kind in members:
            item=tarfile.TarInfo(name)
            if kind=='link':item.type=tarfile.SYMTYPE;item.linkname='../outside'
            else:item.size=len(value)
            archive.addfile(item,io.BytesIO(value) if kind!='link' else None)
    data=output.getvalue();(release/'workspace.tar.gz.part001').write_bytes(data)
    manifest={'schema_version':1,'version':'fixture','files':[
        {'path':name,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()} for name,value in files],
        'archive':{'format':'tar+gzip','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
            'parts':[{'name':'workspace.tar.gz.part001','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}}
    (release/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return release/'manifest.json'


@pytest.mark.parametrize('members,files',[
    ([('../outside',b'evil','file')],[('safe',b'evil')]),
    ([('safe',b'','link')],[('safe',b'')]),
    ([('safe',b'x','file'),('safe',b'x','file')],[('safe',b'x')]),
    ([('safe',b'changed','file')],[('safe',b'original')]),
    ([('extra',b'x','file')],[('safe',b'x')]),
    ([('safe',b'x','file'),('SAFE',b'x','file')],[('safe',b'x'),('SAFE',b'x')]),
])
def test_hash_valid_but_unsafe_archives_are_rejected_atomically(tmp_path,members,files):
    manifest=archive_fixture(tmp_path,members,files)
    with pytest.raises(ValueError):restore_bundle(manifest,tmp_path/'target')
    assert not (tmp_path/'target').exists()
    assert not (tmp_path/'outside').exists()


def test_manifest_cannot_redirect_part_reads_outside_release(tmp_path):
    manifest=archive_fixture(tmp_path,[('safe',b'x','file')],[('safe',b'x')])
    contents=json.loads(manifest.read_text());contents['archive']['parts'][0]['name']='../private-file'
    manifest.write_text(json.dumps(contents))
    with pytest.raises(ValueError):restore_bundle(manifest,tmp_path/'target')


def test_concurrent_empty_destination_is_never_replaced(monkeypatch,tmp_path):
    manifest=archive_fixture(tmp_path,[('safe',b'x','file')],[('safe',b'x')])
    target=tmp_path/'target';original=Path.exists;checks=0
    def racing_exists(path):
        nonlocal checks
        if path==target:
            checks+=1
            if checks==2:
                observed=original(path)
                target.mkdir()
                return observed
        return original(path)
    monkeypatch.setattr(Path,'exists',racing_exists)
    with pytest.raises(FileExistsError):restore_bundle(manifest,target)
    assert target.is_dir() and list(target.iterdir())==[]
