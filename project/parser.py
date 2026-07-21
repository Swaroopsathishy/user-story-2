"""
parser.py
=========
Module responsible for detecting file types and parsing raw byte content into
pandas DataFrames.

Detection strategy (in priority order):
1. **Magic byte signatures** — most reliable; identifies XLSX and XLS.
2. **Filename extension hint** — fallback when magic bytes do not match.
3. **Plain-text UTF-8 decode** — final fallback; treats valid text as CSV.

Classes
-------
- ParserError  : Custom exception for detection or parsing failures.
- Parser       : File-type detector and multi-format CSV/Excel parser.
"""

import io
from typing import Optional

import pandas as pd

from logger import get_logger

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class ParserError(Exception):
    """Custom exception raised for errors during file-type detection or parsing.

    Wraps the underlying exception as its ``__cause__`` where applicable.
    """


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class Parser:
    """Automatically detect file format and parse CSV / Excel content.

    Supports:
    - ``csv``  — comma-separated values (UTF-8 or Latin-1).
    - ``xlsx`` — Excel 2007+ (Open XML / ZIP-based).
    - ``xls``  — Excel 97-2003 (OLE2 / BIFF8-based).

    Example::

        parser = Parser()
        df = parser.parse(raw_bytes, filename="employees.csv")
    """

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def detect_file_type(
        content: bytes, filename: Optional[str] = None
    ) -> str:
        """Detect the file format from *content* bytes and an optional *filename*.

        Detection strategy (in priority order):

        1. **Magic bytes** — identifies XLSX (``PK\\x03\\x04``) and XLS
           (OLE2 ``\\xd0\\xcf\\x11\\xe0…``).
        2. **Filename extension** — ``.xlsx``, ``.xls``, ``.csv``.
        3. **UTF-8 decode** — any binary without null bytes that decodes
           cleanly is treated as CSV.

        Args:
            content (bytes): Raw byte content of the file.
            filename (Optional[str]): Optional filename hint.

        Returns:
            str: Detected format — one of ``'csv'``, ``'xlsx'``, ``'xls'``.

        Raises:
            ParserError: If content is empty, contains unsupported binary,
                or cannot be identified.
        """
        if not content:
            raise ParserError("Empty file content received.")

        # 1. Magic bytes — XLSX is a ZIP archive.
        if content.startswith(b"PK\x03\x04"):
            log.info("Detected file type: xlsx (ZIP magic bytes)")
            return "xlsx"

        # 1b. XLS — OLE2 compound document.
        if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            log.info("Detected file type: xls (OLE2 magic bytes)")
            return "xls"

        # 2. Filename extension fallback.
        if filename:
            name_lower = filename.lower()
            if name_lower.endswith(".xlsx"):
                log.info("Detected file type: xlsx (filename extension)")
                return "xlsx"
            if name_lower.endswith(".xls"):
                log.info("Detected file type: xls (filename extension)")
                return "xls"
            if name_lower.endswith(".csv"):
                log.info("Detected file type: csv (filename extension)")
                return "csv"

        # 3. Binary null-byte guard (binary formats we cannot handle).
        if b"\x00" in content:
            raise ParserError(
                "Unsupported binary format detected (null bytes present)."
            )

        # 4. Plain-text UTF-8 decode → assume CSV.
        try:
            content.decode("utf-8")
            log.info("Detected file type: csv (UTF-8 plain-text decode)")
            return "csv"
        except UnicodeDecodeError:
            pass

        raise ParserError(
            "Unsupported file type: format could not be detected."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(
        self, content: bytes, filename: Optional[str] = None
    ) -> pd.DataFrame:
        """Parse *content* bytes into a :class:`pandas.DataFrame`.

        Delegates format detection to :meth:`detect_file_type` and then
        reads the content with the appropriate pandas reader.

        Args:
            content (bytes): Raw byte content of the downloaded file.
            filename (Optional[str]): Optional filename hint for detection.

        Returns:
            pd.DataFrame: Parsed employee data with original column names.

        Raises:
            ParserError: If detection fails or if pandas cannot parse the
                file (e.g. corrupted archive).

        Example::

            parser = Parser()
            df = parser.parse(raw_bytes, filename="employees.xlsx")
            print(df.shape)
        """
        file_type = self.detect_file_type(content, filename)
        log.info("Parsing content as format: %s", file_type)

        try:
            if file_type == "csv":
                df = pd.read_csv(io.BytesIO(content))
            elif file_type == "xlsx":
                df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            elif file_type == "xls":
                df = pd.read_excel(io.BytesIO(content), engine="xlrd")
            else:
                raise ParserError(f"Unsupported file format: '{file_type}'")

            log.info(
                "Parse successful — %d row(s) × %d column(s)",
                len(df),
                len(df.columns),
            )
            return df

        except ParserError:
            raise
        except Exception as exc:
            log.error("Failed to parse file content: %s", exc)
            raise ParserError(
                f"Parsing error for type '{file_type}': {exc}"
            ) from exc
