from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .resolver import CompanyResolution, resolve_company
from .sources import DEFAULT_SOURCES, SourceDefinition, SourceResult


@dataclass
class RefreshOutcome:
    company: str
    opened: bool
    is_new_opening: bool
    evidence: str
    error: str | None


class CampusWatchStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sources (
                    company TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_opened INTEGER,
                    last_checked_at TEXT,
                    last_opened_at TEXT,
                    content_hash TEXT,
                    evidence TEXT,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS refresh_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    opened INTEGER NOT NULL,
                    is_new_opening INTEGER NOT NULL,
                    evidence TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS watch_list (
                    company TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        self.seed_defaults()

    def seed_defaults(self) -> None:
        with self._connect() as conn:
            for source in DEFAULT_SOURCES:
                conn.execute(
                    """
                    INSERT INTO sources(company, url, enabled)
                    VALUES (?, ?, 1)
                    ON CONFLICT(company) DO UPDATE SET url=excluded.url
                    """,
                    (source.company, source.url),
                )

    def list_sources(self) -> list[SourceDefinition]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT company, url FROM sources WHERE enabled = 1 ORDER BY company"
            ).fetchall()
        return [SourceDefinition(row["company"], row["url"]) for row in rows]

    def resolve_source(self, company: str) -> tuple[CompanyResolution, SourceDefinition | None]:
        resolution = resolve_company(company)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT company, url FROM sources WHERE enabled = 1 ORDER BY company"
            ).fetchall()
        source_map = {
            row["company"]: SourceDefinition(row["company"], row["url"]) for row in rows
        }
        if resolution.resolved and resolution.canonical in source_map:
            return resolution, source_map[resolution.canonical]

        target = company.strip().lower()
        fuzzy = [
            SourceDefinition(row["company"], row["url"])
            for row in rows
            if row["company"].lower() == target or target in row["company"].lower()
        ]
        if len(fuzzy) == 1:
            return resolution, fuzzy[0]
        return resolution, None

    def record_refresh(self, result: SourceResult) -> RefreshOutcome:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_opened FROM sources WHERE company = ?",
                (result.company,),
            ).fetchone()
            previous_opened = None if row is None else row["last_opened"]
            is_new_opening = bool(result.opened and previous_opened != 1)
            conn.execute(
                """
                UPDATE sources
                SET last_opened = ?,
                    last_checked_at = ?,
                    last_opened_at = CASE WHEN ? = 1 THEN ? ELSE last_opened_at END,
                    content_hash = ?,
                    evidence = ?,
                    last_error = ?
                WHERE company = ?
                """,
                (
                    1 if result.opened else 0,
                    result.checked_at,
                    1 if result.opened else 0,
                    result.checked_at,
                    result.content_hash,
                    result.evidence,
                    result.error,
                    result.company,
                ),
            )
            conn.execute(
                """
                INSERT INTO refresh_log(company, checked_at, opened, is_new_opening, evidence, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.company,
                    result.checked_at,
                    1 if result.opened else 0,
                    1 if is_new_opening else 0,
                    result.evidence,
                    result.error,
                ),
            )
        return RefreshOutcome(
            company=result.company,
            opened=result.opened,
            is_new_opening=is_new_opening,
            evidence=result.evidence,
            error=result.error,
        )

    def add_watch(self, company: str) -> str:
        resolution, source = self.resolve_source(company)
        if not source:
            if resolution.ambiguous:
                raise ValueError(f"公司名有歧义: {company}，候选: {'、'.join(resolution.candidates)}")
            raise ValueError(f"未找到公司: {company}")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO watch_list(company) VALUES (?)", (source.company,)
            )
        return source.company

    def remove_watch(self, company: str) -> str:
        resolution, source = self.resolve_source(company)
        if not source:
            if resolution.ambiguous:
                raise ValueError(f"公司名有歧义: {company}，候选: {'、'.join(resolution.candidates)}")
            raise ValueError(f"未找到公司: {company}")
        with self._connect() as conn:
            conn.execute("DELETE FROM watch_list WHERE company = ?", (source.company,))
        return source.company

    def list_watch(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT company FROM watch_list ORDER BY created_at, company"
            ).fetchall()
        return [row["company"] for row in rows]

    def list_today_openings(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT company, checked_at, evidence
                FROM refresh_log
                WHERE is_new_opening = 1
                  AND substr(checked_at, 1, 10) = date('now', 'localtime')
                ORDER BY checked_at DESC, company
                """
            ).fetchall()
        return rows

    def list_current_status(self, watch_only: bool = False) -> list[sqlite3.Row]:
        sql = """
            SELECT s.company, s.url, s.last_opened, s.last_checked_at, s.evidence, s.last_error
            FROM sources s
        """
        if watch_only:
            sql += " INNER JOIN watch_list w ON w.company = s.company"
        sql += " ORDER BY s.company"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return rows
