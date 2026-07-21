"""
validator.py
============
Employee DataFrame validation pipeline (Module 2 responsibility).

This module validates a ``pandas.DataFrame`` produced by the parser and
returns two DataFrames: one containing only clean, warehouse-ready rows and
one containing every row that failed validation together with the reasons
for failure.

High-level pipeline
-------------------
1. :func:`validate_columns`   — structural check (all required columns present)
2. :func:`strip_whitespace`   — strip leading/trailing whitespace from strings
3. :func:`remove_duplicates`  — drop duplicate rows, log count
4. :func:`validate_record`    — per-row rule engine (null checks, regex, etc.)
5. :func:`validate_dataframe` — orchestrates the above, returns ``(clean, invalid)``

Validation rules
----------------
* **Employee ID**   : Required, non-empty, must be a positive integer string.
* **First Name**    : Required, non-empty after whitespace strip.
* **Last Name**     : Required, non-empty after whitespace strip.
* **Email**         : Required, must match a standard e-mail pattern.
* **Job Title**     : Required, non-empty after whitespace strip.
* **Phone Number**  : Optional. When present, must match a valid phone pattern.
* **Hire Date**     : Required, must be parseable as a calendar date.

Constants
---------
REQUIRED_COLUMNS : list[str]
    Canonical column names that **must** be present in the incoming DataFrame.
"""

from __future__ import annotations

import datetime
import re
from typing import Dict, List, Tuple

import pandas as pd

from logger import get_logger
from models import EmployeeValidationResult

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical column names required by the user story.
REQUIRED_COLUMNS: List[str] = [
    "employee_id",
    "first_name",
    "last_name",
    "email",
    "job_title",
    "phone_number",
    "hire_date",
]

# Compiled regex patterns — compiled once at import time for performance.

#: RFC-5321-like e-mail pattern.
_EMAIL_RE: re.Pattern[str] = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$",
    re.IGNORECASE,
)

#: Accepts the most common phone number formats:
#:   +1-800-555-0100   (international with dashes)
#:   +18005550100      (international compact)
#:   (800) 555-0100    (US local with parens)
#:   800-555-0100      (dashes only)
#:   800.555.0100      (dots as separators)
#:   8005550100        (digit-only, 7–20 chars)
_PHONE_RE: re.Pattern[str] = re.compile(
    r"^\+?[\d\s\-\.\(\)]{7,20}$"
)

#: Configurable column mapping for common variations.
COLUMN_MAPPING: Dict[str, str] = {
    "index": "employee_id",
    "user_id": "employee_id",
    "id": "employee_id",
    "emp_id": "employee_id",
    "employeeid": "employee_id",
    "first_name": "first_name",
    "first": "first_name",
    "last_name": "last_name",
    "last": "last_name",
    "email": "email",
    "email_address": "email",
    "phone": "phone_number",
    "phone_number": "phone_number",
    "telephone": "phone_number",
    "cell": "phone_number",
    "job_title": "job_title",
    "title": "job_title",
    "role": "job_title",
    "date_of_birth": "hire_date",
    "birth_date": "hire_date",
    "hire_date": "hire_date",
    "hired": "hire_date",
    "hired_date": "hire_date",
}


def normalize_column_name(name: object) -> str:
    """Normalize a single column name:
    - strips leading/trailing spaces
    - converts to lowercase
    - replaces spaces, hyphens, and dots with underscores
    - removes duplicate underscores
    """
    name_str = str(name).strip()
    name_str = name_str.lower()
    name_str = re.sub(r'[\s\-\.]', '_', name_str)
    name_str = re.sub(r'_+', '_', name_str)
    name_str = name_str.strip('_')
    return name_str


def normalize_and_map_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and map DataFrame column names.

    1. Inspects the parsed DataFrame.
    2. Automatically normalizes column names.
    3. Maps common header variations using COLUMN_MAPPING.
    4. Preserves extra columns.
    5. Adds logging.
    """
    df = df.copy()
    original_cols = df.columns.tolist()

    # 1. Normalize
    normalized_cols = [normalize_column_name(col) for col in original_cols]

    # 2. Map using COLUMN_MAPPING, avoiding duplicate targets.
    # We prioritize columns that already match internal schema names exactly (after normalization)
    rename_dict = {}
    mapped_targets = set()

    # First pass: direct matches
    for col in original_cols:
        norm = normalize_column_name(col)
        if norm in REQUIRED_COLUMNS:
            rename_dict[col] = norm
            mapped_targets.add(norm)

    # Second pass: mapping using COLUMN_MAPPING
    for col in original_cols:
        if col in rename_dict:
            continue
        norm = normalize_column_name(col)
        mapped = COLUMN_MAPPING.get(norm, norm)
        if mapped in REQUIRED_COLUMNS:
            if mapped not in mapped_targets:
                rename_dict[col] = mapped
                mapped_targets.add(mapped)
            else:
                # Target is already mapped, preserve as normalized
                rename_dict[col] = norm
        else:
            # Preserve as normalized
            rename_dict[col] = norm

    # Log the columns before, during, and after
    df = df.rename(columns=rename_dict)
    final_cols = df.columns.tolist()

    log.info("Original column names: %s", original_cols)
    log.info("Normalized column names: %s", normalized_cols)
    log.info("Final mapped column names: %s", final_cols)

    return df


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_missing(value: object) -> bool:
    """Return ``True`` when *value* represents a missing / empty cell.

    Args:
        value (object): The raw cell value from a DataFrame row.

    Returns:
        bool: ``True`` if the value is ``None``, ``NaN``, ``pd.NA``, or an
            empty string after whitespace stripping.
    """
    if value is None:
        return True
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _parse_date(value: object) -> datetime.date | None:
    """Attempt to parse *value* as a :class:`datetime.date`.

    Args:
        value (object): Raw cell value — may be a string, ``datetime.date``,
            ``datetime.datetime``, or a ``pandas.Timestamp``.

    Returns:
        Optional[datetime.date]: Parsed date, or ``None`` on failure.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, str):
        for fmt in (
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%m-%d-%Y",
        ):
            try:
                return datetime.datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strip leading and trailing whitespace from all string columns.

    Operates on a *copy* of *df* to avoid mutating the caller's DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame from the parser.

    Returns:
        pd.DataFrame: A copy of *df* with string cells stripped.
    """
    df = df.copy()
    str_cols = df.select_dtypes(include=["object", "string"]).columns
    for col in str_cols:
        df[col] = df[col].apply(
            lambda v: v.strip() if isinstance(v, str) else v
        )
    return df


def validate_columns(df: pd.DataFrame) -> List[str]:
    """Verify that *df* contains every column listed in :data:`REQUIRED_COLUMNS`.

    Comparison is **case-insensitive** and ignores surrounding whitespace so
    that minor formatting differences in the source file do not cause false
    failures.

    Args:
        df (pd.DataFrame): DataFrame to inspect.

    Returns:
        List[str]: Names of required columns that are **missing** from *df*.
            An empty list means all required columns are present.

    Raises:
        TypeError: If *df* is not a :class:`pandas.DataFrame`.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(
            f"Expected a pandas DataFrame, got {type(df).__name__}."
        )

    normalised_cols = {c.strip().lower() for c in df.columns}
    missing = [
        col for col in REQUIRED_COLUMNS if col.lower() not in normalised_cols
    ]

    if missing:
        log.warning("Missing required columns: %s", missing)
    else:
        log.debug("All required columns are present.")

    return missing


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Remove fully duplicate rows from *df* and log the count removed.

    A row is considered a duplicate when **all** column values are identical
    to another row.  The first occurrence is kept; subsequent duplicates are
    dropped.

    Args:
        df (pd.DataFrame): Input DataFrame.

    Returns:
        pd.DataFrame: De-duplicated copy of *df* with reset index.
    """
    original_count = len(df)
    df_dedup = df.drop_duplicates(keep="first").reset_index(drop=True)
    removed = original_count - len(df_dedup)

    if removed > 0:
        log.warning("Removed %d duplicate row(s) from the dataset.", removed)
    else:
        log.debug("No duplicate rows found.")

    return df_dedup, removed


def validate_record(
    row: pd.Series,  # type: ignore[type-arg]
    row_index: int,
) -> EmployeeValidationResult:
    """Validate a single DataFrame row against all business rules.

    Rules applied (in order):
    1. Strip whitespace (non-mutating; uses local copies for checks).
    2. Required fields are non-null and non-empty.
    3. ``employee_id`` is a positive integer.
    4. ``email`` matches :data:`_EMAIL_RE`.
    5. ``phone_number``, when present, matches :data:`_PHONE_RE`.
    6. ``hire_date`` is parseable as a calendar date.

    Args:
        row (pd.Series): A single row from the validated DataFrame.
        row_index (int): Zero-based positional index used in error reporting.

    Returns:
        EmployeeValidationResult: Validation outcome for the row.
    """
    errors: List[str] = []

    def _get(col: str) -> object:
        """Return stripped string value, or the original if not a str."""
        val = row.get(col)  # type: ignore[attr-defined]
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, float):
            try:
                if val.is_integer():
                    return str(int(val))
            except (ValueError, TypeError, OverflowError):
                pass
        return val

    # ------------------------------------------------------------------ #
    # 1. Required non-null / non-empty fields
    # ------------------------------------------------------------------ #
    required_fields = [
        "employee_id",
        "first_name",
        "last_name",
        "email",
        "job_title",
        "hire_date",
    ]
    for field_name in required_fields:
        if _is_missing(_get(field_name)):
            errors.append(
                f"'{field_name}' is required but missing or empty."
            )

    # ------------------------------------------------------------------ #
    # 2. Employee ID — must be a positive integer
    # ------------------------------------------------------------------ #
    emp_id = _get("employee_id")
    if not _is_missing(emp_id):
        try:
            if int(str(emp_id).strip()) <= 0:
                errors.append(
                    f"'employee_id' must be a positive integer, got: {emp_id!r}."
                )
        except (ValueError, TypeError):
            errors.append(
                f"'employee_id' must be a positive integer, got: {emp_id!r}."
            )

    # ------------------------------------------------------------------ #
    # 3. Email format
    # ------------------------------------------------------------------ #
    email = _get("email")
    if not _is_missing(email) and not _EMAIL_RE.match(str(email)):
        errors.append(f"'email' is invalid: {email!r}.")

    # ------------------------------------------------------------------ #
    # 4. Phone number format (optional field)
    # ------------------------------------------------------------------ #
    phone = _get("phone_number")
    if not _is_missing(phone) and not _PHONE_RE.match(str(phone)):
        errors.append(f"'phone_number' is invalid: {phone!r}.")

    # ------------------------------------------------------------------ #
    # 5. Hire date parseable
    # ------------------------------------------------------------------ #
    raw_hire_date = _get("hire_date")
    if not _is_missing(raw_hire_date) and _parse_date(raw_hire_date) is None:
        errors.append(
            f"'hire_date' is not a valid date: {raw_hire_date!r}."
        )

    is_valid = len(errors) == 0
    if not is_valid:
        log.debug(
            "Row %d failed validation with %d error(s): %s",
            row_index,
            len(errors),
            errors,
        )

    return EmployeeValidationResult(
        row_index=row_index,
        is_valid=is_valid,
        errors=errors,
    )


def validate_dataframe(
    df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, int]:
    """Run the full validation pipeline on *df*.

    Pipeline steps:
    1. Column presence check (:func:`validate_columns`).
    2. Whitespace stripping (:func:`strip_whitespace`).
    3. Duplicate removal (:func:`remove_duplicates`).
    4. Per-row validation (:func:`validate_record`).
    5. Summary logging.

    Args:
        df (pd.DataFrame): Raw DataFrame from the parser.

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame, int]:
            * **clean_df** — rows that passed all validation rules.
            * **invalid_df** — rows that failed one or more rules, with a
              ``_validation_errors`` column listing the failure reasons.
            * **duplicates_removed** — number of duplicate rows removed.

    Raises:
        TypeError: If *df* is not a :class:`pandas.DataFrame`.
        ValueError: If required columns are missing.
    """
    log.info("Starting DataFrame validation — %d row(s) received.", len(df))

    # Inspect the parsed DataFrame and automatically normalize column names before validation.
    df = normalize_and_map_df_columns(df)

    # ---- Step 1: structural column check --------------------------------
    missing_cols = validate_columns(df)
    if missing_cols:
        raise ValueError(
            f"DataFrame is missing required column(s): {missing_cols}. "
            "Validation cannot continue."
        )

    # ---- Step 2: whitespace strip ---------------------------------------
    df = strip_whitespace(df)

    # ---- Step 3: duplicate removal -------------------------------------
    df, duplicates_removed = remove_duplicates(df)

    # ---- Step 4: per-row validation ------------------------------------
    valid_indices: List[int] = []
    invalid_indices: List[int] = []
    errors_map: Dict[int, List[str]] = {}

    for idx, row in df.iterrows():
        result = validate_record(row, row_index=int(idx))  # type: ignore[arg-type]
        if result.is_valid:
            valid_indices.append(int(idx))
        else:
            invalid_indices.append(int(idx))
            errors_map[int(idx)] = result.errors
            log.warning(
                "Row %d is invalid: %s", idx, "; ".join(result.errors)
            )

    # ---- Step 5: build output DataFrames --------------------------------
    clean_df = df.loc[valid_indices].copy()
    clean_df.loc[:, "_validation_errors"] = [[] for _ in range(len(clean_df))]

    invalid_df = df.loc[invalid_indices].copy()
    invalid_df.loc[:, "_validation_errors"] = [
        errors_map[i] for i in invalid_indices
    ]

    # ---- Step 6: summary log -------------------------------------------
    log.info(
        "Validation complete — %d valid | %d invalid | %d duplicate(s) removed | %d total.",
        len(clean_df),
        len(invalid_df),
        duplicates_removed,
        len(clean_df) + len(invalid_df),
    )

    return (
        clean_df.reset_index(drop=True),
        invalid_df.reset_index(drop=True),
        duplicates_removed,
    )
