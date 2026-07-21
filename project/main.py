"""
main.py
=======
Integration entry-point for the production-ready Employee Scraper.

This module wires together the two completed sub-modules into a single,
end-to-end pipeline:

    Module 1  (downloader + parser)
        └─► raw ``pd.DataFrame``
    Module 2  (validator + mapper)
        └─► cleaned ``pd.DataFrame``  →  ``cleaned_employees.csv``

Workflow
--------
Step 1  – Download the employee file from the configured URL.
Step 2  – Detect the file type (CSV / XLSX / XLS).
Step 3  – Parse raw bytes into a pandas DataFrame.
Step 4  – Pass the DataFrame to the validator.
Step 5  – Validate all employee records (structural + per-row rules).
Step 6  – Map validated rows to strongly-typed Employee objects.
Step 7  – Convert Employee objects back to a clean DataFrame.
Step 8  – Print a human-readable summary to stdout.
Step 9  – Save the cleaned data as ``cleaned_employees.csv``.

Usage
-----
    python main.py

Configuration
-------------
Set the ``EMPLOYEE_URL`` environment variable or edit ``config.py`` to point
to a different data source.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from config import EMPLOYEE_URL, OUTPUT_CSV_PATH
from downloader import Downloader, DownloaderError
from logger import get_logger
from mapper import dataframe_to_employees, employees_to_dataframe
from models import Employee
from parser import Parser, ParserError
from validator import validate_dataframe

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------

log = get_logger(__name__, log_file=Path("logs/employee_scraper.log"))

# ---------------------------------------------------------------------------
# Integration layer
# ---------------------------------------------------------------------------


def run_pipeline(url: str = EMPLOYEE_URL) -> pd.DataFrame:
    """Execute the complete employee-scraper pipeline end-to-end.

    This function is the **integration layer** that connects Module 1
    (downloader + parser) with Module 2 (validator + mapper) and produces
    the final cleaned dataset.

    Args:
        url (str): URL of the employee file to download.  Defaults to the
            value configured in ``config.py``.

    Returns:
        pd.DataFrame: Final cleaned and mapped employee DataFrame, ready for
            downstream consumption or persistence.

    Raises:
        SystemExit: On any unrecoverable error — exits with code 1 so that
            the process can be monitored by orchestration tools.
    """
    # ------------------------------------------------------------------ #
    # Step 1 — Download the employee file
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STEP 1 — Downloading employee file from: %s", url)
    log.info("=" * 60)

    try:
        downloader = Downloader()
        raw_content, filename = downloader.download(url)
        log.info(
            "Download complete. File size: %d bytes | Detected filename: %s",
            len(raw_content),
            filename or "<not provided by server>",
        )
    except DownloaderError as exc:
        log.error("STEP 1 FAILED — Download error: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Step 2 — Detect file type
    # Step 3 — Parse into pandas DataFrame
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STEP 2 — Detecting file type")
    log.info("STEP 3 — Parsing content into DataFrame")
    log.info("=" * 60)

    try:
        parser = Parser()
        file_type = Parser.detect_file_type(raw_content, filename)
        log.info("Detected file type: %s", file_type.upper())

        raw_df: pd.DataFrame = parser.parse(raw_content, filename=filename)
        log.info(
            "Parse complete — %d row(s) × %d column(s)",
            len(raw_df),
            len(raw_df.columns),
        )
    except ParserError as exc:
        log.error("STEP 2/3 FAILED — Parser error: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Step 4 & 5 — Validate the DataFrame
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STEP 4 — Passing DataFrame to validator")
    log.info("STEP 5 — Validating all employee records")
    log.info("=" * 60)

    try:
        clean_df, invalid_df, duplicates_removed = validate_dataframe(raw_df)
        log.info(
            "Validation complete — %d valid | %d invalid | %d duplicate(s) removed",
            len(clean_df),
            len(invalid_df),
            duplicates_removed,
        )
    except (TypeError, ValueError) as exc:
        log.error("STEP 4/5 FAILED — Validation error: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Step 6 — Map employee data to domain objects
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STEP 6 — Mapping validated rows to Employee objects")
    log.info("=" * 60)

    employees, mapping_failures = dataframe_to_employees(clean_df)
    if mapping_failures:
        log.warning(
            "%d row(s) failed mapping and will be excluded from the output.",
            len(mapping_failures),
        )

    # ------------------------------------------------------------------ #
    # Step 7 — Generate cleaned dataset from Employee objects
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STEP 7 — Generating cleaned employee dataset")
    log.info("=" * 60)

    final_df = employees_to_dataframe(employees)
    log.info("Final cleaned dataset contains %d record(s).", len(final_df))

    # ------------------------------------------------------------------ #
    # Step 8 — Print summary
    # ------------------------------------------------------------------ #
    total_records = len(raw_df) + duplicates_removed  # before dedup
    valid_records = len(final_df)
    invalid_records = len(invalid_df) + len(mapping_failures)

    _print_summary(
        total_records=total_records,
        valid_records=valid_records,
        invalid_records=invalid_records,
        duplicates_removed=duplicates_removed,
    )

    # ------------------------------------------------------------------ #
    # Step 9 — Save cleaned data as cleaned_employees.csv
    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STEP 9 — Saving cleaned dataset to: %s", OUTPUT_CSV_PATH)
    log.info("=" * 60)

    _save_csv(final_df, OUTPUT_CSV_PATH)

    return final_df


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _print_summary(
    total_records: int,
    valid_records: int,
    invalid_records: int,
    duplicates_removed: int,
) -> None:
    """Print a formatted pipeline summary to stdout and the log.

    Args:
        total_records (int): Total rows in the raw downloaded file.
        valid_records (int): Rows that passed validation and mapping.
        invalid_records (int): Rows that failed validation or mapping.
        duplicates_removed (int): Duplicate rows that were dropped.
    """
    border = "=" * 50
    summary_lines = [
        "",
        border,
        "        EMPLOYEE SCRAPER — PIPELINE SUMMARY",
        border,
        f"  Total Records          : {total_records}",
        f"  Valid Records          : {valid_records}",
        f"  Invalid Records        : {invalid_records}",
        f"  Duplicate Records Removed : {duplicates_removed}",
        border,
        "",
    ]
    summary = "\n".join(summary_lines)
    print(summary)
    log.info("Pipeline summary — Total: %d | Valid: %d | Invalid: %d | Duplicates removed: %d",
             total_records, valid_records, invalid_records, duplicates_removed)


def _save_csv(df: pd.DataFrame, output_path: str) -> None:
    """Persist *df* to a CSV file at *output_path*.

    Creates parent directories as needed.

    Args:
        df (pd.DataFrame): The cleaned employee DataFrame to save.
        output_path (str): Destination file path (relative or absolute).

    Raises:
        SystemExit: If the file cannot be written (permission error, full
            disk, etc.).
    """
    try:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8")
        log.info("Cleaned dataset saved successfully to: %s", path.resolve())
    except OSError as exc:
        log.error("STEP 9 FAILED — Could not save CSV: %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    log.info("Employee Scraper pipeline starting …")
    final_dataset = run_pipeline()
    log.info(
        "Pipeline completed successfully. %d employee record(s) ready.",
        len(final_dataset),
    )
