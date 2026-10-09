-- SHIP-8: when a label PDF is deleted in the file manager the label record stays, and this column records when its PDF
-- was removed. (No semicolons in comments: the migration runner splits files on them.)
ALTER TABLE labels ADD COLUMN IF NOT EXISTS pdf_deleted_at timestamptz
