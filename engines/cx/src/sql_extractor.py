"""
SQL Extractor for CX Churn Sentinel

Extracts customer-interaction KPI data from the four canonical trend views
(``v_client_csat_trend``, ``v_client_sla_trend``, ``v_client_fcr_trend``,
``v_client_aht_trend``) defined as ``.sql`` artifacts next to this engine.

Key Features:
- Reads the SQL view definitions from ``sql/`` (one file per view)
- Executes against any DB-API 2.0 connection (psycopg2, sqlite3, SQLAlchemy
  engine, …) passed in by the caller — no connection is created here
- Falls back to CSV ingestion when no live DB is available, so the engine
  remains runnable in local-first mode
- Returns a normalized pandas DataFrame keyed by ``client_id`` / ``date``

Design notes:
- This module performs *extraction only*. Scoring lives in :mod:`risk_scorer`,
  aggregation/decay in :mod:`kpi_aggregator`, alert dispatch in
  :mod:`alert_dispatcher`.
- The connection is injected (Constitution 000 — no hardcoded configuration).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical view → KPI mapping used by the CX Sentinel.
KPI_VIEWS = {
    "csat": "v_client_csat_trend",
    "sla": "v_client_sla_trend",
    "fcr": "v_client_fcr_trend",
    "aht": "v_client_aht_trend",
}

# Default SQL artifact directory (lives next to this module under ``sql/``).
DEFAULT_SQL_DIR = Path(__file__).resolve().parent / "sql"


class SQLExtractor:
    """Extract KPI time series from the four trend views / CSV fallback."""

    def __init__(
        self,
        connection: Any | None = None,
        sql_dir: str | Path | None = None,
    ):
        self.connection = connection
        self.sql_dir = Path(sql_dir) if sql_dir else DEFAULT_SQL_DIR

    # ------------------------------------------------------------------ #
    # SQL view resolution
    # ------------------------------------------------------------------ #
    def load_view_sql(self, view_name: str) -> str:
        """Load the SQL definition for ``view_name`` from ``sql/<view>.sql``."""
        path = self.sql_dir / f"{view_name}.sql"
        if not path.exists():
            raise FileNotFoundError(
                f"SQL view definition not found: {path}. "
                f"Expected one of {list(KPI_VIEWS.values())}."
            )
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # DB-backed extraction
    # ------------------------------------------------------------------ #
    def extract_from_db(self, view_name: str) -> pd.DataFrame:
        """Run the named view against the injected connection and return rows."""
        if self.connection is None:
            raise RuntimeError(
                "No database connection provided. Pass a DB-API 2.0 connection "
                "or SQLAlchemy engine to SQLExtractor(connection=...)."
            )
        sql = self.load_view_sql(view_name)
        logger.info("Extracting %s via SQL view", view_name)
        try:
            return pd.read_sql(sql, self.connection)
        except (ValueError, TypeError, OSError) as exc:
            logger.error("Failed to extract %s: %s", view_name, exc)
            raise

    # ------------------------------------------------------------------ #
    # CSV fallback (local-first)
    # ------------------------------------------------------------------ #
    def extract_from_csv(self, kpi: str, csv_path: str | Path) -> pd.DataFrame:
        """Load a KPI trend CSV as the local-first fallback source."""
        df = pd.read_csv(csv_path)
        df["kpi"] = kpi
        logger.info("Loaded %d rows for KPI '%s' from %s", len(df), kpi, csv_path)
        return df

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def extract_all(self, csv_fallback: dict | None = None) -> pd.DataFrame:
        """
        Extract all four KPI trend series and return one long-form DataFrame.

        Args:
            csv_fallback: optional mapping ``{'csat': path, 'sla': path, ...}``
                used when no DB connection is available.

        Returns:
            Long-form DataFrame with columns:
            ``client_id, date, kpi, value``.
        """
        frames: list[pd.DataFrame] = []
        for kpi, view in KPI_VIEWS.items():
            df = self._extract_one(kpi, view, csv_fallback)
            if df is None or df.empty:
                continue
            df = self._normalize(df, kpi)
            frames.append(df)

        if not frames:
            return pd.DataFrame(columns=["client_id", "date", "kpi", "value"])

        long_df = pd.concat(frames, ignore_index=True)
        logger.info(
            "Extracted %d KPI rows across %d clients",
            len(long_df),
            long_df["client_id"].nunique() if "client_id" in long_df else 0,
        )
        return long_df

    def extract_pivot(self, csv_fallback: dict | None = None) -> pd.DataFrame:
        """
        Return wide-form KPI data: one row per ``client_id`` with the latest
        value for each KPI column (``csat``, ``sla``, ``fcr``, ``aht``).

        Suitable for direct ingestion by :func:`risk_scorer.analyze_customer_population`.
        """
        long_df = self.extract_all(csv_fallback=csv_fallback)
        if long_df.empty:
            return pd.DataFrame()

        latest = (
            long_df.sort_values("date")
            .groupby(["client_id", "kpi"], as_index=False)
            .tail(1)
        )
        wide = latest.pivot_table(
            index="client_id", columns="kpi", values="value", aggfunc="last"
        ).reset_index()
        wide.columns.name = None
        return wide

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _extract_one(
        self,
        kpi: str,
        view: str,
        csv_fallback: dict | None,
    ) -> pd.DataFrame | None:
        try:
            if self.connection is not None:
                return self.extract_from_db(view)
        except (ValueError, TypeError, OSError) as exc:
            logger.warning(
                "DB extraction failed for %s (%s); trying CSV fallback", view, exc
            )

        if csv_fallback and kpi in csv_fallback:
            try:
                return self.extract_from_csv(kpi, csv_fallback[kpi])
            except (
                pd.errors.EmptyDataError,
                FileNotFoundError,
                OSError,
                ValueError,
            ) as exc:
                logger.warning("CSV fallback failed for %s: %s", kpi, exc)

        logger.warning("No data source available for KPI '%s' — skipped.", kpi)
        return None

    @staticmethod
    def _normalize(df: pd.DataFrame, kpi: str) -> pd.DataFrame:
        """Coerce heterogeneous source columns to the canonical long-form schema."""
        df = df.copy()
        # Tolerate common column aliases.
        aliases = {
            "client_id": ["client_id", "client", "account_id", "customer_id"],
            "date": ["date", "period", "as_of_date", "snapshot_date"],
            "value": ["value", kpi, "score", "metric_value"],
        }
        for canon, options in aliases.items():
            for opt in options:
                if opt in df.columns:
                    df[canon] = df[opt]
                    break
        if "kpi" not in df.columns:
            df["kpi"] = kpi
        keep = [c for c in ["client_id", "date", "kpi", "value"] if c in df.columns]
        return df[keep]


def create_sql_extractor(
    connection: Any | None = None,
    sql_dir: str | Path | None = None,
) -> SQLExtractor:
    """Factory for :class:`SQLExtractor`."""
    return SQLExtractor(connection=connection, sql_dir=sql_dir)


if __name__ == "__main__":
    print("=== CX Churn Sentinel — SQL Extractor ===")
    print("KPI views:", list(KPI_VIEWS.values()))
    print("SQL artifact dir:", DEFAULT_SQL_DIR)
    extractor = create_sql_extractor()
    # Local-first: with no connection and no CSV fallback, extract_all returns
    # an empty long-form frame rather than raising.
    print("Local-first extract_all() rows:", len(extractor.extract_all()))
