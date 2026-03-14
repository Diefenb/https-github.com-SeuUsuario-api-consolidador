# SESSION_CONTEXT.md — Consolidador de Carteiras API Capital

> **Como usar:** Cole este arquivo no início de qualquer nova conversa com Claude para restaurar o contexto completo do projeto imediatamente. Atualize a seção "Estado Atual" ao final de cada sessão produtiva.

---

## 1. O que é este projeto

Sistema de consolidação de carteiras de investimentos para assessores financeiros da **API Capital / Capital Investimentos**. Processa relatórios PDF de corretoras (XP e BTG), extrai dados, normaliza, consolida múltiplas contas de um mesmo cliente e gera relatório Excel. A partir de 2026-03-14, inclui módulo de reconstrução histórica diária para plotar gráfico de rentabilidade com granularidade dia-a-dia.

**Usuário:** Gabriel (gabidiefenbach@gmail.com)
**Pasta do projeto:** `/Consolidador/` (pasta selecionada no Cowork)

---

## 2. Regra Fundamental (nunca violar)

**SOMENTE DADOS REAIS.** Todo número no relatório final deve ter origem rastreável em um PDF de corretora. Zero cálculos implícitos de rentabilidade. Zero estimativas. Campo sem dados = null. O relatório da corretora é soberano.

> **Exceção explícita:** O módulo de reconstrução histórica (`historico.py`) usa interpolação geométrica intra-mês entre âncoras reais mensais da corretora. Só os pontos intermediários (dentro de cada mês) são estimados; os valores de início e fim de cada mês são exatos.

---

## 3. Arquitetura

```
FLUXO PRINCIPAL (sem IA, custo zero — uso diário):
XP PDF  ──→ Parser Determinístico (pdfplumber) ──→ JSON canônico ─┐
BTG PDF ──→ Parser Determinístico (pdfplumber) ──→ JSON canônico ─┤──→ Consolidador ──→ Excel
JSON/XLSX importado manualmente ──────────────────────────────────┘

FLUXO HISTÓRICO DIÁRIO (novo — gráfico de rentabilidade):
dados["evolucao_por_conta"] ──→ historico.reconstruct_daily() ──→ série diária
(âncoras mensais reais da corretora)   (interpolação geométrica intra-mês)

FLUXO EXCEÇÃO (com IA, sob demanda, ~R$0,50–1,50/PDF):
PDF de corretora nova ──→ Claude API (Sonnet) ──→ JSON canônico ──→ entra no fluxo principal
```

---

## 4. Estrutura de arquivos

```
Consolidador/
├── SESSION_CONTEXT.md             ← ESTE ARQUIVO (atualizar a cada sessão)
├── app.py                         ← Streamlit web app (~1100 linhas, UI v2 + histórico diário ✅)
├── consolidar.py                  ← CLI alternativo
├── requirements.txt               ← inclui rapidfuzz, bizdays, yfinance (pós 2026-03-14)
├── .env                           ← ANTHROPIC_API_KEY (não tocar, não recriar)
│
├── Consolidador_V3/               ← VERSÃO ATIVA DO CÓDIGO
│   ├── CLAUDE.md                  ← doc técnica V3 (sempre ler ao iniciar)
│   ├── src/
│   │   ├── parsers/
│   │   │   ├── __init__.py        ← detect_and_parse() — detecta por conteúdo, 2 páginas
│   │   │   ├── xp_performance.py  ← parse_xp_performance() — 707 linhas ✅
│   │   │   └── btg_performance.py ← parse_btg_performance() — ~500 linhas ✅
│   │   ├── market_data/           ← módulo de dados de mercado (2026-03-14)
│   │   │   ├── __init__.py        ← expõe get_cache(), fetch_cdi_range(), fetch_ipca_ultimos()
│   │   │   ├── cache.py           ← SQLiteCache — 4 tabelas com TTL
│   │   │   ├── bacen.py           ← BACEN SGS série 12 (CDI) e 433 (IPCA)
│   │   │   ├── cvm_funds.py       ← cotas CVM + cadastral + fuzzy match CNPJ
│   │   │   ├── rv_prices.py       ← preços ações/FIIs via brapi.dev + yfinance
│   │   │   └── resolver.py        ← resolução nome → tipo_projecao + parâmetros
│   │   ├── historico.py           ← NOVO — reconstrução diária a partir de âncoras mensais ✅
│   │   ├── enricher.py            ← orquestra resolução de tipo de ativo + persiste JSON
│   │   ├── projector.py           ← fórmulas de projeção (CDI, IPCA, prefixado, fundo, RV)
│   │   ├── consolidator.py        ← agregação entre contas
│   │   ├── normalizer.py          ← normalize_strategy() + clean_asset_name()
│   │   ├── report_generator.py    ← geração Excel 6 abas (523 linhas)
│   │   ├── importer.py            ← importação JSON/XLSX
│   │   └── utils.py               ← helpers
│   ├── schemas/consolidador_v2.json
│   └── output/extractions/
│       ├── xp_3245269_v3.json     ← Jose Mestrener / XP (26 ativos, R$1.826.076)
│       └── xp_8660669_v3.json     ← Jose Mestrener / XP (7 ativos, R$296.706)
│
├── data/                          ← cache e posições (não commitar)
│   ├── market_data/
│   │   ├── market_cache.db        ← SQLite: taxas CDI/IPCA, cotas CVM, preços RV, resoluções
│   │   └── cvm_cadastral_cache.csv ← cadastral CVM (refresh < 7 dias, ~50MB)
│   └── posicoes/                  ← JSON enriquecidos por cliente
│
└── output/
    ├── consolidado_jose_2026-01.xlsx
    └── extractions/ (JSONs via IA — ground truth)
```

---

## 5. Clientes processados

| Cliente | Contas | Patrimônio Total | Status |
|---------|--------|-----------------|--------|
| Jose Goncalves Mestrener Junior | XP 3245269, XP 8660669, BTG 4016217, BTG 4019474 | R$ 4.902.064,78 | ✅ Excel + histórico diário ✅ |
| Cid e Tania | XP 14522738, XP 3476739, BTG 5058054, BTG 5165904 | (a validar) | ✅ Excel gerado |

---

## 6. Schema JSON canônico (`consolidador-v2`)

Campos principais de cada JSON extraído:
- `meta` — cliente, conta, corretora, data_referencia, arquivo_origem
- `resumo_carteira` — patrimônio, rent_mes_pct, ganho_mes_rs, rent_24m_pct, %CDI
- `benchmarks` — CDI, ibovespa, ipca, dolar (mês/ano/12m/24m)
- `estatistica_historica` — meses +/-, volatilidade, retorno max/min
- `composicao_por_estrategia` — saldo e rentabilidade por estratégia
- `rentabilidade_historica_mensal` — tabela ano × mês (portfólio % e %CDI)
- `evolucao_patrimonial` — **tabela mensal com patrimônio_inicial, patrimônio_final, IR, IOF** ← âncoras do histórico diário
- `ativos` — lista detalhada com saldo, qtd, % alocação, rentabilidades
- `movimentacoes` — histórico de entradas/saídas

**Campos adicionados pelo enricher (não persistir no JSON canônico original):**
- `ativos[i]._projecao` — tipo_projecao, pct_cdi, spread_aa, taxa_prefixada_aa, cnpj, ticker, confianca

---

## 7. Decisões tomadas (não reverter sem discussão)

1. **IA é exceção, não produção** — fluxo diário usa pdfplumber (custo zero)
2. **Tipo de ativo, indexador e classificação de fundo foram REMOVIDOS** — foco em estratégia
3. **Segmento removido do Resumo** (não era consistente entre corretoras)
4. **23 categorias de fundos: NÃO reimplementar** sem pedido explícito
5. **`meta.cliente = null` para XP** — relatório não mostra titular
6. **BTG: extrair SOMENTE visão por estratégia**, ignorar tipo de veículo
7. **Caixa = saldo em conta**, não ativo — vai em `composicao_por_estrategia`, não em `ativos`
8. **IR positivo no BTG** = possível restituição — extrair como está, sem interpretar
9. **`consolidado.json` não vai dentro de `extractions/`** — gera conta fantasma
10. **Deploy: Streamlit Community Cloud** (gratuito, conectar GitHub)
11. **Modelo IA:** `claude-sonnet-4-5-20250929` (Sonnet, não Opus — custo/benefício)
12. **Projeção D0 removida da UI** — substituída por reconstrução histórica dia-a-dia (seção 17)
13. **BACEN série 12 retorna taxa DIÁRIA em %** (ex: 0.055131% ao dia ≈ 14,9% a.a.) — NÃO é taxa anual

---

## 8. Estratégias canônicas (normalizer)

| Variações no PDF | Padronizado como |
|-----------------|-----------------|
| Pós Fixado, Pós-fixado, Pos Fixado | `Pós Fixado` |
| Pré Fixado, Pré-fixado, Prefixado | `Pré Fixado` |
| Inflação, IPCA | `Inflação` |
| Multimercado, Multi, Retorno Absoluto, Macro, Long Short | `Multimercado` |
| Renda Variável, Renda Variável Brasil, Ações, Equity | `Renda Variável` |
| Fundos Listados | `Fundos Listados` |
| Alternativo, Cripto | `Alternativo` |
| Caixa, Saldo em conta | `Caixa` |

FIIs (tickers XXXX11) → reclassificar de "Renda Variável" para `Fundos Listados`.

---

## 9. Relatório Excel — 6 abas

| Aba | Conteúdo |
|-----|---------|
| 1 — Resumo | Por conta: patrimônio, rent. mês/ano, %CDI, ganho R$ |
| 2 — Alocação | Por estratégia + por corretora (saldo e % do total) |
| 3 — Posição | Todos os ativos com saldo, % total, rentabilidades |
| 4 — Rentabilidade | Histórico mensal por conta (portfólio % e %CDI) |
| 5 — Evolução | Tabela patrimonial mensal por conta |
| 6 — Movimentações | Lista unificada por data (mais recente primeiro) |

---

## 10. Bugs conhecidos e resolvidos

| Bug | Solução |
|-----|---------|
| Conta fantasma no consolidado | Salvar `consolidado.json` fora de `extractions/` |
| UnicodeEncodeError Windows | `PYTHONIOENCODING=utf-8` |
| PermissionError Excel | Fechar arquivo antes de regerar |
| CDB BTG não reconhecido | Regex `r"\bCDB[-\s]"` |
| Pré Fixado / Pré-fixado split | Unificado em MAPA_ESTRATEGIA |
| Retorno Absoluto (MM) | Mapeado para Multimercado |
| BTG PDF roteado para XP parser | `detect_and_parse` agora usa conteúdo, não nome do arquivo |
| `detect_and_parse` não reconhecia BTG | Regex `r"Relat.{0,4}rio\s*[\n\s]+de\s+Performance"` + 2 páginas |
| BTG ligatura "fi" → `\x00` | `_normalize_btg_strategy()` com padrões regex tolerantes |
| BACEN IPCA `/ultimos/N` → 400 | Usar endpoint de range com datas explícitas |
| CDI projeção zerada | Série 12 retorna taxa DIÁRIA (não anual) — `daily = taxa_pct / 100` |

---

## 11. Stack tecnológico

| Componente | Tecnologia |
|-----------|-----------|
| Extração PDF (fluxo principal) | `pdfplumber` |
| Extração PDF (exceção) | Claude API — Sonnet |
| Consolidação / normalização | Python / pandas |
| Relatório output | Excel (openpyxl) |
| Gráficos interativos | Plotly 6.x |
| Interface web | Streamlit 1.54 |
| Reconstrução histórica diária | `historico.py` — interpolação geométrica intra-mês |
| Cache de mercado | SQLite local (`data/market_data/market_cache.db`) |
| CDI diário | BACEN SGS API — série 12 (gratuito, sem auth) |
| IPCA mensal | BACEN SGS API — série 433 (gratuito, sem auth) |
| Cotas de fundos | CVM Dados Abertos — inf_diario_fi_YYYYMM.zip (D+1) |
| Fuzzy match CNPJ | `rapidfuzz` WRatio vs cadastral CVM |
| Calendário ANBIMA | `bizdays` (fallback: Seg-Sex sem feriados) |
| Preços ações/FIIs | brapi.dev (<1 min) + yfinance fallback (~15 min) |
| Deploy | Streamlit Community Cloud |
| Repositório | GitHub — `Diefenb/https-github.com-SeuUsuario-api-consolidador` |

---

## 12. Identidade visual

- **Cor primária:** Azul escuro `#0D1B3E`
- **Cor secundária / destaque:** Azul médio `#1A56DB`
- **Fundo:** Off-white `#F8FAFC`
- **Cards:** Branco `#FFFFFF` com borda `#E2E8F0`
- **Fonte:** Inter (400, 500, 600)
- **Logo:** Capital Investimentos (sidebar esquerda)

---

## 13. Backlog de features

| # | Feature | Status | Observações |
|---|---------|--------|-------------|
| 1 | Arquivo de contexto de sessão | ✅ Feito | Este arquivo |
| 2 | Parser BTG completo | ✅ Feito | ~500 linhas, state machine |
| 3 | Nova UI — sidebar, cards, gráficos | ✅ Feito | app.py, Plotly |
| 4 | Deploy Streamlit Community Cloud | ✅ Feito | GitHub conectado |
| 5 | Módulo market_data (BACEN, CVM, brapi) | ✅ Implementado | Infra de dados pronta |
| 6 | Reconstrução histórica diária + gráfico | ✅ Feito | historico.py + _section_rentabilidade_diaria |
| 7 | CVM fuzzy match CNPJ para fundos | 🔶 Parcial | Código pronto, CNPJ não populado para José Mestrener |
| 8 | Tabela rentabilidade Excel (visual) | Alta | Implementada, não validada com BTG |
| 9 | Área de remoção de ativos (PL parcial) | Média | UI para excluir ativos antes de consolidar |
| 10 | Gráficos embutidos no Excel | Média | Charts Plotly no Excel exportado |
| 11 | Importação de extratos via IA | Baixa | Além dos relatórios mensais |

---

## 14. Estado atual do projeto

**Última atualização:** 2026-03-14

### Histórico de commits recentes

```
e529f09 feat: add historical daily portfolio reconstruction and chart
cfcf387 refactor: remove forward-projection UI from app.py
8ce97e9 fix: remove illegal XML chars from BTG asset names before Excel write
b03bb2f docs: update SESSION_CONTEXT with UI v2 progress and deploy instructions
0a71f6f feat: redesign UI with dark sidebar, dashboard view, and Plotly charts
98217a2 feat: implement full BTG parser and fix XP/BTG routing
```

### O que está funcionando agora

- ✅ Parsers XP e BTG determinísticos (pdfplumber, custo zero)
- ✅ Consolidação multi-conta com Excel 6 abas
- ✅ UI v2 com sidebar escura, cards, gráficos Plotly
- ✅ Deploy Streamlit Community Cloud via GitHub
- ✅ **Gráfico de rentabilidade diária histórica** — seção "Rentabilidade Diária — Histórico Consolidado" no dashboard
  - Métricas: PL Final, Rent. Acumulada, Ganho Total (R$), Dias Úteis
  - 2 abas: Patrimônio Líquido (R$) e Rentabilidade Acumulada (%)
  - Tabela expansível dia-a-dia com Var. Dia (R$), Var. Dia (%), Acumulado (%)
- ✅ Infraestrutura market_data (BACEN, CVM, brapi, resolver, cache SQLite)

### Pendências

- 🔶 CVM fuzzy match CNPJ para fundos (código pronto, CNPJ não populado)

---

## 15. Como retomar uma sessão

1. Abra o Cowork e selecione a pasta do projeto (`Consolidador/`)
2. Cole o conteúdo deste arquivo no início da conversa com Claude
3. Diga o que quer fazer — Claude terá contexto completo imediatamente
4. Ao final da sessão, peça a Claude para atualizar a **seção 14** com o novo estado

---

## 16. Deploy — Streamlit Community Cloud

**Repositório GitHub:**
`https://github.com/Diefenb/https-github.com-SeuUsuario-api-consolidador`

**Para conectar ao Streamlit Community Cloud (primeira vez):**
1. Acesse `share.streamlit.io` com a conta Google/GitHub do Gabriel
2. "Create app" → "From existing repo"
3. Repositório: `Diefenb/https-github.com-SeuUsuario-api-consolidador`
4. Branch: `main` | Main file: `app.py`
5. Deploy! — lê `requirements.txt` automaticamente
6. Em Settings → Secrets, adicionar: `ANTHROPIC_API_KEY = "sk-ant-..."` (só para fluxo IA)

**Após conectado, deploys futuros são automáticos** com qualquer `git push origin main`.

---

## 17. Módulo de Rentabilidade Histórica Diária — Referência técnica completa

> Implementado em 2026-03-14 e aperfeiçoado com dados reais de mercado por ativo.

### 17.1 Conceito central

Reconstrói o valor diário histórico do portfólio **retroagindo da data âncora** (último relatório da corretora). Para cada ativo, aplica o inverso das taxas/preços/NAVs reais de cada dia útil:

```
saldo[D-1] = saldo[D] / (1 + taxa_real_D)
```

Somando todos os ativos por dia → PL diário consolidado com dados reais de mercado.

**Fontes de dados por tipo de ativo:**

| tipo_projecao | Fonte | Qualidade |
|---|---|---|
| `cdi_pct` | BACEN série 12 (taxa diária real) | Exato |
| `cdi_spread` | BACEN série 12 + spread anual → diário | Exato |
| `ipca_spread` | BACEN série 433 (IPCA mensal/du_mes) + spread | Alta |
| `prefixado` | Fórmula `(1+taxa)^(1/252)` | Exato |
| `fundo_cota` | CVM inf_diario NAVs (se CNPJ disponível) | Real |
| `rv_preco` | yfinance full history (se ticker disponível) | Real |
| `fundo_cota` sem CNPJ | CDI fallback | Aproximado |
| `sem_projecao` | CDI fallback | Aproximado |

**Fallback em cascata:** CVM/yfinance → CDI real BACEN → 0,0555%/dia (hardcoded)

### 17.2 `historico.py` — Módulo de reconstrução

**Localização:** `Consolidador_V3/src/historico.py`

**Função principal:**
```python
from historico import reconstruct_from_assets

registros = reconstruct_from_assets(dados_consolidados, cache=cache)
# dados_consolidados precisa ter:
#   - data_referencia: str (âncora)
#   - ativos_consolidados: list com _projecao em cada ativo
#   - evolucao_por_conta: list (para determinar data_inicio)
# Retorna: [{"data", "pl", "rent_dia_rs", "rent_dia_pct", "rent_acum_pct"}, ...]
```

**Algoritmo:**
1. `data_ancora` = `dados["data_referencia"]` (data do último relatório)
2. `data_inicio` = primeiro dia do mês mais antigo em `evolucao_patrimonial` (~12 meses)
3. Busca CDI (BACEN série 12) e IPCA (BACEN série 433) para o período completo
4. Para fundos com CNPJ: busca série de NAVs via CVM inf_diario mensal (ZIPs)
5. Para ações/FIIs com ticker: busca série de preços via yfinance `.history()`
6. Para cada ativo: `_reconstruir_ativo()` retrocede dia-a-dia aplicando taxa inversa
7. Soma todos os ativos por dia útil → série diária de PL consolidado

**Fórmulas de retroação:**
```python
# CDI %:     saldo[D-1] = saldo[D] / (1 + cdi_D/100 * pct/100)
# CDI+spread: saldo[D-1] = saldo[D] / (1 + cdi_D/100 + (1+spread/100)^(1/252)-1)
# IPCA+spread: taxa_ipca = (1+ipca_M/100)^(1/du_M) - 1  por dia útil do mês
#              saldo[D-1] = saldo[D] / (1 + taxa_ipca + taxa_spread)
# Prefixado:  saldo[D-1] = saldo[D] / (1 + taxa_aa/100)^(1/252)
# Fundo:      saldo[D-1] = saldo[D] * (nav[D-1] / nav[D])
# RV:         saldo[D-1] = saldo[D] * (price[D-1] / price[D])
```

**Fallback mensal** (`_fallback_mensal`): quando ativos não têm `_projecao`, usa interpolação geométrica entre âncoras mensais de `evolucao_patrimonial` (método original). Alias `reconstruct_daily()` mantido para compatibilidade.

### 17.3 Integração com `app.py`

**Enriquecimento automático no processamento:**
```python
# Em _processar_arquivos(), após normalize():
from enricher import enrich_portfolio
norm = enrich_portfolio(norm, use_cvm=False)  # regex only, rápido
# _projecao é adicionado a cada ativo → preservado pelo deepcopy do consolidator
# → disponível em dados["ativos_consolidados"][i]["_projecao"]
```

**Reconstruct no dashboard:**
```python
# _section_rentabilidade_diaria(dados):
from historico import reconstruct_from_assets
registros = reconstruct_from_assets(dados)
# Fallback automático para reconstruct_daily() em caso de erro
```

**Posição no dashboard:**
```
Cards de métricas
↓ Evolução Patrimonial | Rentabilidade Mês a Mês
↓ Patrimônio por Conta | Alocação por Estratégia
↓ Download Excel | Nova Importação
↓ [DIVIDER]
↓ Rentabilidade Diária — Histórico Consolidado
    ↓ Métricas: PL Final | Rent. Acumulada | Ganho Total | Dias Úteis
    ↓ Nota: "Dados reais: CDI BACEN, IPCA BACEN, NAVs CVM, yfinance (ações/FIIs)"
    ↓ Tab "Patrimônio Líquido (R$)" — linha azul com área fill
    ↓ Tab "Rentabilidade Acumulada (%)" — linha verde/vermelha + baseline zero
    ↓ Expander "Detalhamento Diário" — tabela:
        Data | PL (R$) | Var. Dia (R$) | Var. Dia (%) | Acumulado (%)
```

### 17.4 Infraestrutura `market_data/` — referência

Os módulos `market_data/` foram construídos para alimentar projeções futuras e poderão ser integrados ao histórico diário quando necessário (ex: usar CDI real para shape intra-mês em vez de interpolação geométrica).

#### `market_data/cache.py` — SQLiteCache

```python
db_path = Consolidador/data/market_data/market_cache.db
```

4 tabelas SQLite:
- `taxas_diarias(data, serie, valor, updated_at)` — CDI e IPCA do BACEN
- `cotas_fundos(cnpj, data, valor_cota, updated_at)` — cotas CVM por CNPJ
- `precos_rv(ticker, data, fechamento, updated_at)` — ações/FIIs
- `resolved_assets(nome_original, tipo_projecao, cnpj, ticker, pct_cdi, spread_aa, taxa_prefixada_aa, match_score, confianca, resolved_at, override_manual)` — cache de resoluções

**Boas práticas:**
- `override_manual = 1` protege correções manuais de serem sobrescritas
- `get_resolved()` é chamado antes de qualquer lógica — cache evita re-executar fuzzy matching

#### `market_data/bacen.py` — BACEN SGS API

**⚠️ Fato crítico — ler antes de qualquer manutenção:**

A **série 12 (CDI) retorna taxa DIÁRIA em %**, não taxa anual.
- Valor típico: `0.055131` = 0,055131% ao dia ≈ 14,9% a.a.
- Para usar: `daily_rate = valor / 100` (já é diária)
- **NÃO** usar `(1 + taxa/100)^(1/252)` — seria dobrar a conversão

A **série 433 (IPCA)** retorna taxa mensal em %.
- Endpoint `/ultimos/N` retorna **400 Bad Request** — usar `_fetch_serie()` com range de datas

#### `market_data/resolver.py` — Resolução de tipos de ativo

**Prioridade das regras (ordem importa):**

1. **CDI %**: `r"(\d+[,.]?\d*)\s*%\s*(?:DO\s+)?(?:CDI|DI)\b"` — "92,00% CDI", "100% do CDI"
2. **IPCA+**: `r"IPC(?:-?A)?\s*\+\s*([\d,]+)%"` — **crítico**: `(?:-?A)?` cobre AMBOS "IPC-A +" e "IPCA +"
3. **CDI+spread**: `r"(?:CDI|DI)\s*\+\s*([\d,]+)%"` — "CDI + 0,50%"
4. **Fundo** (por nome): `r"\b(?:FIC|FIF|FIDC|FIA|FIRF|FICF|FUNDO|FUND|FIAGRO|FIP|CI)\b"` — "CI" = Capital Investimento
5. **Ticker B3**: `r"\b([A-Z]{4}\d{1,2})\b"` — ações e FIIs
6. **Prefixado** (final da string): `r"[-–]\s*(\d{1,2}[,.]?\d+)%(?:\s*a\.?a\.?)?\s*$"` — "- 12,25%"

**Cobertura validada (Jose Mestrener, 26 ativos, XP 3245269):**
- `fundo_cota`: 15 (58%)
- `ipca_spread`: 7 (27%)
- `prefixado`: 3 (12%)
- `cdi_pct`: 1 (4%)
- **Total: 100% cobertura** (sem CVM fuzzy match)

#### `market_data/cvm_funds.py`

- Cadastral: `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_classe.csv`
- Salvo em: `data/market_data/cvm_cadastral_cache.csv`
- Refresh automático se > 7 dias
- Fuzzy match: `rapidfuzz.fuzz.WRatio`; score ≥ 85 = alta, 70–84 = média, < 70 = rejeitado

#### `market_data/rv_prices.py`

- brapi.dev primary, yfinance (`.SA` suffix) fallback
- Cache em `precos_rv` SQLite

### 17.5 Dependências (pós 2026-03-14)

```
rapidfuzz>=3.6.0    # fuzzy match nome → CNPJ CVM
bizdays>=0.3.12     # calendário ANBIMA (opcional — tem fallback)
yfinance>=0.2.36    # preços RV fallback
requests>=2.31.0    # APIs BACEN, CVM, brapi
```

### 17.6 Boas práticas de manutenção

1. **Nunca modificar a fórmula CDI sem ler 17.4** — série 12 já retorna taxa diária
2. **`override_manual = 1` no SQLite** — ao corrigir manualmente um CNPJ, setar este campo
3. **Adicionar novos padrões de ativo** em `resolver.py::_resolve_by_regex()` na posição correta de prioridade
4. **Testar sempre nos 26 ativos reais** do `xp_3245269_v3.json`
5. **Cache SQLite** está em `data/market_data/market_cache.db` — não commitar (está no .gitignore via `data/`)

---

## 18. Deploy — Variáveis de ambiente opcionais

| Variável | Onde usar | Obrigatório |
|----------|-----------|-------------|
| `ANTHROPIC_API_KEY` | Fluxo exceção (PDF desconhecido) | Não |
| `BRAPI_TOKEN` | brapi.dev (RV/FIIs) | Não (15k req/mês sem token) |

Setar no Streamlit Cloud: Settings → Secrets:
```toml
ANTHROPIC_API_KEY = "sk-ant-..."
BRAPI_TOKEN = "token_brapi_aqui"
```
