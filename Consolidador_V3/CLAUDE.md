# CLAUDE.md — Projeto Consolidador v3

## O que é este projeto
Sistema de consolidação de carteiras de investimentos para assessores financeiros brasileiros. Processa relatórios PDF de corretoras (XP, BTG/API Capital), extrai dados via parsers determinísticos, normaliza, consolida múltiplas contas, e gera relatórios Excel. Interface web via Streamlit com gráfico de rentabilidade histórica dia-a-dia.

## Regra fundamental
**SOMENTE DADOS REAIS.** Todo número no relatório final deve ter origem rastreável em um PDF de corretora ou arquivo de importação. Zero cálculos implícitos de rentabilidade. Zero estimativas. Campo sem dados = null. O relatório da corretora é soberano.

> **Exceção declarada:** O módulo de reconstrução histórica (`historico.py`) usa dados reais de mercado (BACEN CDI, BACEN IPCA, CVM NAVs, yfinance) para reconstruir o valor diário histórico ativo a ativo. Quando dados de mercado não estão disponíveis, usa interpolação geométrica intra-mês entre âncoras mensais reais como fallback.

## Arquitetura

```
FLUXO PRINCIPAL (sem IA, custo zero — uso diário):
XP PDF  ──→ Parser Determinístico ──→ JSON canônico ─┐
BTG PDF ──→ Parser Determinístico ──→ JSON canônico ─┤──→ Consolidador ──→ Excel
JSON/XLSX importado manualmente ────────────────────┘

FLUXO HISTÓRICO DIÁRIO (gráfico de rentabilidade):
dados["ativos_consolidados"] ──→ enricher.enrich_portfolio() ──→ tipo_projecao por ativo
                             ──→ historico.reconstruct_from_assets() ──→ série diária [data, pl, rent_dia, acum]
(BACEN CDI série 12, BACEN IPCA série 433, CVM NAVs, yfinance B3)
Fallback: evolucao_por_conta → interpolação geométrica intra-mês entre âncoras mensais

FLUXO EXCEÇÃO (com IA, sob demanda, ~R$0,50-1,50):
PDF de corretora nova ──→ Claude API ──→ JSON canônico ──→ entra no fluxo principal
```

**Princípio:** IA é ferramenta de exceção, não de produção. O fluxo diário roda 100% determinístico.

## Estrutura do projeto

```
Consolidador/
├── CLAUDE.md                          ← este arquivo (leia SEMPRE ao iniciar)
├── .env                               ← ANTHROPIC_API_KEY (só para fluxo exceção)
├── requirements.txt                   ← inclui rapidfuzz, bizdays, yfinance (pós 2026-03-14)
├── app.py                             ← Streamlit web app (~1100 linhas, UI v2 + histórico diário ✅)
├── consolidar.py                      ← CLI alternativo
├── config/prompts/                    ← Prompts IA (só para fluxo exceção)
│   ├── xp_performance.txt
│   └── btg_performance.txt
├── src/
│   ├── __init__.py
│   ├── parsers/                       ← Parsers determinísticos (FLUXO PRINCIPAL)
│   │   ├── __init__.py                ← detect_and_parse() — detecta por conteúdo (2 págs)
│   │   ├── xp_performance.py          ← parse_xp_performance() — 707 linhas
│   │   └── btg_performance.py         ← parse_btg_performance() — ~500 linhas
│   ├── market_data/                   ← NOVO (2026-03-14) — dados de mercado em tempo real
│   │   ├── __init__.py                ← expõe get_cache(), fetch_cdi_range(), fetch_ipca_ultimos()
│   │   ├── cache.py                   ← SQLiteCache — 4 tabelas, TTL, override_manual
│   │   ├── bacen.py                   ← BACEN SGS série 12 (CDI diário) e 433 (IPCA mensal)
│   │   ├── cvm_funds.py               ← cotas fundos CVM + cadastral + fuzzy match CNPJ
│   │   ├── rv_prices.py               ← preços ações/FIIs: brapi.dev + yfinance fallback
│   │   └── resolver.py                ← nome do ativo → tipo_projecao + parâmetros (sem rede)
│   ├── historico.py                   ← reconstrução diária com dados reais (BACEN/CVM/yfinance); fallback geométrico
│   ├── enricher.py                    ← orquestra resolução de tipo de ativo + persiste JSON
│   ├── projector.py                   ← fórmulas de projeção (CDI, IPCA, prefixado, fundo, RV)
│   ├── extractor.py                   ← Extração via IA (SÓ EXCEÇÕES)
│   ├── normalizer.py                  ← SOMENTE: normalize_strategy() + clean_asset_name()
│   ├── consolidator.py                ← Agregação entre contas (estratégia + corretora)
│   ├── report_generator.py            ← Geração Excel 6 abas (523 linhas)
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

### Tela 2: Resultado (Dashboard)
- 4 cards: PL total, contas processadas, total de ativos, data de referência
- Gráfico evolução patrimonial (mensal, linha com área)
- Gráfico rentabilidade mês a mês (barras, últimos 6 meses)
- Tabela: Patrimônio por conta | Alocação por estratégia
- Botão download Excel
- **Seção "Rentabilidade Diária — Histórico Consolidado":**
  - Métricas: PL Final, Rent. Acumulada (%), Ganho Total (R$), Dias Úteis
  - Aba "Patrimônio Líquido (R$)": linha azul com área, hover com detalhes
  - Aba "Rentabilidade Acumulada (%)": linha verde/vermelha, baseline zero tracejado
  - Expander "Detalhamento Diário": tabela com Data | PL (R$) | Var.Dia (R$) | Var.Dia (%) | Acumulado (%)

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
| CDI projeção = quase zero | Série 12 retorna taxa DIÁRIA (não anual) | `daily = taxa_pct / 100` |
| IPCA BACEN retorna 400 | Endpoint `/ultimos/N` inválido para série 433 | Usar range de datas explícitas |
| "V8 Mercury CI" sem projeção | "CI" não estava no padrão de fundos | Adicionar `CI` ao `_FUND_PATTERN` |
| IPCA+ classificado como prefixado | Regex `IPC[A-]?` não captura "IPC-A" | Regex corrigido: `IPC(?:-?A)?` |

## Módulo de Rentabilidade Histórica Diária (`historico.py`)

> Implementado em 2026-03-14. Reconstrói o valor diário histórico do portfólio retroagindo da data âncora (última data do relatório), usando taxas reais de mercado por tipo de ativo.

### Conceito central

```
saldo[D-1] = saldo[D] / (1 + taxa_real_D)
```

Parte do `saldo_bruto` atual de cada ativo e retroage dia a dia aplicando a inversa da taxa real de mercado. A soma de todos os ativos em cada dia forma o PL diário consolidado.

### `historico.reconstruct_from_assets(dados, cache=None)`

```python
from historico import reconstruct_from_assets
registros = reconstruct_from_assets(dados)
# [{"data": "YYYY-MM-DD", "pl": float, "rent_dia_rs": float,
#   "rent_dia_pct": float, "rent_acum_pct": float}, ...]
```

**Fontes de dados por tipo de ativo (`tipo_projecao`):**

| tipo_projecao | Fonte | Taxa usada |
|---|---|---|
| `cdi_pct` | BACEN série 12 | `CDI_diario × pct_cdi / 100` |
| `cdi_spread` | BACEN série 12 | `CDI_diario + spread_diario` |
| `ipca_spread` | BACEN série 433 (mensal) | `IPCA_mensal^(1/du_mes) + spread_diario` |
| `prefixado` | — | `(1 + taxa_aa/100)^(1/252) - 1` |
| `fundo_cota` | CVM inf_diario (ZIP mensal) | `nav[D-1]/nav[D]` (retroativo) |
| `rv_preco` | yfinance `.SA` (único call) | `price[D-1]/price[D]` (retroativo) |
| fallback | BACEN série 12 | CDI cheio (0.055131%/dia) |

**Fallback:** Se `reconstruct_from_assets` falhar, `app.py` chama `reconstruct_daily(evolucao_por_conta)` — interpolação geométrica intra-mês entre âncoras mensais.

**Fórmula fallback:** `taxa_diaria = (pf/p0)^(1/n) - 1` → PL_d = P0 × (1 + taxa)^d

### Enrichment em `app.py._processar_arquivos()`

```python
try:
    from enricher import enrich_portfolio
    norm = enrich_portfolio(norm, use_cvm=False)  # sem rede na ingestão
except Exception:
    pass
```

`_projecao` é preservado via `deepcopy` no consolidador → disponível em `dados["ativos_consolidados"]`.

### Infraestrutura `market_data/` — dados de mercado

| Módulo | Função principal | Detalhe |
|---|---|---|
| `bacen.py` | `fetch_cdi_range(ini, fim)` → `{date: float}` | Série 12, taxa diária em % |
| `bacen.py` | `fetch_ipca_range(ini, fim)` → `{YYYY-MM: float}` | Série 433, mensal em % |
| `cvm_funds.py` | `fetch_fund_nav_series(cnpj, ini, fim)` → `{date: float}` | ZIPs mensais CVM inf_diario |
| `rv_prices.py` | `fetch_price_series(ticker, ini, fim)` → `{date: float}` | yfinance `.SA`, call único |
| `cache.py` | `SQLiteCache` — 4 tabelas SQLite com TTL | `get/set_precos_range`, `get/set_cotas_range` |
| `resolver.py` | `resolve_asset(nome)` → `tipo_projecao + params` | Pure regex, sem rede |

### Fato crítico — BACEN série 12

**A série 12 retorna taxa CDI DIÁRIA em %, não anual.**
- Valor `0.055131` = 0,055131% ao dia ≈ 14,9% a.a.
- Uso correto: `daily_rate = valor / 100.0`
- **NÃO** aplicar `(1 + taxa/100)^(1/252)` — seria dobrar a conversão
- Série 433 (IPCA): endpoint `/ultimos/N` retorna 400 — usar range de datas explícitas

### Resolver — prioridade das regras (ordem importa)

1. CDI %: `r"(\d+[,.]?\d*)\s*%\s*(?:DO\s+)?(?:CDI|DI)\b"` — "92,00% CDI"
2. IPCA+: `r"IPC(?:-?A)?\s*\+\s*([\d,]+)%"` — **`(?:-?A)?` cobre IPC-A e IPCA**
3. CDI+spread: `r"(?:CDI|DI)\s*\+\s*([\d,]+)%"` — "CDI + 0,50%"
4. Fundo: `r"\b(?:FIC|FIF|FIDC|FIA|FIRF|FICF|FUNDO|FUND|FIAGRO|FIP|CI)\b"` — **CI = Capital Investimento**
5. Ticker B3: `r"\b([A-Z]{4}\d{1,2})\b"` — ações e FIIs
6. Prefixado (fim da string): `r"[-–]\s*(\d{1,2}[,.]?\d+)%(?:\s*a\.?a\.?)?\s*$"` — "- 12,25%"

**Cobertura validada (Jose Mestrener, 26 ativos):** 100% sem CVM — 15 fundos, 7 IPCA+, 3 prefixados, 1 CDI%.

### Cache SQLite (`data/market_data/market_cache.db`)

- `resolved_assets.override_manual = 1` protege correções manuais de sobrescrita
- Limpar resoluções para re-testar: `DELETE FROM resolved_assets` no SQLite

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
12. **Projeção D0 removida da UI** — substituída por reconstrução histórica dia-a-dia (`historico.py`)
13. **BACEN série 12 = taxa DIÁRIA** — não converter de anual para diária (já é diária)
14. **Resolver persiste no SQLite** — `override_manual=1` protege correções manuais
15. **Histórico diário usa dados reais de mercado** — BACEN CDI/IPCA, CVM NAVs, yfinance; interpolação geométrica só como fallback
16. **reconstruct_from_assets() retroage da data âncora** — composição atual usada para todo o período (limitação conhecida: ativos novos distorcem meses antigos)

## Clientes processados

| Cliente | Contas | Patrimônio Total | Ativos | Status |
|---------|--------|-----------------|--------|--------|
| Jose Mestrener | XP 3245269, XP 8660669, BTG 4016217, BTG 4019474 | R$ 4.902.064,78 | 100 | ✅ Extraído, consolidado, histórico diário ✅ |
| Cid e Tania | XP 14522738, XP 3476739, BTG 5058054, BTG 5165904 | (a validar) | (a validar) | ✅ Extraído via IA |

## Fase atual
**Fase 3 completa:** Parsers XP e BTG + UI v2 + gráfico de rentabilidade diária histórica com dados reais de mercado.
Próximo: validar série diária com dados reais vs interpolação; popular CNPJs de fundos via CVM fuzzy match para cobertura 100% no resolver.
