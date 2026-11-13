CREATE TABLE IF NOT EXISTS hadith_component_sets (
    id uuid PRIMARY KEY,
    target_version_id uuid NOT NULL REFERENCES text_versions(id),
    language text NOT NULL CHECK(language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$' AND language !~ '^ar(-|$)'),
    segmentation_version text NOT NULL CHECK(length(trim(segmentation_version))>0),
    payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
    payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
    supersedes_id uuid REFERENCES hadith_component_sets(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK(payload->>'target_version_id'=target_version_id::text AND payload->>'language'=language)
);
CREATE UNIQUE INDEX IF NOT EXISTS hadith_components_one_root ON hadith_component_sets(target_version_id,language) WHERE supersedes_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS hadith_components_one_child ON hadith_component_sets(supersedes_id) WHERE supersedes_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS hadith_components_target ON hadith_component_sets(target_version_id,language);
CREATE OR REPLACE FUNCTION guard_component_parent() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent hadith_component_sets;
BEGIN
    IF NEW.supersedes_id IS NOT NULL THEN
        SELECT * INTO parent FROM hadith_component_sets WHERE id=NEW.supersedes_id;
        IF parent.id IS NULL OR ROW(parent.target_version_id,parent.language) IS DISTINCT FROM ROW(NEW.target_version_id,NEW.language) THEN
            RAISE EXCEPTION 'Component correction must bind the same source version and language';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS component_parent_guard ON hadith_component_sets;
CREATE TRIGGER component_parent_guard BEFORE INSERT ON hadith_component_sets FOR EACH ROW EXECUTE FUNCTION guard_component_parent();
DROP TRIGGER IF EXISTS immutable_guard ON hadith_component_sets;
CREATE TRIGGER immutable_guard BEFORE UPDATE OR DELETE ON hadith_component_sets FOR EACH ROW EXECUTE FUNCTION reject_mutation();
