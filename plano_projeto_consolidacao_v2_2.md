# Projeto: Consolidação de Carteiras — Plano Revisado v2

## Premissa Fundamental

**Somente consolidamos dados reais.** Nenhum cálculo implícito de rentabilidade. Todos os números reportados ao cliente devem vir diretamente dos relatórios oficiais das corretoras.

---

## Correção Crítica: XP Performance ≠ XP Posição Consolidada

O relatório **"XPerformance"** (Relatório de Investimentos) da XP é muito mais rico que o "Posição Consolidada" analisado anteriormente. Ele fornece:

### Dados disponíveis por relatório

| Dado | XP Performance | BTG/API Capital | Disponível? |
|------|---------------|-----------------|-------------|
| Saldo Bruto por ativo | ✅ | ✅ | Ambos |
| Quantidade/Cotas | ✅ | ✅ | Ambos |
| % Alocação | ✅ | ✅ | Ambos |
| Rentabilidade Mês (%) | ✅ | ✅ | Ambos |
| %CDI Mês | ✅ | ✅ | Ambos |
| Rentabilidade Ano (%) | ✅ | ✅ | Ambos |
| %CDI Ano | ✅ | ✅ | Ambos |
| Rentabilidade 24M (%) | ✅ (XP) | ✅ 12M/Acum (BTG) | Períodos diferentes |
| Rent. por Estratégia | ✅ | ✅ (por estratégia) | Ambos |
| Evolução Patrimonial | ✅ (12 meses) | ✅ | Ambos |
| Movimentações | ✅ | ✅ | Ambos |
| Benchmarks (CDI/IBOV/IPCA/Dólar) | ✅ | ✅ | Ambos |
| Histórico mensal de retorno | ✅ (por ano, 24M) | ✅ | Ambos |
| Ganho Financeiro (R$) | ✅ | ✅ | Ambos |
| Estatística Histórica | ✅ (vol, meses +/-) | ❌ | Só XP |

**Conclusão: NÃO há gap de dados. Ambas as fontes fornecem rentabilidade por ativo. O projeto consolida apenas dados reais extraídos.**

---

## Arquitetura Simplificada

```
[PDFs das Corretoras]
    → EXTRAÇÃO (LLM parse PDF → JSON canônico)
    → NORMALIZAÇÃO (padronizar nomes, tipos, classificações)
    → CONSOLIDAÇÃO (agregar posições e retornos de todas as contas)
    → RELATÓRIO (Excel/PDF consolidado)
```

Sem etapa de "enriquecimento" ou "cálculo implícito". Tudo que aparece no relatório final veio de um relatório de corretora.

---

## Schema Canônico Revisado

Cada ativo extraído é mapeado para este formato:

```json
{
  "meta": {
    "cliente": "JOSE GONCALVES MESTRENER JUNIOR",
    "conta": "3245269",
    "corretora": "XP",
    "segmento": "Signature",
    "parceiro": "Guilherme Barbosa",
    "data_referencia": "2026-01-30",
    "arquivo_origem": "XPerformance_-_3245269_-_Ref_30_01.pdf"
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
    "movimentacoes_mes": 0.00,
    "movimentacoes_12m": 285446.05
  },

  "benchmarks": {
    "cdi": { "mes": 1.16, "ano": 1.16, "12m": 14.49, "24m": 26.99 },
    "ibovespa": { "mes": 12.56, "ano": 12.56, "12m": 43.79, "24m": 41.96 },
    "ipca": { "mes": 0.33, "ano": 0.33, "12m": 4.44, "24m": 9.20 },
    "dolar": { "mes": -4.95, "ano": -4.95, "12m": -10.29, "24m": 5.58 }
  },

  "estatistica_historica": {
    "meses_positivos": 24,
    "meses_negativos": 0,
    "retorno_mensal_max": 1.73,
    "retorno_mensal_min": 0.56,
    "meses_acima_cdi": 11,
    "meses_abaixo_cdi": 13,
    "volatilidade_12m": 0.64,
    "volatilidade_24m": 0.69
  },

  "composicao_por_estrategia": [
    {
      "estrategia": "Pós Fixado",
      "saldo_bruto": 1187595.07,
      "pct_alocacao": 65.04,
      "rent_mes": 1.71,
      "rent_ano": 1.71,
      "rent_12m": 15.99,
      "rent_24m": 30.48
    }
  ],

  "rentabilidade_historica_mensal": [
    {
      "ano": 2026,
      "meses": {
        "jan": { "portfolio": 1.73, "pct_cdi": 148.67 }
      },
      "ano_pct": 1.73,
      "acumulada_pct": 58.70
    },
    {
      "ano": 2025,
      "meses": {
        "jan": { "portfolio": 1.13, "pct_cdi": 111.96 },
        "fev": { "portfolio": 0.91, "pct_cdi": 92.65 },
        "mar": { "portfolio": 1.15, "pct_cdi": 119.87 },
        "abr": { "portfolio": 1.32, "pct_cdi": 124.56 },
        "mai": { "portfolio": 1.13, "pct_cdi": 98.99 },
        "jun": { "portfolio": 1.14, "pct_cdi": 104.45 },
        "jul": { "portfolio": 0.82, "pct_cdi": 64.18 },
        "ago": { "portfolio": 1.38, "pct_cdi": 118.27 },
        "set": { "portfolio": 1.15, "pct_cdi": 94.26 },
        "out": { "portfolio": 1.04, "pct_cdi": 81.78 },
        "nov": { "portfolio": 1.20, "pct_cdi": 114.24 },
        "dez": { "portfolio": 1.01, "pct_cdi": 82.54 }
      },
      "ano_pct": 14.23,
      "acumulada_pct": 56.00
    }
  ],

  "evolucao_patrimonial": [
    {
      "data": "2026-01",
      "patrimonio_inicial": 1795827.49,
      "movimentacoes": 0.00,
      "ir": -52.85,
      "iof": -8.05,
      "patrimonio_final": 1826076.84,
      "ganho_financeiro": 30310.25,
      "rentabilidade": 1.73,
      "pct_cdi": 148.67
    }
  ],

  "ativos": [
    {
      "nome_original": "V8 Mercury CI Renda Fixa CP LP - Resp. Limitada",
      "estrategia": "Pós Fixado",
      "saldo_bruto": 212338.29,
      "quantidade": 179386.11,
      "pct_alocacao": 11.63,
      "rent_mes": 1.46,
      "pct_cdi_mes": 125.02,
      "rent_ano": 1.46,
      "pct_cdi_ano": 125.02,
      "rent_24m": 6.92,
      "pct_cdi_24m": 108.65
    },
    {
      "nome_original": "CDB BANCO XP S.A. - JUN/2026 - IPC-A + 10,20%",
      "estrategia": "Inflação",
      "saldo_bruto": 53899.95,
      "quantidade": 50,
      "pct_alocacao": 2.95,
      "rent_mes": 1.15,
      "pct_cdi_mes": 98.79,
      "rent_ano": 1.15,
      "pct_cdi_ano": 98.79,
      "rent_24m": 7.80,
      "pct_cdi_24m": 87.46
    }
  ],

  "movimentacoes": [
    {
      "data_mov": "2026-01-21",
      "data_liq": "2026-01-21",
      "historico": "DÉBITO IOF KP CP 35 FIDC RL",
      "valor": -8.05,
      "saldo": 0.00
    }
  ]
}
```

---

## Mapeamento de Campos por Relatório

### XP Performance (Relatório de Investimentos)

**Seção "Evolução Patrimonial" (p.1-2):**
- `patrimonio_total_bruto` → "PATRIMÔNIO TOTAL BRUTO"
- `rentabilidade_mes_pct` → "RENTABILIDADE MÊS"
- `ganho_mes_rs` → "GANHO MÊS"
- Tabela "Referências (%)" → benchmarks (CDI, Ibovespa, IPCA, Dólar) com Mês/Ano/12M/24M
- Tabela "Resumo de Informações" → ganho financeiro, rentabilidade, %CDI, movimentações por período
- "Estatística Histórica" → meses positivos/negativos, retorno max/min, volatilidade

**Seção "Rentabilidade Histórica" (p.3):**
- Tabela por ano (2024, 2025, 2026) com Portfólio e %CDI para cada mês → `rentabilidade_historica_mensal`

**Seção "Evolução Patrimonial por Período" (p.4):**
- Tabela: Data, Patrimônio inicial, Movimentações, IR, IOF, Patrimônio final, Ganho, Rent., %CDI → `evolucao_patrimonial`

**Seção "Estratégia: Composição" (p.5):**
- Tabela: Estratégia, Saldo Bruto, Mês Atual, Ano, 12M, 24M → `composicao_por_estrategia`

**Seção "Posição Detalhada" (p.6-9):**
- Tabela: Estratégia/Ativo, Saldo Bruto, Qtd, %Aloc, Rent. Mês, %CDI Mês, Rent. Ano, %CDI Ano, Rent. 24M, %CDI 24M → `ativos`

**Seção "Movimentações" (p.10-11):**
- Tabela: MOV, LIQ, Histórico, Valor, Saldo → `movimentacoes`

### BTG/API Capital (Relatório de Performance)

**Já mapeado anteriormente.** Campos análogos com períodos ligeiramente diferentes (Mês, Ano, 12M, Acumulado vs Mês, Ano, 12M, 24M na XP).

---

## O que o Consolidador FAZ (somente dados reais)

### 1. Extrai dados dos PDFs → JSON canônico
- Cada PDF vira um JSON seguindo o schema acima
- Zero interpretação: números exatamente como no relatório

### 2. Normaliza nomes e classificações
- Padroniza nomes de ativos entre contas (ex: mesmo fundo em contas diferentes)
- Classifica por tipo (CDB, CRA, LCA, Fundo, FII, etc.)
- Classifica por indexador (CDI, IPCA, Prefixado)

### 3. Consolida entre contas do mesmo cliente
- **Patrimônio total:** soma dos patrimônios de cada conta/corretora
- **Posição por ativo:** lista unificada com indicação de corretora/conta
- **Alocação consolidada:** recalcula % de alocação sobre o total consolidado
- **Composição por estratégia:** agrega saldos por estratégia entre contas

### 4. Reporta rentabilidade REAL por nível
- **Por conta:** rentabilidade conforme relatório da corretora (dado real)
- **Por ativo:** rentabilidade conforme relatório da corretora (dado real)
- **Por estratégia:** rentabilidade conforme relatório da corretora (dado real)
- **Consolidada entre contas:** ⚠️ **NÃO CALCULAMOS** — reportamos a rent. de cada conta separadamente

> **REGRA DE OURO:** Se um número não veio de um relatório oficial, ele NÃO aparece no consolidado. Campos sem dados ficam em branco/null.

### O que NÃO fazemos
- ❌ Calcular rentabilidade implícita via snapshots
- ❌ Calcular rentabilidade teórica por curva de juros
- ❌ Calcular rentabilidade consolidada ponderada entre contas (a menos que o cliente peça explicitamente e entenda que é um cálculo nosso)
- ❌ Estimar valores de ativos sem dados
- ❌ Interpolar dados faltantes

---

## Tratamento de Diferenças entre Formatos

### Períodos de rentabilidade

| Período | XP Performance | BTG/API Capital | Consolidado |
|---------|---------------|-----------------|-------------|
| Mês | ✅ | ✅ | ✅ |
| Ano | ✅ | ✅ | ✅ |
| 12 Meses | ✅ (tabela referências) | ✅ | ✅ |
| 24 Meses | ✅ (por ativo) | ❌ | Só XP |
| Acumulado desde início | ✅ (hist. anual) | ✅ | ✅ |

**Regra:** No consolidado, reportamos o que cada fonte fornece. Se XP tem 24M e BTG não, o campo fica preenchido para XP e em branco para BTG. Sem interpolação.

### Estratégias / Classificação

| XP Performance | BTG/API Capital | Consolidado (padronizado) |
|---------------|-----------------|--------------------------|
| Pós Fixado | Renda Fixa | Pós Fixado |
| Inflação | Renda Fixa (IPCA) | Inflação / IPCA |
| Pré Fixado | Renda Fixa (Pré) | Pré Fixado |
| Multimercado | Multimercado | Multimercado |
| Renda Variável Brasil | Renda Variável | Renda Variável |
| Caixa | Caixa | Caixa |

---

## Stack Tecnológico

| Componente | Tecnologia | Justificativa |
|-----------|------------|---------------|
| Extração PDF → JSON | Claude API (Sonnet 4.5) | Custo-benefício; Opus para fallback |
| Normalização | Python (regras determinísticas) | Previsível, auditável |
| Consolidação | Python (pandas) | Agregação simples |
| Relatório output | Excel (openpyxl) | Familiar para assessor |
| Armazenamento | JSON files por cliente/mês | Simples, portável |
| Orquestração | Script Python CLI | Sem overhead |

### Custo estimado (Sonnet 4.5)
- ~5 PDFs/cliente × ~10 páginas = 50 páginas
- Sonnet é ~10x mais barato que Opus
- Para 50 clientes: custo mensal estimado < R$50 em API

---

## Estrutura do Relatório Consolidado (Excel)

### Aba 1 — Resumo por Conta
| Corretora | Conta | Segmento | Patrimônio Bruto | Rent. Mês | %CDI Mês | Rent. Ano | %CDI Ano |
|-----------|-------|----------|-----------------|-----------|----------|-----------|----------|
| XP | 3245269 | Signature | R$ 1.826.076,84 | 1,73% | 148,67% | 1,73% | 148,67% |
| XP | 8660669 | Exclusive | R$ 296.706,75 | 1,31% | 112,83% | 1,31% | 112,83% |
| BTG | 4016217 | - | R$ 476.537,57 | - | - | - | - |
| BTG | 4019474 | - | R$ 2.284.768,44 | - | - | - | - |
| **TOTAL** | | | **R$ 4.884.089,60** | | | | |

### Aba 2 — Alocação Consolidada
- Distribuição por estratégia (Pós Fixado, Inflação, Pré, Multi, RV)
- Distribuição por corretora
- % de cada ativo sobre o patrimônio total
- Saldos somados (dados reais), % recalculados sobre total

### Aba 3 — Posição Detalhada (todos os ativos)
| Corretora | Conta | Estratégia | Ativo | Saldo Bruto | %Aloc. Total | Rent. Mês | %CDI Mês | Rent. Ano | %CDI Ano |
|-----------|-------|-----------|-------|-------------|-------------|-----------|----------|-----------|----------|
| XP | 3245269 | Pós Fixado | V8 Mercury CI RF CP LP | R$ 212.338,29 | 4,35% | 1,46% | 125,02% | 1,46% | 125,02% |
| XP | 3245269 | Inflação | CDB Pine IPCA+7,35% | R$ 132.273,63 | 2,71% | 0,91% | 78,14% | 0,91% | 78,14% |

*(% Alocação Total é o único recálculo: saldo_bruto / patrimonio_total_consolidado. É uma divisão simples sobre dados reais.)*

### Aba 4 — Rentabilidade por Conta (histórico mensal)
- Para cada conta, tabela mensal conforme relatório da corretora
- Sem consolidação entre contas

### Aba 5 — Evolução Patrimonial por Conta
- Tabela de evolução (patrimônio inicial, movimentações, IR, IOF, patrimônio final) conforme relatório
- Um bloco por conta

### Aba 6 — Movimentações
- Lista unificada de todas as movimentações de todas as contas
- Ordenada por data

---

## Plano de Execução

### Fase 1 — Piloto com 1 cliente (2 semanas)

**Sprint 1 (Semana 1): Extração**
- [ ] Definir schema JSON canônico final (validação com jsonschema)
- [ ] Criar prompt de extração para XP Performance
- [ ] Criar prompt de extração para BTG/API Capital Performance
- [ ] Testar nos 5 PDFs disponíveis (2 XP Performance + 2 BTG + 1 XP Posição)
- [ ] Validar: comparar JSON extraído com dados visuais do PDF (100% match)
- [ ] Decisão: Sonnet 4.5 é suficiente? Ou precisa Opus?

**Sprint 2 (Semana 2): Consolidação + Relatório**
- [ ] Script Python: normalizar nomes e classificações
- [ ] Script Python: consolidar JSONs de todas as contas → visão unificada
- [ ] Script Python: gerar Excel consolidado (6 abas)
- [ ] Comparar resultado com planilha manual existente (cruzamento_carteiras.xlsx)
- [ ] Ajustar e documentar

### Fase 2 — Expansão para 10 clientes (3-4 semanas)
- [ ] Adicionar formato C6 (precisa amostra)
- [ ] CLI: `python consolidar.py --cliente jose --mes 2026-01 --pdfs ./pdfs/`
- [ ] Batch: processar N clientes de uma vez
- [ ] Testes de qualidade com 10 clientes reais
- [ ] Documentar mapeamento de campos por formato

### Fase 3 — Escala para 50 clientes (4-6 semanas)
- [ ] Interface Streamlit para upload e processamento
- [ ] Armazenamento organizado (JSON por cliente/mês)
- [ ] Batch API do Claude para custo reduzido
- [ ] Alertas automáticos de erros de extração
- [ ] Template de Excel profissional

---

## Riscos Revisados

| Risco | Prob. | Impacto | Mitigação |
|-------|-------|---------|-----------|
| Corretora muda formato do PDF | Alta | Médio | LLM é resiliente; prompt genérico |
| Formato C6 muito diferente | Média | Baixo | Aguardar amostra; LLM adapta |
| Acurácia de extração < 100% | Média | Alto | Validação humana; testes de regressão |
| Períodos de rentabilidade incompatíveis entre corretoras | Certa | Baixo | Reportar o que cada uma fornece, sem inventar |
| Ativos com mesmo nome mas saldos divergentes | Média | Médio | Reportar ambos valores, flag de divergência |

---

## Métricas de Sucesso

1. **Acurácia de extração:** 100% dos valores numéricos extraídos corretamente (tolerância: R$0,01)
2. **Cobertura:** 100% dos ativos listados nos PDFs aparecem no consolidado
3. **Zero cálculos inventados:** nenhum número no relatório final que não tenha origem rastreável em um PDF de corretora
4. **Tempo:** < 15 min para consolidar 1 cliente (vs ~2h manual)
5. **Custo API:** < R$2 por cliente/mês (usando Sonnet)

---

## Próximo Passo Imediato

Começar Sprint 1: criar o prompt de extração para o formato XP Performance usando os 2 PDFs fornecidos (contas 3245269 e 8660669) e validar a extração contra os dados visíveis nos relatórios.
