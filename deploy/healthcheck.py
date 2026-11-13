import json
import os
from urllib.parse import urlsplit
from urllib.request import Request,urlopen

origin=urlsplit(os.environ['HADIS_PUBLIC_ORIGIN'])
request=Request('http://127.0.0.1:8080/api/health',headers={'Host':origin.netloc})
try:
    with urlopen(request,timeout=5) as response:ready=json.load(response).get('ready') is True
except Exception:ready=False
raise SystemExit(0 if ready else 1)
