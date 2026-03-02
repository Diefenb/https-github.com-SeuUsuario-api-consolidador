"""
Parsers determinísticos para relatórios de corretoras.
Custo zero — sem IA, sem API.
"""

import pdfplumber
import logging

logger = logging.getLogger(__name__)


class UnknownFormatError(Exception):
    pass


def _extract_first_page_text(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        if pdf.pages:
            return pdf.pages[0].extract_text() or ""
    return ""


def detect_and_parse(pdf_path: str) -> dict:
    """Detecta o formato do PDF e chama o parser correto."""
    text = _extract_first_page_text(pdf_path)

    if "Relatório de" in text and ("Investimentos" in text or "XP" in text or "8660669" in text or "3245269" in text):
        from .xp_performance import parse_xp_performance
        return parse_xp_performance(pdf_path)
    elif "Relatório de Performance" in text or "API Capital" in text or "BTG" in text:
        from .btg_performance import parse_btg_performance
        return parse_btg_performance(pdf_path)
    # Fallback: tentar XP se texto contém marcadores típicos
    elif "XPerformance" in pdf_path or "XP" in pdf_path:
        from .xp_performance import parse_xp_performance
        return parse_xp_performance(pdf_path)
    else:
        raise UnknownFormatError(f"Formato não reconhecido: {pdf_path}")
