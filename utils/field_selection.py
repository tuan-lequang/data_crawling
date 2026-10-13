"""Pure helpers for selectable product and review output fields."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd


def normalize_selected_columns(selected: Iterable[str], allowed: Sequence[str]) -> list[str]:
    """Return valid, unique selections in canonical order."""
    selected_set = set(selected or [])
    return [column for column in allowed if column in selected_set]


def validate_field_selection(selected: Iterable[str], allowed: Sequence[str], label: str = "output") -> list[str]:
    """Validate an output-field selection and return it in canonical order."""
    if selected is None or isinstance(selected, (str, bytes)):
        raise ValueError(f"Please select at least one {label} field.")
    selected_list = list(selected)
    if not selected_list:
        raise ValueError(f"Please select at least one {label} field.")
    invalid = [column for column in selected_list if column not in allowed]
    if invalid:
        raise ValueError(f"The selected {label} fields contain an unsupported column.")
    normalized = normalize_selected_columns(selected_list, allowed)
    if not normalized:
        raise ValueError(f"Please select at least one {label} field.")
    return normalized


def select_columns(df: pd.DataFrame, selected: Iterable[str], allowed: Sequence[str] | None = None) -> pd.DataFrame:
    """Select output columns without modifying the internal source DataFrame."""
    canonical = list(allowed if allowed is not None else df.columns)
    columns = validate_field_selection(selected, canonical)
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError("The source dataset is missing one or more selected fields.")
    return df.loc[:, columns].copy()


def selection_matches(selected: Iterable[str], expected: Iterable[str]) -> bool:
    """Compare field selections without depending on checkbox ordering."""
    return set(selected or []) == set(expected or [])
