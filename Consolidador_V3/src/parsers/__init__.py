"""
Parsers determinísticos para relatórios de corretoras.
Custo zero — sem IA, sem API.
"""

import pdfplumber
import logging

logger = logging.getLogger(__name__)


class UnknownFormatError(Exception):
    pass


def _extract_first_pages_text(pdf_path: str, n_pages: int = 2) -> str:
    """Extrai texto das primeiras N páginas para detecção de formato."""
    texts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:n_pages]:
            texts.append(page.extract_text() or "")
    return "\n".join(texts)


def detect_and_parse(pdf_path: str) -> dict:
    """
    Detecta o formato do PDF e chama o parser correto.

    Detecção:
      - BTG: 'Relatório de Performance' (pode ter \\n entre palavras) ou 'API Capital'
      - XP:  'Relatório de Investimentos' ou indicadores XP ('Exclusive','Signature','XP')
    """
    # Lê as 2 primeiras páginas para detecção robusta
    # (\x00 substitui alguns chars — usar 'Relat' como prefixo comum)
    text = _extract_first_pages_text(pdf_path, n_pages=2)

    # Detecção BTG: título pode ser "Relatório\nde Performance" (com \n)
    # ou ter \x00 no lugar de caracteres acentuados
    import re
    is_btg = bool(
        re.search(r"Relat.{0,4}rio\s*[\n\s]+de\s+Performance", text) or
        re.search(r"Relat.{0,4}rio\s+de\s+Performance", text) or
        "API Capital" in text or
        "BTG Pactual" in text or
        "BTG PACTUAL" in text
    )

    is_xp = bool(
        "Relatório de Investimentos" in text or
        re.search(r"Relat.{0,4}rio\s+de\s+Investimentos", text) or
        "XPerformance" in text or
        re.search(r"\bXP\b.*Exclusive|Exclusive.*\bXP\b", text) or
        re.search(r"\bExclusive\b|\bSignature\b|\bPrivate\b", text)
    )

    if is_btg:
        from .btg_performance import parse_btg_performance
        return parse_btg_performance(pdf_path)
    elif is_xp:
        from .xp_performance import parse_xp_performance
        return parse_xp_performance(pdf_path)
    else:
        raise UnknownFormatError(f"Formato não reconhecido: {pdf_path}")
