"""
Importador de arquivos manuais (JSON) para a arquitetura V3.

Recebe um JSON extraído manualmente ou legado, injeta a estrutura
mínima "consolidador-v2" se necessário e retorna o dicionário pronto
para o pipeline de normalização e consolidação.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

def import_manual_json(file_path: str) -> dict:
    """
    Lê um arquivo JSON e formata no padrão esperado pela V3.
    
    Args:
        file_path: Caminho do arquivo .json
        
    Returns:
        Dict compatível com "consolidador-v2"
    """
    logger.info(f"Importando arquivo manual: {os.path.basename(file_path)}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Verificação de sanitização do schema
    schema_ver = data.get("$schema")
    
    if schema_ver != "consolidador-v2":
        logger.warning("Schema diferente de 'consolidador-v2' detectado. Adequando estrutura.")
        
        # Envelopando os dados legados num novo container
        novo_data = {
            "$schema": "consolidador-v2",
            "meta": data.get("meta", {}),
            "resumo_carteira": data.get("resumo_carteira", {}),
            "benchmarks": data.get("benchmarks", {}),
            "estatistica_historica": data.get("estatistica_historica", {}),
            "composicao_por_estrategia": data.get("composicao_por_estrategia", []),
            "rentabilidade_historica_mensal": data.get("rentabilidade_historica_mensal", []),
            "evolucao_patrimonial": data.get("evolucao_patrimonial", []),
            "ativos": data.get("ativos", []),
            "movimentacoes": data.get("movimentacoes", [])
        }
        
        # Fallbacks obrigatórios para evitar quebra no consolidator.py
        if not novo_data["meta"].get("corretora"):
            novo_data["meta"]["corretora"] = "Manual / Importado"
            
        data = novo_data
        
    return data
