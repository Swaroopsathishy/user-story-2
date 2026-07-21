"""
models.py
=========
Domain models for the employee scraper pipeline.

This module defines the core data structures used across the validation
and mapping layers.  All models use Python ``dataclasses`` for
zero-boilerplate attribute definitions, ``typing`` for full type safety,
and ``datetime`` for strongly-typed date handling.

Classes
-------
- Employee                  : Canonical representation of one employee record.
- EmployeeValidationResult  : Per-row outcome produced by the validator.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------


@dataclass
class Employee:
    """Canonical representation of one employee record.

    All string fields are normalised (whitespace-stripped) on construction
    via :meth:`__post_init__`.

    Attributes:
        employee_id (str): Unique identifier for the employee.  Must be a
            non-empty string that can be parsed as a positive integer.
        first_name (str): Employee's given name (whitespace-stripped).
        last_name (str): Employee's family name (whitespace-stripped).
        email (str): Valid RFC-5321-like e-mail address.
        job_title (str): The employee's current job title.
        phone_number (Optional[str]): Contact phone number.  ``None`` when
            the source record contains no phone information.
        hire_date (datetime.date): Date on which the employee was hired.

    Example::

        emp = Employee(
            employee_id="1001",
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.com",
            job_title="Software Engineer",
            phone_number="+1-800-555-0100",
            hire_date=datetime.date(2021, 3, 15),
        )
    """

    employee_id: str
    first_name: str
    last_name: str
    email: str
    job_title: str
    phone_number: Optional[str]
    hire_date: datetime.date

    def __post_init__(self) -> None:
        """Normalise string fields immediately after construction.

        Strips leading / trailing whitespace from every ``str`` attribute so
        that :class:`Employee` objects are always in a clean, canonical state
        regardless of their origin.  A phone number that becomes empty after
        stripping is set to ``None``.
        """
        self.employee_id = self.employee_id.strip()
        self.first_name = self.first_name.strip()
        self.last_name = self.last_name.strip()
        self.email = self.email.strip()
        self.job_title = self.job_title.strip()
        if self.phone_number is not None:
            stripped_phone = self.phone_number.strip()
            self.phone_number = stripped_phone if stripped_phone else None


# ---------------------------------------------------------------------------
# EmployeeValidationResult
# ---------------------------------------------------------------------------


@dataclass
class EmployeeValidationResult:
    """Outcome of validating a single DataFrame row.

    Produced by :func:`validator.validate_record` and aggregated by
    :func:`validator.validate_dataframe`.

    Attributes:
        row_index (int): Zero-based positional index of the source row inside
            the input DataFrame.
        is_valid (bool): ``True`` when **all** validation rules passed.
        errors (List[str]): Human-readable error messages, one per failed
            rule.  Empty when ``is_valid`` is ``True``.

    Example::

        result = EmployeeValidationResult(
            row_index=0,
            is_valid=False,
            errors=["email is invalid: 'not-an-email'"],
        )
    """

    row_index: int
    is_valid: bool
    errors: List[str] = field(default_factory=list)
