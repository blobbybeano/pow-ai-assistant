"""Postgres-backed persistence layer.

On Replit Autoscale (and similar ephemeral hosts) the local filesystem is reset
on every deploy/restart, so any JSON/text file written at runtime is lost. This
module stores those files as rows in a Postgres `app_kv` table instead, keyed by
filename. It is portable: pointing DATABASE_URL at any Postgres (e.g. Fly) keeps
all data intact.

`PersistentFile` is a drop-in stand-in for a pathlib.Path that transparently
routes `.read_text()`, `.write_text()` and `.exists()` through Postgres, with the
on-disk file used only to *seed* the database the first time (so committed
defaults like the admin account migrate automatically).

If DATABASE_URL is not set or Postgres is unreachable, everything falls back to
plain file behaviour so local development still works.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATABASE_URL = os.getenv("DATABASE_URL")
_lock = threading.RLock()
_conn = None
_initialized = False
_available: Optional[bool] = None
_last_fail_check = 0.0
_RETRY_AFTER_SECONDS = 30.0


def _connect():
    global _conn
    if _conn is not None and getattr(_conn, "closed", 1) == 0:
        return _conn
    import psycopg2  # lazy import so the app still boots without the driver

    _conn = psycopg2.connect(_DATABASE_URL)
    _conn.autocommit = True
    return _conn


def _ensure_table() -> None:
    global _initialized
    if _initialized:
        return
    conn = _connect()
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS app_kv ("
            "key TEXT PRIMARY KEY, "
            "value TEXT NOT NULL, "
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    _initialized = True


def kv_available() -> bool:
    """True if Postgres is configured and reachable.

    A successful connection is cached permanently. A failure is NOT cached
    forever — it is retried after ``_RETRY_AFTER_SECONDS`` so a transient outage
    at startup does not strand the app in ephemeral-file mode for its whole life.
    """
    global _available, _last_fail_check
    if _available is True:
        return True
    if not _DATABASE_URL:
        if _available is None:
            logger.info("pg_store: DATABASE_URL not set — using local files only")
        _available = False
        return False
    # _available is None (first call) or False (retry after backoff window)
    if _available is False and (time.monotonic() - _last_fail_check) < _RETRY_AFTER_SECONDS:
        return False
    try:
        with _lock:
            _ensure_table()
        _available = True
        logger.info("pg_store: Postgres connected — persisting app data to database")
    except Exception as exc:  # pragma: no cover - environment dependent
        _available = False
        _last_fail_check = time.monotonic()
        logger.warning("pg_store: Postgres unavailable (%s) — using local files", exc)
    return _available


def _exec(query: str, params=(), fetch: bool = False):
    """Run a statement with the shared connection, reconnecting once on failure."""
    global _conn
    with _lock:
        try:
            conn = _connect()
            _ensure_table()
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone() if fetch else None
        except Exception as exc:
            logger.warning("pg_store: query failed (%s) — reconnecting", exc)
            try:
                if _conn is not None:
                    _conn.close()
            except Exception:
                pass
            _conn = None
            conn = _connect()
            _ensure_table()
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone() if fetch else None


def kv_get(key: str) -> Optional[str]:
    if not kv_available():
        return None
    try:
        row = _exec("SELECT value FROM app_kv WHERE key = %s", (key,), fetch=True)
        return row[0] if row else None
    except Exception as exc:
        logger.warning("pg_store.kv_get(%s) failed: %s", key, exc)
        return None


def kv_set(key: str, value: str) -> bool:
    if not kv_available():
        return False
    try:
        _exec(
            "INSERT INTO app_kv (key, value, updated_at) VALUES (%s, %s, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (key, value),
        )
        return True
    except Exception as exc:
        logger.warning("pg_store.kv_set(%s) failed: %s", key, exc)
        return False


def kv_delete(key: str) -> bool:
    if not kv_available():
        return False
    try:
        _exec("DELETE FROM app_kv WHERE key = %s", (key,))
        return True
    except Exception as exc:
        logger.warning("pg_store.kv_delete(%s) failed: %s", key, exc)
        return False


class PersistentFile:
    """Drop-in replacement for a Path that stores its contents in Postgres.

    The wrapped on-disk path is used only to seed the database the first time a
    value is read (migrating any committed defaults), and as a best-effort mirror
    on write so local development keeps working even without a database.
    """

    def __init__(self, path, key: Optional[str] = None) -> None:
        self._path = Path(path)
        self._key = key or self._path.name

    # ── Path-like API used across the app ─────────────────────────────────────
    def read_text(self, encoding: str = "utf-8") -> str:
        val = kv_get(self._key)
        if val is not None:
            return val
        # Not in DB yet — read the on-disk seed (may raise FileNotFoundError,
        # matching the original Path.read_text behaviour) and migrate it.
        text = self._path.read_text(encoding=encoding)
        kv_set(self._key, text)
        return text

    def write_text(self, data, encoding: str = "utf-8") -> int:
        if not isinstance(data, str):
            data = str(data)
        kv_set(self._key, data)
        try:
            self._path.write_text(data, encoding=encoding)
        except Exception:
            pass  # ephemeral filesystem / read-only — Postgres is source of truth
        return len(data)

    def exists(self) -> bool:
        if kv_get(self._key) is not None:
            return True
        return self._path.exists()

    def unlink(self, missing_ok: bool = False) -> None:
        existed = kv_get(self._key) is not None or self._path.exists()
        kv_delete(self._key)
        try:
            self._path.unlink(missing_ok=True)
        except Exception:
            pass
        if not existed and not missing_ok:
            raise FileNotFoundError(str(self._path))

    # ── Passthroughs so the wrapper behaves like a Path elsewhere ─────────────
    def __fspath__(self) -> str:
        return str(self._path)

    def __str__(self) -> str:
        return str(self._path)

    def __repr__(self) -> str:
        return f"PersistentFile({self._path!r}, key={self._key!r})"

    def __truediv__(self, other):
        return self._path / other

    @property
    def parent(self):
        return self._path.parent

    @property
    def name(self):
        return self._path.name
