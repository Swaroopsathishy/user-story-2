"""
tests/conftest.py
=================
Shared pytest fixtures for the employee scraper integration test suite.

Fixtures
--------
- valid_csv_bytes         : Minimal valid CSV bytes representing employee data.
- valid_employee_df       : pandas DataFrame with all required, valid columns.
- df_with_missing_fields  : DataFrame containing rows with missing required fields.
- df_with_duplicates      : DataFrame containing intentional duplicate rows.
- df_missing_columns      : DataFrame that is structurally incomplete (missing columns).
"""

from __future__ import annotations

import io
from typing import Optional
from unittest.mock import MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Shared raw CSV content
# ---------------------------------------------------------------------------

#: Minimal valid CSV content that satisfies all required columns.
VALID_CSV_CONTENT: bytes = (
    b"employee_id,first_name,last_name,email,job_title,phone_number,hire_date\n"
    b"1001,Alice,Smith,alice.smith@example.com,Software Engineer,+1-800-555-0101,2020-01-15\n"
    b"1002,Bob,Jones,bob.jones@example.com,Data Analyst,+1-800-555-0102,2021-06-01\n"
    b"1003,Carol,White,carol.white@example.com,DevOps Engineer,,2019-09-23\n"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_csv_bytes() -> bytes:
    """Return raw CSV bytes with valid employee records.

    Returns:
        bytes: UTF-8 encoded CSV payload.
    """
    return VALID_CSV_CONTENT


@pytest.fixture
def valid_employee_df() -> pd.DataFrame:
    """Return a pandas DataFrame with three valid, well-formed employee rows.

    Returns:
        pd.DataFrame: Clean employee data suitable for validation testing.
    """
    return pd.read_csv(io.BytesIO(VALID_CSV_CONTENT))


@pytest.fixture
def df_with_missing_fields() -> pd.DataFrame:
    """Return a DataFrame with deliberately missing required field values.

    The second row has a blank email and the third row is missing a hire_date.

    Returns:
        pd.DataFrame: DataFrame with structural gaps in required columns.
    """
    return pd.DataFrame(
        {
            "employee_id": [2001, 2002, 2003],
            "first_name": ["Dave", "Eve", "Frank"],
            "last_name": ["Brown", "Davis", "Evans"],
            "email": ["dave.brown@example.com", "", "frank.evans@example.com"],
            "job_title": ["QA Engineer", "Project Manager", "UX Designer"],
            "phone_number": [None, None, None],
            "hire_date": ["2022-03-10", "2023-07-20", None],
        }
    )


@pytest.fixture
def df_with_duplicates() -> pd.DataFrame:
    """Return a DataFrame with two exact duplicate rows.

    Returns:
        pd.DataFrame: DataFrame containing a fully duplicated row.
    """
    base_row = {
        "employee_id": 3001,
        "first_name": "Grace",
        "last_name": "Hall",
        "email": "grace.hall@example.com",
        "job_title": "HR Manager",
        "phone_number": "+1-800-555-9999",
        "hire_date": "2018-11-05",
    }
    return pd.DataFrame([base_row, base_row, {
        "employee_id": 3002,
        "first_name": "Hank",
        "last_name": "Irving",
        "email": "hank.irving@example.com",
        "job_title": "Finance Analyst",
        "phone_number": None,
        "hire_date": "2021-02-28",
    }])


@pytest.fixture
def df_missing_columns() -> pd.DataFrame:
    """Return a DataFrame that is structurally incomplete.

    Missing the ``email`` and ``hire_date`` columns entirely.

    Returns:
        pd.DataFrame: DataFrame lacking required columns.
    """
    return pd.DataFrame(
        {
            "employee_id": [4001],
            "first_name": ["Iris"],
            "last_name": ["Johnson"],
            "job_title": ["Marketing Lead"],
            "phone_number": [None],
        }
    )
