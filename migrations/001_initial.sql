-- Shipment Label Printing Portal (Green Shadow Enterprises) — initial schema.
-- See tasks/2026-08-11/shipment-label-portal.md for the full data model plan.

CREATE TABLE app_settings (
    id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),

    from_name text NOT NULL DEFAULT 'Navdeep Bajaj',
    from_company text NOT NULL DEFAULT 'Green Shadow Enterprises',
    from_address1 text NOT NULL DEFAULT '293 Whitehead Rd',
    from_address2 text,
    from_city text NOT NULL DEFAULT 'Trenton',
    from_state text NOT NULL DEFAULT 'NJ',
    from_postal_code text NOT NULL DEFAULT '08619-3250',
    from_country text NOT NULL DEFAULT 'US',
    from_phone text,
    from_email text,

    label_directory text NOT NULL DEFAULT 'labels',
    default_service_code text NOT NULL DEFAULT 'EP05'
        CHECK (default_service_code IN ('EP03', 'EP05')),
    epg_environment text NOT NULL DEFAULT 'sandbox'
        CHECK (epg_environment IN ('sandbox', 'production')),

    last_quota_available integer,
    last_quota_checked_at timestamptz,

    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_settings (id) VALUES (1);

CREATE TABLE bulk_runs (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,

    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'queued', 'running', 'completed',
                           'completed_with_errors', 'failed')),

    source_filename text NOT NULL,
    source_path text NOT NULL,

    weight_unit_override text CHECK (weight_unit_override IN ('oz', 'kg', 'lb')),
    dimension_unit_override text CHECK (dimension_unit_override IN ('inch', 'cm')),
    default_service_code text NOT NULL CHECK (default_service_code IN ('EP03', 'EP05')),

    total_rows integer NOT NULL DEFAULT 0,
    valid_rows integer NOT NULL DEFAULT 0,
    success_count integer NOT NULL DEFAULT 0,
    failure_count integer NOT NULL DEFAULT 0,

    error_message text
);

CREATE TABLE labels (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),

    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'created', 'failed', 'voided')),
    source text NOT NULL CHECK (source IN ('single', 'bulk')),
    bulk_run_id bigint REFERENCES bulk_runs (id),

    service_code text NOT NULL CHECK (service_code IN ('EP03', 'EP05')),

    recipient_name text NOT NULL,
    recipient_company text,
    recipient_address1 text NOT NULL,
    recipient_address2 text,
    recipient_city text NOT NULL,
    recipient_state text NOT NULL,
    recipient_postal_code text NOT NULL,
    recipient_country text NOT NULL DEFAULT 'US',
    recipient_phone text,
    recipient_phone_digits text,
    recipient_email text,

    from_name text,
    from_company text NOT NULL,
    from_address1 text NOT NULL,
    from_address2 text,
    from_city text NOT NULL,
    from_state text NOT NULL,
    from_postal_code text NOT NULL,
    from_country text NOT NULL DEFAULT 'US',
    from_phone text,
    from_email text,

    weight_value numeric(10, 2) NOT NULL,
    weight_unit text NOT NULL CHECK (weight_unit IN ('oz', 'kg', 'lb')),
    weight_oz numeric(10, 2) NOT NULL,

    length_value numeric(10, 2),
    width_value numeric(10, 2),
    height_value numeric(10, 2),
    dimension_unit text CHECK (dimension_unit IN ('inch', 'cm')),
    length_in numeric(10, 2),
    width_in numeric(10, 2),
    height_in numeric(10, 2),

    declared_value numeric(10, 2) NOT NULL,
    currency_code text NOT NULL DEFAULT 'USD',
    reference1 text,

    tracking_number text,
    unique_reference_id text,

    epg_request_json jsonb,
    epg_response_json jsonb,
    epg_error_code text,
    epg_error_message text,

    pdf_path text,
    pdf_size_bytes bigint,

    voided_at timestamptz,
    void_error text,

    search_text text GENERATED ALWAYS AS (
        lower(
            coalesce(recipient_name, '') || ' ' ||
            coalesce(recipient_company, '') || ' ' ||
            coalesce(recipient_address1, '') || ' ' ||
            coalesce(recipient_address2, '') || ' ' ||
            coalesce(recipient_city, '') || ' ' ||
            coalesce(recipient_state, '') || ' ' ||
            coalesce(recipient_postal_code, '') || ' ' ||
            coalesce(recipient_phone, '') || ' ' ||
            coalesce(recipient_phone_digits, '') || ' ' ||
            coalesce(reference1, '')
        )
    ) STORED
);

CREATE UNIQUE INDEX labels_unique_reference_id_idx
    ON labels (unique_reference_id) WHERE unique_reference_id IS NOT NULL;
CREATE INDEX labels_created_at_idx ON labels (created_at DESC);
CREATE INDEX labels_status_idx ON labels (status);
CREATE INDEX labels_bulk_run_id_idx ON labels (bulk_run_id);

CREATE TABLE bulk_run_rows (
    id bigserial PRIMARY KEY,
    bulk_run_id bigint NOT NULL REFERENCES bulk_runs (id),
    row_number integer NOT NULL,

    raw jsonb NOT NULL,

    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'invalid', 'success', 'failed', 'skipped')),
    validation_error text,
    epg_error_code text,
    epg_error_message text,

    label_id bigint REFERENCES labels (id),
    processed_at timestamptz
);

CREATE INDEX bulk_run_rows_run_status_idx ON bulk_run_rows (bulk_run_id, status);

-- schema_migrations itself is created by the migration runner (app/db.py)
-- before any migration file is applied, so it is not defined here.
