"""Datei-Import/-Export für das lokale Telefonbuch: Fritz!Box-XML, CSV, vCard.

Reine Datei-/Domänenlogik ohne Zugriff auf fritz/ oder Netzwerk - die GUI ruft
parse_*/write_* direkt auf (analog zu sync/normalize.py) und reicht das
Ergebnis über import_contacts() an db.repository.LocalPhonebookRepository
weiter.
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from fritz_callhistory.sync.normalize import normalize_number

if TYPE_CHECKING:
    from fritz_callhistory.db.repository import LocalPhonebookRepository

_DEFAULT_NUMBER_TYPE = "home"


class PhonebookImportError(Exception):
    """Strukturell ungültige Datei (Parsen nicht möglich)."""


@dataclass
class ImportedNumber:
    number_raw: str
    number_normalized: str
    number_type: str


@dataclass
class ImportedContact:
    display_name: str
    notes: str | None
    numbers: list[ImportedNumber]
    box_uniqueid: str | None = None


@dataclass
class ImportResult:
    contacts: list[ImportedContact]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportSummary:
    created: int
    skipped_duplicate: int
    warnings: list[str]


def _normalized_number_or_warn(
    raw: str, contact_name: str, number_type: str, warnings: list[str]
) -> ImportedNumber | None:
    """Normalisiert *raw* für einen Kontakt-Import; bei nicht erkennbaren/
    unterdrückten Nummern None und eine Warnung statt eines Fehlers - geteilt
    zwischen parse_xml/parse_csv/parse_vcard."""
    normalized, is_anonymous = normalize_number(raw)
    if is_anonymous:
        warnings.append(f"Nummer '{raw}' bei Kontakt '{contact_name}' übersprungen (nicht erkennbar).")
        return None
    return ImportedNumber(number_raw=raw, number_normalized=normalized, number_type=number_type)


# --- Fritz!Box-kompatibles XML ---


def parse_xml(path: Path) -> ImportResult:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise PhonebookImportError(f"Ungültige XML-Datei: {exc}") from exc
    if root.tag != "phonebooks":
        raise PhonebookImportError(
            "Keine gültige Fritz!Box-Telefonbuch-Datei (Root-Element 'phonebooks' erwartet)."
        )

    contacts: list[ImportedContact] = []
    warnings: list[str] = []
    for contact_el in root.iter("contact"):
        name_el = contact_el.find("person/realName")
        name = (name_el.text or "").strip() if name_el is not None and name_el.text else ""
        if not name:
            warnings.append("Kontakt ohne Namen übersprungen.")
            continue

        uniqueid_el = contact_el.find("uniqueid")
        box_uniqueid = (
            uniqueid_el.text.strip() if uniqueid_el is not None and uniqueid_el.text else None
        )

        numbers: list[ImportedNumber] = []
        for number_el in contact_el.findall("telephony/number"):
            raw = (number_el.text or "").strip()
            if not raw:
                continue
            number_type = number_el.get("type") or _DEFAULT_NUMBER_TYPE
            number = _normalized_number_or_warn(raw, name, number_type, warnings)
            if number is not None:
                numbers.append(number)
        contacts.append(
            ImportedContact(display_name=name, notes=None, numbers=numbers, box_uniqueid=box_uniqueid)
        )
    return ImportResult(contacts=contacts, warnings=warnings)


def write_xml(
    path: Path, contacts: list[ImportedContact], phonebook_name: str = "Fritz Callhistory Export"
) -> None:
    root = ET.Element("phonebooks")
    phonebook_el = ET.SubElement(root, "phonebook", {"name": phonebook_name})
    for contact in contacts:
        contact_el = ET.SubElement(phonebook_el, "contact")
        ET.SubElement(contact_el, "category").text = "0"
        person_el = ET.SubElement(contact_el, "person")
        ET.SubElement(person_el, "realName").text = contact.display_name
        telephony_el = ET.SubElement(
            contact_el, "telephony", {"nid": str(max(len(contact.numbers), 1))}
        )
        for index, number in enumerate(contact.numbers):
            number_el = ET.SubElement(
                telephony_el,
                "number",
                {
                    "type": number.number_type or _DEFAULT_NUMBER_TYPE,
                    "prio": "1" if index == 0 else "0",
                    "id": str(index),
                },
            )
            number_el.text = number.number_raw
        # <uniqueid> nur setzen, wenn der Kontakt von einem frueheren Box-Import
        # stammt - sonst vergibt die Box beim manuellen Import selbst eine neue
        # Id (siehe fritz/client.py phonebook_contacts_detailed()).
        if contact.box_uniqueid:
            ET.SubElement(contact_el, "uniqueid").text = contact.box_uniqueid
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


# --- CSV ---

_CSV_HEADER = ["contact_id", "display_name", "notes", "number", "number_type"]


def parse_csv(path: Path) -> ImportResult:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != _CSV_HEADER:
                raise PhonebookImportError(
                    f"Unerwarteter CSV-Header, erwartet: {','.join(_CSV_HEADER)}"
                )
            rows = list(reader)
    except OSError as exc:
        raise PhonebookImportError(f"Datei konnte nicht gelesen werden: {exc}") from exc
    except csv.Error as exc:
        raise PhonebookImportError(f"Ungültige CSV-Datei: {exc}") from exc

    warnings: list[str] = []
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        raw_id = (row.get("contact_id") or "").strip()
        if not raw_id.lstrip("-").isdigit():
            warnings.append(f"Zeile mit ungültiger contact_id '{raw_id}' übersprungen.")
            continue
        if raw_id not in grouped:
            grouped[raw_id] = {"display_name": "", "notes": "", "numbers": []}
            order.append(raw_id)
        group = grouped[raw_id]

        name = (row.get("display_name") or "").strip()
        if name and not group["display_name"]:
            group["display_name"] = name
        elif name and group["display_name"] and name != group["display_name"]:
            warnings.append(
                f"Kontakt '{raw_id}': abweichender Name '{name}' ignoriert, "
                f"'{group['display_name']}' wird verwendet."
            )

        notes = (row.get("notes") or "").strip()
        if notes and not group["notes"]:
            group["notes"] = notes

        raw_number = (row.get("number") or "").strip()
        if raw_number:
            number_type = (row.get("number_type") or "").strip() or _DEFAULT_NUMBER_TYPE
            group["numbers"].append((raw_number, number_type))

    contacts: list[ImportedContact] = []
    for raw_id in order:
        group = grouped[raw_id]
        name = group["display_name"]
        if not name:
            warnings.append(f"Kontakt '{raw_id}' ohne Namen übersprungen.")
            continue
        numbers: list[ImportedNumber] = []
        for raw_number, number_type in group["numbers"]:
            number = _normalized_number_or_warn(raw_number, name, number_type, warnings)
            if number is not None:
                numbers.append(number)
        contacts.append(ImportedContact(display_name=name, notes=group["notes"] or None, numbers=numbers))
    return ImportResult(contacts=contacts, warnings=warnings)


def write_csv(path: Path, contacts: list[ImportedContact]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADER)
        writer.writeheader()
        for index, contact in enumerate(contacts, start=1):
            numbers = contact.numbers or [None]
            for number in numbers:
                writer.writerow(
                    {
                        "contact_id": index,
                        "display_name": contact.display_name,
                        "notes": contact.notes or "",
                        "number": number.number_raw if number else "",
                        "number_type": number.number_type if number else "",
                    }
                )


# --- vCard 3.0 ---

_VCARD_TEL_TYPE_TO_LOCAL = {"CELL": "mobile", "WORK,FAX": "fax_work", "FAX,WORK": "fax_work"}
_LOCAL_TO_VCARD_TEL_TYPE = {"mobile": "CELL", "work": "WORK", "fax_work": "WORK,FAX", "home": "HOME"}


def _vcard_number_type(key_part: str) -> str:
    params = {p.upper() for p in key_part.split(";")[1:]}
    types: set[str] = set()
    for param in params:
        types.update(param.removeprefix("TYPE=").split(",")) if param.startswith("TYPE=") else types.add(param)
    if "CELL" in types:
        return "mobile"
    if "WORK" in types and "FAX" in types:
        return "fax_work"
    if "WORK" in types:
        return "work"
    if "HOME" in types:
        return "home"
    return _DEFAULT_NUMBER_TYPE


def _escape_vcard(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace("\n", "\\n")


def _unescape_vcard(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\\\", "\\")


def parse_vcard(path: Path) -> ImportResult:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PhonebookImportError(f"Datei konnte nicht gelesen werden: {exc}") from exc

    # vCard erlaubt "folding": Fortsetzungszeilen beginnen mit Leerzeichen/Tab.
    unfolded_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith((" ", "\t")) and unfolded_lines:
            unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)

    if not any(line.strip().upper() == "BEGIN:VCARD" for line in unfolded_lines):
        raise PhonebookImportError("Keine gültige vCard-Datei (kein 'BEGIN:VCARD' gefunden).")

    contacts: list[ImportedContact] = []
    warnings: list[str] = []
    current: dict | None = None
    for line in unfolded_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper() == "BEGIN:VCARD":
            current = {"name": None, "notes": None, "numbers": []}
            continue
        if stripped.upper() == "END:VCARD":
            if current is None:
                continue
            name = current["name"]
            if not name:
                warnings.append("vCard ohne FN-Feld (Name) übersprungen.")
                current = None
                continue
            numbers: list[ImportedNumber] = []
            for raw_number, number_type in current["numbers"]:
                number = _normalized_number_or_warn(raw_number, name, number_type, warnings)
                if number is not None:
                    numbers.append(number)
            contacts.append(ImportedContact(display_name=name, notes=current["notes"], numbers=numbers))
            current = None
            continue
        if current is None or ":" not in stripped:
            continue
        key_part, _, value = stripped.partition(":")
        key = key_part.split(";")[0].upper()
        if key == "FN":
            current["name"] = _unescape_vcard(value.strip())
        elif key == "NOTE":
            current["notes"] = _unescape_vcard(value.strip()) or None
        elif key == "TEL":
            current["numbers"].append((value.strip(), _vcard_number_type(key_part)))

    return ImportResult(contacts=contacts, warnings=warnings)


def write_vcard(path: Path, contacts: list[ImportedContact]) -> None:
    lines: list[str] = []
    for contact in contacts:
        lines.append("BEGIN:VCARD")
        lines.append("VERSION:3.0")
        lines.append(f"FN:{_escape_vcard(contact.display_name)}")
        for number in contact.numbers:
            type_param = _LOCAL_TO_VCARD_TEL_TYPE.get(number.number_type, "HOME")
            lines.append(f"TEL;TYPE={type_param}:{number.number_raw}")
        if contact.notes:
            lines.append(f"NOTE:{_escape_vcard(contact.notes)}")
        lines.append("END:VCARD")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


# --- Import in die DB ---


def import_contacts(repo: LocalPhonebookRepository, result: ImportResult) -> ImportSummary:
    """Legt neue Telefonbuch-Kontakte an; überspringt Duplikate.

    Ein Kontakt gilt als Duplikat, wenn seine komplette (nicht-leere)
    Nummernmenge bereits vollständig einem bestehenden lokalen Kontakt gehört
    - macht wiederholtes Importieren derselben Datei idempotent (zweiter Lauf:
    created=0, skipped_duplicate=N). Änderte sich die Datei zwischenzeitlich,
    wird der Kontakt als neu importiert (kein Fuzzy-Merge).
    """
    created = 0
    skipped_duplicate = 0
    for contact in result.contacts:
        numbers_normalized = [n.number_normalized for n in contact.numbers]
        if numbers_normalized and repo.all_numbers_belong_to_one_contact(numbers_normalized):
            skipped_duplicate += 1
            continue
        repo.create(
            display_name=contact.display_name,
            notes=contact.notes,
            numbers=[(n.number_raw, n.number_normalized, n.number_type) for n in contact.numbers],
            box_uniqueid=contact.box_uniqueid,
        )
        created += 1
    return ImportSummary(created=created, skipped_duplicate=skipped_duplicate, warnings=list(result.warnings))
