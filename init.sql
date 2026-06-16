-- btree_gist lets the GiST index combine equality (satellite_id, asset_type)
-- with range-overlap operator (&&) in a single exclusion constraint.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS asset_versions (
    id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    satellite_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    validity    TSTZRANGE NOT NULL,
    payload_uri TEXT NOT NULL,
    media_type   TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    lineage_version_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_lookup
    ON asset_versions (satellite_id, asset_type);

-- DEFERRABLE so multi-step plans (the split/caso 1) can pass
-- through transient overlaps and are validated atomically at commit
ALTER TABLE asset_versions
    ADD CONSTRAINT no_overlapping_validity
    EXCLUDE USING gist (
        satellite_id WITH =,
        asset_type WITH =,
        validity WITH &&
    )
    DEFERRABLE INITIALLY DEFERRED;