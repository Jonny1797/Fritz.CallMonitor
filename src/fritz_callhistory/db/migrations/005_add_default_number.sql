ALTER TABLE phonebook_contact_numbers ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX idx_phonebook_number_default
    ON phonebook_contact_numbers (phonebook_contact_id)
    WHERE is_default = 1;
