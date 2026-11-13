"""Report the full remaining scope; stored candidates never mean completion."""
import json
from pathlib import Path
from .localization import NARRATOR_FIELDS
from .source import open_readonly, STRUCTURAL_IDS
from .working import stable_id
from .importer import verify_artifact
from .controlled_terms import controlled_term_coverage
from .hadith_components import component_progress


def write_translation_progress(working, settings, output):
    manifest=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())
    verify_artifact(settings.source_db,manifest['database_sha256'])
    snapshot=stable_id('snapshot','gk45','4.5',manifest['database_sha256'])
    with open_readonly(settings.source_db) as c:
        scope={label:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for label,table in
               [('hadith_texts','hadith_text'),('books','books'),('dictionary_roots','dictionary'),('critic_identities','critics')]}
        scope['narrators']=c.execute('SELECT COUNT(*) FROM narrators WHERE id NOT IN (30000,30001,30002)').fetchone()[0]
        scope['narrator_field_cells']=c.execute('SELECT SUM('+ '+'.join(
            f"CASE WHEN length(trim(coalesce({field},'')))>0 THEN 1 ELSE 0 END" for field in NARRATOR_FIELDS)+
            ') FROM narrators WHERE id NOT IN (30000,30001,30002)').fetchone()[0]
        scope['distinct_critic_opinions']=c.execute('SELECT COUNT(*) FROM '
            '(SELECT rawy_id,alem_id,opinion FROM critic_opinions GROUP BY rawy_id,alem_id,opinion)').fetchone()[0]
        scope['isnad_records']=c.execute('SELECT COUNT(*) FROM sanad').fetchone()[0]
        # These surfaces are present in the source and remain in the goal,
        # even though the current reader does not expose all of them yet.
        additional={label:{'source_rows':c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],
                           'translation_coverage':'not_yet_audited'} for label,table in
                    [('bibliography','references_bib'),('authors','authors'),('book_topics','topic_nodes'),
                     ('manuscript_cards','manuscripts'),('lexical_word_forms','word_forms'),
                     ('commentaries','commentaries'),('quran_references','quran_verses')]}
        additional['narrator_other_fields']={'columns':['e5telat','tadleese','date_of_birth','death_year','age',
            'tabaka','bokhary','moslem','marweyaat'],'translation_coverage':'not_yet_audited'}
    with working.connection() as c:
        aligned=c.execute("SELECT DISTINCT u.source_key FROM alignment_members am "
            "JOIN text_versions tv ON tv.id=am.text_version_id JOIN text_units u ON u.id=tv.unit_id "
            "JOIN alignment_revisions r ON r.id=am.revision_id "
            "WHERE am.role='target_arabic' AND u.namespace='gk45:ar' AND tv.snapshot_id=%s AND r.sealed "
            "AND EXISTS (SELECT 1 FROM alignment_members tm JOIN text_versions tr ON tr.id=tm.text_version_id "
            "WHERE tm.revision_id=r.id AND tm.role='translation' AND tr.language='tr')",(snapshot,)).fetchall()
        classified=c.execute("SELECT DISTINCT r.id,tv.unit_id FROM alignment_revisions r JOIN alignment_members am "
            "ON am.revision_id=r.id AND am.role='target_arabic' JOIN text_versions tv ON tv.id=am.text_version_id "
            "WHERE tv.snapshot_id=%s AND r.sealed AND r.scope<>'unclassified' "
            "AND EXISTS(SELECT 1 FROM alignment_members tm JOIN text_versions tr ON tr.id=tm.text_version_id "
            "WHERE tm.revision_id=r.id AND tm.role='translation' AND tr.language='tr')",(snapshot,)).fetchall()
        claims=c.execute("SELECT entity_type,field,status,count(*) AS n FROM localization_claims cl "
            "WHERE snapshot_id=%s AND language='tr' AND NOT EXISTS "
            "(SELECT 1 FROM localization_claims newer WHERE newer.supersedes_id=cl.id) "
            "GROUP BY entity_type,field,status ORDER BY entity_type,field,status",(snapshot,)).fetchall()
    compared={str(row['unit_id']) for row in classified if working.assessment(row['id'])['status']=='source_compared'}
    components=component_progress(working,settings,snapshot)
    alignment_candidates={row['source_key'] for row in aligned}
    candidates=len(alignment_candidates | set(components['matn_candidate_keys']))
    report={'source_snapshot_id':str(snapshot),'source_artifact_sha256':manifest['database_sha256'],
            'source_scope':scope,'additional_translation_surfaces':additional,
            'counted_narrator_field_columns':list(NARRATOR_FIELDS),
            'working':{'hadith_targets_with_candidates':candidates,'text_scope_source_compared_targets':len(compared),
                       'alignment_targets_with_candidates':len(alignment_candidates),
                       'source_compared_hadith_targets':components['fully_compared_targets'],
                       'component_reviews':components,
                       'stored_current_snapshot_localization_claims':claims},
            'controlled_terminology':controlled_term_coverage(working,settings),
            'remaining':{'hadith_targets_without_candidate':scope['hadith_texts']-candidates,
                         'hadith_targets_without_completed_comparison':scope['hadith_texts']-components['fully_compared_targets']},
            'project_complete':False,
            'completion_reason':'All source surfaces require coverage; candidates, drafts and unaudited surfaces are not completed translations.'}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report
