"""Audit immutable source and search bindings; only the requested report is written."""
import argparse
import json
from pathlib import Path
from hadis_web.config import Settings
from hadis_web.integrity import audit


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('.local/reader-integrity.json'))
    args=parser.parse_args()
    report=audit(Settings.load())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ok':report['ok'],'counts':report['counts'],
                      'findings':[{k:v for k,v in f.items() if k!='examples'} for f in report['findings']]},ensure_ascii=True))
    raise SystemExit(0 if report['ok'] else 1)
