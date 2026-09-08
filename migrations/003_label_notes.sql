-- Internal-only free-text note per label (customer-specific instructions).
-- Not sent to EPG -- no verified field exists on their ship request for this.

ALTER TABLE labels ADD COLUMN notes text;
