import argparse
import json
import uvicorn
from .config import Settings
from .working import WorkingStore
from .importer import load_pilot
from .localization import load_localization_pilot
from .opinions import load_opinion_batches, load_critic_names
from .translation_queue import write_narrator_queue
from .corpus import load_corpus
from .progress import write_translation_progress
from .controlled_terms import load_controlled_terms
from .field_reviews import load_field_review_batches
from .opinion_reviews import load_opinion_reviews
from .critic_name_reviews import load_critic_name_reviews
from .hadith_reviews import load_hadith_reviews


def main():
    parser = argparse.ArgumentParser(description='Cevâmi local reader and source-preserving pilot tools')
    parser.add_argument('command', choices=['bootstrap', 'import-corpus', 'localize', 'localize-opinions', 'localize-critic-names', 'localize-terms', 'review-fields', 'review-opinions', 'review-critic-names', 'review-hadiths', 'translation-queue', 'translation-progress', 'counts', 'serve'])
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.command == 'serve':
        uvicorn.run('hadis_web.app:create_app', factory=True, host='127.0.0.1', port=args.port)
        return
    settings = Settings.load()
    if not settings.postgres_dsn:
        parser.error('Local PostgreSQL connection is not configured in .local/settings.json or HADIS_DATABASE_URL')
    store = WorkingStore(settings.postgres_dsn, settings.postgres_schema)
    if args.command == 'bootstrap':
        store.migrate()
        print('Reference checks and source-preserving Buhârî import started.', flush=True)
        result = load_pilot(store, settings)
    elif args.command == 'localize':
        store.migrate()
        result = load_localization_pilot(store, settings)
    elif args.command == 'translation-queue':
        result=write_narrator_queue(store,settings,settings.project_root/'research/bukhari-review/narrator-translation-queue.jsonl')
    elif args.command == 'localize-opinions':
        store.migrate()
        result=load_opinion_batches(store,settings)
    elif args.command == 'import-corpus':
        store.migrate()
        result=load_corpus(store,settings)
    elif args.command == 'localize-critic-names':
        store.migrate()
        result=load_critic_names(store,settings)
    elif args.command == 'localize-terms':
        store.migrate()
        result=load_controlled_terms(store)
    elif args.command == 'review-fields':
        store.migrate()
        result=load_field_review_batches(store,settings)
    elif args.command == 'review-opinions':
        store.migrate()
        result=load_opinion_reviews(store,settings)
    elif args.command == 'review-critic-names':
        store.migrate()
        result=load_critic_name_reviews(store,settings)
    elif args.command == 'review-hadiths':
        store.migrate()
        result=load_hadith_reviews(store,settings)
    elif args.command == 'translation-progress':
        result=write_translation_progress(store,settings,settings.project_root/'research/corpus-review/translation-progress.json')
    else:
        result = store.counts()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
