"""
SQLiteCache — cache local com TTL para dados de mercado.

Tabelas:
    taxas_diarias(data, serie, valor, updated_at)   — CDI, SELIC, IPCA
    cotas_fundos(cnpj, data, valor_cota, updated_at) — cotas CVM
    precos_rv(ticker, data, fechamento, updated_at)  — ações/FIIs
    resolved_assets(nome_original, ...)              — resolução nome→tipo/CNPJ/ticker
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

# Caminho padrão: <raiz_projeto>/data/market_data/market_cache.db
# __file__ = .../Consolidador_V3/src/market_data/cache.py → 4x .parent = .../Consolidador/
_DEFAULT_DB = Path(__file__).parent.parent.parent.parent / "data" / "market_data" / "market_cache.db"

_DDL = """
CREATE TABLE IF NOT EXISTS taxas_diarias (
    data       TEXT NOT NULL,
    serie      TEXT NOT NULL,
    valor      REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (data, serie)
);

CREATE TABLE IF NOT EXISTS cotas_fundos (
    cnpj       TEXT NOT NULL,
    data       TEXT NOT NULL,
    valor_cota REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (cnpj, data)
);

CREATE TABLE IF NOT EXISTS precos_rv (
    ticker     TEXT NOT NULL,
    data       TEXT NOT NULL,
    fechamento REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (ticker, data)
);

CREATE TABLE IF NOT EXISTS resolved_assets (
    nome_original      TEXT PRIMARY KEY,
    tipo_projecao      TEXT,
    cnpj               TEXT,
    ticker             TEXT,
    pct_cdi            REAL,
    spread_aa          REAL,
    taxa_prefixada_aa  REAL,
    match_score        REAL,
    confianca          TEXT,
    resolved_at        TEXT,
    override_manual    INTEGER DEFAULT 0
);
"""


class SQLiteCache:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript(_DDL)

    def _now(self) -> str:
        return datetime.now().isoformat()

    # ------------------------------------------------------------------ #
    #  taxas_diarias                                                       #
    # ------------------------------------------------------------------ #

    def get_taxas_range(self, serie: str, data_ini: str, data_fim: str) -> dict[str, float]:
        """Retorna {data_iso: valor} para o intervalo, somente do cache."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data, valor FROM taxas_diarias WHERE serie=? AND data>=? AND data<=?",
                (serie, data_ini, data_fim),
            ).fetchall()
        return {r["data"]: r["valor"] for r in rows}

    def set_taxas(self, serie: str, registros: dict[str, float]):
        """Insere/atualiza registros {data_iso: valor} para a série."""
        now = self._now()
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO taxas_diarias(data, serie, valor, updated_at) VALUES(?,?,?,?)",
                [(d, serie, v, now) for d, v in registros.items()],
            )

    # ------------------------------------------------------------------ #
    #  cotas_fundos                                                        #
    # ------------------------------------------------------------------ #

    def get_cota(self, cnpj: str, data: str) -> Optional[float]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT valor_cota FROM cotas_fundos WHERE cnpj=? AND data=?",
                (cnpj, data),
            ).fetchone()
        return row["valor_cota"] if row else None

    def set_cota(self, cnpj: str, data: str, valor: float):
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cotas_fundos(cnpj, data, valor_cota, updated_at) VALUES(?,?,?,?)",
                (cnpj, data, valor, now),
            )

    def get_cotas_range(self, cnpj: str, data_ini: str, data_fim: str) -> dict[str, float]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data, valor_cota FROM cotas_fundos WHERE cnpj=? AND data>=? AND data<=?",
                (cnpj, data_ini, data_fim),
            ).fetchall()
        return {r["data"]: r["valor_cota"] for r in rows}

    def set_cotas_bulk(self, cnpj: str, registros: dict[str, float]):
        now = self._now()
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO cotas_fundos(cnpj, data, valor_cota, updated_at) VALUES(?,?,?,?)",
                [(cnpj, d, v, now) for d, v in registros.items()],
            )

    # ------------------------------------------------------------------ #
    #  precos_rv                                                           #
    # ------------------------------------------------------------------ #

    def get_precos_range(self, ticker: str, data_ini: str, data_fim: str) -> dict[str, float]:
        """Retorna {date_iso: preco} para o ticker no intervalo."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data, fechamento FROM precos_rv "
                "WHERE ticker=? AND data>=? AND data<=? ORDER BY data",
                (ticker, data_ini, data_fim),
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def set_precos_bulk(self, ticker: str, serie: dict[str, float]) -> None:
        """Salva múltiplos preços de uma vez."""
        from datetime import date as _date
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO precos_rv (ticker, data, fechamento, updated_at) VALUES (?,?,?,?)",
                [(ticker, d, v, _date.today().isoformat()) for d, v in serie.items()],
            )

    def get_preco(self, ticker: str, data: str) -> Optional[float]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT fechamento FROM precos_rv WHERE ticker=? AND data=?",
                (ticker, data),
            ).fetchone()
        return row["fechamento"] if row else None

    def set_preco(self, ticker: str, data: str, fechamento: float):
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO precos_rv(ticker, data, fechamento, updated_at) VALUES(?,?,?,?)",
                (ticker, data, fechamento, now),
            )

    # ------------------------------------------------------------------ #
    #  resolved_assets                                                     #
    # ------------------------------------------------------------------ #

    def get_resolved(self, nome_original: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM resolved_assets WHERE nome_original=?",
                (nome_original,),
            ).fetchone()
        return dict(row) if row else None

    def set_resolved(self, nome_original: str, dados: dict):
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO resolved_assets
                   (nome_original, tipo_projecao, cnpj, ticker, pct_cdi,
                    spread_aa, taxa_prefixada_aa, match_score, confianca,
                    resolved_at, override_manual)
                   VALUES (?,?,?,?,?,?,?,?,?,?,COALESCE(
                       (SELECT override_manual FROM resolved_assets WHERE nome_original=?), 0
                   ))""",
                (
                    nome_original,
                    dados.get("tipo_projecao"),
                    dados.get("cnpj"),
                    dados.get("ticker"),
                    dados.get("pct_cdi"),
                    dados.get("spread_aa"),
                    dados.get("taxa_prefixada_aa"),
                    dados.get("match_score"),
                    dados.get("confianca"),
                    now,
                    nome_original,
                ),
            )

    def get_all_resolved(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM resolved_assets").fetchall()
        return [dict(r) for r in rows]
