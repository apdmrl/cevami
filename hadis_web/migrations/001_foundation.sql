CREATE TABLE IF NOT EXISTS source_snapshots (
    id uuid PRIMARY KEY, provider text NOT NULL, revision text NOT NULL,
    artifact_sha256 text NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    artifact_name text NOT NULL, acquired_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(provider,revision,artifact_sha256)
);
CREATE TABLE IF NOT EXISTS text_units (
    id uuid PRIMARY KEY, namespace text NOT NULL, source_key text NOT NULL,
    UNIQUE(namespace,source_key)
);
CREATE TABLE IF NOT EXISTS text_versions (
    id uuid PRIMARY KEY, unit_id uuid NOT NULL REFERENCES text_units(id),
    snapshot_id uuid NOT NULL REFERENCES source_snapshots(id), language text NOT NULL,
    raw_text text NOT NULL, display_text text NOT NULL,
    raw_sha256 text NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
    locator jsonb NOT NULL, derivation_version text NOT NULL DEFAULT 'reader-v1',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS text_versions_unit_idx ON text_versions(unit_id);
CREATE TABLE IF NOT EXISTS text_segments (
    id uuid PRIMARY KEY, text_version_id uuid NOT NULL REFERENCES text_versions(id),
    kind text NOT NULL, start_codepoint integer NOT NULL CHECK(start_codepoint>=0),
    end_codepoint integer NOT NULL CHECK(end_codepoint>start_codepoint)
);
CREATE TABLE IF NOT EXISTS alignment_cases (
    id uuid PRIMARY KEY, fingerprint text NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS alignment_revisions (
    id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES alignment_cases(id),
    revision integer NOT NULL CHECK(revision>0), scope text NOT NULL,
    relation_type text NOT NULL DEFAULT 'proposed', sealed boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(case_id,revision)
);
CREATE TABLE IF NOT EXISTS alignment_members (
    revision_id uuid NOT NULL REFERENCES alignment_revisions(id),
    text_version_id uuid NOT NULL REFERENCES text_versions(id),
    role text NOT NULL CHECK(role IN ('target_arabic','bridge_arabic','translation')),
    ordinal integer NOT NULL CHECK(ordinal>=0),
    PRIMARY KEY(revision_id,role,ordinal)
);
CREATE INDEX IF NOT EXISTS alignment_member_text_idx ON alignment_members(text_version_id,role);
CREATE TABLE IF NOT EXISTS comparison_evidence (
    id uuid PRIMARY KEY, revision_id uuid NOT NULL REFERENCES alignment_revisions(id),
    method text NOT NULL, evidence jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS review_events (
    id uuid PRIMARY KEY, revision_id uuid NOT NULL REFERENCES alignment_revisions(id),
    actor text NOT NULL, actor_kind text NOT NULL CHECK(actor_kind IN ('automated_check','assistant_source_review','expert_review')),
    dimension text NOT NULL CHECK(dimension IN ('arabic_relation','translation_meaning','translation_completeness','notes_separation','bibliography')),
    outcome text NOT NULL CHECK(outcome IN ('pending','pass','fail','not_applicable')),
    rationale text NOT NULL CHECK(length(trim(rationale))>0),
    source_refs jsonb NOT NULL CHECK(jsonb_typeof(source_refs)='array' AND jsonb_array_length(source_refs)>0),
    supersedes_id uuid REFERENCES review_events(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(NOT(actor_kind='automated_check' AND outcome IN ('pass','not_applicable')))
);
CREATE UNIQUE INDEX IF NOT EXISTS review_single_superseder ON review_events(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS narrator_records (
    id uuid PRIMARY KEY, snapshot_id uuid NOT NULL REFERENCES source_snapshots(id),
    source_id integer NOT NULL, data jsonb NOT NULL, UNIQUE(snapshot_id,source_id)
);
CREATE TABLE IF NOT EXISTS sanad_records (
    id uuid PRIMARY KEY, snapshot_id uuid NOT NULL REFERENCES source_snapshots(id),
    source_sanad_id integer NOT NULL, hadith_version_id uuid NOT NULL REFERENCES text_versions(id),
    rawy_ids_raw text NOT NULL, source_data jsonb NOT NULL, UNIQUE(snapshot_id,source_sanad_id)
);
CREATE INDEX IF NOT EXISTS sanad_hadith_idx ON sanad_records(hadith_version_id);
CREATE TABLE IF NOT EXISTS sanad_members (
    sanad_id uuid NOT NULL REFERENCES sanad_records(id), position integer NOT NULL CHECK(position>=0),
    source_value text NOT NULL, narrator_record_id uuid REFERENCES narrator_records(id),
    kind text NOT NULL CHECK(kind IN ('narrator','structural_marker','unresolved')),
    PRIMARY KEY(sanad_id,position)
);

CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable source or review record; add a new version or event'; END;
$$;
CREATE OR REPLACE FUNCTION validate_segment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE text_length integer;
BEGIN
    SELECT char_length(display_text) INTO text_length FROM text_versions WHERE id=NEW.text_version_id;
    IF NEW.end_codepoint>text_length THEN RAISE EXCEPTION 'Segment outside its immutable text version'; END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS segment_bounds ON text_segments;
CREATE TRIGGER segment_bounds BEFORE INSERT ON text_segments FOR EACH ROW EXECUTE FUNCTION validate_segment();

CREATE OR REPLACE FUNCTION guard_alignment_member() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE is_sealed boolean; lang text;
BEGIN
    SELECT sealed INTO is_sealed FROM alignment_revisions WHERE id=NEW.revision_id FOR UPDATE;
    IF is_sealed THEN RAISE EXCEPTION 'Sealed alignment revision cannot gain members'; END IF;
    SELECT language INTO lang FROM text_versions WHERE id=NEW.text_version_id;
    IF NEW.role IN ('target_arabic','bridge_arabic') AND lang<>'ar' THEN RAISE EXCEPTION 'Arabic member must reference Arabic text'; END IF;
    IF NEW.role='translation' AND lang='ar' THEN RAISE EXCEPTION 'Translation member must reference a translation language'; END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS alignment_member_guard ON alignment_members;
CREATE TRIGGER alignment_member_guard BEFORE INSERT ON alignment_members FOR EACH ROW EXECUTE FUNCTION guard_alignment_member();

CREATE OR REPLACE FUNCTION guard_alignment_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Alignment revision is immutable'; END IF;
    IF OLD.sealed=false AND NEW.sealed=true AND (to_jsonb(OLD)-'sealed')=(to_jsonb(NEW)-'sealed') THEN
        IF (SELECT count(DISTINCT role) FROM alignment_members WHERE revision_id=OLD.id)<>3 THEN
            RAISE EXCEPTION 'Alignment needs target Arabic, bridge Arabic and translation members';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Alignment revision is immutable; create another revision';
END;
$$;
DROP TRIGGER IF EXISTS alignment_revision_guard ON alignment_revisions;
CREATE TRIGGER alignment_revision_guard BEFORE UPDATE OR DELETE ON alignment_revisions FOR EACH ROW EXECUTE FUNCTION guard_alignment_revision();

CREATE OR REPLACE FUNCTION validate_review() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_event review_events;
BEGIN
    IF NOT (SELECT sealed FROM alignment_revisions WHERE id=NEW.revision_id) THEN
        RAISE EXCEPTION 'Cannot review an unsealed alignment';
    END IF;
    IF NEW.supersedes_id IS NOT NULL THEN
        SELECT * INTO old_event FROM review_events WHERE id=NEW.supersedes_id;
        IF old_event.revision_id<>NEW.revision_id OR old_event.actor<>NEW.actor OR old_event.dimension<>NEW.dimension THEN
            RAISE EXCEPTION 'Superseded review must have same revision, actor and dimension';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS review_guard ON review_events;
CREATE TRIGGER review_guard BEFORE INSERT ON review_events FOR EACH ROW EXECUTE FUNCTION validate_review();

DO $$ DECLARE table_name text; BEGIN
    FOREACH table_name IN ARRAY ARRAY['source_snapshots','text_units','text_versions','text_segments',
        'alignment_cases','alignment_members','comparison_evidence','review_events','narrator_records','sanad_records','sanad_members']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS immutable_guard ON %I',table_name);
        EXECUTE format('CREATE TRIGGER immutable_guard BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION reject_mutation()',table_name);
    END LOOP;
END $$;
