CREATE TABLE IF NOT EXISTS localization_claims (
    id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES source_snapshots(id),
    entity_type text NOT NULL, entity_key text NOT NULL,
    source_record jsonb NOT NULL CHECK(jsonb_typeof(source_record)='object'),
    source_record_sha256 text NOT NULL CHECK(source_record_sha256 ~ '^[0-9a-f]{64}$'),
    field text NOT NULL CHECK(length(trim(field))>0),
    language text NOT NULL CHECK(language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$' AND language !~ '^ar(-|$)'),
    translated_text text NOT NULL CHECK(length(trim(translated_text))>0),
    rendering_kind text NOT NULL CHECK(rendering_kind IN ('translation','transliteration','name_form','source_summary')),
    status text NOT NULL CHECK(status IN ('needs_review','source_compared','problem_detected')),
    actor_kind text NOT NULL CHECK(actor_kind IN ('automated_check','assistant_source_review','expert_review')),
    sources jsonb NOT NULL CHECK(jsonb_typeof(sources)='array' AND jsonb_array_length(sources)>0),
    rationale text NOT NULL CHECK(length(trim(rationale))>0),
    supersedes_id uuid REFERENCES localization_claims(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(NOT(actor_kind='automated_check' AND status='source_compared')),
    CHECK(rendering_kind='source_summary' OR (source_record ? field AND length(trim(source_record->>field))>0))
);
CREATE INDEX IF NOT EXISTS localization_lookup ON localization_claims(snapshot_id,entity_type,entity_key,language);
CREATE UNIQUE INDEX IF NOT EXISTS localization_single_superseder ON localization_claims(supersedes_id) WHERE supersedes_id IS NOT NULL;

CREATE OR REPLACE FUNCTION guard_localization_claim() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous localization_claims; ref jsonb;
BEGIN
    IF NEW.rendering_kind='source_summary' AND NEW.field !~ '_note$' THEN
        RAISE EXCEPTION 'A source summary must use a separate note field, never a translated source field';
    END IF;
    FOR ref IN SELECT value FROM jsonb_array_elements(NEW.sources) LOOP
        IF jsonb_typeof(ref)<>'object' OR coalesce(ref->>'url','') !~ '^(https?://|gk45:)' OR
           length(trim(coalesce(ref->>'title','')))=0 OR length(trim(coalesce(ref->>'locator','')))=0 OR
           coalesce(ref->>'accessed_on','') !~ '^\d{4}-\d{2}-\d{2}$' THEN
            RAISE EXCEPTION 'Source reference requires safe URL, title, locator and access date';
        END IF;
    END LOOP;
    IF NEW.supersedes_id IS NOT NULL THEN
        SELECT * INTO previous FROM localization_claims WHERE id=NEW.supersedes_id FOR UPDATE;
        IF previous.id IS NULL OR ROW(previous.snapshot_id,previous.entity_type,previous.entity_key,
            previous.source_record_sha256,previous.field,previous.language) IS DISTINCT FROM
            ROW(NEW.snapshot_id,NEW.entity_type,NEW.entity_key,NEW.source_record_sha256,NEW.field,NEW.language) THEN
            RAISE EXCEPTION 'Correction must refer to the same entity, source record, field and language';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS localization_claim_guard ON localization_claims;
CREATE TRIGGER localization_claim_guard BEFORE INSERT ON localization_claims FOR EACH ROW EXECUTE FUNCTION guard_localization_claim();
DROP TRIGGER IF EXISTS immutable_guard ON localization_claims;
CREATE TRIGGER immutable_guard BEFORE UPDATE OR DELETE ON localization_claims FOR EACH ROW EXECUTE FUNCTION reject_mutation();
