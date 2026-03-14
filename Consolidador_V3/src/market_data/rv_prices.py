"""
rv_prices.py — Preços de ações e FIIs via brapi.dev e yfinance (fallback).

Estratégia:
1. Tentar cache SQLite
2. Tentar brapi.dev (preferido — <1 min delay)
3. Fallback: yfinance (~15 min delay)
"""

import logging
import os
from datetime import date, timedelta
from typing import Optional

import requests

from .cache import SQLiteCache

logger = logging.getLogger(__name__)

_TIMEOUT = 10
_BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "")
_BRAPI_URL = "https://brapi.dev/api/quote/{ticker}"


# ─────────────────────────────────────────────────────────────────────────────
# brapi.dev
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_brapi_current(ticker: str) -> Optional[float]:
    """Retorna o preço atual (último fechamento) via brapi.dev."""
    params = {"token": _BRAPI_TOKEN} if _BRAPI_TOKEN else {}
    try:
        resp = requests.get(_BRAPI_URL.format(ticker=ticker), params=params, timeout=_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if results:
            return results[0].get("regularMarketPrice")
    except Exception as e:
        logger.warning(f"brapi.dev falhou para {ticker}: {e}")
    return None


def _fetch_brapi_historical(ticker: str, data_iso: str) -> Optional[float]:
    """Tenta obter preço histórico via brapi.dev."""
    params = {
        "range": "1mo",
        "interval": "1d",
    }
    if _BRAPI_TOKEN:
        params["token"] = _BRAPI_TOKEN
    try:
        url = f"https://brapi.dev/api/quote/{ticker}"
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        if resp.status_code in (404, 422):
            return None
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        hist = results[0].get("historicalDataPrice", [])
        # Procurar a data exata ou a mais próxima
        for entry in reversed(hist):
            d = entry.get("date", "")
            if isinstance(d, int):
                from datetime import datetime
                d = datetime.fromtimestamp(d).date().isoformat()
            if d <= data_iso:
                close = entry.get("close") or entry.get("adjclose")
                if close:
                    return float(close)
    except Exception as e:
        logger.warning(f"brapi.dev histórico falhou para {ticker}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# yfinance (fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_yfinance_current(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf
        tk = yf.Ticker(f"{ticker}.SA")
        info = tk.info
        return info.get("regularMarketPrice") or info.get("currentPrice")
    except Exception as e:
        logger.warning(f"yfinance falhou para {ticker}: {e}")
    return None


def _fetch_yfinance_historical(ticker: str, data_iso: str) -> Optional[float]:
    try:
        import yfinance as yf
        from datetime import datetime, timedelta
        data = datetime.fromisoformat(data_iso).date()
        tk = yf.Ticker(f"{ticker}.SA")
        hist = tk.history(start=data - timedelta(days=5), end=data + timedelta(days=1))
        if hist.empty:
            return None
        # Pegar o fechamento mais próximo à data
        for idx in reversed(hist.index):
            row_date = idx.date() if hasattr(idx, "date") else idx
            if row_date.isoformat() <= data_iso:
                return float(hist.loc[idx, "Close"])
    except Exception as e:
        logger.warning(f"yfinance histórico falhou para {ticker}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Interface principal
# ─────────────────────────────────────────────────────────────────────────────

def fetch_price_pair(
    ticker: str,
    data_ancora: date,
    data_hoje: date,
    cache: Optional[SQLiteCache] = None,
) -> tuple[Optional[float], Optional[float]]:
    """
    Retorna (preco_ancora, preco_hoje) para o ticker.
    Tenta cache → brapi → yfinance.

    Returns:
        (preco_ancora, preco_hoje)  — pode ser None se não disponível
    """
    if cache is None:
        cache = SQLiteCache()

    ancora_iso = data_ancora.isoformat()
    hoje_iso = data_hoje.isoformat()

    # 1. Cache
    preco_ancora = cache.get_preco(ticker, ancora_iso)
    preco_hoje = None
    for delta in range(0, 5):
        tentativa = (data_hoje - timedelta(days=delta)).isoformat()
        preco_hoje = cache.get_preco(ticker, tentativa)
        if preco_hoje is not None:
            break

    if preco_hoje is None:
        # 2. brapi — preço atual
        preco_hoje = _fetch_brapi_current(ticker)
        if preco_hoje:
            cache.set_preco(ticker, hoje_iso, preco_hoje)
        else:
            # Fallback yfinance
            preco_hoje = _fetch_yfinance_current(ticker)
            if preco_hoje:
                cache.set_preco(ticker, hoje_iso, preco_hoje)

    if preco_ancora is None:
        # Tentar histórico
        preco_ancora = _fetch_brapi_historical(ticker, ancora_iso)
        if preco_ancora is None:
            preco_ancora = _fetch_yfinance_historical(ticker, ancora_iso)
        if preco_ancora:
            cache.set_preco(ticker, ancora_iso, preco_ancora)

    return preco_ancora, preco_hoje
