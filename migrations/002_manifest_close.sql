-- Manifest Close (D25-D37). See tasks/2026-08-11/shipment-label-portal.md,
-- "Plan — Manifest Close (2026-08-31)" and its later "Answers received"
-- amendment (D28 revised: account numbers are auto-captured, not typed in).

ALTER TABLE app_settings
    ADD COLUMN epg_account_number_sandbox text,
    ADD COLUMN epg_account_number_production text;

CREATE TABLE manifest_closes (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'failed')),
    epg_environment text NOT NULL CHECK (epg_environment IN ('sandbox', 'production')),
    account_number text NOT NULL,
    close_id text,
    close_reports jsonb,
    candidate_label_ids jsonb NOT NULL,
    epg_response_json jsonb,
    error_message text,
    resolved_manually boolean NOT NULL DEFAULT false
);

CREATE INDEX manifest_closes_created_at_idx ON manifest_closes (created_at DESC);

ALTER TABLE labels ADD COLUMN manifest_close_id bigint REFERENCES manifest_closes (id);
ALTER TABLE labels ADD COLUMN epg_environment text NOT NULL DEFAULT 'sandbox';

CREATE INDEX labels_manifest_close_id_idx ON labels (manifest_close_id);
CREATE INDEX labels_open_idx ON labels (created_at DESC)
    WHERE status = 'created' AND manifest_close_id IS NULL;
