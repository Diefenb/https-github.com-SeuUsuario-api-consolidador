# CLAUDE.md — Projeto Consolidador v3

## O que é este projeto
Sistema de consolidação de carteiras de investimentos para assessores financeiros brasileiros. Processa relatórios PDF de corretoras (XP, BTG/API Capital), extrai dados via parsers determinísticos, normaliza, consolida múltiplas contas, e gera relatórios Excel. Interface web via Streamlit.

## Regra fundamental
**SOMENTE DADOS REAIS.** Todo número no relatório final deve ter origem rastreável em um PDF de corretora ou arquivo de importação. Zero cálculos implícitos de rentabilidade. Zero estimativas. Campo sem dados = null. O relatório da corretora é soberano.

## Arquitetura

```
FLUXO PRINCIPAL (sem IA, custo zero):
XP PDF ──→ Parser Determinístico ──→ JSON padrão ─┐
BTG PDF ──→ Parser Determinístico ──→ JSON padrão ─┤──→ Consolidador ──→ Excel
JSON/XLSX importado manualmente ───────────────────┘

FLUXO EXCEÇÃO (com IA, sob demanda, custo ~R$0,50-1,50):
PDF de corretora nova ──→ Claude API ──→ JSON padrão ──→ entra no fluxo principal
```

**Princípio:** IA é ferramenta de exceção, não de produção. O fluxo diário roda 100% determinístico.

## Estrutura do projeto

```
Consolidador/
├── CLAUDE.md                          ← este arquivo (leia SEMPRE ao iniciar)
├── .env                               ← ANTHROPIC_API_KEY (só para fluxo exceção)
├── requirements.txt
├── app.py                             ← Streamlit web app (interface principal)
├── consolidar.py                      ← CLI alternativo
├── config/prompts/                    ← Prompts IA (só para fluxo exceção)
│   ├── xp_performance.txt
│   └── btg_performance.txt
├── src/
│   ├── __init__.py
│   ├── parsers/                       ← Parsers determinísticos (FLUXO PRINCIPAL)
│   │   ├── __init__.py                ← detect_and_parse()
│   │   ├── xp_performance.py          ← parse_xp_performance()
│   │   └── btg_performance.py         ← parse_btg_performance()
│   ├── extractor.py                   ← Extração via IA (SÓ EXCEÇÕES)
│   ├── normalizer.py                  ← SOMENTE: normalize_strategy() + clean_asset_name()
│   ├── consolidator.py                ← Agregação entre contas (estratégia + corretora)
│   ├── report_generator.py            ← Geração Excel 6 abas
│   ├── importer.py                    ← Importação de JSON/XLSX padrão
│   └── utils.py                       ← Helpers (formatação BR, parsing números)
├── schemas/
│   └── consolidador_v2.json           ← JSON Schema (Draft-07)
├── templates/
│   └── importacao_template.xlsx       ← Template para importação manual
├── tests/
│   ├── test_parsers.py                ← Testes parsers vs JSONs validados
│   └── fixtures/                      ← JSONs extraídos via IA como ground truth
├── data/historico/                     ← Consolidações salvas por cliente/mês
└── output/
    ├── extractions/                   ← JSONs extraídos (NÃO colocar consolidado.json aqui)
    └── consolidado_*.xlsx
```

## Parsers Determinísticos (src/parsers/)

### Tecnologia: `pdfplumber`
Extrai tabelas e texto diretamente do PDF sem IA. Custo zero, sem dependência externa.

### Parser XP Performance (`xp_performance.py`)
- **Identificação:** Texto contém "Relatório de Investimentos" ou "XP"
- **Extração capa:** Regex para conta, parceiro, data, segmento
- **Extração tabelas:** `page.extract_tables()` para benchmarks, evolução, composição, ativos, movimentações
- **Desafio:** Sub-headers de estratégia misturados com ativos → detectar por padrão (tem saldo, não tem quantidade)
- **Colunas ativos:** Saldo, Qtd, %Aloc, Rent.Mês, %CDI.Mês, Rent.Ano, %CDI.Ano, Rent.24M, %CDI.24M
- **NÃO tem:** 12M por ativo → null

### Parser BTG Performance (`btg_performance.py`)
- **Identificação:** Texto contém "Relatório de Performance" ou "API Capital" ou "BTG"
- **Períodos:** Mês/Ano/12M/Acumulado (diferente da XP)
- **Formato CDB:** "BANCO PINE S/A - CDB-CDBC258QL68" → regex `r"\bCDB[-\s]"`
- **Duas visões:** Extrair SOMENTE estratégia de investimento, IGNORAR tipo de veículo
- **Conta conjunta:** Pode ter múltiplos titulares

### Detector (`__init__.py`)
```python
def detect_and_parse(pdf_path: str) -> dict:
    text = extract_first_page_text(pdf_path)
    if "Relatório de Investimentos" in text or "XP" in text:
        return parse_xp_performance(pdf_path)
    elif "Relatório de Performance" in text or "API Capital" in text or "BTG" in text:
        return parse_btg_performance(pdf_path)
    else:
        raise UnknownFormatError(f"Formato não reconhecido: {pdf_path}")
```

### Validação cruzada
Testar parsers contra JSONs já extraídos via IA (ground truth em `tests/fixtures/`):
- Patrimônio total: diff < R$ 1,00
- Quantidade de ativos: exatamente igual
- Saldo de cada ativo: diff < R$ 0,01
- Rentabilidades: diff < 0,01%

## Importação Manual (src/importer.py)

Para corretoras sem parser, o usuário importa dados via:
1. **JSON** no formato `consolidador-v2` (direto)
2. **XLSX** usando template padronizado (`templates/importacao_template.xlsx`)

O importer converte XLSX → JSON canônico antes de consolidar.

## Extração via IA (src/extractor.py) — SÓ EXCEÇÕES

Mantido como fallback para PDFs de formato desconhecido.
- **Modelo:** `claude-sonnet-4-5-20250929`
- **Key:** em `.env` — NÃO alterar, NÃO mostrar, NÃO recriar
- **Custo:** ~R$ 0,50-1,50 por PDF
- **Quando usar:** Somente quando parser determinístico não existe para o formato
- **MAX_TOKENS:** 16000 por chamada

## Normalizer (src/normalizer.py) — SIMPLIFICADO

Faz SOMENTE:
- `normalize_strategy()` — unifica grafias de estratégia
- `clean_asset_name()` — padroniza nomes de ativos

### NÃO faz (removido intencionalmente, NÃO reimplementar):
- ~~Classificação de tipo de ativo (CDB, LCA, FII, etc.)~~
- ~~Classificação de indexador (CDI, IPCA, Prefixado)~~
- ~~Classificação de fundo (23 categorias)~~

### Mapa de estratégias canônicas

| Variações no PDF | Estratégia padronizada |
|-----------------|----------------------|
| Pós Fixado, Pós-fixado, Pos Fixado | `Pós Fixado` |
| Pré Fixado, Pré-fixado, Pre Fixado, Prefixado, Pre-fixado | `Pré Fixado` |
| Inflação, IPCA | `Inflação` |
| Multimercado, Multi, Retorno Absoluto, Retorno Absoluto (MM), Macro, Long Short, Long Biased | `Multimercado` |
| Renda Variável, Renda Variável Brasil, Ações, Equity | `Renda Variável` |
| Fundos Listados | `Fundos Listados` |
| Alternativo, Cripto | `Alternativo` |
| Caixa, Saldo em conta | `Caixa` |

FIIs (tickers XXXX11) → reclassificar de "Renda Variável" para `Fundos Listados`.

## Relatório Excel — 6 abas

### Aba 1: Resumo
| Corretora | Conta | Patrimônio Bruto | Rent. Mês (%) | %CDI Mês | Rent. Ano (%) | %CDI Ano | Ganho Mês (R$) | Ganho Ano (R$) |
- SEM coluna Segmento
- Linha TOTAL com soma

### Aba 2: Alocação
Duas tabelas:
1. **Por Estratégia** — Estratégia, Saldo Bruto, % Total
2. **Por Corretora** — Corretora, Saldo Bruto, % Total
- SEM "Por Tipo de Ativo" / SEM "Por Classificação de Fundo"

### Aba 3: Posição Detalhada
| Corretora | Conta | Estratégia | Ativo | Saldo Bruto | % Total | Rent. Mês | %CDI Mês | Rent. Ano | %CDI Ano |
- SEM colunas Tipo, Indexador, Classificação
- Ordenado: Estratégia (asc) → Saldo Bruto (desc)
- % Total = saldo_bruto / patrimonio_total_consolidado (único recálculo)

### Aba 4: Rentabilidade
Tabela mensal por conta (Portfólio % e %CDI). Blocos separados por conta.

### Aba 5: Evolução Patrimonial
Tabela mensal por conta. Blocos separados por conta.

### Aba 6: Movimentações
Lista unificada, ordenada por data (mais recente primeiro).

## Streamlit Web App (app.py)

### Tela 1: Upload
- Campo: Nome do Cliente
- Campo: Mês/Ano de Referência
- Upload: múltiplos PDFs + JSONs/XLSX de importação
- Auto-detecção de formato (XP/BTG/Importação/Desconhecido)
- Para formato desconhecido: oferecer extração IA (com aviso de custo) ou template manual

### Tela 2: Resultado
- Resumo por conta (corretora, patrimônio, ativos)
- Patrimônio total consolidado
- Preview das abas do Excel
- Botão download do Excel

### Deploy: Streamlit Community Cloud (gratuito)

## Números brasileiros
- `R$ 1.826.076,84` → float `1826076.84`
- `1,73%` → float `1.73`
- `-R$ 52,85` → float `-52.85`
- Excel: formatação brasileira (R$ #.##0,00)

## Bugs conhecidos e resolvidos

| Bug | Causa | Solução |
|-----|-------|---------|
| Conta fantasma no consolidado | `consolidado.json` dentro de `extractions/` | Salvar fora de `extractions/` |
| UnicodeEncodeError Windows | `cp1252` não suporta emoji | `PYTHONIOENCODING=utf-8` |
| PermissionError Excel | Arquivo aberto | Fechar ou usar nome diferente |
| CDB BTG não reconhecido | Formato "BANCO X - CDB-CODE" | Regex `r"\bCDB[-\s]"` |
| Pré Fixado / Pré-fixado split | Grafias diferentes XP vs BTG | Unificado em MAPA_ESTRATEGIA |
| Retorno Absoluto (MM) | BTG classifica assim | Mapeado para Multimercado |
| meta.cliente = parceiro | XP não mostra titular | `meta.cliente = null` para XP |

## Histórico de decisões

1. XP Performance traz rentabilidade por ativo — não há gap de dados vs BTG
2. Caixa = saldo em conta, não ativo → `composicao_por_estrategia`, NÃO em `ativos`
3. IR positivo no BTG = possível restituição — extrair como está
4. Relatório não mostra titular → `meta.cliente = null`
5. Relatório da corretora é soberano — se há divergência entre seções, extrair fielmente
6. Tipo de ativo, indexador e classificação de fundo REMOVIDOS — foco em estratégia
7. Segmento removido do Resumo
8. BTG: extrair SOMENTE visão por estratégia, IGNORAR tipo de veículo
9. 23 categorias de fundos implementadas e removidas — não reimplementar sem pedido
10. **IA é ferramenta de exceção** — fluxo principal usa parsers determinísticos (custo zero)
11. **Streamlit Community Cloud** como plataforma de deploy (gratuito)

## Clientes processados

| Cliente | Contas | Patrimônio Total | Ativos | Status |
|---------|--------|-----------------|--------|--------|
| Jose Mestrener | XP 3245269, XP 8660669, BTG 4016217, BTG 4019474 | R$ 4.902.064,78 | 100 | ✅ Extraído via IA e consolidado |
| Cid e Tania | XP 14522738, XP 3476739, BTG 5058054, BTG 5165904 | (a validar) | (a validar) | ✅ Extraído via IA |

## Fase atual
**Fase 1:** Implementar parsers determinísticos para XP e BTG, validar contra JSONs existentes.
Consultar `plano_consolidador_v3.md` para cronograma completo.
