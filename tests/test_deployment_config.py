"""Validate the configuration Docker actually parses, without starting services."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from ipaddress import ip_address,ip_network

import pytest


@pytest.fixture(scope='module')
def deployment():
    if not shutil.which('docker'):pytest.skip('Docker Compose is not installed')
    result=subprocess.run(['docker','compose','-f','deploy/compose.yml','config','--format','json'],
        cwd=Path(__file__).resolve().parents[1],env={**os.environ,'CEVAMI_DOMAIN':'ci.example.invalid'},
        capture_output=True,text=True,encoding='utf-8',timeout=30,check=True)
    return json.loads(result.stdout)


def test_temporary_mounts_are_absolute_paths_not_split_yaml_options(deployment):
    for service in deployment['services'].values():
        for mount in service.get('tmpfs',[]):
            assert mount.split(':',1)[0].startswith('/'),mount


def test_database_and_app_are_not_published_and_app_has_no_writeable_root(deployment):
    services=deployment['services']
    assert not services['database'].get('ports')
    assert not services['app'].get('ports')
    assert services['app']['read_only'] is True
    assert deployment['networks']['backend']['internal'] is True
    assert services['app']['environment']['HADIS_PUBLIC_ORIGIN']=='https://ci.example.invalid'


def test_proxy_address_cannot_be_taken_by_a_database_started_first(deployment):
    network=deployment['networks']['backend']['ipam']['config'][0]
    proxy=deployment['services']['app']['environment']['HADIS_PROXY_IP']
    assert ip_address(proxy) not in ip_network(network.get('ip_range',network['subnet']))
