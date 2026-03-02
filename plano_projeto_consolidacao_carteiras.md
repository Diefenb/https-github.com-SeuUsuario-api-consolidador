# Projeto: Consolidação de Carteiras de Investimentos via IA

## Contexto e Escopo

**Objetivo:** Gerar relatórios mensais consolidados de carteiras de investimentos para 10-50 clientes, cruzando dados de múltiplas corretoras (XP, BTG, C6, e potencialmente outras).

**Usuário final:** Assessor/gestor (uso interno).

**Modelo de referência:** Claude Opus 4.6 Extended como motor de extração e normalização de dados.

---

## Diagnóstico da Situação Atual

### O que já existe
- Planilha de cruzamento manual (`cruzamento_carteiras.xlsx`) com 6 abas por conta/corretora
- Relatórios PDF das corretoras (XP Posição Consolidada, BTG/API Capital Relatório de Performance)
- Processo manual de extração e comparação

### Problemas identificados
1. **Formatos heterogêneos** — cada corretora gera PDFs com estrutura e campos completamente diferentes
2. **Nomes inconsistentes** — mesmo ativo aparece com nomes diferentes entre corretoras e consolidadores (ex: "CRA UNIDAS (OURO VERDE)" vs "CRA Ouro Verde/Opea")
3. **Gap de rentabilidade** — XP só fornece posição estática; BTG fornece rentabilidade completa por ativo
4. **Divergências de valores** — diferenças significativas entre fontes (ex: V8 Mercury R$331k vs R$184k)
5. **Ativos órfãos** — posições que existem em uma fonte mas não na outra
6. **Processo não escalável** — funciona para 1 cliente, inviável para 50

---

## Arquitetura Proposta

### Visão Geral do Pipeline

```
[PDFs das Corretoras] 
    → Etapa 1: EXTRAÇÃO (LLM parse PDF → JSON estruturado)
    → Etapa 2: NORMALIZAÇÃO (padronizar nomes, tipos, indexadores)
    → Etapa 3: RECONCILIAÇÃO (matching entre contas/corretoras)
    → Etapa 4: ENRIQUECIMENTO (rentabilidade, benchmarks)
    → Etapa 5: GERAÇÃO DE RELATÓRIO (Excel + PDF consolidado)
```

### Schema Canônico (modelo de dados central)

Cada ativo extraído é normalizado para este formato:

```json
{
  "cliente": "JOSE GONCALVES MESTRENER JUNIOR",
  "conta": "3245269",
  "corretora": "XP",
  "data_referencia": "2026-01-31",
  
  "ativo": {
    "nome_original": "CRA UNIDAS (OURO VERDE) - DEZ/2028",
    "nome_normalizado": "CRA Ouro Verde DEZ/2028",
    "tipo": "CRA",
    "classe": "Renda Fixa",
    "subclasse": "Prefixada",
    "emissor": "Ouro Verde / Opea",
    "indexador": "Prefixado",
    "taxa_contratada": 13.82,
    "vencimento": "2028-12-15"
  },

  "posicao": {
    "valor_aplicado": 130446.03,
    "posicao_bruta": 132180.51,
    "posicao_liquida": 132180.51,
    "quantidade": null,
    "valor_cota": null
  },

  "rentabilidade": {
    "mes_pct": null,
    "mes_rs": null,
    "ano_pct": null,
    "ano_rs": null,
    "12m_pct": null,
    "acumulada_pct": null,
    "pct_cdi_mes": null,
    "pct_cdi_ano": null
  },

  "liquidez": {
    "carencia": "2028-12-15",
    "disponivel": 134,
    "prazo_resgate": null
  },

  "metadata": {
    "fonte": "XP Posição Consolidada",
    "arquivo_origem": "document_pdf.pdf",
    "pagina": 2,
    "confianca_extracao": 0.95
  }
}
```

---

## Detalhamento das Etapas

### ETAPA 1 — Extração via LLM

**Estratégia:** Usar Claude Opus 4.6 como parser universal de PDFs financeiros.

**Por que LLM e não OCR/regex?**
- Relatórios mudam formato entre versões
- Nomes de ativos são variáveis e não padronizados
- Tabelas têm layouts complexos (merged cells, subcategorias)
- LLM entende contexto (sabe que "IPC-A + 10,15%" é indexador IPCA)

**Abordagem:**
1. Converter PDF em imagens de alta resolução (pdftoppm 300dpi)
2. Enviar páginas relevantes ao Claude com prompt de extração
3. Prompt inclui o schema canônico como template de saída
4. Validar JSON de saída contra schema

**Prompts de extração por tipo de relatório:**

| Formato | Corretora | Campos disponíveis |
|---------|-----------|-------------------|
| Posição Consolidada XP | XP | Ativo, aplicação, carência, vencimento, taxa, valor aplicado, posição mercado, valor líquido |
| Relatório Performance API Capital | BTG | Tudo acima + rentabilidade mensal/anual/12m/acumulada, % CDI, quantidade, preço, preço médio |
| Extrato C6 | C6 | A definir — precisa de amostra |

**Desafio principal:** O relatório da XP NÃO traz rentabilidade por ativo. Soluções:
- **Opção A:** Calcular rentabilidade implícita comparando snapshots mensais consecutivos (necessário manter histórico)
- **Opção B:** Cruzar com extrato de movimentações da XP (se disponível)
- **Opção C:** Para renda fixa, calcular rentabilidade teórica pela taxa contratada + curva de juros
- **Recomendação:** Começar com Opção A (snapshots), pois é a mais genérica

**Custo estimado de API por cliente/mês:**
- ~3-5 PDFs por cliente × ~10 páginas por PDF = ~40 páginas
- ~4000 tokens por página (imagem + extração) ≈ 160K tokens input
- ~2000 tokens de output por página ≈ 80K tokens output
- Para 50 clientes: ~8M input + 4M output tokens/mês
- Custo Opus 4.6: verificar preços atuais (pode ser significativo para 50 clientes)
- **Alternativa de custo:** Usar Sonnet 4.5 para extração e Opus só para reconciliação

### ETAPA 2 — Normalização

**Objetivo:** Transformar dados brutos extraídos em formato padronizado.

**Regras de normalização:**
1. **Tipo de ativo:** Mapear para enum (CDB, CRA, CRI, LCI, LCA, LCD, LF, DEB, NTN-B, Fundo RF, Fundo Multi, Fundo RV, FII, ETF, Ação, Cripto)
2. **Indexador:** Mapear para enum (CDI, IPCA, Prefixado, Dólar, Ibovespa, IFIX)
3. **Classe:** Mapear para (Renda Fixa, Fundos, Renda Variável, Alternativo, Saldo)
4. **Subclasse:** Mapear para (Pós-fixada, Prefixada, Inflação, Multimercado, Ações, FIIs, etc)
5. **Nome normalizado:** Remover códigos internos, padronizar formato (ex: "CDB BANCO XP S.A. - JUN/2026" → "CDB Banco XP JUN/2026")
6. **Datas:** Converter tudo para ISO 8601 (YYYY-MM-DD)
7. **Valores:** Converter para float, remover "R$", tratar separadores brasileiros

**Implementação:** Pode ser feita com regras determinísticas (Python) para ~90% dos casos, com LLM como fallback para casos ambíguos.

### ETAPA 3 — Reconciliação (Matching entre fontes)

**Problema:** O mesmo ativo pode aparecer em múltiplas fontes com nomes diferentes. Precisamos identificar que são o mesmo ativo.

**Algoritmo de matching:**
1. **Match exato** por chave composta: (corretora + conta + tipo + vencimento + taxa) → resolve ~70% dos casos
2. **Match fuzzy** por nome normalizado: usando similaridade de strings (Levenshtein, token sort ratio) → resolve ~20%
3. **Match assistido por LLM:** para os ~10% restantes, enviar pares candidatos ao Claude para confirmar

**Tabela de reconciliação (output):**
| ID Ativo | Fonte 1 (Corretora) | Fonte 2 (Externo) | Status Match | Divergência |
|----------|--------------------|--------------------|-------------|-------------|
| A001 | CRA Unidas DEZ/2028 R$132.180 | CRA Ouro Verde DEZ/2028 R$132.522 | OK | 0,26% |
| A002 | SPX Seahawk Deb D45 R$160.022 | — | SÓ CORRETORA | — |

### ETAPA 4 — Enriquecimento com Rentabilidade

**Fontes de rentabilidade por prioridade:**
1. **Relatório BTG/API Capital:** Já traz rentabilidade completa por ativo (% mês, ano, 12m, acumulada, % CDI)
2. **Cálculo implícito via snapshots:** Para XP e C6 — (posição_atual - posição_anterior - aportes + resgates) / posição_anterior
3. **Cálculo teórico:** Para renda fixa com taxa conhecida — rentabilidade esperada pela curva

**Dados necessários para cálculo implícito:**
- Posição do mês atual (extraído do relatório)
- Posição do mês anterior (mantido em banco de dados/histórico)
- Movimentações do mês (aportes e resgates)

**Banco de dados de histórico (essencial):**
- Armazenar cada snapshot mensal por ativo
- Formato sugerido: arquivo JSON ou SQLite por cliente
- Permite calcular rentabilidade mesmo sem dados da corretora
- Permite gerar gráficos de evolução patrimonial

### ETAPA 5 — Geração de Relatório

**Output final:** Planilha Excel com múltiplas abas + opcionalmente PDF formatado.

**Estrutura do relatório:**

**Aba 1 — Resumo Consolidado**
- Patrimônio total do cliente (todas as corretoras)
- Patrimônio por corretora
- Rentabilidade consolidada do mês, ano, 12m
- Rentabilidade vs CDI, IPCA, Ibovespa
- Gráfico de evolução patrimonial (se disponível)

**Aba 2 — Alocação**
- Distribuição por classe (Renda Fixa, Fundos, RV, Alternativo)
- Distribuição por indexador (CDI, IPCA, Pré, Dólar)
- Distribuição por liquidez (D+0, D+1 a D+30, D+31 a D+90, > D+90)
- Distribuição por corretora
- Comparação com alocação alvo (se definida)

**Aba 3 — Posição Detalhada**
- Lista completa de todos os ativos em todas as corretoras
- Colunas: Corretora, Conta, Ativo, Tipo, Classe, Indexador, Taxa, Vencimento, Valor Aplicado, Posição Bruta, Posição Líquida, Rent. Mês, Rent. Ano, %CDI
- Ordenado por classe e valor (maior para menor)

**Aba 4 — Rentabilidade por Estratégia**
- Rentabilidade agregada por classe/subclasse
- Comparação com benchmarks (CDI, IPCA, Ibovespa, IFIX)

**Aba 5 — Vencimentos**
- Calendário de vencimentos dos próximos 12 meses
- Útil para planejamento de reinvestimento

**Aba 6 — Reconciliação/Divergências**
- Cruzamento entre fontes (como a planilha atual)
- Alertas de divergências significativas

---

## Stack Tecnológico Recomendado

### Para o piloto (fase 1)
| Componente | Tecnologia | Justificativa |
|-----------|------------|---------------|
| Extração | Claude API (Opus ou Sonnet) | Flexibilidade máxima com PDFs |
| Processamento | Python (pandas, openpyxl) | Manipulação de dados tabulares |
| Banco de dados | SQLite ou JSON files | Simplicidade, portabilidade |
| Relatório output | Excel via openpyxl | Familiar, flexível |
| Orquestração | Scripts Python + CLI | Sem overhead de infra |

### Para escalar (fase 2)
| Componente | Tecnologia | Justificativa |
|-----------|------------|---------------|
| Extração | Claude API Batch | Custo reduzido, processamento paralelo |
| Processamento | Python + dbt ou similar | Pipeline reprodutível |
| Banco de dados | PostgreSQL ou DuckDB | Consultas complexas, histórico |
| Relatório output | Excel + PDF (reportlab ou weasyprint) | Profissional |
| Orquestração | Airflow ou Prefect | Agendamento, retry, monitoramento |
| Interface | Streamlit ou similar | Upload de PDFs, config por cliente |

---

## Plano de Execução

### Fase 1 — Piloto (2-3 semanas)
**Objetivo:** Consolidar 1 cliente completo (Jose Mestrener) end-to-end.

- [ ] **Sprint 1 (Semana 1):**
  - Definir schema canônico final (JSON schema com validação)
  - Criar prompt de extração para relatório XP Posição Consolidada
  - Criar prompt de extração para relatório BTG/API Capital Performance
  - Testar extração nos 3 PDFs de amostra
  - Validar qualidade da extração (>95% de acurácia)

- [ ] **Sprint 2 (Semana 2):**
  - Implementar normalização em Python
  - Implementar reconciliação (matching entre contas)
  - Cruzar dados extraídos com planilha existente para validação
  - Implementar cálculo de rentabilidade consolidada

- [ ] **Sprint 3 (Semana 3):**
  - Gerar relatório Excel consolidado automatizado
  - Comparar com relatório manual existente
  - Ajustar e iterar
  - Documentar processo

### Fase 2 — Expansão (4-6 semanas)
**Objetivo:** Suportar 10 clientes, incluir C6.

- [ ] Criar prompt de extração para C6
- [ ] Implementar banco de histórico (SQLite)
- [ ] Cálculo de rentabilidade via snapshots para XP/C6
- [ ] Interface CLI para processar lote de clientes
- [ ] Pipeline batch: upload PDFs → processamento → relatórios
- [ ] Testes de qualidade com 10 clientes reais

### Fase 3 — Escala (6-10 semanas)
**Objetivo:** 50 clientes, processo automatizado.

- [ ] API Batch do Claude para custo reduzido
- [ ] Interface web simples (Streamlit) para upload e config
- [ ] Dashboard de monitoramento de qualidade
- [ ] Alertas automáticos de divergências
- [ ] Relatório PDF profissional (além do Excel)
- [ ] Documentação para equipe

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|-------------|---------|-----------|
| Corretora muda formato do PDF | Alta | Médio | LLM é resiliente a mudanças; manter prompts genéricos |
| Custo de API alto para 50 clientes | Média | Alto | Usar Sonnet para extração, Opus só para reconciliação; batch API |
| Acurácia insuficiente na extração | Baixa | Alto | Validação humana em loop; testes de regressão |
| Gap de rentabilidade XP | Certa | Médio | Snapshots mensais; aceitar que mês 1 não terá rent. XP |
| Ativos muito exóticos/novos | Média | Baixo | Fallback para categorização manual |
| Mudança regulatória/fiscal | Baixa | Médio | Schema flexível com campos extras |

---

## Métricas de Sucesso

1. **Acurácia de extração:** >95% dos valores extraídos corretamente (sem intervenção manual)
2. **Cobertura de ativos:** >98% dos ativos reconhecidos e classificados
3. **Tempo de processamento:** <30 minutos para gerar relatório de 1 cliente (vs ~2h manual)
4. **Divergências explicadas:** <5% de divergências não explicáveis entre fontes
5. **Custo por cliente/mês:** <R$10 em API (viável comercialmente)

---

## Decisões Pendentes

1. **Formato C6:** Precisamos de amostra de relatório/extrato do C6 para criar o extrator
2. **Consolidador externo:** Qual sistema gera os dados "externos" da planilha de cruzamento? Ele tem API?
3. **Alocação alvo:** Os clientes têm uma alocação target definida para comparar?
4. **Histórico retroativo:** Existe histórico de relatórios anteriores para alimentar a base de snapshots?
5. **Frequência:** Sempre mensal? Ou eventualmente semanal/sob demanda?
6. **Sonnet vs Opus para extração:** Testar se Sonnet 4.5 tem acurácia suficiente (custo ~10x menor)

---

## Próximos Passos Imediatos

1. Validar este plano e ajustar prioridades
2. Começar pela Fase 1, Sprint 1: schema + prompts de extração
3. Testar com os 3 PDFs já disponíveis
4. Iterar baseado nos resultados
