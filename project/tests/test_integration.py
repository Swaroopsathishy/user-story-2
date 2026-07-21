"""
tests/test_integration.py
=========================
Integration test suite for the Employee Scraper pipeline.

Test Cases
----------
✓ Test Case 1: Verify CSV File Download
✓ Test Case 2: Verify CSV File Extraction (parsing to DataFrame)
✓ Test Case 3: Validate File Type and Format
✓ Test Case 4: Validate Data Structure (required columns present)
✓ Test Case 5: Handle Missing or Invalid Data

Each test is self-contained, uses mocks where network access is required,
and covers both happy-path and failure scenarios.
"""

from __future__ import annotations

import io
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure the project root (parent of tests/) is on sys.path so that flat
# imports like ``from downloader import Downloader`` resolve correctly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from downloader import Downloader, DownloaderError
from mapper import dataframe_to_employees, employees_to_dataframe
from models import Employee
from parser import Parser, ParserError
from validator import validate_dataframe, validate_columns, REQUIRED_COLUMNS


# ===========================================================================
# Test Case 1 — Verify CSV File Download
# ===========================================================================


class TestCSVFileDownload:
    """✓ Test Case 1: Verify CSV File Download.

    Covers the Downloader's ability to fetch a CSV file from a remote URL,
    handle HTTP headers, apply retry logic, and raise on failure.
    """

    def test_successful_csv_download_returns_bytes_and_filename(
        self, valid_csv_bytes: bytes
    ) -> None:
        """A successful download returns the raw bytes and the filename from headers."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = valid_csv_bytes
        mock_response.headers = {
            "Content-Disposition": 'attachment; filename="employees.csv"'
        }

        downloader = Downloader(retries=0, delay=0)
        with patch("requests.get", return_value=mock_response):
            content, filename = downloader.download(
                "https://example.com/employees.csv"
            )

        assert content == valid_csv_bytes, "Content should match mock response."
        assert filename == "employees.csv", "Filename should be extracted from header."

    def test_download_with_no_content_disposition_returns_none_filename(
        self, valid_csv_bytes: bytes
    ) -> None:
        """When Content-Disposition is absent the filename should be None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = valid_csv_bytes
        mock_response.headers = {}

        downloader = Downloader(retries=0, delay=0)
        with patch("requests.get", return_value=mock_response):
            content, filename = downloader.download(
                "https://example.com/data"
            )

        assert content == valid_csv_bytes
        assert filename is None

    def test_retry_succeeds_after_transient_failure(
        self, valid_csv_bytes: bytes
    ) -> None:
        """Downloader retries and succeeds when a transient error precedes success."""
        import requests as _requests

        fail = _requests.exceptions.ConnectionError("timeout")

        success = MagicMock()
        success.status_code = 200
        success.content = valid_csv_bytes
        success.headers = {}

        downloader = Downloader(retries=2, delay=0)
        with patch("requests.get", side_effect=[fail, fail, success]):
            with patch("time.sleep"):
                content, _ = downloader.download(
                    "https://example.com/employees.csv"
                )

        assert content == valid_csv_bytes

    def test_all_retries_exhausted_raises_downloader_error(self) -> None:
        """DownloaderError is raised when every retry attempt fails."""
        import requests as _requests

        downloader = Downloader(retries=2, delay=0)
        with patch(
            "requests.get",
            side_effect=_requests.exceptions.HTTPError("503"),
        ):
            with patch("time.sleep"):
                with pytest.raises(DownloaderError) as exc_info:
                    downloader.download("https://example.com/employees.csv")

        assert "Failed to download" in str(exc_info.value)

    def test_invalid_url_scheme_raises_immediately(self) -> None:
        """An invalid URL scheme raises DownloaderError without making a request."""
        downloader = Downloader(retries=0, delay=0)
        invalid_urls = [
            "",
            "ftp://example.com/data.csv",
            "just_a_filename.csv",
        ]
        for url in invalid_urls:
            with patch("requests.get") as mock_get:
                with pytest.raises(DownloaderError) as exc_info:
                    downloader.download(url)
                mock_get.assert_not_called()
                assert "Invalid URL scheme" in str(exc_info.value)


# ===========================================================================
# Test Case 2 — Verify CSV File Extraction (parsing to DataFrame)
# ===========================================================================


class TestCSVFileExtraction:
    """✓ Test Case 2: Verify CSV File Extraction.

    Covers the Parser's ability to turn raw bytes into a pandas DataFrame.
    """

    def test_valid_csv_bytes_parsed_to_dataframe(
        self, valid_csv_bytes: bytes
    ) -> None:
        """Valid CSV bytes produce a non-empty DataFrame with the correct shape."""
        parser = Parser()
        df = parser.parse(valid_csv_bytes, filename="employees.csv")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3, "Expected 3 data rows."
        assert "employee_id" in df.columns
        assert "email" in df.columns

    def test_csv_column_names_are_preserved(
        self, valid_csv_bytes: bytes
    ) -> None:
        """Column names from the CSV header row are preserved verbatim."""
        expected_columns = [
            "employee_id",
            "first_name",
            "last_name",
            "email",
            "job_title",
            "phone_number",
            "hire_date",
        ]
        parser = Parser()
        df = parser.parse(valid_csv_bytes)
        assert list(df.columns) == expected_columns

    def test_xlsx_bytes_parsed_to_dataframe(self) -> None:
        """Valid XLSX bytes are parsed correctly using the openpyxl engine."""
        source_df = pd.DataFrame(
            {
                "employee_id": [5001],
                "first_name": ["Jack"],
                "last_name": ["Kim"],
                "email": ["jack.kim@example.com"],
                "job_title": ["Data Engineer"],
                "phone_number": [None],
                "hire_date": ["2023-01-10"],
            }
        )
        buf = io.BytesIO()
        source_df.to_excel(buf, index=False, engine="openpyxl")
        xlsx_bytes = buf.getvalue()

        parser = Parser()
        result_df = parser.parse(xlsx_bytes, filename="employees.xlsx")

        assert isinstance(result_df, pd.DataFrame)
        assert len(result_df) == 1
        assert result_df.iloc[0]["email"] == "jack.kim@example.com"

    def test_corrupted_xlsx_raises_parser_error(self) -> None:
        """A ZIP-magic-byte file with corrupt content raises ParserError."""
        corrupted = b"PK\x03\x04\x00\x00\x00\x00"  # ZIP header, no valid body
        parser = Parser()
        with pytest.raises(ParserError):
            parser.parse(corrupted, filename="bad.xlsx")

    def test_empty_content_raises_parser_error(self) -> None:
        """Empty byte input raises ParserError with a descriptive message."""
        parser = Parser()
        with pytest.raises(ParserError) as exc_info:
            parser.parse(b"")
        assert "Empty file content" in str(exc_info.value)


# ===========================================================================
# Test Case 3 — Validate File Type and Format
# ===========================================================================


class TestFileTypeAndFormat:
    """✓ Test Case 3: Validate File Type and Format.

    Covers the Parser's static file-type detection logic.
    """

    def test_xlsx_detected_by_zip_magic_bytes(self) -> None:
        """XLSX is detected from the ZIP magic-byte signature."""
        xlsx_magic = b"PK\x03\x04\x14\x00\x08\x00\x08\x00"
        assert Parser.detect_file_type(xlsx_magic) == "xlsx"

    def test_xls_detected_by_ole2_magic_bytes(self) -> None:
        """XLS is detected from the OLE2 compound-document signature."""
        xls_magic = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x00"
        assert Parser.detect_file_type(xls_magic) == "xls"

    def test_csv_detected_by_filename_extension(self) -> None:
        """CSV is detected via filename when content is plain text."""
        generic_text = b"id,name\n1,Alice"
        assert Parser.detect_file_type(generic_text, "data.csv") == "csv"

    def test_csv_detected_by_utf8_decode_fallback(self) -> None:
        """Plain UTF-8 text without a matching filename defaults to CSV."""
        csv_bytes = b"employee_id,first_name\n1001,Alice"
        assert Parser.detect_file_type(csv_bytes) == "csv"

    def test_empty_bytes_raise_parser_error(self) -> None:
        """Empty content raises ParserError."""
        with pytest.raises(ParserError) as exc_info:
            Parser.detect_file_type(b"")
        assert "Empty file content" in str(exc_info.value)

    def test_binary_null_bytes_raise_parser_error(self) -> None:
        """Binary content containing null bytes raises ParserError."""
        binary = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        with pytest.raises(ParserError) as exc_info:
            Parser.detect_file_type(binary)
        assert "Unsupported" in str(exc_info.value)

    def test_filename_extension_overrides_text_for_xlsx(self) -> None:
        """Filename extension takes priority over plain-text fallback for xlsx."""
        generic = b"some random text"
        result = Parser.detect_file_type(generic, "report.xlsx")
        assert result == "xlsx"


# ===========================================================================
# Test Case 4 — Validate Data Structure
# ===========================================================================


class TestDataStructure:
    """✓ Test Case 4: Validate Data Structure.

    Covers structural validation — required columns, whitespace, deduplication.
    """

    def test_all_required_columns_detected_as_present(
        self, valid_employee_df: pd.DataFrame
    ) -> None:
        """validate_columns returns an empty list when all required columns exist."""
        missing = validate_columns(valid_employee_df)
        assert missing == [], f"Expected no missing columns, got: {missing}"

    def test_missing_columns_are_reported_correctly(
        self, df_missing_columns: pd.DataFrame
    ) -> None:
        """validate_columns identifies each absent required column by name."""
        missing = validate_columns(df_missing_columns)
        assert "email" in missing
        assert "hire_date" in missing

    def test_validate_dataframe_raises_on_missing_columns(
        self, df_missing_columns: pd.DataFrame
    ) -> None:
        """validate_dataframe raises ValueError when structural columns are absent."""
        with pytest.raises(ValueError) as exc_info:
            validate_dataframe(df_missing_columns)
        assert "missing required column" in str(exc_info.value).lower()

    def test_duplicates_are_removed_during_validation(
        self, df_with_duplicates: pd.DataFrame
    ) -> None:
        """validate_dataframe removes fully duplicate rows and reports the count."""
        clean_df, invalid_df, duplicates_removed = validate_dataframe(
            df_with_duplicates
        )
        total_after = len(clean_df) + len(invalid_df)
        # Original has 3 rows but 1 duplicate → 2 unique rows
        assert duplicates_removed == 1
        assert total_after == 2

    def test_clean_output_contains_only_valid_rows(
        self, valid_employee_df: pd.DataFrame
    ) -> None:
        """All rows in the clean output pass validation rules."""
        clean_df, invalid_df, _ = validate_dataframe(valid_employee_df)
        assert len(clean_df) == 3
        assert len(invalid_df) == 0

    def test_mapping_produces_employee_objects(
        self, valid_employee_df: pd.DataFrame
    ) -> None:
        """dataframe_to_employees maps each clean row to an Employee domain object."""
        clean_df, _, _ = validate_dataframe(valid_employee_df)
        employees, failures = dataframe_to_employees(clean_df)

        assert len(failures) == 0
        assert len(employees) == 3
        for emp in employees:
            assert isinstance(emp, Employee)
            assert emp.employee_id
            assert "@" in emp.email

    def test_employees_to_dataframe_produces_correct_columns(
        self, valid_employee_df: pd.DataFrame
    ) -> None:
        """employees_to_dataframe produces a DataFrame with all expected columns."""
        clean_df, _, _ = validate_dataframe(valid_employee_df)
        employees, _ = dataframe_to_employees(clean_df)
        result_df = employees_to_dataframe(employees)

        expected_cols = {
            "employee_id",
            "first_name",
            "last_name",
            "email",
            "job_title",
            "phone_number",
            "hire_date",
        }
        assert expected_cols.issubset(set(result_df.columns))
        assert len(result_df) == 3


# ===========================================================================
# Test Case 5 — Handle Missing or Invalid Data
# ===========================================================================


class TestMissingAndInvalidData:
    """✓ Test Case 5: Handle Missing or Invalid Data.

    Covers row-level validation of missing fields, bad email formats,
    invalid phone numbers, and unparseable dates.
    """

    def test_rows_with_missing_required_fields_go_to_invalid_df(
        self, df_with_missing_fields: pd.DataFrame
    ) -> None:
        """Rows with empty required fields are quarantined in the invalid DataFrame."""
        clean_df, invalid_df, _ = validate_dataframe(df_with_missing_fields)
        # Row with blank email and row with null hire_date should both be invalid
        assert len(invalid_df) >= 2

    def test_invalid_email_format_is_caught(self) -> None:
        """A row with a malformed email address is flagged as invalid."""
        df = pd.DataFrame(
            [
                {
                    "employee_id": 6001,
                    "first_name": "Laura",
                    "last_name": "Morris",
                    "email": "not-an-email",
                    "job_title": "Scrum Master",
                    "phone_number": None,
                    "hire_date": "2022-08-15",
                }
            ]
        )
        _, invalid_df, _ = validate_dataframe(df)
        assert len(invalid_df) == 1
        errors = invalid_df.iloc[0]["_validation_errors"]
        assert any("email" in err for err in errors)

    def test_invalid_phone_number_is_caught(self) -> None:
        """A row with a malformed phone number is flagged as invalid."""
        df = pd.DataFrame(
            [
                {
                    "employee_id": 6002,
                    "first_name": "Mike",
                    "last_name": "Nash",
                    "email": "mike.nash@example.com",
                    "job_title": "Support Lead",
                    "phone_number": "CALL-ME-NOW",  # invalid
                    "hire_date": "2021-05-10",
                }
            ]
        )
        _, invalid_df, _ = validate_dataframe(df)
        assert len(invalid_df) == 1
        errors = invalid_df.iloc[0]["_validation_errors"]
        assert any("phone_number" in err for err in errors)

    def test_invalid_hire_date_is_caught(self) -> None:
        """A row with an unparseable hire_date is flagged as invalid."""
        df = pd.DataFrame(
            [
                {
                    "employee_id": 6003,
                    "first_name": "Nina",
                    "last_name": "Owens",
                    "email": "nina.owens@example.com",
                    "job_title": "Data Scientist",
                    "phone_number": None,
                    "hire_date": "not-a-date",
                }
            ]
        )
        _, invalid_df, _ = validate_dataframe(df)
        assert len(invalid_df) == 1
        errors = invalid_df.iloc[0]["_validation_errors"]
        assert any("hire_date" in err for err in errors)

    def test_non_positive_employee_id_is_caught(self) -> None:
        """An employee_id of 0 or negative fails the positive-integer rule."""
        df = pd.DataFrame(
            [
                {
                    "employee_id": 0,
                    "first_name": "Oscar",
                    "last_name": "Patel",
                    "email": "oscar.patel@example.com",
                    "job_title": "Analyst",
                    "phone_number": None,
                    "hire_date": "2020-04-01",
                }
            ]
        )
        _, invalid_df, _ = validate_dataframe(df)
        assert len(invalid_df) == 1
        errors = invalid_df.iloc[0]["_validation_errors"]
        assert any("employee_id" in err for err in errors)

    def test_completely_empty_dataframe_returns_empty_clean_set(self) -> None:
        """A DataFrame with no rows produces empty clean and invalid sets."""
        df = pd.DataFrame(
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
        clean_df, invalid_df, duplicates_removed = validate_dataframe(df)
        assert len(clean_df) == 0
        assert len(invalid_df) == 0
        assert duplicates_removed == 0

    def test_full_pipeline_with_mixed_data(self) -> None:
        """End-to-end: mixed valid/invalid rows are correctly split by the pipeline."""
        df = pd.DataFrame(
            [
                # Valid
                {
                    "employee_id": 7001,
                    "first_name": "Quinn",
                    "last_name": "Reid",
                    "email": "quinn.reid@example.com",
                    "job_title": "Backend Engineer",
                    "phone_number": "+1-800-555-0200",
                    "hire_date": "2019-03-12",
                },
                # Invalid — missing email
                {
                    "employee_id": 7002,
                    "first_name": "Ryan",
                    "last_name": "Scott",
                    "email": "",
                    "job_title": "Frontend Engineer",
                    "phone_number": None,
                    "hire_date": "2022-11-01",
                },
                # Valid
                {
                    "employee_id": 7003,
                    "first_name": "Sara",
                    "last_name": "Turner",
                    "email": "sara.turner@example.com",
                    "job_title": "ML Engineer",
                    "phone_number": None,
                    "hire_date": "2023-01-07",
                },
            ]
        )
        clean_df, invalid_df, _ = validate_dataframe(df)
        assert len(clean_df) == 2
        assert len(invalid_df) == 1

        employees, failures = dataframe_to_employees(clean_df)
        assert len(employees) == 2
        assert len(failures) == 0

        result_df = employees_to_dataframe(employees)
        assert len(result_df) == 2
        emails = set(result_df["email"].tolist())
        assert "quinn.reid@example.com" in emails
        assert "sara.turner@example.com" in emails

    def test_original_schema_remains_valid(self) -> None:
        """The original schema is validated and maps without changes."""
        df = pd.DataFrame(
            [
                {
                    "employee_id": 1001,
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john.doe@example.com",
                    "job_title": "Developer",
                    "phone_number": "+1-800-555-0101",
                    "hire_date": "2020-01-15",
                }
            ]
        )
        clean_df, invalid_df, _ = validate_dataframe(df)
        assert len(clean_df) == 1
        assert list(clean_df.columns)[:7] == [
            "employee_id",
            "first_name",
            "last_name",
            "email",
            "job_title",
            "phone_number",
            "hire_date",
        ]

    def test_alternate_header_names(self) -> None:
        """Alternate headers map correctly to expected columns."""
        df = pd.DataFrame(
            [
                {
                    "id": 1001,
                    "first": "John",
                    "last": "Doe",
                    "email_address": "john.doe@example.com",
                    "role": "Developer",
                    "cell": "+1-800-555-0101",
                    "hired": "2020-01-15",
                }
            ]
        )
        clean_df, _, _ = validate_dataframe(df)
        assert len(clean_df) == 1
        assert str(clean_df.iloc[0]["employee_id"]) == "1001"
        assert clean_df.iloc[0]["first_name"] == "John"
        assert clean_df.iloc[0]["last_name"] == "Doe"
        assert clean_df.iloc[0]["email"] == "john.doe@example.com"
        assert clean_df.iloc[0]["job_title"] == "Developer"
        assert clean_df.iloc[0]["phone_number"] == "+1-800-555-0101"
        assert str(clean_df.iloc[0]["hire_date"]) == "2020-01-15"

    def test_mixed_case_headers(self) -> None:
        """Mixed case headers are normalized and mapped correctly."""
        df = pd.DataFrame(
            [
                {
                    "Employee_Id": 1001,
                    "First_Name": "John",
                    "Last_Name": "Doe",
                    "Email": "john.doe@example.com",
                    "Job_Title": "Developer",
                    "Phone_Number": "+1-800-555-0101",
                    "Hire_Date": "2020-01-15",
                }
            ]
        )
        clean_df, _, _ = validate_dataframe(df)
        assert len(clean_df) == 1
        assert "employee_id" in clean_df.columns
        assert "first_name" in clean_df.columns

    def test_headers_with_spaces_and_special_chars(self) -> None:
        """Headers with spaces, hyphens, and dots are normalized and mapped."""
        df = pd.DataFrame(
            [
                {
                    "  employee.id--  ": 1001,
                    "first name": "John",
                    "last-name": "Doe",
                    "email": "john.doe@example.com",
                    "job title": "Developer",
                    "phone.number": "+1-800-555-0101",
                    "hire date": "2020-01-15",
                    "extra column": "preserve_me",
                }
            ]
        )
        clean_df, _, _ = validate_dataframe(df)
        assert len(clean_df) == 1
        assert str(clean_df.iloc[0]["employee_id"]) == "1001"
        assert clean_df.iloc[0]["first_name"] == "John"
        assert clean_df.iloc[0]["last_name"] == "Doe"
        assert clean_df.iloc[0]["email"] == "john.doe@example.com"
        assert clean_df.iloc[0]["job_title"] == "Developer"
        assert clean_df.iloc[0]["phone_number"] == "+1-800-555-0101"
        assert str(clean_df.iloc[0]["hire_date"]) == "2020-01-15"
        assert clean_df.iloc[0]["extra_column"] == "preserve_me"

    def test_real_downloaded_csv_schema(self) -> None:
        """The exact schema of the real downloaded CSV is mapped and validated."""
        df = pd.DataFrame(
            [
                {
                    "Index": 1,
                    "User Id": "8717bbf45cCDbEe",
                    "First Name": "John",
                    "Last Name": "Doe",
                    "Sex": "Male",
                    "Email": "john.doe@example.com",
                    "Phone": "+1-800-555-0101",
                    "Date of birth": "2020-01-15",
                    "Job Title": "Developer",
                }
            ]
        )
        clean_df, _, _ = validate_dataframe(df)
        assert len(clean_df) == 1
        assert str(clean_df.iloc[0]["employee_id"]) == "1"
        assert clean_df.iloc[0]["user_id"] == "8717bbf45cCDbEe"
        assert clean_df.iloc[0]["first_name"] == "John"
        assert clean_df.iloc[0]["last_name"] == "Doe"
        assert clean_df.iloc[0]["sex"] == "Male"
        assert clean_df.iloc[0]["email"] == "john.doe@example.com"
        assert clean_df.iloc[0]["phone_number"] == "+1-800-555-0101"
        assert str(clean_df.iloc[0]["hire_date"]) == "2020-01-15"
        assert clean_df.iloc[0]["job_title"] == "Developer"
