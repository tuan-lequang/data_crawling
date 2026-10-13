"""CSV and Excel exports with round-trip verification and optional field selection."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from config import (
    BOOL_COLUMNS, CSV_ENCODING, EXPORT_DIR, FILENAME_PREFIX, FILENAME_TIME_FORMAT,
    ID_COLUMNS, PRICE_COLUMNS, STANDARD_COLUMNS, TEXT_COLUMNS,
)
from utils.validators import validate_selected_columns

UTF8_BOM = b"\xef\xbb\xbf"
EXCEL_SHEET_NAME = "Products"


def _timestamp(now: Optional[datetime] = None) -> str:
    return (now or datetime.now()).strftime(FILENAME_TIME_FORMAT)


def make_filename(now: Optional[datetime] = None) -> str:
    return f"{FILENAME_PREFIX}_{_timestamp(now)}.csv"


def make_excel_filename(now: Optional[datetime] = None) -> str:
    return f"{FILENAME_PREFIX}_{_timestamp(now)}.xlsx"


def _selected_columns(columns: Sequence[str] | None = None) -> list[str]:
    return list(STANDARD_COLUMNS) if columns is None else validate_selected_columns(columns, STANDARD_COLUMNS, "product output")


def _export_frame(df: pd.DataFrame, columns: Sequence[str] | None = None) -> pd.DataFrame:
    """Return selected columns without mutating the 20-column internal DataFrame."""
    selected = _selected_columns(columns)
    export_df = df.reindex(columns=selected).copy()
    for column in ID_COLUMNS:
        if column in export_df.columns:
            export_df[column] = export_df[column].astype("string").fillna("")
    return export_df


def dataframe_to_csv_bytes(df: pd.DataFrame, columns: Sequence[str] | None = None) -> bytes:
    text = _export_frame(df, columns).to_csv(index=False, float_format="%g")
    return text.encode(CSV_ENCODING)


def dataframe_to_excel_bytes(df: pd.DataFrame, columns: Sequence[str] | None = None) -> bytes:
    """Create an Excel workbook with selected fields and stable string IDs."""
    export_df = _export_frame(df, columns)
    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = EXCEL_SHEET_NAME
    headers = list(export_df.columns)
    for index, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=index, value=header)
        cell.font = Font(bold=True)
        cell.data_type = "s"
    ws.freeze_panes = "A2"
    if headers:
        ws.auto_filter.ref = ws.dimensions
    header_to_index = {header: i + 1 for i, header in enumerate(headers)}
    for row_index, record in enumerate(export_df.itertuples(index=False, name=None), start=2):
        for col_index, (column, value) in enumerate(zip(headers, record), start=1):
            if pd.isna(value):
                value = None
            cell = ws.cell(row=row_index, column=col_index, value=value)
            if column in ID_COLUMNS:
                cell.number_format = "@"
                if value is not None:
                    cell.value = str(value)
                    cell.data_type = "s"
            elif column in TEXT_COLUMNS and value is not None:
                cell.value = str(value)
                cell.data_type = "s"
            elif column in PRICE_COLUMNS and value is not None:
                cell.number_format = "#,##0"
            elif column == "discount_pct" and value is not None:
                cell.number_format = "0.##"
            elif column == "rating" and value is not None:
                cell.number_format = "0.##"
    for column_cells in ws.columns:
        letter = column_cells[0].column_letter
        max_len = max((len(str(cell.value)) if cell.value is not None else 0) for cell in column_cells[:51])
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 45)
    wb.save(output)
    return output.getvalue()


def verify_csv_bytes(data: bytes, df: pd.DataFrame, columns: Sequence[str] | None = None) -> tuple[bool, str]:
    selected = _selected_columns(columns)
    expected = _export_frame(df, selected)
    if not data.startswith(UTF8_BOM):
        return False, "CSV does not start with a UTF-8 BOM (utf-8-sig)."
    try:
        back = pd.read_csv(io.BytesIO(data), encoding=CSV_ENCODING, dtype=str, keep_default_na=False)
    except Exception:
        return False, "CSV could not be read back."
    if list(back.columns) != selected:
        return False, "CSV columns differ from the selected schema."
    if len(back) != len(expected):
        return False, "CSV row count differs from the DataFrame."
    for column in TEXT_COLUMNS:
        if column not in selected:
            continue
        original = expected[column].astype("string").fillna("").tolist()
        if back[column].tolist() != original:
            return False, f"Text changed during CSV export in column '{column}'."
    for column in ID_COLUMNS:
        if column not in selected:
            continue
        original = expected[column].astype("string").fillna("").tolist()
        if back[column].tolist() != original:
            return False, f"ID values changed during CSV export in column '{column}'."
    return True, f"CSV verified: {len(back)} rows, {len(back.columns)} selected columns, UTF-8-SIG; text fields preserved."


def verify_excel_bytes(data: bytes, df: pd.DataFrame, columns: Sequence[str] | None = None) -> tuple[bool, str]:
    selected = _selected_columns(columns)
    expected = _export_frame(df, selected)
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        if EXCEL_SHEET_NAME not in wb.sheetnames:
            return False, f"Excel sheet '{EXCEL_SHEET_NAME}' is missing."
        ws = wb[EXCEL_SHEET_NAME]
        rows = list(ws.iter_rows(values_only=True))
    except Exception:
        return False, "Excel file could not be read back."
    if not rows:
        return False, "Excel file is empty."
    headers = list(rows[0])
    if headers != selected:
        return False, "Excel columns differ from the selected schema."
    if len(rows) - 1 != len(expected):
        return False, "Excel row count differs from the DataFrame."
    for column in set(TEXT_COLUMNS + ID_COLUMNS):
        if column not in selected:
            continue
        idx = headers.index(column)
        original = expected[column].astype("string").fillna("").tolist()
        actual = ["" if row[idx] is None else str(row[idx]) for row in rows[1:]]
        if actual != original:
            return False, f"Text or ID values changed during Excel export in column '{column}'."
    return True, f"Excel verified: {len(rows) - 1} rows, {len(headers)} selected columns."


def export_csv(df: pd.DataFrame, directory: Path | None = None,
               now: Optional[datetime] = None, columns: Sequence[str] | None = None) -> Path:
    directory = Path(directory or EXPORT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / make_filename(now)
    data = dataframe_to_csv_bytes(df, columns)
    path.write_bytes(data)
    ok, message = verify_csv_bytes(path.read_bytes(), df, columns)
    if not ok:
        raise ValueError(message)
    return path


def export_excel(df: pd.DataFrame, directory: Path | None = None,
                 now: Optional[datetime] = None, columns: Sequence[str] | None = None) -> Path:
    directory = Path(directory or EXPORT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / make_excel_filename(now)
    data = dataframe_to_excel_bytes(df, columns)
    path.write_bytes(data)
    ok, message = verify_excel_bytes(path.read_bytes(), df, columns)
    if not ok:
        raise ValueError(message)
    return path
