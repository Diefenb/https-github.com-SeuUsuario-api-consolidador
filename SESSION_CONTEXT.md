# SESSION_CONTEXT.md — Consolidador de Carteiras API Capital

> **Como usar:** Cole este arquivo no início de qualquer nova conversa com Claude para restaurar o contexto completo do projeto imediatamente. Atualize a seção "Estado Atual" ao final de cada sessão produtiva.

---

## 1. O que é este projeto

Sistema de consolidação de carteiras de investimentos para assessores financeiros da **API Capital / Capital Investimentos**. Processa relatórios PDF de corretoras (XP e BTG), extrai dados, normaliza, consolida múltiplas contas de um mesmo cliente e gera relatório Excel e PDF.

**Usuário:** Gabriel (gabidiefenbach@gmail.com)
**Pasta do projeto:** `/Consolidador/` (pasta selecionada no Cowork)

---

## 2. Regra Fundamental (nunca violar)

**SOMENTE DADOS REAIS.** Todo número no relatório final deve ter origem rastreável em um PDF de corretora. Zero cálculos implícitos de rentabilidade. Zero estimativas. Campo sem dados = null. O relatório da corretora é soberano.

---

## 3. Arquitetura

```
FLUXO PRINCIPAL (sem IA, custo zero — uso diário):
XP PDF  ──→ Parser Determinístico (pdfplumber) ──→ JSON canônico ─┐
BTG PDF ──→ Parser Determinístico (pdfplumber) ──→ JSON canônico ─┤──→ Consolidador ──→ Excel
JSON/XLSX importado manualmente ──────────────────────────────────┘

FLUXO EXCEÇÃO (com IA, sob demanda, ~R$0,50–1,50/PDF):
PDF de corretora nova ──→ Claude API (Sonnet) ──→ JSON canônico ──→ entra no fluxo principal
```

---

## 4. Estrutura de arquivos

```
Consolidador/
├── SESSION_CONTEXT.md             ← ESTE ARQUIVO (atualizar a cada sessão)
├── CLAUDE.md                      ← referência técnica detalhada (não apagar)
├── app.py                         ← Streamlit web app (interface principal, 253 linhas)
├── consolidar.py                  ← CLI alternativo
├── requirements.txt
├── .env                           ← ANTHROPIC_API_KEY (não tocar, não recriar)
│
├── Consolidador_V3/               ← VERSÃO ATIVA DO CÓDIGO
│   ├── CLAUDE.md                  ← doc técnica V3 (mais completa)
│   ├── plano_consolidador_v3.md   ← cronograma e roadmap
│   ├── src/
│   │   ├── parsers/
│   │   │   ├── __init__.py        ← detect_and_parse()
│   │   │   ├── xp_performance.py  ← parse_xp_performance() — 707 linhas, IMPLEMENTADO
│   │   │   └── btg_performance.py ← parse_btg_performance() — ~500 linhas, IMPLEMENTADO ✅
│   │   ├── consolidator.py        ← agregação entre contas
│   │   ├── normalizer.py          ← normalize_strategy() + clean_asset_name()
│   │   ├── report_generator.py    ← geração Excel 6 abas (510 linhas)
│   │   ├── importer.py            ← importação de JSON/XLSX padrão
│   │   └── utils.py               ← helpers (parse_br_number, formatação)
│   ├── schemas/consolidador_v2.json  ← JSON Schema Draft-07
│   ├── templates/importacao_template.xlsx
│   └── tests/
│       ├── test_parsers.py
│       └── fixtures/              ← VAZIO (ainda sem ground truth validado aqui)
│
├── output/
│   ├── consolidado_jose_2026-01.xlsx       ← relatório Jose Mestrener gerado
│   ├── consolidado_jose_2026-01_v2.xlsx    ← versão refinada
│   ├── consolidado_cid_tania_2026-01.xlsx
│   ├── consolidado_cid_tania_2026-01_v2.xlsx
│   └── extractions/
│       ├── jose_mestrener/        ← JSONs extraídos via IA (ground truth)
│       ├── btg_5058054.json       ← Cid e Tania / BTG
│       ├── btg_5165904.json
│       ├── xp_14522738.json       ← Cid e Tania / XP
│       └── xp_3476739.json
│
├── plano_projeto_consolidacao_v2_2.md  ← doc de decisões antigas (referência)
└── prompt_gemini_identidade_visual.md  ← identidade visual Capital Investimentos
```

---

## 5. Clientes processados

| Cliente | Contas | Patrimônio Total | Status |
|---------|--------|-----------------|--------|
| Jose Goncalves Mestrener Junior | XP 3245269, XP 8660669, BTG 4016217, BTG 4019474 | R$ 4.902.064,78 | ✅ Excel gerado (v2) |
| Cid e Tania | XP 14522738, XP 3476739, BTG 5058054, BTG 5165904 | (a validar) | ✅ Excel gerado (v2) |

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
| BTG PDF roteado para XP parser | `app.py` usava `"btg" in file.name` — PDFs BTG se chamam `RelatorioDePerformance-XXXXXXX.pdf`. Resolvido: `detect_and_parse` por conteúdo |
| `detect_and_parse` não reconhecia BTG | Texto BTG tem `"Relatório\nde Performance"` com `\n` no meio. Resolvido: regex `r"Relat.{0,4}rio\s*[\n\s]+de\s+Performance"` + leitura de 2 páginas |
| BTG ligatura "fi" → `\x00` | pdfplumber substitui a ligatura fi por `\x00` null byte. Ex: "fixado" → "\x00xado". Resolvido: `_STRAT_CANONICAL` com padrões regex `\x00xado` |
| Nomes de estratégia BTG mangled em composição | `_parse_composicao` usava `re.sub(r"[\x00]", "")` simples, resultando em "Pós-xado". Resolvido: substituir por `_normalize_btg_strategy()` |

---

## 11. Stack tecnológico

| Componente | Tecnologia |
|-----------|-----------|
| Extração PDF (fluxo principal) | `pdfplumber` |
| Extração PDF (exceção) | Claude API — Sonnet |
| Consolidação / normalização | Python / pandas |
| Relatório output | Excel (openpyxl) |
| Interface web | Streamlit |
| Armazenamento | JSON files por cliente/mês |
| Deploy | Streamlit Community Cloud |

---

## 12. Identidade visual (para UI e relatórios)

- **Cor primária:** Azul escuro `#0D1B3E`
- **Cor secundária / destaque:** Azul médio `#1E4D8C` / turquesa `#0097A7`
- **Fundo:** Off-white `#F8FAFC`
- **Cards:** Branco `#FFFFFF` com borda `#E2E8F0`
- **Fonte:** Inter (400, 500, 600)
- **Logo:** Capital Investimentos (sidebar esquerda)
- **Referência de UI:** Dashboard com 4 cards de métrica no topo, sidebar fixa, gráfico de área para evolução PL, barras verticais para rentabilidade mês a mês

---

## 13. Backlog de features (To-Do List)

> Ordem sugerida de implementação baseada em impacto × esforço.

| # | Feature | Prioridade | Observações |
|---|---------|-----------|-------------|
| 1 | **Arquivo de contexto de sessão** | ✅ Feito | Este arquivo |
| 2 | **Parser BTG completo** | ✅ Feito | ~500 linhas — state machine, todas as seções, testado vs ground truth |
| 3 | **Aprimorar UI** | Alta | Seguir mockups Capital Investimentos (dashboard com métricas + gráficos) |
| 4 | **Tabela rentabilidade mensal + Benchmarks** | Alta | Dados já extraídos, falta aba/seção dedicada no relatório |
| 5 | **Gráficos de rentabilidade e evolução PL** | Média | No Streamlit e embutido no Excel/PDF |
| 6 | **Área de remoção de ativos (PL parcial)** | Média | UI para excluir ativos antes de consolidar |
| 7 | **Ajuste template PDF e Excel exportado** | Média | Identidade visual API Capital nos outputs |
| 8 | **Importação de extratos via IA + lançamento manual** | Média | Expandir além dos relatórios mensais de performance |
| 9 | **Carteiras de recomendação** | Baixa | Integração com planilhas asset da API Capital |

---

## 14. Estado atual do projeto (atualizar a cada sessão)

**Última atualização:** 2026-03-07

### O que foi feito nesta sessão (2026-03-07)

#### 1. Parser BTG completo — `btg_performance.py` (81 → ~500 linhas)

O parser foi reescrito do zero. Antes existiam apenas 81 linhas de esqueleto sem lógica real. Agora cobre todas as seções do PDF BTG:

**Seções extraídas:**
- **Capa (pág. 0):** nome do cliente, número da conta (sem zeros à esquerda), data de referência (data final do período). Regex com `.{0,3}` para absorver `\x00` nas palavras acentuadas.
- **Resumo (págs. 1 + 2):** patrimônio bruto, rentabilidade mês/ano, ganho financeiro mês/ano, rentabilidades 12m e 24m, %CDI calculado (rent / cdi * 100 para cada período), movimentações.
- **Benchmarks (pág. 2):** CDI mês/ano/12m/24m extraído das linhas de período.
- **Rentabilidade histórica mensal (pág. 2):** tabela ano × mês (14 valores por ano: jan–dez + total_ano + acumulado). Três linhas por bloco: portfólio%, CDI%, %CDI. Regex multi-token para cada linha.
- **Evolução patrimonial (pág. 4):** tabela mensal com patrimônio_inicial, movimentações, IR pago, patrimônio_final, ganho, portfólio%, CDI%. BTG não tem IOF separado → `iof=0.0`.
- **Composição por estratégia (pág. 5):** extração em dois passos — (1) tabela de alocação: nome + pct% + R$ saldo; (2) tabela de rentabilidade: 5 percentuais + nome abaixo. Matching fuzzy `_best_match` para unir os dois.
- **Ativos (págs. 8+, seção "A rentabilidade completa"):** state machine com 7 estados (detalhado abaixo).

**State machine para ativos (2 formatos de bloco):**

```
Formato A — Renda Fixa (CDB, LCA, etc.):
  Linha 1: NOME_PARCIAL + 4 pct% (ex: "BANCO AGIBANK S.A - CDB- 1,20% 1,20% 14,01% 29,82%")
  Linha 2: SALDO + pct + pct + DATA (ex: "19.676,10 100,00 1,68 10/07/2027")
  Linha 3: NOME_CONT + 4 abs_R$ (ex: "CDBB231B2JG 235,92 235,92 2.405,09 4.413,39")
  Linha 4: CDI ...
  Linha 5: % do CDI ...

Formato B — Fundos e Tickers:
  Linha 1: 4 pct% sozinhos (ex: "1,34% 1,34% 15,66% 32,90%")
  Linha 2: NOME + SALDO + pct + pct + [DATA] (fundo) ou TICKER + SALDO + pct + pct (ação)
  Linha 3: 4 abs_R$
  Linha 4: CDI ...
  Linha 5: % do CDI ...

Sub-header de estratégia: NOME + 3 números (detectado apenas no estado FIND)
```

**Estados:**
- `FIND` → detecta sub-header de estratégia, Formato A ou Formato B
- `RF_SALDO` → lê linha de saldo+data para Formato A
- `RF_CONT` → lê continuação do nome + 4 abs para Formato A
- `FUND_NAME` → lê linha de nome/saldo para Formato B
- `ABS_EARN` → consome linha de ganhos absolutos
- `WAIT_CDI` → espera linha `CDI ...`
- `WAIT_PCTCDI` → lê `% do CDI ...` e salva ativo

#### 2. `_STRAT_CANONICAL` e `_normalize_btg_strategy()`

O pdfplumber substitui a ligatura tipográfica "fi" (fi-ligature, U+FB01) pelo null byte `\x00`. Isso afeta palavras como:
- "fixado" → "\x00xado"
- "fixo" → "\x00xo"

E alguns outros caracteres são substituídos por `\ufffd` (replacement char). Portanto:
- "Pós-fixado" → "Pós-\x00xado"
- "Pré-fixado" → "Pré-\x00xado"
- "Inflação" → "Infla\ufffdo" (o "ã" vira \ufffd)
- "Renda Variável" → "Rend\x00 Vari\ufffavel" (fi de "Rend**a**" não, mas "fi" em "fixado" sim)

`_STRAT_CANONICAL` é uma lista de `(regex_compilado, nome_canônico)` que cobre todos esses casos com padrões tolerantes. A função `_normalize_btg_strategy(text)` percorre a lista e retorna o canônico, ou faz fallback removendo os caracteres problemáticos.

#### 3. Fix `_parse_composicao` — nomes de estratégia limpos

**Problema:** A função usava `re.sub(r"[\x00]", "", nome_raw)` para limpar o nome, mas isso só removia o null byte, resultando em "Pós-xado" (sem o "fi").

**Solução:** Substituído por `_normalize_btg_strategy(nome_raw)`, que mapeia corretamente para "Pós-fixado", "Pré-fixado", etc. usando os mesmos padrões canônicos.

#### 4. Fix `detect_and_parse` — `parsers/__init__.py`

**Problemas encontrados:**
1. Lia apenas 1 página — BTG tem a primeira página com apenas "Relatório" e a segunda com "de Performance" (split por `\n`).
2. O regex buscava `"Relatório de Performance"` como string literal — falhava quando havia `\n` entre as palavras.
3. Regra XP incluía número de conta hardcoded (`"8660669" in text`).

**Solução:**
- Passou a ler 2 páginas (`n_pages=2`) para detecção.
- Regex tolerante: `r"Relat.{0,4}rio\s*[\n\s]+de\s+Performance"` captura tanto na mesma linha quanto em linhas separadas.
- Removidas heurísticas frágeis baseadas em número de conta.

#### 5. Fix `app.py` — roteamento por conteúdo, não por nome de arquivo

**Problema:** `app.py` roteava PDFs usando `"btg" in file.name.lower()`. PDFs BTG se chamam `RelatorioDePerformance-005058054.pdf` — não contém "btg". Resultado: XP parser rodava em PDFs BTG e retornava `ativos=[]`.

**Solução:** Removida a lógica de roteamento por nome. Agora todos os PDFs passam por `detect_and_parse(tmp_path)`, que faz a detecção por conteúdo.

#### 6. Testes realizados

Todos os 7 PDFs dos dois clientes foram testados com `detect_and_parse`:

| PDF | Detecção | Conta | Ativos | Patrimônio |
|-----|----------|-------|--------|------------|
| RelatorioDePerformance-005058054.pdf | BTG | 5058054 | 31 | R$ 1.171.109,49 |
| RelatorioDePerformance-005165904.pdf | BTG | 5165904 | 36 | R$ 1.212.485,66 |
| XPerformance - 14522738 - Ref.30.01.pdf | XP | 14522738 | 25 | R$ 1.376.095,14 |
| XPerformance - 3476739 - Ref.30.01.pdf | XP | 3476739 | 29 | R$ 1.240.327,68 |
| RelatorioDePerformance-004016217.pdf | BTG | 4016217 | 20 | R$ 472.169,37 |
| XPerformance - 3245269 - Ref.30.01.pdf | XP | 3245269 | 26 | R$ 1.826.076,84 |
| XPerformance - 8660669 - Ref.30.01.pdf | XP | 8660669 | 7 | R$ 296.706,75 |

Validação contra ground truth (`btg_5058054.json`):
- `patrimonio_total_bruto`: OK (1.171.109,49)
- `rentabilidade_mes_pct`: OK (1,51%)
- `ganho_mes_rs`: OK (16.825,50)
- `pct_cdi_mes`: OK (130,17%)
- `rentabilidade_12m_pct`: OK (15,43%)
- Todos os 6 estratégias da composição: OK com nomes canônicos corretos
- Contagem de ativos: OK (31/31)

#### 7. Commit realizado

```
git commit: feat: implement full BTG parser and fix XP/BTG routing
Hash: 01b4b07
Arquivos: Consolidador_V3/src/parsers/btg_performance.py
          Consolidador_V3/src/parsers/__init__.py
          app.py
+944 / -64 linhas
```

---

### O que está funcionando agora

- **Parser XP** (`xp_performance.py`) — 707 linhas, funcional, testado ✅
- **Parser BTG** (`btg_performance.py`) — ~500 linhas, funcional, testado vs ground truth ✅
- **Detecção automática de formato** (`detect_and_parse`) — conteúdo-based, 2 páginas, regex robusto ✅
- **Roteamento app.py** — todos PDFs passam por `detect_and_parse`, sem heurística de nome ✅
- **Consolidador** (`consolidator.py`) — agrega múltiplas contas ✅
- **Gerador de Excel** (`report_generator.py`) — 6 abas ✅
- **Streamlit app** (`app.py`) — upload + processamento + download Excel ✅
- **Dois clientes processados** com Excel gerado: Jose Mestrener e Cid e Tania ✅

### O que ainda está incompleto

- `tests/fixtures/` — vazio, sem ground truth nos fixtures formais (os JSONs estão em `output/extractions/`)
- UI do Streamlit — funcional mas sem identidade visual Capital Investimentos (sem dashboard, sem gráficos)
- Abas 4 (Rentabilidade mensal) e 5 (Evolução) no Excel precisam validação visual com os novos dados BTG

### Próximo passo sugerido

**Aprimorar a UI do Streamlit** seguindo a identidade visual Capital Investimentos:
- Dashboard com 4 cards de métrica no topo (AuM Total, Rent. Mês, %CDI, Contas)
- Sidebar fixa com logo Capital Investimentos
- Gráfico de área para evolução patrimonial
- Barras verticais para rentabilidade mês a mês
- Tabela de alocação por estratégia com cores

Ou, alternativamente, **validar o Excel gerado** com os parsers determinísticos para garantir que os dados BTG aparecem corretamente nas 6 abas.

---

## 15. Como retomar uma sessão

1. Abra o Cowork e selecione a pasta do projeto (`Consolidador/`)
2. Cole o conteúdo deste arquivo no início da conversa com Claude
3. Diga o que quer fazer — Claude terá contexto completo imediatamente
4. Ao final da sessão, peça a Claude para atualizar a **seção 14** com o novo estado
