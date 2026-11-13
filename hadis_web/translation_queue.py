"""A research work list; lack of a local translation is not proof of absence."""
from collections import Counter
import json
from pathlib import Path
from .source import SourceReader, open_readonly, STRUCTURAL_IDS
from .localization import LocalizationStore, NARRATOR_FIELDS, record_digest, opinion_record, opinion_key, merge_critic_name
from .working import stable_id
from .controlled_terms import apply_controlled_terms


def write_narrator_queue(working, settings, output):
    reader=SourceReader(settings)
    with open_readonly(settings.source_db) as source:
        chains=source.execute("SELECT s.rawy_ids FROM sanad s JOIN hadith_text t ON t.bhid=s.bhid WHERE t.book_id='146'").fetchall()
        ids={int(n.strip()) for row in chains for n in row['rawy_ids'].split(',') if n.strip().isdigit()}-STRUCTURAL_IDS
        opinion_counts={str(row['rawy_id']):row['n'] for row in source.execute(
            'SELECT rawy_id,COUNT(*) AS n FROM critic_opinions GROUP BY rawy_id')}
    records=reader.narrator_records(ids)
    if len(records)!=len(ids):
        raise ValueError('Missing source people in the translation queue')
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    snapshot=stable_id('snapshot','gk45','4.5',manifest['database_sha256'])
    localized=LocalizationStore(working).for_records(snapshot,'narrator',records,'tr')
    localized=apply_controlled_terms(working,snapshot,records,localized,'tr')
    # Only fetch opinion records for people with previous work; untouched
    # people remain unsearched rather than becoming presumed untranslated.
    with working.connection() as c:
        started=c.execute("SELECT DISTINCT source_record->>'narrator_id' AS person FROM localization_claims "
                          "WHERE snapshot_id=%s AND entity_type='critic_opinion' AND language='tr'",(snapshot,)).fetchall()
    opinion_records={}
    for row in started:
        if row['person'] not in records:
            continue
        offset=0
        while True:
            page=reader.critic_opinions(int(row['person']),limit=100,offset=offset)
            for item in page['items']:
                record=opinion_record(row['person'],item)
                opinion_records[opinion_key(record)]=record
            offset+=len(page['items'])
            if offset>=page['total']: break
            if not page['items']: raise ValueError('Source opinions changed during queue paging')
    opinion_localized=LocalizationStore(working).for_records(snapshot,'critic_opinion',opinion_records,'tr')
    critics=reader.critic_records({record['alem_id'] for record in opinion_records.values()})
    critic_names=LocalizationStore(working).for_records(snapshot,'critic',critics,'tr')
    opinion_work={}
    for key,record in opinion_records.items():
        identity=str(record['alem_id']);data=opinion_localized[key]
        if identity in critics:
            data=merge_critic_name(data,record['critic'],critics[identity],critic_names[identity])
        opinion_work.setdefault(str(record['narrator_id']),[]).append(data)
    first={6817:0,4698:1,3443:2,8272:3,6796:4,5719:5,5913:6}
    stages=Counter(); tasks=0
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',encoding='utf-8',newline='\n') as stream:
        for key,record in sorted(records.items(),key=lambda pair:(first.get(int(pair[0]),7),int(pair[0]))):
            fields=[f for f in NARRATOR_FIELDS if record.get(f)]
            if opinion_counts.get(key): fields.append('critic_opinions')
            for field in fields:
                claims=localized[key]['fields'].get(field,[])
                progress=opinion_work.get(key,[]) if field=='critic_opinions' else []
                if progress:
                    claims=[claim for item in progress for rows in item['fields'].values() for claim in rows]
                availability='unknown'
                if not claims:
                    stage='source_search_not_started'
                elif any(c['status']=='problem_detected' for c in claims):
                    stage='source_issue_review'
                elif field in localized[key]['conflicting_fields'] or any(item['conflicting_fields'] for item in progress):
                    stage='conflicting_translation_review'
                elif any(c['turkish_availability'] in ('candidate_unverified','candidate_inaccessible') for c in claims):
                    stage='source_candidate_review'
                elif any(c['translation_origin']=='controlled_vocabulary' for c in claims):
                    stage='controlled_term_review'
                elif any(c['translation_origin']=='assistant_translation' for c in claims):
                    stage='translation_draft_review'
                elif all(c['status']=='source_compared' for c in claims):
                    stage='source_compared'
                else:
                    stage='source_search_pending'
                values={c['turkish_availability'] for c in claims}
                if len(values)==1: availability=next(iter(values))
                row={'narrator_id':int(key),'field':field,'language':'tr','stage':stage,
                     'turkish_availability':availability,'source_snapshot_id':str(snapshot),
                     'source_record_sha256':record_digest(record),'source_text':record.get(field),
                     'claim_ids':[c['id'] for c in claims if not c.get('derived_from_claim_id')],
                     'derived_rendering_ids':[c['id'] for c in claims if c.get('derived_from_claim_id')],
                     'derived_from_claim_ids':[c['derived_from_claim_id'] for c in claims if c.get('derived_from_claim_id')]}
                if field=='critic_opinions':
                    row['source_row_count']=opinion_counts[key]
                    if progress:
                        row['opinion_progress']={'distinct_opinions':len(progress),
                            'translated_opinions':sum(bool(item['fields'].get('opinion')) for item in progress),
                            'source_compared_texts':sum(bool(item['fields'].get('opinion')) and
                                'opinion' not in item['pending_fields'] for item in progress),
                            'complete_opinions':sum(item['complete'] for item in progress)}
                        if stage=='source_compared' and not all(item['complete'] for item in progress):
                            stage=row['stage']='source_search_pending'
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                stages[stage]+=1; tasks+=1
    return {'narrators':len(records),'field_tasks':tasks,'stages':dict(stages),'path':str(output)}
