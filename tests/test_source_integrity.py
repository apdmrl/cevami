import hashlib
from dataclasses import replace
import pytest
from test_localization import environment


def test_verified_artifact_detects_same_size_content_change(tmp_path):
    from hadis_web.importer import verify_artifact
    path=tmp_path/'source.db';path.write_bytes(b'first data')
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    assert verify_artifact(path,checksum)==checksum
    assert verify_artifact(path,checksum)==checksum
    path.write_bytes(b'other data')
    with pytest.raises(ValueError,match='checksum'):
        verify_artifact(path,checksum)


def test_opinion_entrypoint_rejects_actual_artifact_change_before_pg_writes(environment,tmp_path):
    from hadis_web.opinions import load_opinion_batches
    settings,store,_=environment
    path=tmp_path/'changed.db';path.write_bytes(b'changed artifact')
    with pytest.raises(ValueError,match='checksum'):
        load_opinion_batches(store,replace(settings,source_db=path),include_critic_names=False)
    with store.connection() as c:
        assert c.execute('SELECT count(*) AS n FROM localization_claims').fetchone()['n']==0
