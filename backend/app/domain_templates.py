"""Preschool, Paneerwala, Space View, and Hiring templates.

Original roadmap Sprint 10. The catalog is the field dictionary for the four
worksheets in the operator workbook. Publishing and import still go through
the existing form, version, and import APIs. Paneerwala is not published:
its header row does not describe the cells underneath it.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

SOURCE_WORKBOOK = Path(r"c:\Users\lenovo\Downloads\CRM.xlsx")
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_EPOCH = datetime(1899, 12, 30)
_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_WHOLE = re.compile(r"^-?\d+(\.0+)?$")
_MOBILE = re.compile(r"^\+?[0-9]{8,15}$")
_MOBILE_SPLIT = re.compile(r"[\s().-]")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PANEER_STAMP = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\s+-\s+\d{1,2}:\d{2}\s*[AP]M$", re.IGNORECASE)


@dataclass(frozen=True)
class Cell:
    text: str
    kind: str
    formula: bool


@dataclass(frozen=True)
class Worksheet:
    name: str
    headers: dict[str, str]
    cells: dict[tuple[int, str], Cell]
    max_row: int
    merges: tuple[str, ...]

    def data_rows(self) -> list[int]:
        rows = []
        for number in range(2, self.max_row + 1):
            if any(self.cells.get((number, letter)) for letter in self.headers):
                present = False
                for letter in self.headers:
                    cell = self.cells.get((number, letter))
                    if cell is not None and (cell.text.strip() or cell.formula):
                        present = True
                        break
                if present:
                    rows.append(number)
        return rows


@dataclass(frozen=True)
class Column:
    letter: str
    source_header: str
    derived_header: str
    field_key: str
    transform: str


@dataclass(frozen=True)
class Template:
    key: str
    form_name: str
    description: str
    project_code: str
    project_name: str
    publish: bool
    block_reason: str
    fields: tuple[dict[str, object], ...]
    columns: tuple[Column, ...]
    idempotency_key: str
    identifier_field: str
    sheet_name: str


def _field(
    key: str,
    label: str,
    field_type: str,
    *,
    required: bool,
    section: str,
    help_text: str = "",
    options: tuple[tuple[str, str], ...] = (),
) -> dict[str, object]:
    payload: dict[str, object] = {
        "field_key": key,
        "label": label,
        "field_type": field_type,
        "required": required,
        "section_name": section,
        "help_text": help_text,
    }
    if options:
        payload["options"] = [{"value": value, "label": label_text} for value, label_text in options]
    return payload


_POSITION = (
    ("sales_resource", "Sales Resource"),
    ("accountant", "Accountant"),
    ("accounting_and_sales", "Accounting & Sales"),
    ("interior_designer", "Interior Designer"),
)
_FINAL = (("accepted", "Accepted"), ("closed", "Closed"))


def _columns(*items: tuple[str, str, str, str, str]) -> tuple[Column, ...]:
    return tuple(Column(*item) for item in items)


PRESCHOOL = Template(
    key="preschool",
    form_name="Preschool",
    description=(
        "B2B school enquiry form for the Preschool worksheet. "
        "Follow-up comments stay on the record because those cells are unstructured text, not activity-log rows."
    ),
    project_code="PRESCHOOL",
    project_name="Preschool",
    publish=True,
    block_reason="",
    identifier_field="lead_id",
    sheet_name="Preschool",
    idempotency_key="preschool-source-v1",
    fields=(
        _field("lead_id", "Lead ID", "number", required=True, section="Identity", help_text="Source lead identifier. The project record number is separate."),
        _field("inquiry_date", "Inquiry Date", "date", required=False, section="Identity"),
        _field("school_name", "School Name", "text", required=True, section="Identity", help_text="Record title for a school prospect."),
        _field("contact_person", "Contact Person", "text", required=False, section="Contact"),
        _field("mobile_number", "Mobile Number", "mobile", required=False, section="Contact"),
        _field("email", "Email ID", "email", required=False, section="Contact"),
        _field("website", "Website", "url", required=False, section="Contact"),
        _field("city", "City", "text", required=False, section="Contact"),
        _field("selling_point", "Selling Point", "long_text", required=False, section="Interest"),
        _field("lead_source", "Lead Source", "text", required=False, section="Interest", help_text="Original source text. The starter picklist is not applied."),
        _field("interested_product", "Interested Product", "text", required=False, section="Interest"),
        _field("requirement_details", "Requirement Details", "long_text", required=False, section="Interest"),
        _field("student_strength", "Student Strength", "number", required=False, section="Interest", help_text="No source values were present. A count is stored as a number."),
        _field("branch_count", "No of Branches", "number", required=False, section="Interest", help_text="No source values were present. A count is stored as a number."),
        _field("priority", "Priority", "text", required=False, section="Follow-up", help_text="Original text. Hot, Warm, and Cold are not enforced as a picklist."),
        _field("follow_up_date", "Follow-up Date", "date", required=False, section="Follow-up"),
        _field("connected", "Connected", "text", required=False, section="Follow-up"),
        _field("discussion_summary", "Discussion Summary", "long_text", required=False, section="Follow-up"),
        _field("followup_comments_1", "Followup Comments 1", "long_text", required=False, section="Follow-up", help_text="First Followup Comments column. The source header is repeated."),
        _field("followup_comments_2", "Followup Comments 2", "long_text", required=False, section="Follow-up", help_text="Second Followup Comments column. The source header is repeated."),
    ),
    columns=_columns(
        ("A", "Lead ID", "Lead ID", "lead_id", "whole_number"),
        ("B", "Inquiry Date", "Inquiry Date", "inquiry_date", "date"),
        ("C", "School Name", "School Name", "school_name", "text"),
        ("D", "Contact Person", "Contact Person", "contact_person", "text"),
        ("E", "Mobile Number", "Mobile Number", "mobile_number", "mobile"),
        ("F", "Email ID", "Email ID", "email", "email"),
        ("G", "Website ", "Website", "website", "url"),
        ("H", "City", "City", "city", "text"),
        ("I", "Selling Point ", "Selling Point", "selling_point", "text"),
        ("J", "Lead Source", "Lead Source", "lead_source", "text"),
        ("K", "Interested Product", "Interested Product", "interested_product", "text"),
        ("L", "Requirement Details", "Requirement Details", "requirement_details", "text"),
        ("M", "Student Strength", "Student Strength", "student_strength", "whole_number"),
        ("N", "No of Branches", "No of Branches", "branch_count", "whole_number"),
        ("O", "Priority", "Priority", "priority", "text"),
        ("P", "Follow-up Date", "Follow-up Date", "follow_up_date", "date"),
        ("Q", "Connected", "Connected", "connected", "text"),
        ("R", "Discussion Summary", "Discussion Summary", "discussion_summary", "text"),
        ("S", "Followup Comments ", "Followup Comments 1", "followup_comments_1", "text"),
        ("T", "Followup Comments ", "Followup Comments 2", "followup_comments_2", "text"),
    ),
)

SPACE_VIEW = Template(
    key="space_view",
    form_name="Space View",
    description=(
        "Interior enquiry form for the Space View worksheet. "
        "Original casing is stored as entered. Follow-up columns stay on the record."
    ),
    project_code="SPACE-VIEW",
    project_name="Space View",
    publish=True,
    block_reason="",
    identifier_field="sr_no",
    sheet_name="Space View",
    idempotency_key="space-view-source-v1",
    fields=(
        _field("sr_no", "SR.NO", "number", required=True, section="Identity", help_text="Source serial. It is not unique in the worksheet."),
        _field("inquiry_date", "INQUIRY DATE", "date", required=False, section="Identity"),
        _field("name", "NAME", "text", required=True, section="Identity"),
        _field("contact_no", "CONTACT NO.", "mobile", required=False, section="Contact"),
        _field("location", "LOCATION", "text", required=False, section="Enquiry"),
        _field("requirement_details", "REQUIRMENT DETAILS", "long_text", required=False, section="Enquiry", help_text="Source header spelling is REQUIRMENT."),
        _field("lead_source", "LEAD SOURCE", "text", required=False, section="Enquiry", help_text="Original source text, including its casing."),
        _field("priority", "PRIORITY", "text", required=False, section="Enquiry", help_text="Original casing is kept."),
        _field("follow_up_date_1", "Follow Up date 1", "date", required=False, section="Follow-up"),
        _field("follow_up_1_details", "FOLLOW UP 1 - Details", "long_text", required=False, section="Follow-up"),
        _field("follow_up_date_2", "Follow Up date 2", "date", required=False, section="Follow-up"),
        _field("follow_up_2_details", "FOLLOW UP 2 - Details", "long_text", required=False, section="Follow-up"),
        _field("follow_up_3", "FOLLOW UP 3", "long_text", required=False, section="Follow-up"),
        _field("follow_up_4", "FOLLOW UP 4", "long_text", required=False, section="Follow-up"),
    ),
    columns=_columns(
        ("A", "SR.NO", "SR.NO", "sr_no", "whole_number"),
        ("B", "INQUIRY DATE", "INQUIRY DATE", "inquiry_date", "date"),
        ("C", "NAME", "NAME", "name", "text"),
        ("D", "CONTACT NO.", "CONTACT NO.", "contact_no", "mobile"),
        ("E", "LOCATION", "LOCATION", "location", "text"),
        ("F", "REQUIRMENT DETAILS", "REQUIRMENT DETAILS", "requirement_details", "text"),
        ("G", "LEAD SOURCE", "LEAD SOURCE", "lead_source", "text"),
        ("H", "PRIORITY", "PRIORITY", "priority", "text"),
        ("I", "Follow Up date 1", "Follow Up date 1", "follow_up_date_1", "date"),
        ("J", "FOLLOW UP 1 - Details", "FOLLOW UP 1 - Details", "follow_up_1_details", "text"),
        ("K", "Follow Up date 2", "Follow Up date 2", "follow_up_date_2", "date"),
        ("L", "FOLLOW UP 2 - Details", "FOLLOW UP 2 - Details", "follow_up_2_details", "text"),
        ("M", "FOLLOW UP 3", "FOLLOW UP 3", "follow_up_3", "text"),
        ("N", "FOLLOW UP 4", "FOLLOW UP 4", "follow_up_4", "text"),
    ),
)

HIRING = Template(
    key="hiring",
    form_name="Hiring",
    description=(
        "Candidate form for the Hiring worksheet. "
        "Position and final status use the values present in the source and named by the PRD. "
        "There is no resume column in the source, so no file field is included."
    ),
    project_code="HIRING",
    project_name="Hiring",
    publish=True,
    block_reason="",
    identifier_field="lead_id",
    sheet_name="Hiring",
    idempotency_key="hiring-source-v1",
    fields=(
        _field("lead_id", "Lead ID", "number", required=True, section="Identity", help_text="Source lead identifier. Cells A3:A14 are a shared formula; the cached integers are imported."),
        _field("contact_person", "Contact Person", "text", required=True, section="Identity"),
        _field("position", "Position", "dropdown", required=True, section="Role", options=_POSITION),
        _field("mobile_no", "Mobile No", "mobile", required=False, section="Contact"),
        _field("location", "Location", "text", required=False, section="Contact"),
        _field("lead_source", "Lead Source", "text", required=False, section="Contact", help_text="Original source text. It is not rewritten to the starter picklist."),
        _field("prority", "Prority", "text", required=False, section="Review", help_text="The source header is spelled Prority."),
        _field("call_status", "Call Status", "text", required=False, section="Review", help_text="Original call status, including values outside the starter list."),
        _field("discussion_summary_1", "Discussion Summary - 1", "long_text", required=False, section="Follow-up"),
        _field("followup_comments_2", "Followup Comments - 2", "long_text", required=False, section="Follow-up"),
        _field("followup_comments_3", "Followup Comments - 3", "long_text", required=False, section="Follow-up"),
        _field("final_status", "Final Status", "dropdown", required=False, section="Outcome", options=_FINAL),
        _field("closed_date", "Closed Date", "date", required=False, section="Outcome"),
    ),
    columns=_columns(
        ("A", "Lead ID", "Lead ID", "lead_id", "whole_number"),
        ("B", "Contact Person", "Contact Person", "contact_person", "text"),
        ("C", "Position", "Position", "position", "label"),
        ("D", "Mobile No", "Mobile No", "mobile_no", "mobile"),
        ("E", "Location", "Location", "location", "text"),
        ("F", "Lead Source", "Lead Source", "lead_source", "text"),
        ("G", "Prority", "Prority", "prority", "text"),
        ("H", "Call Status", "Call Status", "call_status", "text"),
        ("I", "Discussion Summary - 1", "Discussion Summary - 1", "discussion_summary_1", "text"),
        ("J", "Followup Comments - 2", "Followup Comments - 2", "followup_comments_2", "text"),
        ("K", "Followup Comments - 3", "Followup Comments - 3", "followup_comments_3", "text"),
        ("L", "Final Status", "Final Status", "final_status", "label"),
        ("M", "Closed Date", "Closed Date", "closed_date", "date"),
    ),
)

PANEERWALA = Template(
    key="paneerwala",
    form_name="Paneerwala",
    description="Not published. The worksheet headers do not describe the values in the same columns.",
    project_code="PANEERWALA",
    project_name="Paneerwala",
    publish=False,
    block_reason=(
        "Paneerwala column A contains enquiry timestamps, column D contains names, and column E contains phone numbers. "
        "The header row calls those columns Lead ID, Date, and Name. "
        "A one-column shift is not applied, because the Warm and Converted headers still do not match the values beneath them, "
        "and the PRD says priority must not be stored as requirement type. No Paneerwala form is published and no row is imported."
    ),
    identifier_field="",
    sheet_name="Paneerwala",
    idempotency_key="",
    fields=(),
    columns=(),
)

TEMPLATES: dict[str, Template] = {
    item.key: item for item in (PRESCHOOL, PANEERWALA, SPACE_VIEW, HIRING)
}
PUBLISHABLE: tuple[Template, ...] = tuple(item for item in TEMPLATES.values() if item.publish)


def browser_catalog() -> list[dict[str, object]]:
    """Field definitions for a browser setup. No source rows are included."""

    catalog = []
    for template in PUBLISHABLE:
        catalog.append(
            {
                "key": template.key,
                "form_name": template.form_name,
                "description": template.description,
                "project_code": template.project_code,
                "project_name": template.project_name,
                "fields": [dict(field) for field in template.fields],
            }
        )
    return catalog


def option_value(template: Template, field_key: str, label: str) -> str | None:
    for field in template.fields:
        if field["field_key"] != field_key:
            continue
        options = field.get("options")
        if not isinstance(options, list):
            return None
        matches = [item["value"] for item in options if item["label"] == label.strip()]
        if len(matches) == 1:
            return str(matches[0])
    return None


def read_workbook(path: Path) -> dict[str, Worksheet]:
    with ZipFile(path) as package:
        shared = _shared_strings(package)
        workbook = ElementTree.fromstring(package.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(package.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib.get("Id"): item.attrib.get("Target", "") for item in relations}
        sheets: dict[str, Worksheet] = {}
        for node in workbook.iter(f"{_MAIN}sheet"):
            name = node.attrib["name"]
            target = targets.get(node.attrib.get(f"{_OFFICE_REL}id"), "")
            sheet_path = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
            sheets[name] = _worksheet(name, ElementTree.fromstring(package.read(sheet_path)), shared)
    return sheets


def prepare_import(template: Template, path: Path = SOURCE_WORKBOOK) -> dict[str, object]:
    """Build one single-sheet CSV and the expected stored values for that template."""

    if not template.publish:
        raise RuntimeError(template.block_reason)
    sheet = read_workbook(path)[template.sheet_name]
    for column in template.columns:
        if sheet.headers.get(column.letter) != column.source_header:
            raise RuntimeError(f"{template.form_name} column {column.letter} does not match the approved header.")
    headers = [column.derived_header for column in template.columns]
    if len(headers) != len(set(headers)):
        raise RuntimeError(f"{template.form_name} derived headers are not unique.")
    body: list[list[str]] = []
    expectations: list[dict[str, object]] = []
    formula_cells = 0
    for number in sheet.data_rows():
        raw_row: list[str] = []
        stored: dict[str, object] = {}
        raw_values: dict[str, str] = {}
        problems: list[str] = []
        for column in template.columns:
            cell = sheet.cells.get((number, column.letter))
            text = "" if cell is None else cell.text
            if cell is not None and cell.formula:
                formula_cells += 1
            written, value, problem = _transform(template, column, text)
            raw_row.append(written)
            raw_values[column.field_key] = text
            if problem:
                problems.append(problem)
            elif value is not None:
                stored[column.field_key] = value
        body.append(raw_row)
        expectations.append(
            {
                "source_row": number,
                "identifier": stored.get(template.identifier_field),
                "raw": raw_values,
                "stored": stored,
                "problems": problems,
                "rejected": bool(problems),
            }
        )
    return {
        "filename": f"{template.key}.csv",
        "content": _write_csv(headers, body),
        "headers": headers,
        "mapping": {column.derived_header: column.field_key for column in template.columns},
        "expectations": expectations,
        "source_data_rows": len(sheet.data_rows()),
        "submitted_rows": len(body),
        "excluded_rows": 0,
        "formula_cells": formula_cells,
        "predicted_rejected": sum(1 for item in expectations if item["rejected"]),
        "predicted_accepted": sum(1 for item in expectations if not item["rejected"]),
    }


def paneerwala_finding(path: Path = SOURCE_WORKBOOK) -> dict[str, object]:
    sheet = read_workbook(path)["Paneerwala"]
    rows = sheet.data_rows()
    stamps = 0
    numeric_ids = 0
    name_column_text = 0
    phone_column_numbers = 0
    order_values = 0
    for number in rows:
        lead = sheet.cells.get((number, "A"))
        text = "" if lead is None else lead.text.strip()
        if _PANEER_STAMP.fullmatch(text):
            stamps += 1
        if _WHOLE.fullmatch(text):
            numeric_ids += 1
        name = sheet.cells.get((number, "D"))
        name_text = "" if name is None else name.text.strip()
        if name_text and name.kind == "s" and _date_text(name_text) is None:
            name_column_text += 1
        phone = sheet.cells.get((number, "E"))
        if phone is not None and phone.kind == "n" and phone.text.strip():
            phone_column_numbers += 1
        for letter in ("S", "T", "U", "V", "W", "X", "Y", "Z"):
            cell = sheet.cells.get((number, letter))
            if cell is not None and cell.text.strip():
                order_values += 1
    folded: dict[str, list[str]] = {}
    blank_headers = []
    for letter, header in sheet.headers.items():
        if not header.strip():
            blank_headers.append(letter)
            continue
        folded.setdefault(header.strip().casefold(), []).append(letter)
    duplicates = {header: letters for header, letters in folded.items() if len(letters) > 1}
    return {
        "publish": False,
        "data_rows": len(rows),
        "blank_data_rows": sheet.max_row - 1 - len(rows),
        "merges": list(sheet.merges),
        "formula_cells": sum(1 for cell in sheet.cells.values() if cell.formula),
        "column_a_timestamps": stamps,
        "column_a_numeric_ids": numeric_ids,
        "column_d_text_not_dates": name_column_text,
        "column_e_numbers": phone_column_numbers,
        "order_column_values": order_values,
        "duplicate_headers": duplicates,
        "blank_headers": blank_headers,
        "reason": PANEERWALA.block_reason,
    }


def sheet_profile(path: Path = SOURCE_WORKBOOK) -> dict[str, dict[str, object]]:
    """Counts and header names only. Cell values are not returned."""

    profiles = {}
    for name, sheet in read_workbook(path).items():
        rows = sheet.data_rows()
        folded: dict[str, int] = {}
        for header in sheet.headers.values():
            key = header.strip().casefold()
            if key:
                folded[key] = folded.get(key, 0) + 1
        profiles[name] = {
            "header_row": 1,
            "data_rows": len(rows),
            "blank_data_rows": max(sheet.max_row - 1 - len(rows), 0),
            "columns": len(sheet.headers),
            "merges": len(sheet.merges),
            "formula_cells": sum(1 for cell in sheet.cells.values() if cell.formula),
            "duplicate_headers": sorted(key for key, count in folded.items() if count > 1),
            "headers": [{"letter": letter, "header": header} for letter, header in sheet.headers.items()],
        }
    return profiles


def _transform(template: Template, column: Column, raw: str) -> tuple[str, object | None, str | None]:
    text = raw.strip()
    if not text:
        field = _field_by_key(template, column.field_key)
        if field.get("required") is True:
            return "", None, f"{column.derived_header} is required."
        return "", None, None
    if column.transform == "whole_number":
        number = _whole_number(text)
        if number is None:
            return text, None, f"{column.derived_header} must be a number."
        return str(number), number, None
    if column.transform == "date":
        iso = _date_text(text)
        if iso is None:
            return text, None, f"{column.derived_header} must use YYYY-MM-DD."
        return iso, iso, None
    if column.transform == "mobile":
        digits = _mobile_text(text)
        if not _MOBILE.fullmatch(digits):
            return digits or text, None, f"{column.derived_header} must contain 8 to 15 digits."
        return digits, digits, None
    if column.transform == "email":
        if not _EMAIL.fullmatch(text) or len(text) > 200:
            return text, None, f"{column.derived_header} must be an email address."
        return text, text.casefold(), None
    if column.transform == "url":
        if len(text) > 500 or not text.startswith(("http://", "https://")):
            return text, None, f"{column.derived_header} must start with http:// or https://."
        return text, text, None
    if column.transform == "label":
        value = option_value(template, column.field_key, text)
        if value is None:
            return text, None, f"{column.derived_header} must use one of the listed options."
        return text, value, None
    return raw, text, None


def _field_by_key(template: Template, key: str) -> dict[str, object]:
    for field in template.fields:
        if field["field_key"] == key:
            return field
    raise KeyError(key)


def _whole_number(text: str) -> int | None:
    if _WHOLE.fullmatch(text):
        return int(text.split(".", 1)[0])
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if number != number.to_integral_value():
        return None
    return int(number)


def _date_text(text: str) -> str | None:
    if _WHOLE.fullmatch(text):
        serial = int(text.split(".", 1)[0])
        if 1 <= serial <= 60000:
            return (_EPOCH + timedelta(days=serial)).date().isoformat()
        return None
    match = _DMY.fullmatch(text)
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def _mobile_text(text: str) -> str:
    if _WHOLE.fullmatch(text) or "e" in text.casefold():
        try:
            number = Decimal(text)
        except InvalidOperation:
            return _MOBILE_SPLIT.sub("", text)
        if number == number.to_integral_value():
            return format(number.to_integral_value(), "f")
    return _MOBILE_SPLIT.sub("", text)


def _write_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _shared_strings(package: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in package.namelist():
        return []
    root = ElementTree.fromstring(package.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(f"{_MAIN}t")) for item in root.findall(f"{_MAIN}si")]


def _worksheet(name: str, root: ElementTree.Element, shared: list[str]) -> Worksheet:
    merges = tuple(node.attrib.get("ref", "") for node in root.iter(f"{_MAIN}mergeCell"))
    cells: dict[tuple[int, str], Cell] = {}
    max_row = 1
    max_column = 1
    for node in root.iter(f"{_MAIN}c"):
        row_number, column = _ref(node.attrib.get("r", ""))
        if row_number is None or column is None:
            continue
        max_row = max(max_row, row_number)
        max_column = max(max_column, column + 1)
        kind = node.attrib.get("t") or "n"
        formula = node.find(f"{_MAIN}f") is not None
        value = node.find(f"{_MAIN}v")
        raw = "" if value is None or value.text is None else value.text
        if kind == "s" and raw:
            text = shared[int(raw)]
        elif kind == "inlineStr":
            text = "".join(item.text or "" for item in node.iter(f"{_MAIN}t"))
        else:
            text = raw
        cells[(row_number, _column_name(column))] = Cell(text=text, kind=kind, formula=formula)
    headers = {}
    for index in range(max_column):
        letter = _column_name(index)
        cell = cells.get((1, letter))
        headers[letter] = "" if cell is None else cell.text
    return Worksheet(name=name, headers=headers, cells=cells, max_row=max_row, merges=merges)


def _ref(value: str) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", value.upper())
    if match is None:
        return None, None
    index = 0
    for character in match.group(1):
        index = index * 26 + (ord(character) - 64)
    return int(match.group(2)), index - 1


def _column_name(index: int) -> str:
    number = index + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
