"""CSV and XLSX reading and writing.

XLSX formula cells are rejected. Their expressions are not evaluated. CSV text
is stored as data. Export prefixes values that a spreadsheet could treat as a
formula.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from xml.etree import ElementTree

MAX_BYTES = 1_048_576
MAX_ROWS = 500
MAX_COLUMNS = 40
MAX_CELL = 5000
_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_OFFICE_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class SpreadsheetError(Exception):
    """The file cannot be imported as uploaded."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def read_table(filename: str, content: bytes) -> tuple[list[str], list[tuple[int, dict[str, str], list[str]]]]:
    """Return headers and data rows.

    Each data row is the spreadsheet row number, a header-to-text map, and
    cell errors. The header row is not a data row. Rows past the limit are
    rejected rather than dropped.
    """

    if len(content) > MAX_BYTES:
        raise SpreadsheetError("The file is larger than 1 MB.")
    if not content:
        raise SpreadsheetError("The file is empty.")
    extension = _extension(filename)
    if extension == ".xlsx":
        if not content.startswith(b"PK"):
            raise SpreadsheetError("This .xlsx file is not a workbook.")
        headers, grid, problems = _read_xlsx(content)
    elif extension == ".csv":
        if content.startswith(b"PK"):
            raise SpreadsheetError("This .csv file is a workbook. Upload it as .xlsx or export CSV text.")
        headers, grid, problems = _read_csv(content)
    else:
        raise SpreadsheetError("Upload a .csv or .xlsx file.")
    if not headers:
        raise SpreadsheetError("The file needs a header row.")
    if len(headers) > MAX_COLUMNS:
        raise SpreadsheetError(f"The file has more than {MAX_COLUMNS} columns.")
    cleaned = [_header(item) for item in headers]
    if any(not item for item in cleaned):
        raise SpreadsheetError("A header cell is blank.")
    if len(set(cleaned)) != len(cleaned):
        raise SpreadsheetError("A header name is repeated.")
    if len(grid) > MAX_ROWS:
        raise SpreadsheetError(f"The file has more than {MAX_ROWS} data rows. Split it and import each part.")
    if not grid:
        raise SpreadsheetError("The file has no data rows.")
    rows: list[tuple[int, dict[str, str], list[str]]] = []
    for offset, cells in enumerate(grid):
        number = offset + 2
        if len(cells) > len(cleaned):
            raise SpreadsheetError(f"Row {number} has more values than headers.")
        padded = list(cells) + [""] * (len(cleaned) - len(cells))
        values = {cleaned[index]: padded[index] for index in range(len(cleaned))}
        if all(not value.strip() for value in values.values()):
            problems.setdefault(number, []).append("This row is empty.")
        rows.append((number, values, problems.get(number, [])))
    return cleaned, rows


def write_csv(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([neutralize(item) for item in headers])
    for row in rows:
        writer.writerow([neutralize(item) for item in row])
    return buffer.getvalue().encode("utf-8-sig")


def write_xlsx(headers: list[str], rows: list[list[str]]) -> bytes:
    sheet = _sheet_xml([neutralize(item) for item in headers], [[neutralize(item) for item in row] for row in rows])
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        package.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        package.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Records" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        package.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        package.writestr("xl/worksheets/sheet1.xml", sheet)
    return payload.getvalue()


def neutralize(value: object) -> str:
    """Keep a cell as text when a spreadsheet would otherwise evaluate it."""

    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _extension(filename: str) -> str:
    lowered = filename.strip().lower()
    if lowered.endswith(".xlsx"):
        return ".xlsx"
    if lowered.endswith(".csv"):
        return ".csv"
    return ""


def _header(value: str) -> str:
    return value.strip()


def _read_csv(content: bytes) -> tuple[list[str], list[list[str]], dict[int, list[str]]]:
    if b"\x00" in content:
        raise SpreadsheetError("This CSV file is not text.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SpreadsheetError("This CSV file must be UTF-8 text.") from exc
    sample = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    grid = [list(row) for row in reader]
    while grid and not any(cell.strip() for cell in grid[-1]):
        grid.pop()
    if not grid:
        raise SpreadsheetError("The file is empty.")
    headers = [_limit_cell(cell, 1, index) for index, cell in enumerate(grid[0], start=1)]
    data: list[list[str]] = []
    for row_number, row in enumerate(grid[1:], start=2):
        data.append([_limit_cell(cell, row_number, index) for index, cell in enumerate(row, start=1)])
    return headers, data, {}


def _limit_cell(value: str, row_number: int, column: int) -> str:
    if len(value) > MAX_CELL:
        raise SpreadsheetError(f"Row {row_number} column {column} is longer than {MAX_CELL} characters.")
    return value


def _read_xlsx(content: bytes) -> tuple[list[str], list[list[str]], dict[int, list[str]]]:
    try:
        package = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise SpreadsheetError("This .xlsx file is not a workbook.") from exc
    names = set(package.namelist())
    if any(name.endswith("vbaProject.bin") for name in names) or "EncryptionInfo" in names:
        raise SpreadsheetError("Macro and encrypted workbooks are not imported.")
    shared = _shared_strings(package, names)
    sheet_name = _first_sheet(package, names)
    try:
        root = ElementTree.fromstring(package.read(sheet_name))
    except ElementTree.ParseError as exc:
        raise SpreadsheetError("This workbook sheet could not be read.") from exc
    by_row: dict[int, dict[int, tuple[str, bool]]] = {}
    for cell in root.iter(f"{_MAIN}c"):
        ref = cell.attrib.get("r", "")
        row_number, column = _ref(ref)
        if row_number is None or column is None:
            continue
        formula = cell.find(f"{_MAIN}f") is not None
        by_row.setdefault(row_number, {})[column] = (_cell_text(cell, shared), formula)
    if not by_row:
        raise SpreadsheetError("The file has no data rows.")
    ordered = sorted(by_row)
    width = max(max(columns) for columns in by_row.values()) + 1
    if width > MAX_COLUMNS:
        raise SpreadsheetError(f"The file has more than {MAX_COLUMNS} columns.")
    header_index = ordered[0]
    headers: list[str] = []
    problems: dict[int, list[str]] = {}
    for column in range(width):
        text, formula = by_row[header_index].get(column, ("", False))
        if formula:
            raise SpreadsheetError("A header cell contains a formula. Replace it with the column name.")
        headers.append(_limit_cell(text, header_index, column + 1))
    grid: list[list[str]] = []
    for row_number in ordered[1:]:
        cells: list[str] = []
        for column in range(width):
            text, formula = by_row[row_number].get(column, ("", False))
            if formula:
                problems.setdefault(row_number, []).append(
                    f"Column {headers[column] or column + 1} contains a formula. Paste the value and upload the file again."
                )
                cells.append("")
            else:
                cells.append(_limit_cell(text, row_number, column + 1))
        grid.append(cells)
    return headers, grid, problems


def _shared_strings(package: zipfile.ZipFile, names: set[str]) -> list[str]:
    if "xl/sharedStrings.xml" not in names:
        return []
    try:
        root = ElementTree.fromstring(package.read("xl/sharedStrings.xml"))
    except ElementTree.ParseError as exc:
        raise SpreadsheetError("This workbook could not be read.") from exc
    values: list[str] = []
    for item in root.findall(f"{_MAIN}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{_MAIN}t")))
    return values


def _first_sheet(package: zipfile.ZipFile, names: set[str]) -> str:
    if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
        raise SpreadsheetError("This .xlsx file is not a workbook.")
    try:
        workbook = ElementTree.fromstring(package.read("xl/workbook.xml"))
        relations = ElementTree.fromstring(package.read("xl/_rels/workbook.xml.rels"))
    except ElementTree.ParseError as exc:
        raise SpreadsheetError("This workbook could not be read.") from exc
    sheets = list(workbook.iter(f"{_MAIN}sheet"))
    if len(sheets) != 1:
        raise SpreadsheetError("The workbook must contain one worksheet. Extra sheets were not imported.")
    relation_id = sheets[0].attrib.get(f"{_OFFICE_REL}id")
    target = ""
    for relation in relations:
        if relation.attrib.get("Id") == relation_id:
            target = relation.attrib.get("Target", "")
    if not target:
        raise SpreadsheetError("This workbook sheet could not be read.")
    path = target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
    if path not in names:
        raise SpreadsheetError("This workbook sheet could not be read.")
    return path


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{_MAIN}t"))
    node = cell.find(f"{_MAIN}v")
    raw = "" if node is None or node.text is None else node.text
    if kind == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError) as exc:
            raise SpreadsheetError("This workbook contains an unreadable text cell.") from exc
    if kind == "b":
        return "true" if raw == "1" else "false"
    if kind == "e":
        return ""
    return raw


def _ref(value: str) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", value.upper())
    if match is None:
        return None, None
    index = 0
    for character in match.group(1):
        index = index * 26 + (ord(character) - 64)
    return int(match.group(2)), index - 1


def _sheet_xml(headers: list[str], rows: list[list[str]]) -> str:
    body = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", f"<worksheet xmlns=\"{_MAIN[1:-1]}\"><sheetData>"]
    body.append(_row_xml(1, headers))
    for offset, row in enumerate(rows, start=2):
        body.append(_row_xml(offset, row))
    body.append("</sheetData></worksheet>")
    return "".join(body)


def _row_xml(number: int, values: list[str]) -> str:
    cells = []
    for index, value in enumerate(values):
        letter = _column_name(index)
        escaped = (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        cells.append(f'<c r="{letter}{number}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>')
    return f"<row r=\"{number}\">{''.join(cells)}</row>"


def _column_name(index: int) -> str:
    number = index + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
