"""
Parser determinístico para BTG Pactual (Relatório de Performance).
Esqueleto base para extração via pdfplumber compatível com a V3.

Aviso: A implementação exata de regex requer análise da estrutura
textual específica de um PDF do BTG.
"""

import re
import logging
import os
import pdfplumber

logger = logging.getLogger(__name__)

def _parse_capa(text: str, arquivo_origem: str) -> dict:
    """Extrai metadados básicos."""
    meta = {
        "cliente": "Cliente BTG Padrão",  # TODO: Regex real
        "conta": "000000",
        "segmento": "Wealth",
        "parceiro": None,
        "data_referencia": None,
        "arquivo_origem": os.path.basename(arquivo_origem),
    }
    
    # Exemplo simples de busca de conta
    m = re.search(r"Conta:\s*(\d+)", text, re.IGNORECASE)
    if m:
        meta["conta"] = m.group(1)
        
    return meta

def _parse_resumo(text: str) -> dict:
    """Extrai patrimônio bruto."""
    resumo = {
        "patrimonio_total_bruto": 0.0
    }
    # Tenta encontrar formato comum de total
    m = re.search(r"Total(?: Geral)?.*?R\$\s*([\d.,]+)", text, re.IGNORECASE)
    if m:
        val_str = m.group(1).replace(".", "").replace(",", ".")
        try:
            resumo["patrimonio_total_bruto"] = float(val_str)
        except:
            pass
    return resumo

def parse_btg_performance(pdf_path: str) -> dict:
    """
    Função de entrada para o pipeline da V3.
    """
    logger.info(f"Iniciando conversão BTG: {os.path.basename(pdf_path)}")
    
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
            
    full_text = "\n".join(pages_text)
    
    # Montagem da estrutura V2 esperada pelo consolidador
    result = {
        "$schema": "consolidador-v2",
        "meta": {
            **_parse_capa(pages_text[0] if pages_text else "", pdf_path),
            "corretora": "BTG",
            "tipo_relatorio": "btg_performance",
        },
        "resumo_carteira": _parse_resumo(full_text),
        "benchmarks": {},
        "estatistica_historica": {},
        "composicao_por_estrategia": [],
        "rentabilidade_historica_mensal": [],
        "evolucao_patrimonial": [],
        "ativos": [],  # TODO: iterar páginas de posições
        "movimentacoes": []
    }
    
    logger.warning("Parser BTG (skeleton) utilizado. Dados numéricos completos não extraídos.")
    return result
