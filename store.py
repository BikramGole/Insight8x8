import json
import os
import sqlite3
import threading
import time


class Store:
    def __init__(self, path):
        self.path = str(path)
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    username TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (username, game_id)
                )
                """
            )
            self._conn.commit()

    def get_cache(self, key):
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= now:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                return None
            try:
                return json.loads(row["value"])
            except (TypeError, ValueError):
                return None

    def set_cache(self, key, value, ttl=3600):
        now = time.time()
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cache (key, value, fetched_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (key, encoded, now, now + ttl),
            )
            self._conn.commit()

    def delete_cache(self, key):
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()

    def clear_username_cache(self, username):
        needle = "%{username}%".format(username=username.lower())
        with self._lock:
            keys = [
                row["key"]
                for row in self._conn.execute(
                    "SELECT key FROM cache WHERE lower(key) LIKE ?", (needle,)
                ).fetchall()
            ]
            for key in keys:
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
        return len(keys)

    def favorites(self, username):
        with self._lock:
            rows = self._conn.execute(
                "SELECT game_id FROM favorites WHERE username = ? ORDER BY created_at DESC",
                (username.lower(),),
            ).fetchall()
        return [row["game_id"] for row in rows]

    def add_favorite(self, username, game_id):
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO favorites (username, game_id, created_at)
                VALUES (?, ?, ?)
                """,
                (username.lower(), game_id, time.time()),
            )
            self._conn.commit()

    def remove_favorite(self, username, game_id):
        with self._lock:
            self._conn.execute(
                "DELETE FROM favorites WHERE username = ? AND game_id = ?",
                (username.lower(), game_id),
            )
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()
