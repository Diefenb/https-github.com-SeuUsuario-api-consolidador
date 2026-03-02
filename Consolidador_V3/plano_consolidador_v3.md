# Plano de Implementação — Consolidador v3: Arquitetura Escalável

## Visão Geral da Nova Arquitetura

```
┌─────────────────────── FLUXO PRINCIPAL (sem IA, custo zero) ───────────────────────┐
│                                                                                     │
│  XP PDF ──→ Parser Determinístico XP ──→ JSON padrão ─┐                            │
│  BTG PDF ──→ Parser Determinístico BTG ──→ JSON padrão ─┤──→ Consolidador ──→ Excel │
│  JSON importado manualmente ────────────────────────────┘                            │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────── FLUXO EXCEÇÃO (com IA, sob demanda) ────────────────────────┐
│                                                                                     │
│  PDF de corretora nova ──→ Claude API ──→ JSON padrão ──→ entra no fluxo principal  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Princípio:** IA é ferramenta de exceção, não de produção. O fluxo diário roda 100% determinístico, sem API, sem custo variável, sem dependência externa.

---

## Fase 1: Parsers Determinísticos (Semana 1-2)

### Objetivo
Substituir o `extractor.py` (que usa Claude API) por parsers baseados em `pdfplumber` que extraem dados diretamente do PDF sem IA.

### 1.1 — Parser XP Performance

**Arquivo:** `src/parsers/xp_performance.py`

**Estratégia de extração:** O PDF XP Performance tem estrutura tabelar consistente. Usar `pdfplumber` para extrair tabelas página por página.

**Mapeamento página → dados:**

| Página | Seção | Técnica de extração |
|--------|-------|-------------------|
| Capa | meta (conta, parceiro, data, segmento) | Regex no texto da página |
| 01 | Evolução Patrimonial (resumo) | Regex nos valores do bloco |
| 01 | Benchmarks (CDI/Ibov/IPCA/Dólar) | Tabela com `extract_tables()` |
| 01 | Resumo de Informações | Regex por label/valor |
| 01 | Estatística Histórica | Regex por label/valor |
| 02 | Rentabilidade Histórica Mensal | Tabela com `extract_tables()` |
| 03 | Evolução Patrimonial (tabela) | Tabela com `extract_tables()` |
| 04 | Composição por Estratégia | Tabela com `extract_tables()` |
| 05+ | Posição Detalhada (ativos) | Tabela multi-página com `extract_tables()` |
| Últimas | Movimentações | Tabela com `extract_tables()` |

**Desafios conhecidos:**
- Sub-headers de estratégia (ex: "Pós Fixado R$ 1.187.595,07") misturados com linhas de ativos → Detectar linhas com saldo mas sem quantidade
- Tabelas que continuam em múltiplas páginas → Concatenar antes de parsear
- Formatação BR → Reusar `utils.py` (parse_br_number, parse_br_pct)

**Entregável:** Função `parse_xp_performance(pdf_path) -> dict` que retorna JSON no schema `consolidador-v2`.

### 1.2 — Parser BTG/API Capital Performance

**Arquivo:** `src/parsers/btg_performance.py`

**Diferenças vs XP:**
- Layout diferente (sem numeração de páginas fixa)
- Períodos: Mês/Ano/12M/Acumulado (vs Mês/Ano/24M na XP)
- Formato CDB: "BANCO PINE S/A - CDB-CDBC258QL68"
- Duas visões (tipo de veículo + estratégia) → Extrair SOMENTE estratégia
- Pode ter múltiplos titulares (conta conjunta)

**Entregável:** Função `parse_btg_performance(pdf_path) -> dict` que retorna JSON no schema `consolidador-v2`.

### 1.3 — Detector de formato

**Arquivo:** `src/parsers/__init__.py`

```python
def detect_and_parse(pdf_path: str) -> dict:
    """Detecta formato do PDF e chama o parser correto."""
    text = extract_first_page_text(pdf_path)
    
    if "Relatório de Investimentos" in text or "XP" in text:
        return parse_xp_performance(pdf_path)
    elif "Relatório de Performance" in text or "API Capital" in text or "BTG" in text:
        return parse_btg_performance(pdf_path)
    else:
        raise UnknownFormatError(f"Formato não reconhecido: {pdf_path}")
```

### 1.4 — Validação cruzada

**Estratégia:** Para cada PDF, rodar AMBOS os métodos (parser determinístico E extrator IA) e comparar os JSONs campo a campo. Isso garante que o parser determinístico tem a mesma precisão.

**Critérios de validação:**
- Patrimônio total: diff < R$ 1,00
- Quantidade de ativos: exatamente igual
- Saldo de cada ativo: diff < R$ 0,01
- Rentabilidades: diff < 0,01%
- Movimentações: quantidade e valores exatos

**Rodar com os 8 PDFs já extraídos** (4 do Jose Mestrener + 4 do Cid e Tania) como test suite.

### Testes

**Arquivo:** `tests/test_parsers.py`

Usar os JSONs já validados em `output/extractions/` como ground truth. Para cada PDF:
1. Rodar parser determinístico
2. Comparar com JSON existente (extraído via IA)
3. Assertar tolerâncias definidas acima

---

## Fase 2: Streamlit Web App (Semana 3-4)

### Objetivo
Interface web onde o usuário faz upload dos PDFs e recebe o Excel consolidado.

### 2.1 — Estrutura do app

**Arquivo:** `app.py` (raiz do projeto)

**Telas:**

#### Tela 1: Upload e Configuração
```
┌─────────────────────────────────────────────┐
│  🏦 Consolidador de Carteiras              │
│                                             │
│  Nome do Cliente: [___________________]     │
│  Mês de Referência: [Jan ▼] [2026 ▼]       │
│                                             │
│  📁 Arraste os PDFs aqui                    │
│  ┌─────────────────────────────────────┐    │
│  │  XPerformance - 3245269.pdf  ✅ XP  │    │
│  │  XPerformance - 8660669.pdf  ✅ XP  │    │
│  │  RelatorioBTG-004016217.pdf  ✅ BTG │    │
│  │  planilha_importacao.json    ✅ IMP │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  [ 🚀 Consolidar ]                          │
└─────────────────────────────────────────────┘
```

#### Tela 2: Progresso e Resultado
```
┌─────────────────────────────────────────────┐
│  Processando...                             │
│  ✅ XP 3245269 — R$ 1.826.076,84 (27 at.)  │
│  ✅ XP 8660669 — R$ 296.706,75 (7 at.)     │
│  ✅ BTG 4016217 — R$ 472.169,37 (22 at.)   │
│  ✅ Importação manual — R$ 150.000,00       │
│  ──────────────────────────────────────      │
│  Total: R$ 2.744.952,96 | 56 ativos        │
│                                             │
│  📊 Preview (abas do Excel)                 │
│  [Resumo] [Alocação] [Posição] [Rent.]     │
│                                             │
│  [ 📥 Baixar Excel ]                        │
└─────────────────────────────────────────────┘
```

### 2.2 — Fluxo de importação manual (JSON/XLSX padrão)

O usuário pode fazer upload de um arquivo JSON no formato `consolidador-v2` ou um XLSX com template padronizado. Isso entra direto no pipeline sem parser e sem IA.

**Template XLSX de importação:**

| Ativo | Estratégia | Saldo Bruto | Quantidade | % Alocação | Rent. Mês (%) | %CDI Mês | Rent. Ano (%) | %CDI Ano |
|-------|-----------|-------------|-----------|-----------|-------------|----------|-------------|----------|

O app converte o XLSX para JSON canônico antes de consolidar.

### 2.3 — Fluxo de exceção com IA

Quando o usuário faz upload de um PDF de formato desconhecido:
1. App detecta que não é XP nem BTG
2. Mostra aviso: "Formato não reconhecido. Deseja usar extração assistida por IA? (custo estimado: ~R$ 0,50-1,50)"
3. Se sim → chama Claude API → extrai → mostra JSON para validação → consolida
4. Se não → oferece download do template de importação manual

### 2.4 — Deploy

**Opção A (recomendada para começar): Streamlit Community Cloud**
- Custo: R$ 0
- Setup: conectar GitHub, deploy automático
- Limitação: 1GB RAM, domínio `.streamlit.app`

**Opção B (futuro, se precisar de mais controle):**
- VPS (Hetzner/DigitalOcean): ~R$ 30-50/mês
- Domínio próprio, mais RAM, sem limite de sleep

### 2.5 — Dependências adicionais

```
streamlit>=1.30
pdfplumber>=0.10
```

Remover do fluxo principal:
- `anthropic` (mover para dependência opcional, só para fluxo exceção)
- `PyMuPDF` (substituído por pdfplumber)
- `Pillow` (não precisa mais renderizar imagens)

---

## Fase 3: Polimento e Escala (Semana 5-6)

### 3.1 — Histórico de consolidações

Salvar cada consolidação em `data/historico/`:
```
data/historico/
├── jose_mestrener/
│   ├── 2026-01/
│   │   ├── consolidado.json
│   │   ├── consolidado.xlsx
│   │   └── extractions/
│   │       ├── xp_3245269.json
│   │       └── btg_4016217.json
│   └── 2026-02/
│       └── ...
└── cid_tania/
    └── 2026-01/
        └── ...
```

### 3.2 — Comparativo mensal

Com histórico, gerar aba adicional no Excel:
- Patrimônio mês anterior vs atual
- Variação absoluta e percentual
- Novos ativos / ativos liquidados

### 3.3 — Multi-usuário (futuro)

Se mais de um assessor usar o sistema:
- Autenticação via Streamlit (allow-list por email)
- Cada assessor vê apenas seus clientes
- Dados isolados por assessor

---

## Estrutura final do projeto

```
Consolidador/
├── CLAUDE.md
├── .env                          ← API key (só para fluxo exceção)
├── requirements.txt
├── app.py                        ← Streamlit web app
├── consolidar.py                 ← CLI (mantido como alternativa)
├── config/
│   └── prompts/                  ← Prompts IA (só para fluxo exceção)
│       ├── xp_performance.txt
│       └── btg_performance.txt
├── src/
│   ├── __init__.py
│   ├── parsers/                  ← NOVO: parsers determinísticos
│   │   ├── __init__.py           ← detect_and_parse()
│   │   ├── xp_performance.py     ← parse_xp_performance()
│   │   └── btg_performance.py    ← parse_btg_performance()
│   ├── extractor.py              ← MANTIDO: extração via IA (só exceções)
│   ├── normalizer.py             ← normalize_strategy() + clean_asset_name()
│   ├── consolidator.py           ← agregação entre contas
│   ├── report_generator.py       ← geração Excel 6 abas
│   ├── importer.py               ← NOVO: importação de JSON/XLSX padrão
│   └── utils.py                  ← helpers
├── schemas/
│   └── consolidador_v2.json
├── templates/
│   └── importacao_template.xlsx  ← NOVO: template para importação manual
├── tests/
│   ├── test_parsers.py           ← NOVO: testes dos parsers determinísticos
│   ├── test_normalizer.py
│   └── fixtures/                 ← JSONs validados como ground truth
├── data/
│   └── historico/                ← NOVO: consolidações salvas
└── output/
    ├── extractions/
    └── consolidado_*.xlsx
```

---

## Cronograma

| Fase | Semana | Entregável | Dependência |
|------|--------|-----------|-------------|
| 1.1 | 1 | Parser XP Performance testado | PDFs XP de referência |
| 1.2 | 1-2 | Parser BTG Performance testado | PDFs BTG de referência |
| 1.3 | 2 | Detector de formato + validação cruzada | Parsers prontos |
| 1.4 | 2 | Test suite com 8 PDFs | Parsers + JSONs existentes |
| 2.1 | 3 | Streamlit app funcional (upload + consolidação) | Parsers prontos |
| 2.2 | 3 | Template e importador de JSON/XLSX | Schema definido |
| 2.3 | 4 | Fluxo exceção com IA integrado | Extractor existente |
| 2.4 | 4 | Deploy no Streamlit Cloud | App funcional |
| 3.1 | 5 | Histórico de consolidações | App em produção |
| 3.2 | 5-6 | Comparativo mensal | Histórico |
| 3.3 | 6+ | Multi-usuário | Necessidade confirmada |

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| PDF XP muda de layout | Média | Alto | Manter extractor.py como fallback; versionar parsers |
| pdfplumber não extrai tabela corretamente | Média | Médio | Usar `extract_words()` com coordenadas como alternativa |
| Streamlit Cloud RAM insuficiente | Baixa | Médio | Processar PDFs um por vez, liberar memória |
| Novo formato de corretora (C6, etc.) | Certa | Baixo | Fluxo exceção com IA + template importação |
| API Anthropic indisponível | Baixa | Baixo | Só afeta fluxo exceção; fluxo principal é independente |
