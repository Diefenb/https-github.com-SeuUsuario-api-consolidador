# Prompt para Gemini — Identidade Visual: API Consolidador

---

## CONTEXTO DO PROJETO

Estou desenvolvendo uma aplicação web interna chamada **API Consolidador**, usada exclusivamente por assessores de investimentos de uma consultoria financeira brasileira chamada **API Capital Investimentos**.

A ferramenta tem como função consolidar carteiras de investimentos de clientes, processando relatórios PDF de corretoras (XP Investimentos e BTG Pactual), extraindo os dados e gerando relatórios em Excel. A interface web é construída com **Streamlit** (Python).

**Usuários:** 2 a 5 assessores financeiros internos — profissionais financeiros com perfil técnico-analítico, acostumados com dashboards de dados.

**Fluxo principal da aplicação:**
1. **Tela de Upload** — o assessor informa o nome do cliente, o mês de referência, e faz upload dos PDFs das corretoras
2. **Tela de Resultado** — a aplicação processa os dados e exibe: resumo por conta, patrimônio consolidado, preview das abas do Excel, e botão de download

---

## IDENTIDADE DE REFERÊNCIA

A identidade visual do **API Consolidador** deve ser **derivada da API Capital Investimentos**, empresa mãe. Ou seja: mesma família de cores, mesma linguagem tipográfica, mesma sensação de solidez institucional — mas aplicada a uma ferramenta utilitária de dados, não a um site institucional.

**Características visuais observadas na API Capital:**
- Cor primária: azul-marinho profundo (tom aproximado: #0D1B3E ou similar)
- Cor de acento/ação: azul brilhante (tom aproximado: #1A56DB ou similar)
- Fundo: branco limpo, com fundos de card em cinza muito claro
- Tipografia: sans-serif moderna, clean, bem espaçada
- Bordas suaves, cards com sombra leve
- Indicadores positivos em verde, negativos em vermelho/laranja
- Sidebar de navegação branca com texto escuro
- Botões primários: azul-marinho com texto branco
- Tom geral: corporativo, confiável, sóbrio — uma consultoria financeira séria

---

## O QUE PRECISO QUE VOCÊ ENTREGUE

### 1. PALETA DE CORES COMPLETA

Crie um sistema de cores coeso para o API Consolidador, com as seguintes categorias, sempre com **código hex**, **nome semântico** e **uso indicado**:

- **Primary** (ação principal, botões CTA, links ativos)
- **Primary Dark** (hover states, sidebar ativa)
- **Primary Light** (backgrounds de destaque suave, badges)
- **Secondary** (elementos secundários, bordas, ícones inativos)
- **Background Page** (fundo geral da aplicação)
- **Background Card** (fundo de cards, painéis, seções)
- **Background Sidebar** (fundo da navegação lateral)
- **Text Primary** (corpo de texto, labels)
- **Text Secondary** (texto de apoio, subtítulos, metadados)
- **Text Muted** (placeholders, texto desabilitado)
- **Border** (bordas de inputs, cards, separadores)
- **Success** (confirmação, dados positivos, rentabilidade positiva)
- **Warning** (alertas, pendências, formatos desconhecidos)
- **Error / Danger** (erros, rentabilidade negativa)
- **Info** (informações neutras, tooltips)
- **Accent 1** (cor de gráficos — XP Investimentos)
- **Accent 2** (cor de gráficos — BTG Pactual)
- **Accent 3** (cor de gráficos — estratégia Pós Fixado)
- **Accent 4** (cor de gráficos — estratégia Pré Fixado)
- **Accent 5** (cor de gráficos — estratégia Inflação)
- **Accent 6** (cor de gráficos — estratégia Renda Variável)

Para cada cor, informe também: contraste com branco (WCAG), contraste com fundo de card, e se passa AA ou AAA de acessibilidade.

---

### 2. TIPOGRAFIA

Recomende uma família tipográfica (Google Fonts, disponível gratuitamente) que:
- Seja compatível com a identidade corporativa da API Capital
- Funcione bem em interfaces de dados com muitos números
- Tenha boa legibilidade em tamanhos pequenos (dados em tabela)
- Tenha caráter semiprofissional, sem ser fria demais

Para cada nível tipográfico, especifique:
- **H1** (título de página): tamanho, peso, cor, line-height
- **H2** (título de seção/card): tamanho, peso, cor
- **H3** (subtítulo): tamanho, peso, cor
- **Body** (texto corrido): tamanho, peso, cor
- **Small / Caption** (metadados, datas, labels de formulário): tamanho, cor
- **Monospace / Números** (valores financeiros, R$, %): família sugerida, tamanho

---

### 3. ESPECIFICAÇÃO DE COMPONENTES UI

Descreva cada componente com propriedades CSS precisas (border-radius, padding, shadow, cor de fundo, cor de texto, border, hover state, etc.). Use os tokens de cor que você definiu acima.

#### 3.1 Card / Painel
Cards são o elemento central da interface — contêm os dados de cada conta, resumos, e tabelas.
- Fundo, borda, border-radius, sombra, padding interno
- Variante: Card de destaque (patrimônio total)
- Variante: Card de alerta/pendência

#### 3.2 Botão Primário (CTA)
Usado para "Consolidar" e "Baixar Excel" — ações principais.
- Cor, texto, padding, border-radius, hover, disabled state

#### 3.3 Botão Secundário
Usado para ações secundárias como "Usar template de importação" ou "Cancelar".
- Estilo outline ou ghost — especifique

#### 3.4 Botão Terciário / Link-button
Para ações menores como "Ver detalhes", "Remover arquivo"

#### 3.5 Área de Upload (Drag & Drop)
O componente mais importante da Tela 1. O assessor arrasta PDFs aqui.
- Estado vazio (esperando arquivo): borda tracejada, ícone, texto orientativo
- Estado com arquivos: lista de arquivos com badges de tipo (XP / BTG / IMP / ?)
- Badge "XP": cor, texto
- Badge "BTG": cor, texto
- Badge "IMP" (importação manual): cor, texto
- Badge "?" (formato desconhecido): cor, texto + ação de alerta
- Estado de hover (arrastando arquivo sobre a área)

#### 3.6 Campo de Input de Texto
Para "Nome do Cliente"
- Fundo, borda, border-radius, padding, placeholder, focus state

#### 3.7 Select / Dropdown
Para "Mês de Referência" e "Ano"
- Visual consistente com o input de texto

#### 3.8 Badge / Tag de Status
Usado para indicar status de processamento:
- "Processando..." (intermediário)
- "✅ Sucesso"
- "⚠️ Aviso"
- "❌ Erro"

#### 3.9 Progress / Loading State
Quando a aplicação está processando os PDFs — pode ser barra de progresso ou spinner.

#### 3.10 Tabela de Dados
As tabelas são críticas — exibem ativos, rentabilidades, patrimônio.
- Header: fundo, texto, peso, padding
- Linha par / ímpar (zebra striping, se aplicável)
- Hover em linha
- Células numéricas (alinhadas à direita): formatação para valores positivos (verde) e negativos (vermelho)
- Linha de total: destaque visual

#### 3.11 Sidebar de Navegação (se aplicável)
O app em Streamlit pode ter sidebar. Especifique:
- Cor de fundo
- Item ativo vs inativo
- Logo placement

#### 3.12 Alert / Notificação inline
Para avisos como "Formato desconhecido — custo estimado R$ 0,50-1,50 para extração por IA"
- Variantes: info, warning, error, success

---

### 4. CONFIG.TOML PARA STREAMLIT

Com base em tudo acima, gere o arquivo `config.toml` para o Streamlit (localizado em `.streamlit/config.toml`) com:

```toml
[theme]
primaryColor = "..."
backgroundColor = "..."
secondaryBackgroundColor = "..."
textColor = "..."
font = "..."  # "sans serif", "serif" ou "monospace"
```

E também gere um bloco de CSS customizado (injetável via `st.markdown`) para sobrescrever os estilos padrão do Streamlit e aplicar os componentes especificados acima.

---

### 5. ÍCONES

Recomende uma biblioteca de ícones (ex: Lucide, Feather, Heroicons, Phosphor) e liste quais ícones usar para:
- Upload de arquivo
- Arquivo reconhecido (XP)
- Arquivo reconhecido (BTG)
- Arquivo de importação manual
- Arquivo não reconhecido / alerta
- Download do Excel
- Processando / Loading
- Patrimônio / Carteira
- Cliente / Pessoa
- Data / Calendário
- Rentabilidade positiva
- Rentabilidade negativa
- Erro / Falha

---

## RESTRIÇÕES E PRINCÍPIOS DE DESIGN

1. **Dados em primeiro lugar.** A identidade visual nunca deve competir com os números. Elementos decorativos são tolerados apenas quando funcionais.
2. **Sem dark mode por enquanto.** A aplicação é sempre light. Otimize para isso.
3. **Responsivo não é prioridade.** A ferramenta é usada exclusivamente em desktop (1280px+).
4. **Acessibilidade mínima WCAG AA** em todos os textos sobre fundo colorido.
5. **Streamlit-first.** Todas as especificações devem ser implementáveis no Streamlit, sem frameworks JS externos.
6. **Consistência com API Capital.** O usuário que alterna entre o CRM da API Capital e o Consolidador deve sentir que está no mesmo ecossistema.

---

## FORMATO DA RESPOSTA ESPERADA

Organize sua resposta em seções numeradas correspondendo a cada entregável acima. Use tabelas para a paleta de cores. Use blocos de código para CSS e TOML. Seja preciso nos valores — prefiro "padding: 12px 16px" a "padding médio".

---

*Contexto técnico adicional: a interface Streamlit usa `st.file_uploader`, `st.text_input`, `st.selectbox`, `st.dataframe`, `st.metric`, `st.download_button` e `st.expander` como componentes principais.*
