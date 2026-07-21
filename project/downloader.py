"""
downloader.py
=============
Module responsible for downloading employee files from external URLs with
retry logic and comprehensive error handling.

The :class:`Downloader` class supports:

* Configurable retry attempts with inter-attempt delay.
* Extraction of the suggested filename from the ``Content-Disposition``
  response header.
* URL scheme validation before any network call is made.

Classes
-------
- DownloaderError  : Custom exception for all download failures.
- Downloader       : HTTP file downloader with retry capabilities.
"""

import re
import time
from typing import Optional, Tuple

import requests

from logger import get_logger

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class DownloaderError(Exception):
    """Custom exception raised when file downloading fails.

    Wraps the underlying :mod:`requests` exception as its ``__cause__`` so
    callers can inspect the original error when needed.
    """


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------


class Downloader:
    """HTTP file downloader with configurable retry behaviour.

    Args:
        retries (int): Number of *retry* attempts after the first failure.
            Total attempts = ``1 + retries``.  Defaults to ``3``.
        delay (int): Seconds to wait between retry attempts.  Defaults to ``2``.
        timeout (int): HTTP request timeout in seconds.  Defaults to ``15``.

    Example::

        downloader = Downloader(retries=3, delay=2, timeout=15)
        content, filename = downloader.download("https://example.com/employees.csv")
    """

    def __init__(
        self,
        retries: int = 3,
        delay: int = 2,
        timeout: int = 15,
    ) -> None:
        self.retries = retries
        self.delay = delay
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_filename_from_headers(self, headers: dict) -> Optional[str]:
        """Extract the suggested filename from the Content-Disposition header.

        Args:
            headers (dict): HTTP response headers dictionary.

        Returns:
            Optional[str]: Extracted filename, or ``None`` when not present.
        """
        content_disposition = headers.get("Content-Disposition", "")
        if not content_disposition:
            return None

        # Accept: filename="name", filename='name', filename=name
        match = re.search(
            r'filename=["\']?([^"\';\s]+)["\']?', content_disposition
        )
        if match:
            filename = match.group(1).strip()
            log.info("Extracted filename from Content-Disposition header: %s", filename)
            return filename
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def download(self, url: str) -> Tuple[bytes, Optional[str]]:
        """Download a file from *url* with automatic retry on transient failures.

        Args:
            url (str): The HTTP/HTTPS URL to download from.

        Returns:
            Tuple[bytes, Optional[str]]: Raw file bytes and an optional
                filename extracted from response headers.

        Raises:
            DownloaderError: If the URL scheme is invalid, or if the download
                fails after all retry attempts are exhausted.

        Example::

            content, filename = downloader.download(
                "https://example.com/employees.csv"
            )
        """
        log.info("Starting file download from URL: %s", url)

        # Basic URL scheme validation — catches FTP, bare hostnames, etc.
        if not url or not (
            url.startswith("http://") or url.startswith("https://")
        ):
            raise DownloaderError(f"Invalid URL scheme: '{url}'")

        last_exception: Optional[Exception] = None
        total_attempts = 1 + self.retries

        for attempt in range(1, total_attempts + 1):
            try:
                log.info(
                    "Download attempt %d / %d for URL: %s",
                    attempt,
                    total_attempts,
                    url,
                )
                response = requests.get(
                    url, timeout=self.timeout, allow_redirects=True
                )
                # Raises HTTPError for 4xx / 5xx status codes.
                response.raise_for_status()

                log.info(
                    "Download successful. HTTP status: %d, content size: %d bytes",
                    response.status_code,
                    len(response.content),
                )
                filename = self._extract_filename_from_headers(response.headers)
                return response.content, filename

            except requests.exceptions.RequestException as exc:
                last_exception = exc
                log.warning(
                    "Attempt %d / %d failed: %s", attempt, total_attempts, exc
                )
                if attempt < total_attempts:
                    log.info(
                        "Waiting %d second(s) before retry …", self.delay
                    )
                    time.sleep(self.delay)
                else:
                    log.error("All %d download attempt(s) exhausted.", total_attempts)

        raise DownloaderError(
            f"Failed to download file from '{url}' after {total_attempts} "
            f"attempt(s). Last error: {last_exception}"
        ) from last_exception
