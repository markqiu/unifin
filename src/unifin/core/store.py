"""DuckDB local persistence layer — cache and incremental sync.

All data fetched via the Router is automatically persisted here.
Tables are named ``unifin_{model_name}`` and created lazily.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("unifin")

_DEFAULT_DB_PATH = Path.home() / ".unifin" / "data.duckdb"


class DataStore:
    """Local DuckDB-backed data store.

    Provides:
    - Cache: avoid re-fetching unchanged data
    - Persistence: query historical data offline
    - Incremental sync: only fetch missing date ranges
    """

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = None

    @property
    def connection(self):
        """Lazy DuckDB connection."""
        if self._con is None:
            import duckdb

            self._con = duckdb.connect(str(self._db_path))
            logger.debug("Connected to DuckDB at %s", self._db_path)
        return self._con

    # ── write ──

    def save(
        self,
        model_name: str,
        data: list[dict[str, Any]],
        *,
        symbol: str | None = None,
        dedup_keys: list[str] | None = None,
    ) -> int:
        """Save data to local store. Returns number of rows inserted.

        If *dedup_keys* is given (e.g. ``["date", "symbol"]``), existing rows
        with the same key values are replaced (upsert semantics).
        """
        if not data:
            return 0

        import polars as pl

        table_name = f"unifin_{model_name}"
        df = pl.DataFrame(data)

        # Create table lazily
        self.connection.execute(
            f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM df WHERE 1=0"
        )

        if dedup_keys:
            # Delete old rows with matching keys, then insert new
            key_cols = [k for k in dedup_keys if k in df.columns]
            if key_cols:
                conditions = " AND ".join(f"{table_name}.{k} = new_data.{k}" for k in key_cols)
                self.connection.execute(
                    f"DELETE FROM {table_name} WHERE EXISTS "
                    f"(SELECT 1 FROM df AS new_data WHERE {conditions})"
                )

        self.connection.execute(f"INSERT INTO {table_name} SELECT * FROM df")
        logger.debug("Saved %d rows to %s", len(data), table_name)
        return len(data)

    # ── read ──

    def load(
        self,
        model_name: str,
        *,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Load data from local store.

        Args:
            model_name: Registry model name (table = ``unifin_{model_name}``).
            symbol: Filter by ``symbol`` column.
            start_date: Filter ``date >= ?``.
            end_date: Filter ``date <= ?``.
            filters: Extra ``column = value`` filters.
            order_by: Column name(s) to sort by.
            limit: Max rows.
        """
        table_name = f"unifin_{model_name}"

        try:
            conditions: list[str] = []
            if symbol:
                conditions.append(f"symbol = '{symbol}'")
            if start_date:
                conditions.append(f"date >= '{start_date}'")
            if end_date:
                conditions.append(f"date <= '{end_date}'")
            if filters:
                for col, val in filters.items():
                    conditions.append(f"{col} = '{val}'")

            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            order = f" ORDER BY {order_by}" if order_by else ""
            lim = f" LIMIT {limit}" if limit else ""
            sql = f"SELECT * FROM {table_name}{where}{order}{lim}"
            result = self.connection.execute(sql).pl()
            return result.to_dicts()
        except Exception:
            return []

    # ── introspection ──

    def has_data(
        self,
        model_name: str,
        symbol: str | None = None,
    ) -> bool:
        """Check if any data exists for a model/symbol."""
        table_name = f"unifin_{model_name}"
        try:
            where = f" WHERE symbol = '{symbol}'" if symbol else ""
            count = self.connection.execute(f"SELECT COUNT(*) FROM {table_name}{where}").fetchone()[
                0
            ]
            return count > 0
        except Exception:
            return False

    def list_tables(self) -> list[str]:
        """List all unifin tables in the store."""
        try:
            rows = self.connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'unifin_%'"
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def table_row_count(self, model_name: str) -> int:
        """Return the number of rows in a model's table."""
        table_name = f"unifin_{model_name}"
        try:
            return self.connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        except Exception:
            return 0

    def close(self) -> None:
        """Close the database connection."""
        if self._con:
            self._con.close()
            self._con = None


# Global singleton
store = DataStore()
