"""Pinned official SQLite entries; importing a source never approves a match."""
import hashlib
import html
import json
import re

from .importer import verify_artifact
from .source import open_readonly


ARCHIVE = 'hadeethenc-20261104'
REVISION = 'download-2026-11-04'


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _display(text):
    return html.unescape(re.sub('<[^>]+>', '', text))


def _artifact(settings, language):
    if language not in ('tr', 'ar'):
        raise ValueError('Unsupported HadeethEnc language')
    folder = settings.project_root / 'references/turkish' / ARCHIVE
    manifest = json.loads((folder / 'schema-manifest.json').read_text(encoding='utf-8'))
    entry = next(row for row in manifest if row['language'] == language)
    path = folder / (language + '.sqlite')
    verify_artifact(path, entry['sha256'])
    return path, entry


def _row(settings, language, identity, version=None):
    path, artifact = _artifact(settings, language)
    with open_readonly(path) as conn:
        rows = conn.execute('SELECT * FROM hadeeths WHERE id=?', (identity,)).fetchall()
    if language == 'ar' and version is not None:
        rows = [r for r in rows if r['version'] == version]
    if len(rows) != 1:
        raise ValueError('Missing or ambiguous HadeethEnc entry/version')
    return dict(rows[0]), artifact


def _locator(row, language):
    return {'table': 'hadeeths', 'id': row['id'], 'column': 'hadeeth',
            'ar_version': row['version'] if language == 'ar' else row['ar_version'],
            'source_row_sha256': _digest(row)}


def validate_hadeethenc_text(settings, stored: dict) -> None:
    language = stored['language']
    if (language not in ('ar', 'tr') or stored['provider'] != 'hadeethenc'
            or stored['revision'] != REVISION or stored['artifact_name'] != f'{ARCHIVE}/{language}.sqlite'
            or stored['namespace'] != f'hadeethenc:{language}:hadeeth'
            or not str(stored['source_key']).isdigit()):
        raise ValueError('HadeethEnc source metadata differs')
    row, artifact = _row(settings, language, int(stored['source_key']), stored['locator'].get('ar_version'))
    if (artifact['sha256'] != stored['artifact_sha256'] or stored['locator'] != _locator(row, language)
            or row['hadeeth'] != stored['raw_text'] or _display(row['hadeeth']) != stored['display_text']):
        raise ValueError('HadeethEnc full source row or Arabic version differs')


def load_hadeethenc_selection(working, settings, identities: list[int]) -> dict:
    if not identities or len(identities) != len(set(identities)) or any(type(i) is not int or i <= 0 for i in identities):
        raise ValueError('Invalid HadeethEnc selection')
    prepared = []
    for identity in sorted(identities):
        tr, tr_artifact = _row(settings, 'tr', identity)
        ar, ar_artifact = _row(settings, 'ar', identity, tr['ar_version'])
        # The embedded Arabic is additional evidence; do not invent a Turkish version number from ar_version.
        prepared.append((identity, tr, tr_artifact, ar, ar_artifact))
    snapshots = {}
    for language in ('ar', 'tr'):
        _, artifact = _artifact(settings, language)
        snapshots[language] = working.add_snapshot('hadeethenc', REVISION, artifact['sha256'], f'{ARCHIVE}/{language}.sqlite')
    result = {}
    for identity, tr, _, ar, _ in prepared:
        values = {'ar_version': tr['ar_version'], 'translation_version': None, 'translator': None,
                  'source_url': f'https://hadeethenc.com/tr/browse/hadith/{identity}'}
        for language, row in (('ar', ar), ('tr', tr)):
            version = working.add_text(snapshots[language], f'hadeethenc:{language}:hadeeth', str(identity), language,
                                       row['hadeeth'], _display(row['hadeeth']), _locator(row, language))
            values[language + '_version_id'] = str(version)
        result[str(identity)] = values
    return result
