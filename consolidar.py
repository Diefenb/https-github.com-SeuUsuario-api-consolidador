"""
Consolidador — CLI Principal.

Pipeline completo: PDF → JSON → Normalização → Consolidação → Excel

Uso:
    python consolidar.py \
        --cliente "Jose Mestrener" \
        --mes "2026-01" \
        --pdfs ./pdfs/XPerformance_3245269.pdf ./pdfs/BTG_4016217.pdf \
        --output ./output/consolidado_jose_2026-01.xlsx
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Carregar .env do diretório do script
load_dotenv(Path(__file__).parent / ".env", override=True)

# Adicionar diretório do projeto ao path
sys.path.insert(0, str(Path(__file__).parent))

from src.extractor import extract_pdf, get_total_cost
from src.normalizer import normalize
from src.consolidator import consolidate
from src.report_generator import generate_report


def setup_logging(verbose: bool = False):
    """Configura logging com formato legível."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Consolidador de Carteiras de Investimentos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplo:
    python consolidar.py \\
        --cliente "Jose Mestrener" \\
        --mes "2026-01" \\
        --pdfs ./XPerformance*.pdf ./document_pdf*.pdf \\
        --output ./output/consolidado.xlsx
        """,
    )
    parser.add_argument("--cliente", required=True, help="Nome do cliente")
    parser.add_argument("--mes", required=True, help="Mês de referência (YYYY-MM)")
    parser.add_argument("--pdfs", nargs="+", required=True, help="Caminhos dos PDFs")
    parser.add_argument("--output", required=True, help="Caminho do Excel de saída")
    parser.add_argument("--save-json", action="store_true",
                        help="Salvar JSONs intermediários em output/extractions/")
    parser.add_argument("--verbose", "-v", action="store_true", help="Logging detalhado")
    parser.add_argument("--skip-extract", action="store_true",
                        help="Pula extração, usa JSONs já salvos em output/extractions/")
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    logger = logging.getLogger(__name__)
    
    # Verificar API key (só se precisar extrair)
    if not args.skip_extract:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key or len(api_key) < 10:
            print("❌ ANTHROPIC_API_KEY não configurada")
            print("   Configure no .env ou como variável de ambiente")
            sys.exit(1)
    
    print("\n" + "=" * 70)
    print(f"  CONSOLIDADOR — {args.cliente}")
    print(f"  Referência: {args.mes}")
    print(f"  PDFs: {len(args.pdfs)} arquivo(s)")
    print("=" * 70)
    
    start_time = time.time()
    
    # ========================================================================
    # ETAPA 1: EXTRAÇÃO
    # ========================================================================
    print("\n📋 ETAPA 1: Extração de PDFs")
    print("-" * 40)
    
    json_dir = Path(args.output).parent / "extractions"
    json_dir.mkdir(parents=True, exist_ok=True)
    
    extracted = []
    
    if args.skip_extract:
        # Carregar JSONs já salvos
        print("⏩ Usando JSONs já extraídos:")
        for json_file in sorted(json_dir.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            extracted.append(data)
            conta = data.get("meta", {}).get("conta", "?")
            corretora = data.get("meta", {}).get("corretora", "?")
            print(f"   ✅ {json_file.name} ({corretora} {conta})")
    else:
        for pdf_path in args.pdfs:
            pdf = Path(pdf_path)
            if not pdf.exists():
                print(f"   ⚠️  Não encontrado: {pdf.name}")
                continue
            
            try:
                data = extract_pdf(str(pdf))
                extracted.append(data)
                
                # Salvar JSON intermediário
                if args.save_json or True:  # Sempre salvar para segurança
                    conta = data.get("meta", {}).get("conta", "unknown")
                    corretora = data.get("meta", {}).get("corretora", "unknown")
                    json_file = json_dir / f"{corretora.lower()}_{conta}.json"
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"   💾 JSON salvo: {json_file.name}")
                    
            except Exception as e:
                print(f"   ❌ Erro em {pdf.name}: {e}")
                logger.exception(f"Falha na extração de {pdf.name}")
    
    if not extracted:
        print("\n❌ Nenhum PDF extraído com sucesso. Abortando.")
        sys.exit(1)
    
    print(f"\n   ✅ {len(extracted)} PDFs extraídos")
    
    # ========================================================================
    # ETAPA 2: NORMALIZAÇÃO
    # ========================================================================
    print("\n📋 ETAPA 2: Normalização")
    print("-" * 40)
    
    normalized = []
    for data in extracted:
        conta = data.get("meta", {}).get("conta", "?")
        norm = normalize(data)
        normalized.append(norm)
        
        n_ativos = len(norm.get("ativos", []))
        print(f"   ✅ Conta {conta}: {n_ativos} ativos")
    
    # ========================================================================
    # ETAPA 3: CONSOLIDAÇÃO
    # ========================================================================
    print("\n📋 ETAPA 3: Consolidação")
    print("-" * 40)
    
    consolidated = consolidate(
        normalized,
        cliente=args.cliente,
        data_referencia=f"{args.mes}-30",  # Último dia do mês (aproximado)
    )
    
    patrimonio = consolidated.get("patrimonio_total_consolidado", 0)
    n_contas = len(consolidated.get("contas", []))
    n_ativos = len(consolidated.get("ativos_consolidados", []))
    print(f"   ✅ {n_contas} contas | {n_ativos} ativos | R$ {patrimonio:,.2f}")
    
    # Salvar JSON consolidado (fora de extractions/ para não ser re-carregado)
    consolidated_json = Path(args.output).parent / "consolidado.json"
    with open(consolidated_json, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)
    print(f"   💾 JSON consolidado: {consolidated_json.name}")
    
    # ========================================================================
    # ETAPA 4: GERAÇÃO DE RELATÓRIO
    # ========================================================================
    print("\n📋 ETAPA 4: Geração de Relatório Excel")
    print("-" * 40)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    generate_report(consolidated, str(output_path))
    print(f"   ✅ Relatório salvo: {output_path}")
    
    # ========================================================================
    # RESUMO FINAL
    # ========================================================================
    elapsed = time.time() - start_time
    
    print(f"\n{'=' * 70}")
    print(f"  CONCLUÍDO em {elapsed:.1f}s")
    print(f"{'=' * 70}")
    print(f"  Cliente: {args.cliente}")
    print(f"  Contas: {n_contas}")
    print(f"  Ativos: {n_ativos}")
    print(f"  Patrimônio Total: R$ {patrimonio:,.2f}")
    print(f"  Relatório: {output_path}")
    
    if not args.skip_extract:
        cost = get_total_cost()
        print(f"\n  💰 Custo API: ${cost['usd']:.4f}")
        print(f"     Tokens: {cost['input_tokens']:,} in + {cost['output_tokens']:,} out")
        print(f"     Chamadas: {cost['calls']}")
    
    print()


if __name__ == "__main__":
    main()
