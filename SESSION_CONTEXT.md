# SESSION_CONTEXT.md — Consolidador de Carteiras API Capital

> **Como usar:** Cole este arquivo no início de qualquer nova conversa com Claude para restaurar o contexto completo do projeto imediatamente. Atualize a seção "Estado Atual" ao final de cada sessão produtiva.

---

## 1. O que é este projeto

Sistema de consolidação de carteiras de investimentos para assessores financeiros da **API Capital / Capital Investimentos**. Processa relatórios PDF de corretoras (XP e BTG), extrai dados, normaliza, consolida múltiplas contas de um mesmo cliente e gera relatório Excel. A partir de 2026-03-14, projeta posições para D0 usando taxas de mercado reais.

**Usuário:** Gabriel (gabidiefenbach@gmail.com)
**Pasta do projeto:** `/Consolidador/` (pasta selecionada no Cowork)

---

## 2. Regra Fundamental (nunca violar)

**SOMENTE DADOS REAIS.** Todo número no relatório final deve ter origem rastreável em um PDF de corretora. Zero cálculos implícitos de rentabilidade. Zero estimativas. Campo sem dados = null. O relatório da corretora é soberano.

> **Exceção explícita:** O módulo de projeção pro-rata-die (seção 17) é uma estimativa declarada, sempre rotulada como "Estimativa — não substitui o relatório oficial".

---

## 3. Arquitetura

```
FLUXO PRINCIPAL (sem IA, custo zero — uso diário):
XP PDF  ──→ Parser Determinístico (pdfplumber) ──→ JSON canônico ─┐
BTG PDF ──→ Parser Determinístico (pdfplumber) ──→ JSON canônico ─┤──→ Consolidador ──→ Excel
JSON/XLSX importado manualmente ──────────────────────────────────┘

FLUXO PRO-RATA-DIE (novo — atualização diária sem PDF):
JSON canônico ──→ Enricher (resolve tipo de ativo) ──→ Projector ──→ Saldo estimado D0
                  (regex nome + CVM fuzzy match)      (taxas BACEN/CVM/brapi)

FLUXO EXCEÇÃO (com IA, sob demanda, ~R$0,50–1,50/PDF):
PDF de corretora nova ──→ Claude API (Sonnet) ──→ JSON canônico ──→ entra no fluxo principal
```

---

## 4. Estrutura de arquivos

```
Consolidador/
├── SESSION_CONTEXT.md             ← ESTE ARQUIVO (atualizar a cada sessão)
├── app.py                         ← Streamlit web app (~955 linhas, UI v2 + seção D0 ✅)
├── consolidar.py                  ← CLI alternativo
├── requirements.txt               ← inclui rapidfuzz, bizdays, yfinance (pós 2026-03-14)
├── .env                           ← ANTHROPIC_API_KEY (não tocar, não recriar)
│
├── Consolidador_V3/               ← VERSÃO ATIVA DO CÓDIGO
│   ├── CLAUDE.md                  ← doc técnica V3 (sempre ler ao iniciar)
│   ├── plano_consolidador_v3.md
│   ├── plano_ui_v2.md
│   ├── plano_biblioteca_dados_prorata.md  ← plano original do módulo pro-rata-die
│   ├── src/
│   │   ├── parsers/
│   │   │   ├── __init__.py        ← detect_and_parse() — detecta por conteúdo, 2 páginas
│   │   │   ├── xp_performance.py  ← parse_xp_performance() — 707 linhas ✅
│   │   │   └── btg_performance.py ← parse_btg_performance() — ~500 linhas ✅
│   │   ├── market_data/           ← NOVO — módulo de dados de mercado (2026-03-14)
│   │   │   ├── __init__.py        ← expõe get_cache(), fetch_cdi_range(), fetch_ipca_ultimos()
│   │   │   ├── cache.py           ← SQLiteCache — 4 tabelas com TTL
│   │   │   ├── bacen.py           ← BACEN SGS série 12 (CDI) e 433 (IPCA)
│   │   │   ├── cvm_funds.py       ← cotas CVM + cadastral + fuzzy match CNPJ
│   │   │   ├── rv_prices.py       ← preços ações/FIIs via brapi.dev + yfinance
│   │   │   └── resolver.py        ← resolução nome → tipo_projecao + parâmetros
│   │   ├── enricher.py            ← NOVO — orquestra resolução + persiste JSON enriquecido
│   │   ├── projector.py           ← NOVO — cálculo pro-rata-die para D0
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
├── data/                          ← NOVO — cache e posições enriquecidas (2026-03-14)
│   ├── market_data/
│   │   ├── market_cache.db        ← SQLite: taxas CDI/IPCA, cotas CVM, preços RV, resoluções
│   │   └── cvm_cadastral_cache.csv ← cadastral CVM (refresh < 7 dias, ~50MB)
│   └── posicoes/                  ← JSON enriquecidos por cliente (âncora + metadados)
│       ├── jose_mestrener_posicoes.json  (gerado ao salvar via enricher.salvar_posicoes)
│       └── ...
│
└── output/
    ├── consolidado_jose_2026-01.xlsx
    └── extractions/ (JSONs via IA — ground truth)
```

---

## 5. Clientes processados

| Cliente | Contas | Patrimônio Total | Status |
|---------|--------|-----------------|--------|
| Jose Goncalves Mestrener Junior | XP 3245269, XP 8660669, BTG 4016217, BTG 4019474 | R$ 4.902.064,78 | ✅ Excel + projeção D0 testada |
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
- `evolucao_patrimonial` — tabela mensal com patrimônio inicial/final, IR, IOF
- `ativos` — lista detalhada com saldo, qtd, % alocação, rentabilidades
- `movimentacoes` — histórico de entradas/saídas

**Campos adicionados pelo módulo de projeção (nunca persistir no JSON canônico original):**
- `ativos[i]._projecao` — tipo_projecao, pct_cdi, spread_aa, taxa_prefixada_aa, cnpj, ticker, confianca
- `ativos[i]._proj_resultado` — saldo_projetado, variacao_rs, variacao_pct, metodo, detalhe
- `projecao_d0` — pl_ancora, pl_estimado, variacao_rs, variacao_pct, dias_uteis_projetados, cobertura_pct

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
12. **Projeção D0: estimativa declarada** — toda exibição deve ter aviso "Estimativa — não substitui relatório oficial"
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
| 5 | Módulo pro-rata-die — posições D0 | ✅ Implementado | Sprints 1-4 completos |
| 6 | CVM fuzzy match CNPJ para fundos | 🔶 Parcial | Código pronto, CNPJ não populado para José Mestrener |
| 7 | Tabela rentabilidade Excel (visual) | Alta | Implementada, não validada com BTG |
| 8 | Área de remoção de ativos (PL parcial) | Média | UI para excluir ativos antes de consolidar |
| 9 | Gráficos embutidos no Excel | Média | Charts Plotly no Excel exportado |
| 10 | Importação de extratos via IA | Baixa | Além dos relatórios mensais |

---

## 14. Estado atual do projeto

**Última atualização:** 2026-03-14

### Histórico de commits

```
(novo)  feat: implement pro-rata-die projection module with market data APIs
8ce97e9 fix: remove illegal XML chars from BTG asset names before Excel write
b03bb2f docs: update SESSION_CONTEXT with UI v2 progress and deploy instructions
0a71f6f feat: redesign UI with dark sidebar, dashboard view, and Plotly charts
98217a2 feat: implement full BTG parser and fix XP/BTG routing
30e4143 Added Dev Container Folder
```

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

## 17. Módulo Pro-Rata-Die — Referência técnica completa

> Implementado em 2026-03-14. Projeta posições para D0 usando taxas de mercado reais a partir da âncora do último relatório.

### 17.1 Conceito central

```
[Saldo do último relatório]  →  [Projeção N dias com taxas reais]  →  [Estimativa D0]
      (âncora — dado real)                                               (rotulada)
```

O saldo do relatório já incorpora toda a rentabilidade histórica, IR, IOF e movimentações. Projetamos apenas os dias entre o último relatório e hoje — tipicamente 15–45 dias. Zero risco de erros acumulados desde a compra.

### 17.2 Módulos e responsabilidades

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
- `override_manual = 1` protege correções manuais de serem sobrescritas na próxima resolução automática
- Cache de resoluções evita re-executar fuzzy matching a cada run
- `get_resolved()` é chamado antes de qualquer lógica — se tiver cache com `tipo_projecao`, retorna direto

#### `market_data/bacen.py` — BACEN SGS API

**⚠️ Fato crítico — ler antes de qualquer manutenção:**

A **série 12 (CDI) retorna taxa DIÁRIA em %**, não taxa anual.
- Valor típico: `0.055131` = 0,055131% ao dia ≈ 14,9% a.a.
- Para usar: `daily_rate = valor / 100` (já é diária)
- Para 92% CDI: `fator_dia = 1 + (valor/100) * (92/100)`
- **NÃO** usar `(1 + taxa/100)^(1/252)` — seria dobrar a conversão

A **série 433 (IPCA)** retorna taxa mensal em %.
- Endpoint `/ultimos/N` retorna **400 Bad Request** — usar `_fetch_serie()` com range de datas
- Endpoint correto: `/dados?formato=json&dataInicial=DD/MM/YYYY&dataFinal=DD/MM/YYYY`

```python
# ✅ Correto — CDI diário
daily_cdi = taxa_diaria_pct / 100.0   # 0.055131 / 100 = 0.00055131
fator_dia = 1.0 + daily_cdi * (pct_cdi / 100.0)

# ❌ Errado — dobra a conversão
daily_cdi = (1 + taxa/100) ** (1/252) - 1   # NÃO FAZER
```

#### `market_data/resolver.py` — Resolução de tipos de ativo

Resolve o nome do ativo → tipo de projeção + parâmetros, sem chamar API externa.
Usa cache SQLite (`resolved_assets`) para persistir resultados entre runs.

**Prioridade das regras (ordem importa):**

1. **CDI %**: `r"(\d+[,.]?\d*)\s*%\s*(?:DO\s+)?(?:CDI|DI)\b"` — cobre "92,00% CDI", "100% do CDI"
2. **IPCA+**: `r"IPC(?:-?A)?\s*\+\s*([\d,]+)%"` — **crítico**: `(?:-?A)?` cobre AMBOS "IPC-A +" e "IPCA +"
3. **CDI+spread**: `r"(?:CDI|DI)\s*\+\s*([\d,]+)%"` — cobre "CDI + 0,50%"
4. **Fundo** (por nome): `r"\b(?:FIC|FIF|FIDC|FIA|FIRF|FICF|FUNDO|FUND|FIAGRO|FIP|CI)\b"` — "CI" = Capital Investimento
5. **Ticker B3**: `r"\b([A-Z]{4}\d{1,2})\b"` — cobre ações e FIIs
6. **Prefixado** (final da string): `r"[-–]\s*(\d{1,2}[,.]?\d+)%(?:\s*a\.?a\.?)?\s*$"` — "- 12,25%"

**Resultado de cobertura em produção (Jose Mestrener, 26 ativos):**
- `fundo_cota`: 15 (58%) — ex: V8 Mercury CI, SPX Seahawk, Sparta Max
- `ipca_spread`: 7 (27%) — ex: CDB XP IPCA+10.20%, NTN-B IPCA+6.25%
- `prefixado`: 3 (12%) — ex: CDB FACTA 12.25%, CRA UNIDAS 13.70%
- `cdi_pct`: 1 (4%) — LCD BRDE 92% CDI
- **Total: 100% cobertura** (sem CVM fuzzy match)

**Para adicionar novos padrões de ativo:** Inserir na função `_resolve_by_regex()` antes do `return None`, na posição correta de prioridade. Sempre testar contra os ativos reais dos dois clientes.

#### `market_data/cvm_funds.py` — Cotas e CNPJ de fundos

**Cadastral CVM:**
- URL: `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_classe.csv`
- Salvo em: `data/market_data/cvm_cadastral_cache.csv`
- Refresh automático se > 7 dias (via `ensure_cadastral_cache()`)
- Filtrar por `Situacao == "EM FUNCIONAMENTO NORMAL"` (~80k de 300k linhas)
- Requer `rapidfuzz` instalado — sem ele, fuzzy match é desabilitado

**Fuzzy match:** `rapidfuzz.fuzz.WRatio` entre nome normalizado do PDF e `Denominacao_Social` da CVM
- Score ≥ 85 → `confianca = "alta"` + CNPJ aceito
- Score 70-84 → `confianca = "media"` + CNPJ aceito com aviso
- Score < 70 → CNPJ rejeitado, `tipo_projecao = "fundo_cota"` sem CNPJ

**Cotas diárias (inf_diario):**
- URL: `https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip`
- ZIP com CSV, ~10MB comprimido por mês
- Latência D+1 (~10h do dia seguinte)
- FIIs: preferir preço B3 via brapi (mais atualizado) em vez de cota CVM

#### `market_data/rv_prices.py` — Preços RV

- **brapi.dev**: endpoint `https://brapi.dev/api/quote/{ticker}` — token via `BRAPI_TOKEN` env var
- **yfinance fallback**: `yf.Ticker("{ticker}.SA")` — sufixo `.SA` obrigatório para ativos B3
- Preço atual: tentativa brapi → fallback yfinance
- Preço histórico: tentativa brapi com `range=1mo` → fallback yfinance com `history()`
- Cache em `precos_rv` com data de fechamento

#### `enricher.py` — Orquestrador de enriquecimento

```python
from enricher import enrich_portfolio, salvar_posicoes, carregar_posicoes

# Enriquecer um relatório
enriched = enrich_portfolio(relatorio_json, use_cvm=True)

# Salvar para uso futuro (âncora persistida)
caminho = salvar_posicoes(enriched, "jose mestrener")

# Recarregar em outra sessão
enriched = carregar_posicoes("jose mestrener")
```

**Posições salvas em:** `data/posicoes/<cliente>_posicoes.json`

**Importante:** `use_cvm=True` ativa o fuzzy match contra o cadastral CVM (necessário para obter CNPJ de fundos). A primeira execução baixa ~50MB do cadastral.

#### `projector.py` — Cálculo das projeções

```python
from projector import project_portfolio

resultado = project_portfolio(relatorio_enriquecido, data_hoje=date(2026, 3, 14))
proj = resultado["projecao_d0"]
# proj["pl_ancora"], proj["pl_estimado"], proj["variacao_pct"], ...
```

**Fórmulas implementadas:**

| Tipo | Fórmula | Dados necessários |
|------|---------|------------------|
| `cdi_pct` | `VA × ∏(1 + cdi_dia × pct/100)` para cada dia útil | BACEN série 12 |
| `cdi_spread` | `VA × ∏(1 + cdi_dia + spread_diario)` | BACEN série 12 |
| `ipca_spread` | `VA × fator_ipca × (1+spread)^(du/252)` | BACEN série 433 |
| `prefixado` | `VA × (1+taxa)^(du/252)` | Sem API |
| `fundo_cota` | `VA / cota_ancora × cota_hoje` | CVM inf_diario |
| `rv_preco` | `VA / preco_ancora × preco_hoje` | brapi/yfinance |
| `caixa` | Não projetar | — |
| `sem_projecao` | Exibir âncora | — |

**Calendário de dias úteis:**
- Tenta `bizdays.Calendar.load("ANBIMA")` com feriados corretos
- Fallback: Seg-Sex sem feriados (leve subestimação em semanas com feriados)

**Campo `_proj_resultado` adicionado a cada ativo:**
```json
{
  "saldo_projetado": 54526.80,
  "variacao_rs": 626.85,
  "variacao_pct": 1.1629,
  "metodo": "ipca_spread",
  "detalhe": "IPCA + 10.20%",
  "confianca": "alta"
}
```

### 17.3 Integração com app.py

A seção "Posições Estimadas D0" é um `st.expander()` no dashboard, aparece após download do Excel. Não bloqueia o fluxo principal.

```python
# Fluxo no app.py:
relatorios, hist, erros = _processar_arquivos(uploaded_files)
dados = consolidate(reports=relatorios, ...)
generate_report(dados, excel_path)

st.session_state["relatorios_individuais"] = relatorios  # ← novo

# No dashboard:
_posicoes_d0_section(relatorios_individuais)
# → chama enrich_portfolio() + project_portfolio() internamente
```

**Import lazy para não bloquear o app se dependências não estiverem instaladas:**
```python
def _import_projecao():
    try:
        from enricher import enrich_portfolio
        from projector import project_portfolio
        return enrich_portfolio, project_portfolio
    except Exception:
        return None, None
```

### 17.4 Resultados validados em produção

**Base:** Jose Mestrener / XP 3245269 / âncora 2026-01-30 / projeção 2026-03-14 (30 dias úteis)

| Ativo | Tipo | Variação | Esperado |
|-------|------|---------|---------|
| LCD BRDE 92% CDI | cdi_pct | +1,53% | 30du × 0,0507%/du ≈ 1,53% ✅ |
| CDB XP IPCA+10,20% | ipca_spread | +1,94% | IPCA~1,03% + spread~1,21% ≈ 2,2% ✓ |
| CDB FACTA 12,25% a.a. | prefixado | +1,39% | (1,1225)^(30/252) = 1,0138 ✅ |
| CDB Paraná 14,20% a.a. | prefixado | +1,59% | (1,1420)^(30/252) = 1,0159 ✅ |
| CRA UNIDAS 13,70% a.a. | prefixado | +1,54% | (1,1370)^(30/252) = 1,0155 ✅ |

**PL total âncora:** R$ 1.808.182 → **Estimativa D0:** R$ 1.816.993 (+R$ 8.811 / +0,49%)

### 17.5 Dependências novas (pós 2026-03-14)

```
rapidfuzz>=3.6.0    # fuzzy match nome → CNPJ CVM
bizdays>=0.3.12     # calendário ANBIMA (opcional — tem fallback)
yfinance>=0.2.36    # preços RV fallback
requests>=2.31.0    # já existia — APIs BACEN, CVM, brapi
```

Instalar: `pip install rapidfuzz bizdays yfinance`

### 17.6 Boas práticas de manutenção

1. **Nunca modificar a fórmula CDI sem ler a seção 17.2** — a série 12 já retorna taxa diária
2. **`override_manual = 1` no SQLite** — ao corrigir manualmente um CNPJ no banco, setar este campo para proteger da próxima re-resolução
3. **Adicionar novos padrões de ativo** em `resolver.py::_resolve_by_regex()` na posição correta (CDI tem precedência sobre IPCA+ que tem precedência sobre PRE)
4. **Testar sempre nos 26 ativos reais** do xp_3245269_v3.json antes de commitar mudanças no resolver
5. **Cache SQLite** está em `data/market_data/market_cache.db` — não commitar no git (está no .gitignore implícito via `data/`)
6. **Atualizar cadastral CVM** é automático (>7 dias) — se forçar, chamar `ensure_cadastral_cache(force=True)`
7. **Projeção de fundos** só funciona se CNPJ estiver mapeado — o fuzzy match CVM automaticamente faz isso se `use_cvm=True`

### 17.7 O que falta para cobertura completa de fundos

Os 15 fundos classificados como `fundo_cota` precisam de CNPJ para projeção. Próximos passos:
1. Rodar `enrich_portfolio(relatorio, use_cvm=True)` — download do cadastral CVM (~50MB)
2. Verificar os matches no SQLite (`resolved_assets` onde `tipo_projecao='fundo_cota'`)
3. Para matches com `confianca='baixa'`, corrigir manualmente o CNPJ e setar `override_manual=1`
4. Após correto, `fetch_fund_nav()` busca as cotas automaticamente da CVM

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
