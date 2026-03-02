"""
Teste rápido: Normalizer → Consolidator → Report Generator
Usa dados mock baseados nos exemplos reais da especificação.
"""
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.normalizer import normalize
from src.consolidator import consolidate
from src.report_generator import generate_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

# Mock data baseado nos exemplos reais do plano
MOCK_XP_3245269 = {
    "$schema": "consolidador-v2",
    "meta": {
        "cliente": "JOSE GONCALVES MESTRENER JUNIOR",
        "conta": "3245269",
        "corretora": "XP",
        "segmento": "Signature",
        "parceiro": "Guilherme Barbosa",
        "data_referencia": "2026-01-30",
        "tipo_relatorio": "xp_performance",
        "arquivo_origem": "XPerformance - 3245269 - Ref.30.01.pdf"
    },
    "resumo_carteira": {
        "patrimonio_total_bruto": 1826076.84,
        "rentabilidade_mes_pct": 1.73,
        "ganho_mes_rs": 30310.25,
        "rentabilidade_24m_pct": 27.32,
        "ganho_24m_rs": 336958.87,
        "pct_cdi_mes": 148.67,
        "pct_cdi_ano": 148.67,
        "pct_cdi_12m": 102.89,
        "pct_cdi_24m": 101.23,
        "movimentacoes_mes_rs": 0.00,
        "movimentacoes_12m_rs": 285446.05,
        "rentabilidade_ano_pct": 1.73
    },
    "benchmarks": {
        "cdi": {"mes": 1.16, "ano": 1.16, "12m": 14.49, "24m": 26.99},
        "ibovespa": {"mes": 12.56, "ano": 12.56, "12m": 43.79, "24m": 41.96},
        "ipca": {"mes": 0.33, "ano": 0.33, "12m": 4.44, "24m": 9.20},
        "dolar": {"mes": -4.95, "ano": -4.95, "12m": -10.29, "24m": 5.58}
    },
    "estatistica_historica": {
        "meses_positivos": 24, "meses_negativos": 0,
        "retorno_mensal_max_pct": 1.73, "retorno_mensal_min_pct": 0.56,
        "meses_acima_cdi": 11, "meses_abaixo_cdi": 13,
        "volatilidade_12m_pct": 0.64, "volatilidade_24m_pct": 0.69
    },
    "composicao_por_estrategia": [
        {"estrategia": "Pós Fixado", "saldo_bruto": 1187595.07, "pct_alocacao": 65.04, "rent_mes_pct": 1.71, "rent_ano_pct": 1.71, "rent_12m_pct": 15.99, "rent_24m_pct": 30.48},
        {"estrategia": "Inflação", "saldo_bruto": 326432.27, "pct_alocacao": 17.88, "rent_mes_pct": 1.23, "rent_ano_pct": 1.23, "rent_12m_pct": 12.60, "rent_24m_pct": 24.04},
        {"estrategia": "Pré Fixado", "saldo_bruto": 196067.78, "pct_alocacao": 10.74, "rent_mes_pct": 2.24, "rent_ano_pct": 2.24, "rent_12m_pct": 12.23, "rent_24m_pct": 24.80},
        {"estrategia": "Multimercado", "saldo_bruto": 68059.64, "pct_alocacao": 3.73, "rent_mes_pct": -0.66, "rent_ano_pct": -0.66, "rent_12m_pct": 12.88, "rent_24m_pct": 20.50},
        {"estrategia": "Renda Variável Brasil", "saldo_bruto": 47922.09, "pct_alocacao": 2.62, "rent_mes_pct": 8.03, "rent_ano_pct": 8.03, "rent_12m_pct": 38.26, "rent_24m_pct": 41.64}
    ],
    "rentabilidade_historica_mensal": [
        {
            "ano": 2026,
            "meses": {"jan": {"portfolio_pct": 1.73, "pct_cdi": 148.67}},
            "ano_pct": 1.73, "acumulada_pct": 58.70
        },
        {
            "ano": 2025,
            "meses": {
                "jan": {"portfolio_pct": 1.13, "pct_cdi": 111.96},
                "fev": {"portfolio_pct": 0.91, "pct_cdi": 92.65},
                "mar": {"portfolio_pct": 1.15, "pct_cdi": 119.87},
                "abr": {"portfolio_pct": 1.32, "pct_cdi": 124.56},
                "mai": {"portfolio_pct": 1.13, "pct_cdi": 98.99},
                "jun": {"portfolio_pct": 1.14, "pct_cdi": 104.45},
                "jul": {"portfolio_pct": 0.82, "pct_cdi": 64.18},
                "ago": {"portfolio_pct": 1.38, "pct_cdi": 118.27},
                "set": {"portfolio_pct": 1.15, "pct_cdi": 94.26},
                "out": {"portfolio_pct": 1.04, "pct_cdi": 81.78},
                "nov": {"portfolio_pct": 1.20, "pct_cdi": 114.24},
                "dez": {"portfolio_pct": 1.01, "pct_cdi": 82.54}
            },
            "ano_pct": 14.23, "acumulada_pct": 56.00
        }
    ],
    "evolucao_patrimonial": [
        {"data": "2026-01", "patrimonio_inicial": 1795827.49, "movimentacoes": 0.00, "ir": -52.85, "iof": -8.05, "patrimonio_final": 1826076.84, "ganho_financeiro": 30310.25, "rentabilidade_pct": 1.73, "pct_cdi": 148.67}
    ],
    "ativos": [
        {"nome_original": "V8 Mercury CI Renda Fixa CP LP - Resp. Limitada", "estrategia": "Pós Fixado", "saldo_bruto": 212338.29, "quantidade": 179386.11, "pct_alocacao": 11.63, "rent_mes_pct": 1.46, "pct_cdi_mes": 125.02, "rent_ano_pct": 1.46, "pct_cdi_ano": 125.02, "rent_24m_pct": 6.92, "pct_cdi_24m": 108.65},
        {"nome_original": "CDB PINE - AGO/2026 - IPC-A + 7,35%", "estrategia": "Inflação", "saldo_bruto": 132273.63, "quantidade": 90, "pct_alocacao": 7.24, "rent_mes_pct": 0.91, "pct_cdi_mes": 78.14, "rent_ano_pct": 0.91, "pct_cdi_ano": 78.14, "rent_24m_pct": 26.49, "pct_cdi_24m": 98.14},
        {"nome_original": "CRA UNIDAS (OURO VERDE) - DEZ/2028 - 13,70%", "estrategia": "Pré Fixado", "saldo_bruto": 132180.51, "quantidade": 134, "pct_alocacao": 7.24, "rent_mes_pct": 2.84, "pct_cdi_mes": 243.56, "rent_ano_pct": 2.84, "pct_cdi_ano": 243.56, "rent_24m_pct": 1.56, "pct_cdi_24m": 90.77},
        {"nome_original": "Absolute Pace Long Biased Advisory FIC FIA", "estrategia": "Renda Variável Brasil", "saldo_bruto": 17425.77, "quantidade": 5577.3, "pct_alocacao": 0.95, "rent_mes_pct": 5.31, "pct_cdi_mes": 456.01, "rent_ano_pct": 5.31, "pct_cdi_ano": 456.01, "rent_24m_pct": 39.29, "pct_cdi_24m": 145.55},
        {"nome_original": "SPX Seahawk Advisory Debentures D45 FIC FIM CP", "estrategia": "Multimercado", "saldo_bruto": 68059.64, "quantidade": 54419.67, "pct_alocacao": 3.73, "rent_mes_pct": -0.66, "pct_cdi_mes": -56.67, "rent_ano_pct": -0.66, "pct_cdi_ano": -56.67, "rent_24m_pct": 20.50, "pct_cdi_24m": 75.96}
    ],
    "movimentacoes": [
        {"data_mov": "2026-01-21", "data_liq": "2026-01-21", "historico": "DÉBITO IOF KP CP 35 FIDC RL", "valor": -8.05, "saldo": 0.00}
    ]
}

MOCK_XP_8660669 = {
    "$schema": "consolidador-v2",
    "meta": {
        "cliente": "DENISE MESTRENER",
        "conta": "8660669",
        "corretora": "XP",
        "segmento": "Exclusive",
        "parceiro": "Guilherme Barbosa",
        "data_referencia": "2026-01-30",
        "tipo_relatorio": "xp_performance",
        "arquivo_origem": "XPerformance - 8660669 - Ref.30.01.pdf"
    },
    "resumo_carteira": {
        "patrimonio_total_bruto": 296706.75,
        "rentabilidade_mes_pct": 1.31,
        "ganho_mes_rs": 3305.60,
        "pct_cdi_mes": 112.83,
        "rentabilidade_ano_pct": 1.31,
        "pct_cdi_ano": 112.83
    },
    "benchmarks": {
        "cdi": {"mes": 1.16, "ano": 1.16, "12m": 14.49, "24m": 26.99},
        "ibovespa": {"mes": 12.56, "ano": 12.56, "12m": 43.79, "24m": 41.96},
        "ipca": {"mes": 0.33, "ano": 0.33, "12m": 4.44, "24m": 9.20},
        "dolar": {"mes": -4.95, "ano": -4.95, "12m": -10.29, "24m": 5.58}
    },
    "composicao_por_estrategia": [
        {"estrategia": "Pós Fixado", "saldo_bruto": 277238.55, "pct_alocacao": 93.44, "rent_mes_pct": 1.33, "rent_ano_pct": 1.33},
        {"estrategia": "Inflação", "saldo_bruto": 19468.20, "pct_alocacao": 6.56, "rent_mes_pct": 1.08, "rent_ano_pct": 1.08}
    ],
    "rentabilidade_historica_mensal": [
        {
            "ano": 2026,
            "meses": {"jan": {"portfolio_pct": 1.31, "pct_cdi": 112.83}},
            "ano_pct": 1.31, "acumulada_pct": None
        }
    ],
    "evolucao_patrimonial": [],
    "ativos": [
        {"nome_original": "LCA BANCO COOPERATIVO SICOOB - JAN/2030 - 100,00% CDI", "estrategia": "Pós Fixado", "saldo_bruto": 112844.22, "quantidade": 99, "pct_alocacao": 38.03, "rent_mes_pct": 1.37, "pct_cdi_mes": 117.65, "rent_24m_pct": 1.90, "pct_cdi_24m": 117.65},
        {"nome_original": "LCA Bancoob - JUN/2027 - 94,99% CDI", "estrategia": "Pós Fixado", "saldo_bruto": 55989.58, "quantidade": 52, "pct_alocacao": 18.87, "rent_mes_pct": 1.30, "pct_cdi_mes": 111.72, "rent_24m_pct": 1.80, "pct_cdi_24m": 111.71},
        {"nome_original": "V8 Cash Platinum FIF", "estrategia": "Pós Fixado", "saldo_bruto": 734.15, "quantidade": 442.96, "pct_alocacao": 0.25, "rent_mes_pct": 1.28, "pct_cdi_mes": 109.73, "rent_24m_pct": 20.12, "pct_cdi_24m": 103.26},
        {"nome_original": "CDB BANCO XP S.A. - JUN/2026 - IPC-A + 10,10%", "estrategia": "Inflação", "saldo_bruto": 19466.20, "quantidade": 18, "pct_alocacao": 6.56, "rent_mes_pct": 1.08, "pct_cdi_mes": 92.79, "rent_24m_pct": 8.15, "pct_cdi_24m": 86.71}
    ],
    "movimentacoes": []
}


def main():
    print("=" * 60)
    print("TESTE: Pipeline Normalizer → Consolidator → Report")
    print("=" * 60)
    
    # 1. Normalizar
    print("\n1. Normalizando...")
    norm1 = normalize(MOCK_XP_3245269)
    norm2 = normalize(MOCK_XP_8660669)
    
    # Mostrar classificações
    for norm in [norm1, norm2]:
        conta = norm["meta"]["conta"]
        print(f"\n   Conta {conta}:")
        for a in norm["ativos"]:
            print(f"     {a['nome_original'][:50]:50s} → tipo={str(a.get('tipo', '?')):15s} idx={str(a.get('indexador', '?')):10s} strat={a.get('estrategia_normalizada', '?')}")
    
    # 2. Consolidar
    print("\n2. Consolidando...")
    consolidated = consolidate([norm1, norm2], cliente="Jose Mestrener", data_referencia="2026-01-30")
    
    print(f"   Patrimônio total: R$ {consolidated['patrimonio_total_consolidado']:,.2f}")
    print(f"   Contas: {len(consolidated['contas'])}")
    print(f"   Ativos: {len(consolidated['ativos_consolidados'])}")
    
    print("\n   Alocação por estratégia:")
    for a in consolidated["alocacao_por_estrategia"]:
        print(f"     {a['estrategia']:20s} R$ {a['saldo_bruto']:>14,.2f}  ({a['pct_total']:.1f}%)")
    
    print("\n   Alocação por tipo:")
    for a in consolidated["alocacao_por_tipo"]:
        print(f"     {a['tipo']:20s} R$ {a['saldo_bruto']:>14,.2f}  ({a['pct_total']:.1f}%)")
    
    # 3. Gerar Excel
    print("\n3. Gerando Excel...")
    output = Path(__file__).parent / "output" / "test_pipeline.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    generate_report(consolidated, str(output))
    
    print(f"\n✅ TESTE CONCLUÍDO!")
    print(f"   Excel gerado: {output}")
    print(f"   Abra o arquivo para verificar as 6 abas.")


if __name__ == "__main__":
    main()
