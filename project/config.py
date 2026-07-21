"""
config.py
=========
Centralised configuration for the employee scraper pipeline.

All tuneable parameters live here so that no magic strings or numbers are
scattered across the codebase.  Override any value by setting the
corresponding environment variable before running the pipeline.

Environment Variables
---------------------
EMPLOYEE_URL     : Override the default Google Drive download URL.
OUTPUT_CSV_PATH  : Override the default output CSV path.
"""

import os

# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------

#: Public Google Drive direct-download URL for the employee CSV.
EMPLOYEE_URL: str = os.getenv(
    "EMPLOYEE_URL",
    "https://drive.google.com/uc?id=1AWPf-pJodJKeHsARQK_RHiNsE8fjPCVK&export=download",
)

# ---------------------------------------------------------------------------
# Downloader settings
# ---------------------------------------------------------------------------

#: Number of *retry* attempts after the first failure.
DOWNLOAD_RETRIES: int = int(os.getenv("DOWNLOAD_RETRIES", "3"))

#: Seconds to wait between retries.
DOWNLOAD_DELAY_SECONDS: int = int(os.getenv("DOWNLOAD_DELAY_SECONDS", "2"))

#: HTTP request timeout in seconds.
DOWNLOAD_TIMEOUT_SECONDS: int = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "15"))

# ---------------------------------------------------------------------------
# Output settings
# ---------------------------------------------------------------------------

#: Path where the cleaned employee data will be saved.
OUTPUT_CSV_PATH: str = os.getenv("OUTPUT_CSV_PATH", "cleaned_employees.csv")
