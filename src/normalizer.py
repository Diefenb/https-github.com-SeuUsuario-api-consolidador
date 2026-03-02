"""
Consolidador — Normalizador de dados extraídos.

Recebe o JSON bruto da extração e:
1. Padroniza nomes de ativos
2. Classifica por estratégia padronizada (Pós Fixado, Inflação, Pré Fixado, Multimercado, etc.)
"""

import re
import logging
from copy import deepcopy

logger = logging.getLogger(__name__)


# ============================================================================
# MAPEAMENTO DE ESTRATÉGIA PADRONIZADA
# ============================================================================

MAPA_ESTRATEGIA = {
    # XP Performance
    "pós fixado": "Pós Fixado",
    "pos fixado": "Pós Fixado",
    "pós-fixado": "Pós Fixado",
    "pos-fixado": "Pós Fixado",
    "inflação": "Inflação",
    "inflacao": "Inflação",
    "pré fixado": "Pré Fixado",
    "pre fixado": "Pré Fixado",
    "pré-fixado": "Pré Fixado",
    "pre-fixado": "Pré Fixado",
    "prefixado": "Pré Fixado",
    "pré fixado": "Pré Fixado",
    "multimercado": "Multimercado",
    "multi": "Multimercado",
    "retorno absoluto": "Multimercado",
    "retorno absoluto (mm)": "Multimercado",
    "macro": "Multimercado",
    "long short": "Multimercado",
    "long biased": "Multimercado",
    "renda variável brasil": "Renda Variável",
    "renda variavel brasil": "Renda Variável",
    "renda variável": "Renda Variável",
    "renda variavel": "Renda Variável",
    "ações": "Renda Variável",
    "acoes": "Renda Variável",
    "caixa": "Caixa",
    "saldo em conta": "Caixa",
    "proventos": "Proventos",

    # BTG / API Capital
    "renda fixa": "Pós Fixado",
    "renda fixa (cdi)": "Pós Fixado",
    "renda fixa (ipca)": "Inflação",
    "renda fixa (pré)": "Pré Fixado",
    "renda fixa (pre)": "Pré Fixado",

    # Outros
    "fundos listados": "Fundos Listados",
    "fii": "Fundos Listados",
    "etf": "Fundos Listados",
    "internacional": "Internacional",
    "renda variável global": "Internacional",
    "alternativo": "Alternativo",
    "cripto": "Alternativo",
    "previdência": "Previdência",
    "previdencia": "Previdência",
}


# ============================================================================
# FUNÇÕES DE CLASSIFICAÇÃO
# ============================================================================

def normalize_strategy(estrategia_original: str) -> str:
    """
    Mapeia estratégia original para estratégia padronizada.

    Exemplos:
        "Pós Fixado" → "Pós Fixado"
        "Pré-fixado" → "Pré Fixado"
        "Retorno Absoluto (MM)" → "Multimercado"
        "Renda Fixa (CDI)" → "Pós Fixado"
    """
    if not estrategia_original:
        return "Outros"

    key = estrategia_original.strip().lower()

    # Match exato
    if key in MAPA_ESTRATEGIA:
        return MAPA_ESTRATEGIA[key]

    # Match parcial
    for pattern, normalized in MAPA_ESTRATEGIA.items():
        if pattern in key or key in pattern:
            return normalized

    return estrategia_original  # Manter original se não encontrou


def clean_asset_name(nome_original: str) -> str:
    """
    Limpa o nome do ativo: remove espaços extras, normaliza whitespace.
    Mantém o nome essencialmente igual ao original (rastreabilidade).
    """
    if not nome_original:
        return ""

    # Normalizar whitespace
    nome = re.sub(r'\s+', ' ', nome_original.strip())

    return nome


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def normalize(data: dict) -> dict:
    """
    Normaliza os dados extraídos de um relatório.

    Adiciona campos de classificação a cada ativo:
    - estrategia_normalizada: Pós Fixado, Inflação, Multimercado, etc.

    Retorna cópia dos dados com campos adicionais (não modifica o original).
    """
    result = deepcopy(data)

    ativos = result.get("ativos", [])

    for ativo in ativos:
        nome = ativo.get("nome_original", "")

        # Normalizar estratégia
        estrategia_original = ativo.get("estrategia", "")
        estrategia_norm = normalize_strategy(estrategia_original)

        # Fundos com PREV no nome são sempre Previdência
        if re.search(r'\bPREV\b', nome, re.IGNORECASE):
            estrategia_norm = "Previdência"

        ativo["estrategia_normalizada"] = estrategia_norm

        # Limpar nome
        ativo["nome_limpo"] = clean_asset_name(nome)

    # Normalizar estratégias no composicao_por_estrategia
    for comp in result.get("composicao_por_estrategia", []):
        comp["estrategia_normalizada"] = normalize_strategy(comp.get("estrategia", ""))

    logger.info(
        f"Normalização: {len(ativos)} ativos | "
        f"Estratégia normalizada para todos"
    )

    return result
