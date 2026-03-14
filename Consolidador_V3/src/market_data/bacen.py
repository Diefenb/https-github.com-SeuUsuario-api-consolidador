"""
bacen.py — Acesso à API BACEN SGS (Sistema Gerenciador de Séries Temporais).

Séries utilizadas:
    12   → CDI Over Taxa — retorna TAXA DIÁRIA em % (ex: 0.055131 = 0.055131% ao dia)
    433  → IPCA (% mensal)
    13522→ IPCA-15 (% mensal — preview do mês corrente)

ATENÇÃO: A série 12 retorna a taxa CDI DIÁRIA em %, não a taxa anualizada.
    0.055131% ao dia * 252 ≈ 13.89% ao ano (linearmente)
    (1 + 0.00055131)^252 - 1 ≈ 14.9% ao ano (composto)
"""

import logging
from datetime import date, timedelta
from typing import Optional

import requests

from .cache import SQLiteCache

logger = logging.getLogger(__name__)

_BACEN_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial={di}&dataFinal={df}"
_BACEN_LAST = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/{n}?formato=json"

_TIMEOUT = 15  # segundos
_SERIE_CDI   = 12
_SERIE_IPCA  = 433
_SERIE_IPCA15 = 13522


def _fmt(d: date) -> str:
    """Formata data para a API BACEN: DD/MM/YYYY."""
    return d.strftime("%d/%m/%Y")


def _iso(d_str: str) -> str:
    """Converte DD/MM/YYYY → YYYY-MM-DD."""
    parts = d_str.strip().split("/")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return d_str


def _fetch_serie(serie: int, data_ini: date, data_fim: date) -> list[dict]:
    """Busca série SGS entre duas datas. Retorna lista de {data: str, valor: str}."""
    url = _BACEN_BASE.format(
        serie=serie,
        di=_fmt(data_ini),
        df=_fmt(data_fim),
    )
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"BACEN SGS série {serie} falhou: {e}")
        return []


def _fetch_last(serie: int, n: int = 36) -> list[dict]:
    url = _BACEN_LAST.format(serie=serie, n=n)
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"BACEN SGS série {serie} (últimos {n}) falhou: {e}")
        return []


def fetch_cdi_range(
    data_inicio: date,
    data_fim: date,
    cache: Optional[SQLiteCache] = None,
) -> dict[str, float]:
    """
    Retorna taxa CDI diária (% a.a.) para cada dia útil no intervalo.

    Returns:
        {data_iso: taxa_aa_pct}  ex: {"2026-02-03": 13.65, ...}
    """
    if cache is None:
        cache = SQLiteCache()

    ini_iso = data_inicio.isoformat()
    fim_iso = data_fim.isoformat()

    # Tentar cache primeiro
    cached = cache.get_taxas_range("CDI", ini_iso, fim_iso)

    # Verificar se cobrimos o intervalo razoavelmente (> 80% dos dias esperados)
    dias_corridos = (data_fim - data_inicio).days
    dias_uteis_estimados = max(1, int(dias_corridos * 5 / 7))
    if len(cached) >= dias_uteis_estimados * 0.8:
        return cached

    # Buscar da API
    logger.info(f"Buscando CDI BACEN SGS {data_inicio} → {data_fim}")
    registros = _fetch_serie(_SERIE_CDI, data_inicio, data_fim)

    resultado: dict[str, float] = {}
    for r in registros:
        try:
            data_iso = _iso(r["data"])
            valor = float(r["valor"].replace(",", "."))
            resultado[data_iso] = valor
        except (KeyError, ValueError):
            continue

    if resultado:
        cache.set_taxas("CDI", resultado)
        # Merge com cache existente
        cached.update(resultado)

    return cached if cached else resultado


def fetch_ipca_ultimos(
    n: int = 24,
    cache: Optional[SQLiteCache] = None,
) -> list[dict]:
    """
    Retorna os últimos N meses de IPCA.

    Returns:
        [{"data": "YYYY-MM", "valor_pct": 0.16}, ...]  ordem crescente
    """
    if cache is None:
        cache = SQLiteCache()

    hoje = date.today()
    ini = date(hoje.year - 2, hoje.month, 1)
    cached_raw = cache.get_taxas_range("IPCA", ini.isoformat(), hoje.isoformat())

    if len(cached_raw) >= n * 0.8:
        return _ipca_dict_to_list(cached_raw, n)

    logger.info("Buscando IPCA mensal BACEN SGS (range)")
    # Série 433 funciona melhor com intervalo de datas do que com /ultimos
    data_ini_ipca = date(hoje.year - 2, 1, 1)
    registros = _fetch_serie(_SERIE_IPCA, data_ini_ipca, hoje)

    if not registros:
        # Fallback: tentar /ultimos
        registros = _fetch_last(_SERIE_IPCA, n)

    resultado: dict[str, float] = {}
    for r in registros:
        try:
            data_iso = _iso(r["data"])[:7]  # YYYY-MM
            valor = float(r["valor"].replace(",", "."))
            resultado[data_iso] = valor
        except (KeyError, ValueError):
            continue

    if resultado:
        para_cache = {f"{k}-01": v for k, v in resultado.items()}
        cache.set_taxas("IPCA", para_cache)

    return _ipca_dict_to_list(resultado, n)


def _ipca_dict_to_list(d: dict[str, float], n: int) -> list[dict]:
    """Converte dict {YYYY-MM ou YYYY-MM-DD: valor} para lista ordenada."""
    result = []
    for k, v in sorted(d.items()):
        mes = k[:7]  # YYYY-MM
        if mes not in [r["data"] for r in result]:
            result.append({"data": mes, "valor_pct": v})
    return result[-n:]


def cdi_taxa_diaria(taxa_diaria_pct: float) -> float:
    """
    Converte taxa CDI diária em % (como retornada pela BACEN série 12)
    para taxa decimal diária.
    Ex: 0.055131 → 0.00055131
    """
    return taxa_diaria_pct / 100.0
