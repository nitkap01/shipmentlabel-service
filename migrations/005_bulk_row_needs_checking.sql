-- SHIP-3: bulk rows whose label may have been bought (timeout, or bought but the PDF failed) get their own status
-- 'needs_checking' instead of 'failed', so they never go into the re-uploadable "Failed Rows" sheet.
-- 'duplicate' = not bought because an identical label was bought minutes earlier (or its purchase is still uncertain).
ALTER TABLE bulk_run_rows DROP CONSTRAINT IF EXISTS bulk_run_rows_status_check;
ALTER TABLE bulk_run_rows ADD CONSTRAINT bulk_run_rows_status_check
    CHECK (status IN ('pending', 'invalid', 'success', 'failed', 'skipped', 'needs_checking', 'duplicate'));
