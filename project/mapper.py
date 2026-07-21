"""
mapper.py
=========
DataFrame-row to :class:`~models.Employee` mapping layer.

After the validation pipeline (:mod:`validator`) produces a clean DataFrame,
the mapper converts each row into a strongly-typed :class:`~models.Employee`
object that can be handed off to any downstream consumer (ORM, REST client,
warehouse writer, etc.).

Functions
---------
- row_to_employee        : Convert a single ``pd.Series`` row → ``Employee``.
- dataframe_to_employees : Batch-convert a clean DataFrame → ``List[Employee]``.
- employees_to_dataframe : Convert a list of ``Employee`` objects → ``pd.DataFrame``.

Design notes
------------
* ``row_to_employee`` is **pure**: it raises :class:`ValueError` on bad data
  rather than returning ``None``, making failures explicit and testable.
* ``dataframe_to_employees`` catches per-row errors, logs them, and continues
  so that one bad row does not abort the entire batch.
* ``employees_to_dataframe`` is used by the pipeline to produce the final
  cleaned CSV output from the mapped ``Employee`` objects.
"""

from __future__ import annotations

import datetime
from typing import List, Optional, Tuple

import pandas as pd

from logger import get_logger
from models import Employee

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_date(value: object) -> datetime.date:
    """Parse *value* into a :class:`datetime.date`, raising on failure.

    Accepts ``datetime.date``, ``datetime.datetime``, ``pandas.Timestamp``,
    and ISO-formatted / common date strings.

    Args:
        value (object): Raw date-like value.

    Returns:
        datetime.date: Parsed date.

    Raises:
        ValueError: When *value* cannot be converted to a valid date.
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
    raise ValueError(f"Cannot parse date from value: {value!r}")


def _str_or_none(value: object) -> Optional[str]:
    """Convert *value* to a stripped string, or ``None`` when missing.

    Args:
        value (object): Any cell value.

    Returns:
        Optional[str]: Stripped non-empty string, or ``None``.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass

    # Pandas often parses numeric columns with missing values as float64.
    # Convert whole-number floats (e.g. 1001.0) to int to avoid '.0' suffixes.
    if isinstance(value, float):
        try:
            if value.is_integer():
                value = int(value)
        except (ValueError, TypeError, OverflowError):
            pass

    stripped = str(value).strip()
    return stripped if stripped else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def row_to_employee(row: pd.Series) -> Employee:  # type: ignore[type-arg]
    """Convert a validated DataFrame *row* into an :class:`Employee` object.

    This function assumes the row has already been validated by
    :func:`~validator.validate_record` and therefore contains all required
    fields in valid formats.  It will still raise :class:`ValueError` if a
    critical conversion fails to surface data-quality issues.

    Args:
        row (pd.Series): A row from the clean DataFrame returned by
            :func:`~validator.validate_dataframe`.

    Returns:
        Employee: A fully populated :class:`Employee` domain object.

    Raises:
        ValueError: If a required field is missing or a type conversion fails.
        KeyError: If an expected column is absent from *row*.

    Example::

        employee = row_to_employee(clean_df.iloc[0])
        print(employee.email)
    """
    # --- Required string fields -------------------------------------------
    employee_id = _str_or_none(row.get("employee_id"))
    if not employee_id:
        raise ValueError("'employee_id' is missing or empty in row.")

    first_name = _str_or_none(row.get("first_name"))
    if not first_name:
        raise ValueError("'first_name' is missing or empty in row.")

    last_name = _str_or_none(row.get("last_name"))
    if not last_name:
        raise ValueError("'last_name' is missing or empty in row.")

    email = _str_or_none(row.get("email"))
    if not email:
        raise ValueError("'email' is missing or empty in row.")

    job_title = _str_or_none(row.get("job_title"))
    if not job_title:
        raise ValueError("'job_title' is missing or empty in row.")

    # --- Optional field ---------------------------------------------------
    phone_number: Optional[str] = _str_or_none(row.get("phone_number"))

    # --- Hire date --------------------------------------------------------
    hire_date: datetime.date = _parse_date(row.get("hire_date"))

    return Employee(
        employee_id=employee_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        job_title=job_title,
        phone_number=phone_number,
        hire_date=hire_date,
    )


def dataframe_to_employees(
    df: pd.DataFrame,
) -> Tuple[List[Employee], List[int]]:
    """Batch-convert a clean DataFrame into a list of :class:`Employee` objects.

    Iterates over every row in *df*, calls :func:`row_to_employee`, and
    collects the results.  Rows that fail conversion are logged and their
    zero-based positional indices are returned in the second element of the
    tuple.

    Args:
        df (pd.DataFrame): A clean DataFrame produced by
            :func:`~validator.validate_dataframe`.

    Returns:
        Tuple[List[Employee], List[int]]:
            * **employees** — successfully converted :class:`Employee` objects.
            * **failed_indices** — positional row indices that could not be
              converted.

    Example::

        employees, failures = dataframe_to_employees(clean_df)
        print(f"Mapped {len(employees)} employees, {len(failures)} failed.")
    """
    log.info("Mapping %d row(s) to Employee objects.", len(df))

    employees: List[Employee] = []
    failed_indices: List[int] = []

    for positional_idx, (df_idx, row) in enumerate(df.iterrows()):
        try:
            employee = row_to_employee(row)  # type: ignore[arg-type]
            employees.append(employee)
            log.debug(
                "Row %s → Employee(id=%s, email=%s)",
                df_idx,
                employee.employee_id,
                employee.email,
            )
        except (ValueError, KeyError) as exc:
            log.error(
                "Failed to map row %s (positional %d): %s",
                df_idx,
                positional_idx,
                exc,
            )
            failed_indices.append(positional_idx)

    log.info(
        "Mapping complete — %d succeeded | %d failed.",
        len(employees),
        len(failed_indices),
    )
    return employees, failed_indices


def employees_to_dataframe(employees: List[Employee]) -> pd.DataFrame:
    """Convert a list of :class:`Employee` objects to a :class:`pd.DataFrame`.

    Produces a clean, consistently ordered DataFrame suitable for saving
    to a CSV file.

    Args:
        employees (List[Employee]): Successfully mapped Employee objects.

    Returns:
        pd.DataFrame: Flat DataFrame representation of the employee list.

    Example::

        df = employees_to_dataframe(employees)
        df.to_csv("cleaned_employees.csv", index=False)
    """
    if not employees:
        log.warning("employees_to_dataframe called with an empty list.")
        return pd.DataFrame(
            columns=[
                "employee_id",
                "first_name",
                "last_name",
                "email",
                "job_title",
                "phone_number",
                "hire_date",
            ]
        )

    records = [
        {
            "employee_id": emp.employee_id,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "email": emp.email,
            "job_title": emp.job_title,
            "phone_number": emp.phone_number,
            "hire_date": emp.hire_date.isoformat(),
        }
        for emp in employees
    ]
    df = pd.DataFrame(records)
    log.info("Converted %d Employee object(s) to DataFrame.", len(df))
    return df
