"""TTL-aware Parquet cache for OHLCV DataFrames.

Cache keys follow the format ``{TICKER}_ohlcv_1y`` (e.g. ``AAPL_ohlcv_1y``).
A ``manifest.json`` in the cache directory tracks metadata for each stored
entry. Reads and writes are safe for single-process use; the manifest is
updated atomically via a write-then-rename pattern to avoid partial reads.

Environment variables
---------------------
SCREENER_CACHE_DIR
    Directory used for Parquet files and the manifest.
    Default: ``temp/screener/data_cache``

PRICE_DATA_VALIDITY_MINS
    Number of minutes a cached entry is considered fresh.
    Default: ``480`` (8 hours).
"""

import datetime
import json
import logging
import os
import re
import tempfile

import pandas as pd

logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

_DEFAULT_CACHE_DIR = os.path.join("temp", "screener", "data_cache")
_DEFAULT_VALIDITY_MINS = 480
_MANIFEST_FILENAME = "manifest.json"

# Allowlist for cache key characters: alphanumeric, underscore, hyphen only.
# Rejects path separators, dots, and any other character that could be used
# for path traversal or shell injection. Ticker symbols are always [A-Z0-9.-]
# in practice; the dot is deliberately excluded here because it appears in
# the suffix we append (.parquet) and we do not want dots in the base name.
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


# ── main class ────────────────────────────────────────────────────────────────


class CacheStore:
    """TTL-aware Parquet cache for OHLCV DataFrames.

    Args:
        cache_dir: Directory where Parquet files and the manifest are stored.
            Defaults to ``SCREENER_CACHE_DIR`` env var, or
            ``temp/screener/data_cache`` if the env var is absent.
        validity_mins: Number of minutes a cached entry is considered fresh.
            Defaults to ``PRICE_DATA_VALIDITY_MINS`` env var, or ``480``.
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        validity_mins: int | None = None,
    ) -> None:
        self._cache_dir: str = cache_dir or os.environ.get(
            "SCREENER_CACHE_DIR", _DEFAULT_CACHE_DIR
        )
        self._validity_mins: int = validity_mins if validity_mins is not None else int(
            os.environ.get("PRICE_DATA_VALIDITY_MINS", str(_DEFAULT_VALIDITY_MINS))
        )
        logger.info(
            "CacheStore initialised",
            extra={"cache_dir": self._cache_dir, "validity_mins": self._validity_mins},
        )

    # ── public API ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_key(key: str) -> None:
        """Raise ValueError if *key* contains characters that could enable path traversal.

        Cache keys are derived from external ticker symbols returned by yfinance
        or Alpha Vantage. Restricting to [A-Za-z0-9_-] ensures the key cannot
        be used to escape the cache directory (e.g. ``../../etc/passwd``).
        """
        if not _SAFE_KEY_RE.match(key):
            raise ValueError(
                f"Cache key {key!r} contains unsafe characters. "
                "Only alphanumeric, underscore, and hyphen are allowed."
            )

    def get(self, key: str) -> pd.DataFrame | None:
        """Return the cached DataFrame for *key* if it exists and is still fresh.

        Args:
            key: Cache key in the format ``{TICKER}_ohlcv_1y``.

        Returns:
            A ``pd.DataFrame`` when the entry exists and is within
            ``validity_mins``, otherwise ``None``.
        """
        self._validate_key(key)
        logger.info("CacheStore.get called", extra={"key": key})

        manifest = self._load_manifest()
        if key not in manifest:
            logger.info("Cache miss — key not in manifest", extra={"key": key})
            return None

        entry = manifest[key]
        fetched_at = self._parse_fetched_at(entry.get("fetched_at", ""))
        if fetched_at is None:
            logger.info("Cache miss — fetched_at unparseable", extra={"key": key})
            return None

        age_mins = (datetime.datetime.now(datetime.timezone.utc) - fetched_at).total_seconds() / 60.0
        if age_mins >= self._validity_mins:
            logger.info(
                "Cache miss — entry expired",
                extra={"key": key, "age_mins": round(age_mins, 1), "validity_mins": self._validity_mins},
            )
            return None

        # Resolve the path and confirm it stays inside cache_dir to guard
        # against a tampered manifest pointing at an arbitrary filesystem path.
        raw_file = entry.get("file", "")
        parquet_path = os.path.realpath(os.path.join(self._cache_dir, raw_file))
        cache_dir_real = os.path.realpath(self._cache_dir)
        if not parquet_path.startswith(cache_dir_real + os.sep):
            logger.warning(
                "Manifest entry 'file' escapes cache directory — ignoring",
                extra={"key": key, "file": raw_file},
            )
            return None

        if not os.path.isfile(parquet_path):
            logger.info("Cache miss — Parquet file missing", extra={"key": key, "path": parquet_path})
            return None

        df = pd.read_parquet(parquet_path)
        logger.info(
            "Cache hit",
            extra={"key": key, "rows": len(df), "age_mins": round(age_mins, 1)},
        )
        return df

    def put(self, key: str, df: pd.DataFrame) -> None:
        """Persist *df* to a Parquet file and update the manifest atomically.

        Args:
            key: Cache key in the format ``{TICKER}_ohlcv_1y``.
            df: OHLCV DataFrame to cache.

        Raises:
            ValueError: When *key* contains unsafe characters.
            PermissionError: Propagated when the cache directory is not writable.
            OSError: Propagated for other filesystem failures.
        """
        self._validate_key(key)
        logger.info("CacheStore.put called", extra={"key": key, "rows": len(df)})

        try:
            os.makedirs(self._cache_dir, exist_ok=True)
        except (PermissionError, OSError):
            logger.error(
                "Cache directory not writable",
                extra={"path": self._cache_dir},
                exc_info=True,
            )
            raise

        filename = f"{key}.parquet"
        parquet_path = os.path.join(self._cache_dir, filename)

        try:
            df.to_parquet(parquet_path)
        except (PermissionError, OSError):
            logger.error(
                "Cache directory not writable",
                extra={"path": self._cache_dir},
                exc_info=True,
            )
            raise

        logger.info("Parquet file written", extra={"key": key, "path": parquet_path})

        # Update manifest atomically: write to .tmp then rename.
        manifest = self._load_manifest()
        manifest[key] = {
            "file": filename,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._save_manifest(manifest)
        logger.info("Manifest updated", extra={"key": key})

    # ── internal helpers ──────────────────────────────────────────────────────

    def _manifest_path(self) -> str:
        """Return the absolute path to manifest.json."""
        return os.path.join(self._cache_dir, _MANIFEST_FILENAME)

    def _load_manifest(self) -> dict:
        """Load and parse manifest.json.

        Returns an empty dict if the file is absent or contains invalid JSON —
        both cases are treated as an empty cache rather than an error (FM-10).
        """
        path = self._manifest_path()
        if not os.path.isfile(path):
            logger.info("Manifest file absent — treating as empty cache", extra={"path": path})
            return {}

        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            logger.warning(
                "Manifest file contains invalid JSON — treating as empty cache",
                extra={"path": path},
            )
            return {}

    def _save_manifest(self, manifest: dict) -> None:
        """Atomically write *manifest* to manifest.json via a temp-file rename.

        Raises:
            PermissionError: Propagated when the directory is not writable.
            OSError: Propagated for other filesystem failures.
        """
        final_path = self._manifest_path()
        # Write to a sibling temp file in the same directory so os.replace()
        # is an atomic rename on the same filesystem.
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._cache_dir, prefix=".manifest_", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)
            os.replace(tmp_path, final_path)
        except (PermissionError, OSError):
            # Clean up the temp file if possible, then re-raise.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            logger.error(
                "Cache directory not writable",
                extra={"path": self._cache_dir},
                exc_info=True,
            )
            raise

    @staticmethod
    def _parse_fetched_at(value: str) -> datetime.datetime | None:
        """Parse an ISO 8601 timestamp string into a timezone-aware datetime.

        Returns ``None`` on parse failure so callers can treat the entry as
        invalid without crashing.
        """
        if not value:
            return None
        try:
            dt = datetime.datetime.fromisoformat(value)
            # Ensure UTC-aware for consistent age calculations.
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            logger.warning(
                "Could not parse fetched_at timestamp",
                extra={"value": value},
            )
            return None
