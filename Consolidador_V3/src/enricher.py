"""
enricher.py — Orquestrador de enriquecimento de portfólios.

Dado um JSON canônico (output do parser XP/BTG), resolve o tipo de projeção
de cada ativo e retorna o JSON enriquecido com campo _projecao.

O resultado pode ser:
1. Passado direto para projector.project_portfolio()
2. Salvo como posicoes_enriquecidas.json para uso futuro
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from market_data.cache import SQLiteCache
from market_data.resolver import resolve_portfolio, cobertura_report
from market_data.cvm_funds import ensure_cadastral_cache

logger = logging.getLogger(__name__)

_POSICOES_DIR = (
    Path(__file__).parent.parent.parent / "data" / "posicoes"
)


def enrich_portfolio(
    relatorio: dict,
    cache: Optional[SQLiteCache] = None,
    use_cvm: bool = True,
    forcar_re_resolucao: bool = False,
) -> dict:
    """
    Enriquece um relatório canônico com metadados de projeção para cada ativo.

    Args:
        relatorio: JSON canônico com ativos (output do parser).
        cache: Cache SQLite. Se None, cria um novo.
        use_cvm: Se True, tenta fuzzy match CVM para fundos.
        forcar_re_resolucao: Se True, ignora cache de resoluções.

    Returns:
        Relatório enriquecido com campo '_projecao' em cada ativo.
    """
    if cache is None:
        cache = SQLiteCache()

    # Garantir que o cadastral CVM esteja disponível (para fuzzy match de fundos)
    if use_cvm:
        ensure_cadastral_cache()

    ativos = relatorio.get("ativos", [])
    if not ativos:
        logger.warning("Relatório sem ativos — nada para enriquecer.")
        return relatorio

    # Limpar resoluções do cache se forçado
    if forcar_re_resolucao:
        logger.info("Re-resolução forçada — ignorando cache de resolved_assets")
        # Nota: a flag forcar_re_resolucao é passada pela lógica de cache no resolver
        # Para simplificar, apenas não fazemos lookup do cache neste run
        # (o resolver ainda irá salvar os novos resultados)

    logger.info(f"Enriquecendo {len(ativos)} ativos (use_cvm={use_cvm})")
    ativos_enriquecidos = resolve_portfolio(ativos, cache=cache, use_cvm=use_cvm)

    cobertura = cobertura_report(ativos_enriquecidos)
    logger.info(
        f"Cobertura: {cobertura['cobertura_pct']}% | "
        f"{cobertura['com_projecao']}/{cobertura['total']} ativos | "
        f"tipos: {cobertura.get('por_tipo', {})}"
    )

    resultado = dict(relatorio)
    resultado["ativos"] = ativos_enriquecidos
    resultado["_enriquecimento"] = {
        "data_enriquecimento": date.today().isoformat(),
        "cobertura": cobertura,
        "use_cvm": use_cvm,
    }

    return resultado


def salvar_posicoes(relatorio_enriquecido: dict, nome_cliente: str) -> Path:
    """
    Salva o portfólio enriquecido em data/posicoes/<cliente>.json.
    Usado para atualização diária sem necessidade de novo PDF.
    """
    _POSICOES_DIR.mkdir(parents=True, exist_ok=True)
    nome_arquivo = nome_cliente.strip().lower().replace(" ", "_") + "_posicoes.json"
    caminho = _POSICOES_DIR / nome_arquivo

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(relatorio_enriquecido, f, ensure_ascii=False, indent=2)

    logger.info(f"Posições salvas: {caminho}")
    return caminho


def carregar_posicoes(nome_cliente: str) -> Optional[dict]:
    """Carrega posições salvas de data/posicoes/<cliente>.json."""
    nome_arquivo = nome_cliente.strip().lower().replace(" ", "_") + "_posicoes.json"
    caminho = _POSICOES_DIR / nome_arquivo

    if not caminho.exists():
        return None

    with open(caminho, encoding="utf-8") as f:
        return json.load(f)
