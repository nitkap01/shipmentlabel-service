-- Search should also match tracking number. `search_text` is a generated
-- column, so its expression can only be changed by dropping and re-adding it.

ALTER TABLE labels DROP COLUMN search_text;

ALTER TABLE labels ADD COLUMN search_text text GENERATED ALWAYS AS (
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
        coalesce(reference1, '') || ' ' ||
        coalesce(tracking_number, '')
    )
) STORED;
