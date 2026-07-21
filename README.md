# Employee Scraper — Integrated Data Pipeline

A professional, production-ready Python data engineering pipeline that downloads employee files, detects file types, parses CSV/Excel data, normalizes column schemas, validates record compliance, maps data to robust domain objects, and outputs a cleaned dataset.

## Problem Statement

Employee onboarding and resource data are frequently distributed across varying formats (CSV, Excel xlsx, Excel xls) with inconsistent column schemas (e.g. `Index` vs `User Id`, `Phone` vs `Phone Number`, `Date of birth` vs `Hire Date`).

This project solves the data-ingestion challenge by establishing an automated integration pipeline with a robust **Column Normalization & Mapping Layer** that makes it compatible with both standard test schemas and real-world downloaded datasets, ensuring only valid data reaches downstream databases.

---

## Features

- **Automated Download**: Downloader with configurable retries, delays, timeouts, and filename header extraction.
- **Auto Format Detection**: File-type detector via magic bytes (ZIP archives/OLE2 headers) with fallbacks to extension hints and text encoding.
- **Column Normalization Layer**: Automatically cleans column names (strips spaces/underscores, lowercases, replaces dot/hyphen/space delimiters, and deduplicates underscores).
- **Flexible Column Mapping**: Configurable `COLUMN_MAPPING` to seamlessly translate schema variations to the canonical internal model names.
- **Double-Mapping Protection**: Prioritizes exact matches and avoids duplicate mapping conflicts when candidate column duplicates exist.
- **Strict Business Rules Validation**:
  - `employee_id`: Required, positive integer string.
  - `first_name` & `last_name`: Required, non-empty.
  - `email`: Required, RFC-5321 compliant.
  - `phone_number`: Optional, matches common international formats.
  - `hire_date`: Required, parseable calendar date.
- **Strict Error Auditing**: Quarantine of invalid records detailing specific errors, with deduplication logging.
- **Clean Architecture & Domains**: Strongly typed `Employee` domain models.

---

## Project Structure

```
project/
├── config.py              - Central configuration settings (URLs, timeouts, output)
├── downloader.py          - HTTP downloader with retry logic
├── logger.py              - Unified stream & rotating file logger
├── main.py                - Main pipeline orchestrator (9-step workflow)
├── mapper.py              - Data mapping layer (Row <=> Employee object conversion)
├── models.py              - Python dataclass domain models
├── parser.py              - Format detection and CSV/Excel parsing
├── pytest.ini             - pytest configuration
├── requirements.txt       - Core python dependencies
├── validator.py           - Validation rules & column normalization layer
└── tests/
    ├── __init__.py        - Test package init
    ├── conftest.py        - Shared pytest mock data & fixtures
    └── test_integration.py - 36 integration & schema compatibility tests
```

---

## Installation

1. Navigate to the project root directory:
   ```bash
   cd project
   ```

2. Set up and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

---

## Running the Project

Run the end-to-end scraper, normalization, validation, and serialization pipeline with:
```bash
python main.py
```

---

## Running Tests

Execute the full suite of integration and schema compatibility tests with pytest:
```bash
cd project
pytest
```

---

## User Story 2 — Implementation

This repository contains the complete implementation of **User Story 2: Employee Data Pipeline**, including:

- Employee data scraping and processing functionality
- Data transformation and validation
- Improved logging and error handling
- Comprehensive unit and integration tests
- Updated project documentation
