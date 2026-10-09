-- SHIP-8: when a label PDF is deleted in the file manager the label record stays; this records when its PDF was removed
ALTER TABLE labels ADD COLUMN IF NOT EXISTS pdf_deleted_at timestamptz
