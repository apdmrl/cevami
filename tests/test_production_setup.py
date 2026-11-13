import os
from pathlib import Path

import pytest
from scripts.production_setup import prepare_secrets


def test_secret_setup_is_strong_private_and_never_rotates_existing_credentials(tmp_path):
    folder=tmp_path/'secrets'
    paths=prepare_secrets(folder)
    before={p.name:p.read_text() for p in paths}
    assert all(p.read_bytes().endswith(b'\n') and b'\r' not in p.read_bytes() for p in paths)
    assert len(set(before.values()))==2
    assert all(len(value.strip())>=48 for value in before.values())
    assert prepare_secrets(folder)==paths
    assert {p.name:p.read_text() for p in paths}==before
    if os.name!='nt':
        folder.chmod(0o755);paths[0].chmod(0o644)
        prepare_secrets(folder)
        assert folder.stat().st_mode&0o777==0o700
        assert all(p.stat().st_mode&0o777==0o444 for p in paths)


def test_partial_secret_setup_does_not_replace_or_complete_existing_credentials(tmp_path):
    folder=tmp_path/'secrets';folder.mkdir()
    original=folder/'pg_admin_password';original.write_text('preserve-me')
    with pytest.raises(ValueError):prepare_secrets(folder)
    assert original.read_text()=='preserve-me'
    assert not (folder/'web_db_password').exists()
