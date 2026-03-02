"""
Consolidador — Utilitários de formatação e parsing de números brasileiros.
"""

import re
import logging

logger = logging.getLogger(__name__)


def parse_br_currency(text: str) -> float | None:
    """
    Converte texto de moeda brasileira para float.
    
    Exemplos:
        "R$ 1.826.076,84"  → 1826076.84
        "-R$ 52,85"         → -52.85
        "R$ -52,85"         → -52.85
        "1.826.076,84"      → 1826076.84
        ""                  → None
    """
    if text is None or str(text).strip() == "" or str(text).strip() == "-":
        return None
    
    text = str(text).strip()
    
    # Detectar sinal negativo
    negative = False
    if "-" in text:
        negative = True
        text = text.replace("-", "")
    
    # Remover "R$" e espaços
    text = text.replace("R$", "").strip()
    
    # Remover pontos de milhar e trocar vírgula por ponto decimal
    text = text.replace(".", "").replace(",", ".")
    
    try:
        value = float(text)
        return -value if negative else value
    except ValueError:
        logger.warning(f"Não foi possível converter moeda: '{text}'")
        return None


def parse_br_percentage(text: str) -> float | None:
    """
    Converte texto de percentual brasileiro para float.
    
    Exemplos:
        "1,73%"   → 1.73
        "-0,66%"  → -0.66
        "148,67"  → 148.67
        ""        → None
    """
    if text is None or str(text).strip() == "" or str(text).strip() == "-":
        return None
    
    text = str(text).strip().replace("%", "").strip()
    
    # Detectar sinal negativo
    negative = False
    if text.startswith("-"):
        negative = True
        text = text[1:]
    
    # Trocar vírgula por ponto decimal
    # Cuidado: se tem ponto E vírgula, o ponto é milhar
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    
    try:
        value = float(text)
        return -value if negative else value
    except ValueError:
        logger.warning(f"Não foi possível converter percentual: '{text}'")
        return None


def format_br_currency(value: float | None) -> str:
    """
    Formata float como moeda brasileira.
    
    Exemplos:
        1826076.84  → "R$ 1.826.076,84"
        -52.85      → "-R$ 52,85"
        None        → ""
    """
    if value is None:
        return ""
    
    negative = value < 0
    value = abs(value)
    
    # Formatar com 2 casas decimais
    formatted = f"{value:,.2f}"
    # Trocar separadores: , → X, . → ,, X → .
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    
    if negative:
        return f"-R$ {formatted}"
    return f"R$ {formatted}"


def format_br_percentage(value: float | None) -> str:
    """
    Formata float como percentual brasileiro.
    
    Exemplos:
        1.73    → "1,73%"
        -0.66   → "-0,66%"
        148.67  → "148,67%"
        None    → ""
    """
    if value is None:
        return ""
    
    formatted = f"{value:.2f}".replace(".", ",")
    return f"{formatted}%"


def safe_float(value) -> float | None:
    """Converte valor para float de forma segura. Retorna None se impossível."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        # Tenta converter string
        text = str(value).strip()
        if text == "" or text == "-" or text.lower() == "null" or text.lower() == "none":
            return None
        # Se parece com formato BR (tem vírgula como decimal)
        if "," in text:
            return parse_br_currency(text)
        return float(text)
    except (ValueError, TypeError):
        return None


def safe_int(value) -> int | None:
    """Converte valor para int de forma segura. Retorna None se impossível."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
