# Plano de Implementação — Nova UI Consolidador v2

> **Referência visual:** imagens `Dashboards/Gemini_Generated_Image_*.png`
> **Base atual:** `app.py` (250 linhas, single-page, Streamlit 1.54)
> **Meta:** Dashboard clean, profissional, utilizável no dia a dia — sem complexidade desnecessária

---

## 1. Visão Geral

A nova UI mantém o fluxo simples do app atual mas adiciona:

1. **Sidebar profissional** com logo e navegação clara
2. **Tela de Upload reformulada** — dropzone grande, cards de status, feedback visual por arquivo
3. **Tela de Dashboard** — 4 cards de métrica, gráfico de evolução patrimonial, gráfico de rentabilidade mensal, tabela por corretora

O app continua sendo **single-file** (`app.py`) controlado por `st.session_state`. Sem multi-page do Streamlit — mais simples de manter e deployar.

---

## 2. Fluxo de Navegação

```
                    ┌──────────────────────────────┐
                    │         SIDEBAR               │
                    │  [logo Capital Investimentos] │
                    │  ─────────────────────────── │
                    │  > Upload / Importação        │  ← estado: "upload"
                    │    Dashboard                  │  ← estado: "dashboard" (ativo após processar)
                    │  ─────────────────────────── │
                    │  [info do cliente atual]      │
                    └──────────────────────────────┘

Estado "upload":
  ┌─────────────────────────────────────────────┐
  │  4 cards de status (contas, erros, data)    │
  │  ─────────────────────────────────────────  │
  │  Inputs: Nome cliente + Mês/Ano             │
  │  Dropzone grande (PDF/JSON)                 │
  │  Lista de arquivos carregados               │
  │  [Botão: Consolidar]                        │
  │  ─────────────────────────────────────────  │
  │  Tabela: arquivos processados nessa sessão  │
  └─────────────────────────────────────────────┘

Estado "dashboard":
  ┌─────────────────────────────────────────────┐
  │  4 cards: AuM | Rent.Mês | %CDI | Contas   │
  │  ─────────────────────────────────────────  │
  │  [2/3] Gráfico evolução PL  │ [1/3] Barras │
  │       (linha área + CDI)    │  rent. mensal │
  │  ─────────────────────────────────────────  │
  │  Tabela: Patrimônio por Corretora           │
  │  Tabela: Alocação por Estratégia            │
  │  ─────────────────────────────────────────  │
  │  [Botão: Download Excel]                    │
  │  [Botão: Nova Importação]                   │
  └─────────────────────────────────────────────┘
```

---

## 3. Tokens de Design (paleta e tipografia)

Tudo mapeado dos mockups e do CSS atual:

```python
# cores
COR_SIDEBAR      = "#0D1B3E"   # azul escuro — fundo sidebar
COR_PRIMARIA     = "#0D1B3E"   # azul escuro — botões primários, textos chave
COR_ACENTO       = "#1A56DB"   # azul médio  — hover, links, destaque
COR_FUNDO        = "#F8FAFC"   # off-white   — background principal
COR_CARD         = "#FFFFFF"   # branco      — cards
COR_BORDA        = "#E2E8F0"   # cinza claro — bordas
COR_TEXTO_SUB    = "#475569"   # cinza médio — subtítulos, labels
COR_POSITIVO     = "#16A34A"   # verde       — rent. positiva
COR_NEGATIVO     = "#DC2626"   # vermelho    — rent. negativa
COR_NEUTRO       = "#64748B"   # cinza       — valores neutros

# tipografia
FONT_FAMILY  = "Inter"         # importada via Google Fonts
FONT_WEIGHTS = [400, 500, 600]
```

---

## 4. Componentes da Interface

### 4.1 Sidebar

**O que renderizar:**
- Logo "CAPITAL INVESTIMENTOS" como bloco HTML customizado (texto estilizado, sem depender de imagem externa)
- Linha separadora
- Links de navegação: "Upload / Importação" e "Dashboard" — controlados por `st.session_state["view"]`
- Linha separadora
- Se `view == "dashboard"`: bloco com nome do cliente e data de referência
- Botão "Nova Importação" (volta para tela de upload, limpa o estado)

**CSS da sidebar:**
- Fundo `#0D1B3E` (atual é branco — mudar)
- Texto dos itens de menu: branco `#FFFFFF`
- Item ativo: fundo `rgba(255,255,255,0.12)` + borda-esquerda `2px solid #1A56DB`
- Sem bordas desnecessárias

---

### 4.2 Cards de Métrica (4 cards, linha única)

**Tela Upload — 4 cards de status:**

| Card | Valor | Ícone |
|------|-------|-------|
| Arquivos carregados | `len(uploaded_files)` | arquivo |
| Corretoras detectadas | XP / BTG detectados | corretora |
| Última consolidação | horário da última sessão | relógio |
| Erros | count de erros da sessão | alerta |

**Tela Dashboard — 4 cards de resultado:**

| Card | Valor | Cor do delta |
|------|-------|-------------|
| AuM Total Consolidado | `R$ X.XXX.XXX,XX` | neutro |
| Rentabilidade Bruta do Mês | `+X,XX%` | verde/vermelho |
| %CDI no Mês | `XXX%` | verde/vermelho |
| Contas Consolidadas | `N` | neutro |

**Implementação:** HTML customizado via `st.markdown(..., unsafe_allow_html=True)`. Os `st.metric` nativos do Streamlit têm styling limitado — usar HTML garante o visual do mockup.

Template de card:
```html
<div class="metric-card">
  <div class="metric-label">AuM Total Consolidado</div>
  <div class="metric-value">R$ 1.171.109,49</div>
  <div class="metric-delta positive">+1,51% este mês</div>
</div>
```

---

### 4.3 Tela de Upload

**Campos fora do `st.form`** (para feedback imediato):
- `st.text_input` — Nome do Cliente
- `st.text_input` — Mês/Ano de Referência (default: mês atual)

**Dropzone:**
- `st.file_uploader` com `accept_multiple_files=True`, tipos `["pdf", "json"]`
- CSS customizado para fazer a área ficar grande e com ícone centralizado
- Após upload: lista de arquivos com badge de corretora detectada (XP / BTG / JSON)

**Lista de arquivos carregados** (abaixo do dropzone):
- Uma linha por arquivo: `[ícone corretora] nome_arquivo.pdf  [badge: XP / BTG]  [X remover]`
- Implementado como tabela HTML simples

**Botão de ação:**
- `st.button("Consolidar Carteiras", type="primary")` — largo, centralizado
- Spinner durante processamento com mensagem por arquivo: "Processando RelatorioDePerformance-005058054.pdf..."

**Tabela de histórico da sessão** (após primeiro processamento):
- Aparece somente se `st.session_state["historico"]` não estiver vazio
- Colunas: Arquivo | Corretora | Conta | Ativos | Patrimônio | Status

---

### 4.4 Tela de Dashboard

#### Bloco de métricas (4 cards)

Gerados a partir de `dados_consolidados`:
```python
total_aum     = dados_consolidados["patrimonio_total_consolidado"]
rent_mes      = media_ponderada das contas (por patrimônio)
pct_cdi_mes   = media_ponderada %CDI
n_contas      = len(dados_consolidados["contas"])
```

#### Gráfico 1 — Evolução Patrimonial (coluna principal, 2/3 da largura)

**Dados:** `evolucao_patrimonial` de cada conta, somados por mês.

**Tipo:** `plotly.graph_objects.Figure` — área preenchida (`fill='tozeroy'`) para a linha do portfólio + linha tracejada para o benchmark CDI projetado.

**Detalhes visuais:**
- Cor do portfólio: `#1A56DB` (azul)
- Fill: `rgba(26, 86, 219, 0.08)` (azul bem transparente)
- Benchmark CDI: linha tracejada `#94A3B8` (cinza)
- Fundo do gráfico: `#FFFFFF`
- Grid: linhas horizontais sutis `#F1F5F9`
- Eixo X: meses no formato "Jan/26"
- Tooltip: patrimônio formatado em R$
- Sem legenda externa — apenas label inline nas linhas
- Título: "Evolução Patrimonial" com subtítulo dinâmico do período

**Fallback:** se `evolucao_patrimonial` estiver vazio para todas as contas, mostrar mensagem de aviso dentro do card em vez de gráfico quebrado.

#### Gráfico 2 — Rentabilidade Mensal (coluna lateral, 1/3 da largura)

**Dados:** `rentabilidade_historica_mensal` — pegar os últimos 6 meses de alguma conta (ou média entre contas).

**Tipo:** `plotly.graph_objects.Bar` — barras verticais, coloridas por valor.

**Detalhes visuais:**
- Barra positiva: `#16A34A` (verde)
- Barra negativa: `#DC2626` (vermelho)
- Rótulo no topo de cada barra: "+1,51%" ou "-0,30%"
- Eixo X: meses abreviados (Ago, Set, Out, Nov, Dez, Jan)
- Sem eixo Y explícito — apenas os rótulos nas barras
- Fundo: `#FFFFFF`, sem grid
- Título: "Rentabilidade Mês a Mês"

**Fallback:** se menos de 2 meses de dados, não renderizar o gráfico (usar `st.info()`).

#### Tabela — Patrimônio por Corretora/Conta

Gerada a partir de `dados_consolidados["contas"]`:

| Corretora | Conta | Patrimônio (R$) | % da Carteira | Rent. Mês | %CDI |
|-----------|-------|-----------------|---------------|-----------|------|
| BTG | 5058054 | 1.171.109,49 | 29,3% | +1,51% | 130% |
| XP | 14522738 | 1.376.095,14 | 34,4% | +0,98% | 84% |

**Implementação:** `st.dataframe` com `column_config` para formatar valores:
- `patrimonio_bruto`: `st.column_config.NumberColumn("Patrimônio", format="R$ %.2f")`
- `rentabilidade_mes_pct`: `st.column_config.NumberColumn("Rent. Mês", format="%.2f%%")`
- Coloração condicional de `rent_mes_pct`: verde se > 0, vermelho se < 0

#### Tabela — Alocação por Estratégia

Gerada a partir de `dados_consolidados["composicao_por_estrategia"]`:

| Estratégia | Saldo (R$) | % Carteira |
|------------|------------|------------|
| Pós-fixado | 1.802.740,70 | 45,1% |
| Inflação | 866.042,98 | 21,7% |
| ...

**Implementação:** `st.dataframe` simples com largura total.

#### Botões de ação (rodapé do dashboard)

```
[  Download Excel  ]    [  Nova Importação  ]
```

- "Download Excel": `st.download_button` com `type="primary"`
- "Nova Importação": `st.button` que limpa `st.session_state` e volta para view="upload"

---

## 5. Gerenciamento de Estado (`st.session_state`)

```python
# Chaves e valores iniciais
st.session_state.setdefault("view", "upload")            # "upload" | "dashboard"
st.session_state.setdefault("dados_consolidados", None)   # dict retornado por consolidate()
st.session_state.setdefault("excel_bytes", None)          # bytes do Excel gerado
st.session_state.setdefault("cliente_nome", "")
st.session_state.setdefault("data_ref", datetime.now().strftime("%m/%Y"))
st.session_state.setdefault("historico", [])              # lista de dicts por arquivo processado
st.session_state.setdefault("erros_sessao", [])           # erros acumulados na sessão
```

**Transições de estado:**
- Upload → Dashboard: após `consolidate()` bem-sucedido, `st.session_state["view"] = "dashboard"`
- Dashboard → Upload: botão "Nova Importação" limpa `dados_consolidados`, `excel_bytes`, `historico` e define `view = "upload"`
- A sidebar lê `st.session_state["view"]` para destacar o item de menu ativo

---

## 6. Estrutura do `app.py` Refatorado

```
app.py
 │
 ├── _css()                   → injeta todo o CSS customizado
 ├── _sidebar()               → renderiza sidebar (logo + nav + info cliente)
 ├── _render_cards(dados)     → 4 cards HTML
 ├── _chart_evolucao(dados)   → Plotly área — evolução PL
 ├── _chart_rent_mensal(dados)→ Plotly barras — rent. mensal
 ├── _tabela_contas(dados)    → st.dataframe contas por corretora
 ├── _tabela_alocacao(dados)  → st.dataframe alocação por estratégia
 ├── _view_upload()           → tela de upload completa
 ├── _view_dashboard()        → tela de dashboard completa
 └── main()                   → st.set_page_config + _css() + _sidebar() + roteamento
```

Funções auxiliares de formatação:
```python
def _fmt_brl(v: float) -> str:
    """1234567.89 → 'R$ 1.234.567,89'"""

def _fmt_pct(v: float) -> str:
    """1.51 → '+1,51%' | -0.3 → '-0,30%'"""

def _color_pct(v: float) -> str:
    """Retorna classe CSS: 'positive' | 'negative' | 'neutral'"""
```

---

## 7. CSS Customizado — Alterações em Relação ao Atual

O CSS atual (`app.py` linhas 26–116) precisa das seguintes adições/mudanças:

### Sidebar escura (mudança principal)
```css
/* Sidebar fundo escuro */
section[data-testid="stSidebar"] {
    background-color: #0D1B3E;
    border-right: none;
}
section[data-testid="stSidebar"] * {
    color: #E2E8F0 !important;
}

/* Logo Capital Investimentos */
.sidebar-logo {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #FFFFFF;
    line-height: 1.2;
    padding: 8px 0 4px 0;
}
.sidebar-logo span {
    display: block;
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 2px;
    color: #94A3B8;
}

/* Itens de navegação */
.nav-item {
    padding: 10px 12px;
    border-radius: 6px;
    cursor: pointer;
    color: #CBD5E1;
    font-size: 14px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 2px;
    transition: background 0.15s;
}
.nav-item:hover { background: rgba(255,255,255,0.08); }
.nav-item.active {
    background: rgba(255,255,255,0.12);
    border-left: 2px solid #1A56DB;
    color: #FFFFFF;
}
```

### Cards de métrica
```css
.metric-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 20px 24px;
    flex: 1;
}
.metric-label {
    font-size: 12px;
    font-weight: 500;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}
.metric-value {
    font-size: 26px;
    font-weight: 600;
    color: #0D1B3E;
    line-height: 1.1;
}
.metric-delta { font-size: 13px; font-weight: 500; margin-top: 4px; }
.metric-delta.positive { color: #16A34A; }
.metric-delta.negative { color: #DC2626; }
.metric-delta.neutral  { color: #64748B; }
```

### Dropzone de upload
```css
/* Tornar a área de upload mais alta e com ícone grande */
section[data-testid="stFileUploadDropzone"] {
    background: #FFFFFF;
    border: 2px dashed #CBD5E1;
    border-radius: 12px;
    min-height: 160px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}
section[data-testid="stFileUploadDropzone"]:hover {
    border-color: #1A56DB;
    background: #EFF6FF;
}
```

### Badges de corretora
```css
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
.badge-xp  { background: #DBEAFE; color: #1E40AF; }
.badge-btg { background: #FEF3C7; color: #92400E; }
.badge-ok  { background: #DCFCE7; color: #166534; }
.badge-err { background: #FEE2E2; color: #991B1B; }
```

---

## 8. Dependências a Adicionar

Adicionar ao `requirements.txt`:
```
plotly>=5.18.0
```

Nenhuma outra dependência nova — `pandas` já está, `streamlit` já está.

---

## 9. Etapas de Implementação (ordem sugerida)

As etapas são independentes e cada uma entrega valor imediato ao ser mergeada.

### Etapa 1 — CSS + Sidebar escura (30 min)
**O que muda:** visual geral do app sem mudar a lógica
**Arquivos:** `app.py` (seção CSS + sidebar)
**Resultado:** sidebar azul escuro com logo, cards com melhor estilo, dropzone maior
**Risco:** zero — só CSS

### Etapa 2 — Refatoração de estado e navegação (45 min)
**O que muda:** introduz `st.session_state["view"]` e separa o app em `_view_upload()` e `_view_dashboard()`
**Arquivos:** `app.py` (estrutura interna)
**Resultado:** código organizado em funções, pronto para adicionar dashboard
**Risco:** baixo — lógica de negócio não muda

### Etapa 3 — Cards de métrica HTML (30 min)
**O que muda:** substitui `st.metric` por cards HTML customizados
**Arquivos:** `app.py` (função `_render_cards`)
**Resultado:** 4 cards no estilo do mockup, com valores corretos e delta colorido
**Risco:** zero — cosmético

### Etapa 4 — Tabelas reformuladas (30 min)
**O que muda:** `st.dataframe` com `column_config` para formatação de valores
**Arquivos:** `app.py` (funções `_tabela_contas`, `_tabela_alocacao`)
**Resultado:** tabelas com coluna de corretora, % carteira, rent. colorida
**Risco:** zero

### Etapa 5 — Gráfico de barras rentabilidade mensal (45 min)
**O que muda:** adiciona gráfico Plotly com dados de `rentabilidade_historica_mensal`
**Arquivos:** `app.py` (função `_chart_rent_mensal`), `requirements.txt`
**Resultado:** barras verdes/vermelhas por mês ao lado das métricas
**Risco:** baixo — requer validar que os dados de rent. histórica estão chegando corretamente dos parsers

### Etapa 6 — Gráfico de evolução patrimonial (60 min)
**O que muda:** adiciona gráfico Plotly de área com `evolucao_patrimonial`
**Arquivos:** `app.py` (função `_chart_evolucao`)
**Resultado:** curva patrimonial por mês com linha de benchmark CDI
**Risco:** médio — requer agregar evolução de múltiplas contas por mês (lógica de soma)

### Etapa 7 — Tela de upload reformulada (45 min)
**O que muda:** lista de arquivos com badge de corretora, status por arquivo, cards de status
**Arquivos:** `app.py` (função `_view_upload`)
**Resultado:** feedback visual por arquivo antes de processar
**Risco:** baixo

---

## 10. O que NÃO implementar neste ciclo

Para manter o escopo focado e o código simples:

- **Sem multi-page do Streamlit** (pages/ directory) — single file é mais simples de manter
- **Sem autenticação** — uso interno, sem necessidade
- **Sem persistência entre sessões** — `session_state` limpa ao fechar o browser (comportamento atual mantido)
- **Sem gráfico de pizza/donut** para alocação — tabela é mais legível para dados de assessor
- **Sem modo escuro** — identidade visual definida em azul escuro/off-white
- **Sem filtros interativos no dashboard** — o app processa um cliente por vez, sem necessidade de filtro

---

## 11. Estrutura Final do app.py (esboço)

```python
# app.py — ~350 linhas após refatoração

import os, sys, tempfile, traceback
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# ... imports dos módulos internos ...

# ── Constantes de design ──────────────────────────────────────────────────────
COLORS = { ... }

# ── Helpers de formatação ─────────────────────────────────────────────────────
def _fmt_brl(v): ...
def _fmt_pct(v): ...

# ── CSS ───────────────────────────────────────────────────────────────────────
def _inject_css(): st.markdown(CSS, unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
def _sidebar(): ...

# ── Componentes ───────────────────────────────────────────────────────────────
def _render_cards(dados): ...
def _chart_evolucao(dados): ...
def _chart_rent_mensal(dados): ...
def _tabela_contas(dados): ...
def _tabela_alocacao(dados): ...

# ── Processamento ─────────────────────────────────────────────────────────────
def _processar_arquivos(files): ...  # extrai lógica atual do app

# ── Views ─────────────────────────────────────────────────────────────────────
def _view_upload(): ...
def _view_dashboard(): ...

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Consolidador — Capital Investimentos",
                       page_icon=None, layout="wide")
    _inject_css()
    _sidebar()
    if st.session_state.get("view") == "dashboard":
        _view_dashboard()
    else:
        _view_upload()

if __name__ == "__main__":
    main()
```

---

## 12. Critérios de Aceite

Uma etapa está concluída quando:

- [ ] Nenhum `st.error` ou exception no fluxo feliz (upload → consolidar → dashboard)
- [ ] Cards mostram valores corretos dos dados consolidados
- [ ] Tabela de contas mostra todas as contas com patrimônio e rentabilidade
- [ ] Gráfico de barras mostra os últimos N meses com cores corretas
- [ ] Gráfico de evolução renderiza sem erro mesmo com 1 única conta
- [ ] Botão Download Excel gera arquivo válido
- [ ] Botão "Nova Importação" limpa o estado e volta para tela de upload sem recarregar a página
- [ ] App roda sem erros em `streamlit run app.py`

---

*Planejamento criado em 2026-03-07. Implementar por etapas na ordem sugerida na seção 9.*
