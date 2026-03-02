"""
Extração BTG: document_pdf (1).pdf — conta 4019474 (conjunta)
Salva JSON em output/extractions/ para validação.
"""
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Carregar .env do diretório do script
load_dotenv(Path(__file__).parent / ".env", override=True)

sys.path.insert(0, str(Path(__file__).parent))
from src.extractor import extract_pdf, get_total_cost

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_DIR / "output" / "extractions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PDF = PROJECT_DIR / "document_pdf (1).pdf"

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or len(api_key) < 10:
        print("❌ ANTHROPIC_API_KEY não encontrada ou inválida")
        print(f"   Valor lido: '{api_key[:20]}...' (len={len(api_key)})" if api_key else "   Vazia")
        sys.exit(1)
    
    print(f"✅ API Key OK (...{api_key[-4:]})")
    print(f"📄 PDF: {PDF.name}")
    print(f"📂 Output: {OUTPUT_DIR}\n")
    
    data = extract_pdf(str(PDF))
    
    output_file = OUTPUT_DIR / "btg_4019474_2026-01.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ JSON salvo: {output_file}")
    
    cost = get_total_cost()
    print(f"\n💰 CUSTO: ${cost['usd']:.4f}")
    print(f"   Tokens: {cost['input_tokens']:,} in + {cost['output_tokens']:,} out")
    print(f"   Orçamento restante: ~${5.0 - cost['usd']:.4f}")

if __name__ == "__main__":
    main()
