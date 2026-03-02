"""
Consolidador — Consolidação de múltiplos relatórios normalizados.

Recebe lista de JSONs normalizados (um por conta/relatório) e:
1. Agrega patrimônio total entre todas as contas
2. Gera lista unificada de ativos com indicação de corretora/conta
3. Recalcula % de alocação sobre o total consolidado
4. Agrega saldos por estratégia/classe/tipo
5. Unifica movimentações ordenadas por data
"""

import logging
from collections import defaultdict
from copy import deepcopy

logger = logging.getLogger(__name__)


def consolidate(reports: list[dict], cliente: str = None, data_referencia: str = None) -> dict:
    """
    Consolida múltiplos relatórios normalizados em uma visão unificada.
    
    Args:
        reports: Lista de dicts no formato consolidador-v2 (já normalizados).
        cliente: Nome do cliente (opcional, pega do primeiro report se não fornecido).
        data_referencia: Data de referência (opcional, pega do primeiro report).
    
    Returns:
        Dict com dados consolidados.
    """
    if not reports:
        raise ValueError("Nenhum relatório fornecido para consolidação")
    
    # Metadata
    if not cliente:
        cliente = reports[0].get("meta", {}).get("cliente", "Desconhecido")
    if not data_referencia:
        data_referencia = reports[0].get("meta", {}).get("data_referencia", "")
    
    # ========================================================================
    # 1. Resumo por conta
    # ========================================================================
    contas = []
    patrimonio_total = 0.0
    
    for report in reports:
        meta = report.get("meta", {})
        resumo = report.get("resumo_carteira", {})
        patrimonio = resumo.get("patrimonio_total_bruto", 0)
        patrimonio_total += patrimonio
        
        contas.append({
            "corretora": meta.get("corretora", "?"),
            "conta": meta.get("conta", "?"),
            "segmento": meta.get("segmento"),
            "patrimonio_bruto": patrimonio,
            "rentabilidade_mes_pct": resumo.get("rentabilidade_mes_pct"),
            "pct_cdi_mes": resumo.get("pct_cdi_mes"),
            "rentabilidade_ano_pct": resumo.get("rentabilidade_ano_pct"),
            "pct_cdi_ano": resumo.get("pct_cdi_ano"),
            "ganho_mes_rs": resumo.get("ganho_mes_rs"),
            "ganho_ano_rs": resumo.get("ganho_ano_rs"),
        })
    
    logger.info(f"Consolidando {len(reports)} contas | Patrimônio total: R$ {patrimonio_total:,.2f}")
    
    # ========================================================================
    # 2. Ativos consolidados (todos os ativos de todas as contas)
    # ========================================================================
    ativos_consolidados = []
    
    for report in reports:
        meta = report.get("meta", {})
        corretora = meta.get("corretora", "?")
        conta = meta.get("conta", "?")
        
        for ativo in report.get("ativos", []):
            ativo_consolidado = deepcopy(ativo)
            ativo_consolidado["corretora"] = corretora
            ativo_consolidado["conta"] = conta
            
            # Recalcular % sobre o total consolidado
            saldo = ativo.get("saldo_bruto", 0)
            if patrimonio_total > 0:
                ativo_consolidado["pct_total_consolidado"] = round(
                    saldo / patrimonio_total * 100, 2
                )
            else:
                ativo_consolidado["pct_total_consolidado"] = 0
            
            ativos_consolidados.append(ativo_consolidado)
    
    # Ordenar por estratégia (asc) → saldo bruto (desc)
    ativos_consolidados.sort(
        key=lambda a: (
            a.get("estrategia_normalizada", a.get("estrategia", "ZZZ")),
            -(a.get("saldo_bruto", 0))
        )
    )
    
    logger.info(f"Ativos consolidados: {len(ativos_consolidados)}")
    
    # ========================================================================
    # 3. Alocação por Estratégia
    # ========================================================================
    por_estrategia = defaultdict(float)
    for ativo in ativos_consolidados:
        estrategia = ativo.get("estrategia_normalizada", ativo.get("estrategia", "Outros"))
        por_estrategia[estrategia] += ativo.get("saldo_bruto", 0)
    
    alocacao_estrategia = []
    for estrategia, saldo in sorted(por_estrategia.items(), key=lambda x: -x[1]):
        pct = round(saldo / patrimonio_total * 100, 2) if patrimonio_total > 0 else 0
        alocacao_estrategia.append({
            "estrategia": estrategia,
            "saldo_bruto": round(saldo, 2),
            "pct_total": pct,
        })
    
    # ========================================================================
    # 4. Alocação por Corretora
    # ========================================================================
    por_corretora = defaultdict(float)
    for conta_info in contas:
        key = f"{conta_info['corretora']} ({conta_info['conta']})"
        por_corretora[key] += conta_info["patrimonio_bruto"]
    
    alocacao_corretora = []
    for corretora, saldo in sorted(por_corretora.items(), key=lambda x: -x[1]):
        pct = round(saldo / patrimonio_total * 100, 2) if patrimonio_total > 0 else 0
        alocacao_corretora.append({
            "corretora": corretora,
            "saldo_bruto": round(saldo, 2),
            "pct_total": pct,
        })
    
    # ========================================================================
    # 6. Benchmarks (pegar do primeiro relatório que tiver)
    # ========================================================================
    benchmarks = {}
    for report in reports:
        b = report.get("benchmarks", {})
        if b and b.get("cdi", {}).get("mes") is not None:
            benchmarks = deepcopy(b)
            break
    
    # ========================================================================
    # 7. Rentabilidade histórica por conta (copiar sem alterar)
    # ========================================================================
    rentabilidade_por_conta = []
    for report in reports:
        meta = report.get("meta", {})
        rent_hist = report.get("rentabilidade_historica_mensal", [])
        if rent_hist:
            rentabilidade_por_conta.append({
                "corretora": meta.get("corretora", "?"),
                "conta": meta.get("conta", "?"),
                "rentabilidade_historica_mensal": deepcopy(rent_hist),
            })
    
    # ========================================================================
    # 8. Evolução patrimonial por conta (copiar sem alterar)
    # ========================================================================
    evolucao_por_conta = []
    for report in reports:
        meta = report.get("meta", {})
        evolucao = report.get("evolucao_patrimonial", [])
        if evolucao:
            evolucao_por_conta.append({
                "corretora": meta.get("corretora", "?"),
                "conta": meta.get("conta", "?"),
                "evolucao_patrimonial": deepcopy(evolucao),
            })
    
    # ========================================================================
    # 9. Movimentações unificadas (todas as contas, ordenadas por data desc)
    # ========================================================================
    movimentacoes = []
    for report in reports:
        meta = report.get("meta", {})
        corretora = meta.get("corretora", "?")
        conta = meta.get("conta", "?")
        
        for mov in report.get("movimentacoes", []):
            mov_consolidada = deepcopy(mov)
            mov_consolidada["corretora"] = corretora
            mov_consolidada["conta"] = conta
            movimentacoes.append(mov_consolidada)
    
    # Ordenar por data (mais recente primeiro)
    movimentacoes.sort(key=lambda m: m.get("data_mov", ""), reverse=True)
    
    logger.info(f"Movimentações unificadas: {len(movimentacoes)}")
    
    # ========================================================================
    # Resultado final
    # ========================================================================
    consolidated = {
        "cliente": cliente,
        "data_referencia": data_referencia,
        "patrimonio_total_consolidado": round(patrimonio_total, 2),
        "contas": contas,
        "benchmarks": benchmarks,
        "ativos_consolidados": ativos_consolidados,
        "alocacao_por_estrategia": alocacao_estrategia,
        "alocacao_por_corretora": alocacao_corretora,
        "rentabilidade_por_conta": rentabilidade_por_conta,
        "evolucao_por_conta": evolucao_por_conta,
        "movimentacoes_unificadas": movimentacoes,
    }
    
    logger.info(
        f"Consolidação concluída: {len(contas)} contas, "
        f"{len(ativos_consolidados)} ativos, "
        f"R$ {patrimonio_total:,.2f} total"
    )
    
    return consolidated
