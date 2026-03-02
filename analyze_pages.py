"""
Análise de páginas do PDF para decidir quais enviar à API.
Identifica capas, disclaimers e páginas sem dados.
"""
import sys
sys.path.insert(0, ".")
import fitz
from pathlib import Path

pdf_path = Path(r"XPerformance - 8660669 - Ref.30.01.pdf")
doc = fitz.open(str(pdf_path))

print(f"PDF: {pdf_path.name}")
print(f"Total páginas: {len(doc)}")
print("=" * 70)

for i in range(len(doc)):
    page = doc[i]
    text = page.get_text().strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Estimativa de conteúdo
    has_numbers = any(c.isdigit() for c in text)
    has_table = any("%" in l or "R$" in l for l in lines)
    
    # Classificar
    if len(lines) < 5:
        tipo = "CAPA/VAZIA"
    elif any(kw in text.lower() for kw in ["disclaimer", "ouvidoria", "este relatório", "informações legais"]):
        tipo = "DISCLAIMER"
    elif has_table:
        tipo = "DADOS"
    else:
        tipo = "TEXTO"
    
    print(f"\nPágina {i+1} [{tipo}] ({len(lines)} linhas)")
    # Mostrar primeiras 5 linhas
    for line in lines[:5]:
        print(f"  | {line[:80]}")
    if len(lines) > 5:
        print(f"  | ... (+{len(lines)-5} linhas)")

doc.close()
