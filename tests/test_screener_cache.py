"""Unit tests for screener/cache_store.py (CacheStore).

Tests use tmp_path pytest fixture — no writes to real directories.
All filesystem operations are isolated per test.
"""
import datetime
import json
import os

import pandas as pd
import pytest

from screener.cache_store import CacheStore

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_df() -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame for test fixtures."""
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [103.0, 104.0],
            "volume": [1_000_000, 1_100_000],
        },
        index=pd.date_range("2025-01-01", periods=2, freq="D"),
    )


def _write_manifest(cache_dir: str, key: str, filename: str, fetched_at: datetime.datetime) -> None:
    """Write a manifest.json with a single entry directly to cache_dir."""
    manifest = {
        key: {
            "file": filename,
            "fetched_at": fetched_at.isoformat(),
        }
    }
    manifest_path = os.path.join(cache_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)


# ── tests ─────────────────────────────────────────────────────────────────────


class TestCacheStore:
    """Scenario-based tests for CacheStore TTL logic and persistence."""

    def test_cache_miss_when_expired(self, tmp_path: pytest.fixture) -> None:
        """R-CACHE-03: get() returns None when the manifest entry is older than validity_mins."""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir)

        key = "AAPL_ohlcv_1y"
        filename = f"{key}.parquet"
        df = _make_df()

        # Write the Parquet file directly so it physically exists.
        df.to_parquet(os.path.join(cache_dir, filename))

        # Set fetched_at to 600 minutes ago — well beyond the 480-minute default.
        expired_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=600)
        _write_manifest(cache_dir, key, filename, expired_at)

        store = CacheStore(cache_dir=cache_dir, validity_mins=480)
        result = store.get(key)

        assert result is None, "Expected None for an expired cache entry"

    def test_cache_hit_when_fresh(self, tmp_path: pytest.fixture) -> None:
        """R-CACHE-03: get() returns the DataFrame when the manifest entry is within validity_mins."""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir)

        key = "AAPL_ohlcv_1y"
        filename = f"{key}.parquet"
        df = _make_df()

        # Write the Parquet file directly.
        df.to_parquet(os.path.join(cache_dir, filename))

        # Set fetched_at to 1 minute ago — well within the 480-minute default.
        fresh_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
        _write_manifest(cache_dir, key, filename, fresh_at)

        store = CacheStore(cache_dir=cache_dir, validity_mins=480)
        result = store.get(key)

        assert result is not None, "Expected a DataFrame for a fresh cache entry"
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == list(df.columns)
        assert len(result) == len(df)

    def test_cache_put_writes_parquet_and_manifest(self, tmp_path: pytest.fixture) -> None:
        """R-CACHE-04: put() persists the Parquet file and updates manifest with current timestamp."""
        cache_dir = str(tmp_path / "cache")
        # Intentionally do NOT pre-create cache_dir — put() must create it via makedirs.

        key = "TSLA_ohlcv_1y"
        df = _make_df()

        store = CacheStore(cache_dir=cache_dir, validity_mins=480)
        store.put(key, df)

        # Parquet file must exist.
        expected_parquet = os.path.join(cache_dir, f"{key}.parquet")
        assert os.path.isfile(expected_parquet), f"Expected Parquet file at {expected_parquet}"

        # Manifest must exist and contain the key.
        manifest_path = os.path.join(cache_dir, "manifest.json")
        assert os.path.isfile(manifest_path), "Expected manifest.json to exist after put()"

        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)

        assert key in manifest, f"Expected key '{key}' in manifest"
        assert manifest[key]["file"] == f"{key}.parquet"

        # fetched_at must be a recent UTC ISO string (within last 10 seconds).
        fetched_at = datetime.datetime.fromisoformat(manifest[key]["fetched_at"])
        # Ensure timezone-aware for comparison.
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=datetime.timezone.utc)
        age_seconds = (datetime.datetime.now(datetime.timezone.utc) - fetched_at).total_seconds()
        assert age_seconds < 10, f"fetched_at is too old ({age_seconds:.1f}s) — expected < 10s"

        # Parquet content must round-trip correctly.
        loaded = pd.read_parquet(expected_parquet)
        assert list(loaded.columns) == list(df.columns)
        assert len(loaded) == len(df)

    def test_cache_handles_missing_manifest(self, tmp_path: pytest.fixture) -> None:
        """R-CACHE-03 / FM-10: get() returns None (no raise) when manifest.json is absent."""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir)
        # Deliberately leave manifest.json absent.

        store = CacheStore(cache_dir=cache_dir, validity_mins=480)
        # Must not raise — treat missing manifest as empty cache.
        result = store.get("MSFT_ohlcv_1y")

        assert result is None, "Expected None when manifest.json does not exist"

    def test_put_rejects_path_traversal_key(self, tmp_path: pytest.fixture) -> None:
        """Security: put() raises ValueError on a key containing path traversal characters."""
        cache_dir = str(tmp_path / "cache")
        store = CacheStore(cache_dir=cache_dir, validity_mins=480)
        df = _make_df()

        with pytest.raises(ValueError, match="unsafe characters"):
            store.put("../../../etc/evil_ohlcv_1y", df)

    def test_get_rejects_path_traversal_key(self, tmp_path: pytest.fixture) -> None:
        """Security: get() raises ValueError on a key containing path traversal characters."""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir)
        store = CacheStore(cache_dir=cache_dir, validity_mins=480)

        with pytest.raises(ValueError, match="unsafe characters"):
            store.get("../../../etc/passwd_ohlcv_1y")

    def test_get_ignores_manifest_file_escaping_cache_dir(self, tmp_path: pytest.fixture) -> None:
        """Security: get() returns None when manifest 'file' field escapes the cache directory."""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir)

        # Inject a tampered manifest entry whose 'file' points outside cache_dir.
        key = "AAPL_ohlcv_1y"
        fresh_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
        manifest = {key: {"file": "../../outside.parquet", "fetched_at": fresh_at.isoformat()}}
        with open(os.path.join(cache_dir, "manifest.json"), "w") as fh:
            json.dump(manifest, fh)

        store = CacheStore(cache_dir=cache_dir, validity_mins=480)
        result = store.get(key)

        assert result is None, "Expected None when manifest 'file' escapes the cache directory"
