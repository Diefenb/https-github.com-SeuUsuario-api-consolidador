"""
resolver.py — Resolução automática: nome do ativo → tipo de projeção + metadados.

Fluxo por ativo:
    Passo 1: Extração de ticker B3 por regex → rv_preco
    Passo 2: Fuzzy match CVM (registro_classe.csv) → fundo_cota
    Passo 3: Regex de indexador/taxa → cdi_pct | ipca_spread | cdi_spread | prefixado
    Passo 4: Fallback → sem_projecao

Resultados persistidos no SQLite (resolved_assets) para evitar re-execução.
"""

import logging
import re
from datetime import date
from typing import Optional

from .cache import SQLiteCache
from .cvm_funds import find_cnpj_by_name

logger = logging.getLogger(__name__)

# Threshold de confiança para fuzzy match de fundos
_SCORE_ALTA = 85.0
_SCORE_MEDIA = 70.0

# Indicadores de fundos nos nomes (CI = Capital Investimento)
_FUND_PATTERN = re.compile(
    r"\b(?:FIC|FIF|FIDC|FIA|FIRF|FICF|FUNDO|FUND|FIAGRO|FIP|CI)\b",
    re.IGNORECASE,
)

# Ticker B3: 4 letras + 1-2 dígitos
_TICKER_PATTERN = re.compile(r"\b([A-Z]{4}\d{1,2})\b")

# CDI percentual: "92,00% CDI", "100% do CDI", "115% DI"
_CDI_PCT_PATTERN = re.compile(
    r"(\d+[,.]?\d*)\s*%\s*(?:DO\s+)?(?:CDI|DI)\b",
    re.IGNORECASE,
)

# IPCA + spread: "IPC-A + 6,35%", "IPCA + 10,20%", "IPCA+ 5%"
# IPC(?:-?A)? cobre: IPCA, IPC-A, IPC
_IPCA_PATTERN = re.compile(
    r"IPC(?:-?A)?\s*\+\s*([\d,]+)%",
    re.IGNORECASE,
)

# CDI + spread: "CDI + 0,50%", "DI + 1%"
_CDI_SPREAD_PATTERN = re.compile(
    r"(?:CDI|DI)\s*\+\s*([\d,]+)%",
    re.IGNORECASE,
)

# Taxa prefixada no final do nome: "- 12,25%" ou "- 14,20% a.a."
# Cobre: CDB FACTA - DEZ/2026 - 12,25%
_PRE_PATTERN = re.compile(
    r"[-–]\s*(\d{1,2}[,.]?\d+)%(?:\s*a\.?a\.?)?\s*$",
    re.IGNORECASE,
)

# Prefixado sem separador explícito (último número com % no nome, sem CDI/IPCA)
_PRE_FALLBACK = re.compile(
    r"(\d{1,2}[,.]?\d{1,2})%",
    re.IGNORECASE,
)


def _f(s: str) -> float:
    """Converte string numérica BR (vírgula decimal) para float."""
    return float(s.replace(",", "."))


def _resolve_by_regex(nome: str) -> Optional[dict]:
    """
    Tenta resolver o tipo de projeção por regex (sem rede).
    Retorna dict com tipo_projecao e parâmetros, ou None se não reconhecido.
    """
    n = nome.strip()

    # Passo 1: CDI percentual (deve vir antes de prefixado para evitar conflito)
    m = _CDI_PCT_PATTERN.search(n)
    if m:
        return {
            "tipo_projecao": "cdi_pct",
            "pct_cdi": _f(m.group(1)),
            "confianca": "alta",
        }

    # Passo 2: IPCA + spread
    m = _IPCA_PATTERN.search(n)
    if m:
        return {
            "tipo_projecao": "ipca_spread",
            "spread_aa": _f(m.group(1)),
            "confianca": "alta",
        }

    # Passo 3: CDI + spread
    m = _CDI_SPREAD_PATTERN.search(n)
    if m:
        return {
            "tipo_projecao": "cdi_spread",
            "spread_aa": _f(m.group(1)),
            "confianca": "alta",
        }

    # Passo 4: Taxa prefixada (padrão "- XX,XX%" no final)
    m = _PRE_PATTERN.search(n)
    if m:
        return {
            "tipo_projecao": "prefixado",
            "taxa_prefixada_aa": _f(m.group(1)),
            "confianca": "alta",
        }

    return None


def _resolve_ticker(nome: str) -> Optional[dict]:
    """Extrai ticker B3 do nome do ativo."""
    m = _TICKER_PATTERN.search(nome.upper())
    if m:
        ticker = m.group(1)
        # Evitar falsos positivos comuns
        if ticker not in ("FIDC", "FUNDO", "FUND"):
            return {
                "tipo_projecao": "rv_preco",
                "ticker": ticker,
                "confianca": "alta",
            }
    return None


def _is_fund(nome: str) -> bool:
    return bool(_FUND_PATTERN.search(nome))


def resolve_asset(
    nome_original: str,
    estrategia: str = "",
    cache: Optional[SQLiteCache] = None,
    use_cvm: bool = True,
) -> dict:
    """
    Resolve o tipo de projeção de um ativo a partir do nome original.

    Args:
        nome_original: Nome do ativo como aparece no PDF/JSON.
        estrategia: Estratégia extraída do relatório (ex: "Pós Fixado").
        cache: Cache SQLite. Se None, cria um novo.
        use_cvm: Se True, tenta fuzzy match na CVM para fundos.

    Returns:
        dict com:
            tipo_projecao: 'cdi_pct' | 'cdi_spread' | 'ipca_spread' |
                           'prefixado' | 'fundo_cota' | 'rv_preco' | 'sem_projecao'
            confianca: 'alta' | 'media' | 'baixa' | 'nenhuma'
            pct_cdi, spread_aa, taxa_prefixada_aa, cnpj, ticker (conforme o tipo)
            match_score: float (para fuzzy match)
    """
    if cache is None:
        cache = SQLiteCache()

    # 1. Verificar cache persistido
    cached = cache.get_resolved(nome_original)
    if cached and cached.get("override_manual", 0) == 1:
        return cached  # Nunca sobrescrever correção manual
    if cached and cached.get("tipo_projecao"):
        return cached

    resultado: dict = {
        "nome_original": nome_original,
        "tipo_projecao": "sem_projecao",
        "cnpj": None,
        "ticker": None,
        "pct_cdi": None,
        "spread_aa": None,
        "taxa_prefixada_aa": None,
        "match_score": None,
        "confianca": "nenhuma",
    }

    # Passo A: Regex de indexador/taxa (mais confiável, sem rede)
    by_regex = _resolve_by_regex(nome_original)
    if by_regex:
        resultado.update(by_regex)
        cache.set_resolved(nome_original, resultado)
        return resultado

    # Passo B: Verificar se é fundo pelo padrão do nome
    if _is_fund(nome_original):
        resultado["tipo_projecao"] = "fundo_cota"
        resultado["confianca"] = "alta" if not use_cvm else "media"

        if use_cvm:
            cnpj, score = find_cnpj_by_name(nome_original)
            resultado["match_score"] = score
            resultado["cnpj"] = cnpj

            if score >= _SCORE_ALTA:
                resultado["confianca"] = "alta"
            elif score >= _SCORE_MEDIA:
                resultado["confianca"] = "media"
            else:
                resultado["cnpj"] = None
                resultado["confianca"] = "baixa"

        cache.set_resolved(nome_original, resultado)
        return resultado

    # Passo C: Extração de ticker B3
    by_ticker = _resolve_ticker(nome_original)
    if by_ticker:
        resultado.update(by_ticker)
        cache.set_resolved(nome_original, resultado)
        return resultado

    # Passo D: Fallback — tentar taxa prefixada genérica
    m = _PRE_FALLBACK.search(nome_original)
    if m and any(kw in nome_original.upper() for kw in ["CDB", "CRA", "CRI", "LCI", "LCA", "LCD", "DEB", "NTN"]):
        resultado["tipo_projecao"] = "prefixado"
        resultado["taxa_prefixada_aa"] = _f(m.group(1))
        resultado["confianca"] = "baixa"
        cache.set_resolved(nome_original, resultado)
        return resultado

    # Nenhuma regra aplicável
    cache.set_resolved(nome_original, resultado)
    return resultado


def resolve_portfolio(
    ativos: list[dict],
    cache: Optional[SQLiteCache] = None,
    use_cvm: bool = True,
) -> list[dict]:
    """
    Resolve todos os ativos de um portfólio.

    Args:
        ativos: Lista de ativos no formato do JSON canônico.
        cache: Cache SQLite compartilhado.
        use_cvm: Se True, habilita fuzzy match CVM para fundos.

    Returns:
        Lista de ativos com campo '_projecao' adicionado.
    """
    if cache is None:
        cache = SQLiteCache()

    resultado = []
    for ativo in ativos:
        nome = ativo.get("nome_original", "")
        estrategia = ativo.get("estrategia", "")
        projecao = resolve_asset(nome, estrategia, cache=cache, use_cvm=use_cvm)

        ativo_enriquecido = dict(ativo)
        ativo_enriquecido["_projecao"] = projecao
        resultado.append(ativo_enriquecido)

    return resultado


def cobertura_report(ativos_enriquecidos: list[dict]) -> dict:
    """Retorna estatísticas de cobertura da resolução."""
    total = len(ativos_enriquecidos)
    if total == 0:
        return {"total": 0}

    por_tipo: dict[str, int] = {}
    por_confianca: dict[str, int] = {}

    for a in ativos_enriquecidos:
        p = a.get("_projecao", {})
        tipo = p.get("tipo_projecao", "sem_projecao")
        conf = p.get("confianca", "nenhuma")
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
        por_confianca[conf] = por_confianca.get(conf, 0) + 1

    com_projecao = total - por_tipo.get("sem_projecao", 0)
    return {
        "total": total,
        "com_projecao": com_projecao,
        "sem_projecao": por_tipo.get("sem_projecao", 0),
        "cobertura_pct": round(com_projecao / total * 100, 1),
        "por_tipo": por_tipo,
        "por_confianca": por_confianca,
    }
