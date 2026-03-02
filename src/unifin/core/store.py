"""DuckDB local persistence layer — cache and incremental sync."""

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

    def save(
        self,
        model_name: str,
        data: list[dict[str, Any]],
        symbol: str | None = None,
    ) -> int:
        """Save data to local store. Returns number of rows inserted."""
        if not data:
            return 0

        import polars as pl

        table_name = f"unifin_{model_name}"
        df = pl.DataFrame(data)

        # Create or append
        self.connection.execute(
            f"CREATE TABLE IF NOT EXISTS {table_name} AS SELECT * FROM df WHERE 1=0"
        )
        self.connection.execute(f"INSERT INTO {table_name} SELECT * FROM df")
        logger.debug("Saved %d rows to %s", len(data), table_name)
        return len(data)

    def load(
        self,
        model_name: str,
        symbol: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Load data from local store."""

        table_name = f"unifin_{model_name}"

        try:
            conditions = []
            if symbol:
                conditions.append(f"symbol = '{symbol}'")
            if start_date:
                conditions.append(f"date >= '{start_date}'")
            if end_date:
                conditions.append(f"date <= '{end_date}'")

            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
            result = self.connection.execute(
                f"SELECT * FROM {table_name}{where} ORDER BY date"
            ).pl()
            return result.to_dicts()
        except Exception:
            return []

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

    def close(self) -> None:
        """Close the database connection."""
        if self._con:
            self._con.close()
            self._con = None


# Global singleton
store = DataStore()
