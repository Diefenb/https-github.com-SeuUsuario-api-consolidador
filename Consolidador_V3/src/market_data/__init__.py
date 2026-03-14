"""
market_data — módulo de dados de mercado para projeção pro-rata-die.

Expõe a interface principal:
    get_market_data(tipo, data_inicio, data_fim) → dados do cache ou API
"""

from .cache import SQLiteCache
from .bacen import fetch_cdi_range, fetch_ipca_ultimos

_cache = None


def get_cache() -> SQLiteCache:
    global _cache
    if _cache is None:
        _cache = SQLiteCache()
    return _cache


__all__ = [
    "SQLiteCache",
    "fetch_cdi_range",
    "fetch_ipca_ultimos",
    "get_cache",
]
