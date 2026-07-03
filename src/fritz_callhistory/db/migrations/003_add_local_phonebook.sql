CREATE TABLE phonebook_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    notes TEXT,
    box_uniqueid TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_phonebook_contacts_display_name ON phonebook_contacts (display_name);
CREATE INDEX idx_phonebook_contacts_box_uniqueid ON phonebook_contacts (box_uniqueid);

CREATE TABLE phonebook_contact_numbers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phonebook_contact_id INTEGER NOT NULL REFERENCES phonebook_contacts (id) ON DELETE CASCADE,
    number_raw TEXT NOT NULL,
    number_normalized TEXT NOT NULL,
    number_type TEXT NOT NULL DEFAULT 'home'
);

CREATE INDEX idx_phonebook_contact_numbers_contact ON phonebook_contact_numbers (phonebook_contact_id);
CREATE INDEX idx_phonebook_contact_numbers_normalized ON phonebook_contact_numbers (number_normalized);
