"""
Parser determinístico para BTG Pactual (Relatório de Performance).
Custo zero — usa pdfplumber + regex. Sem IA, sem API.

Estrutura do PDF (observada via inspeção):
  Pág 0 (capa):    Nome, Conta, Período
  Pág 1 (resumo):  Patrimônio bruto/líquido, performance mês/ano, evolução saldo
  Pág 2 (rent.):   Rentabilidade por períodos + histórico mensal
  Pág 3 (posição): Overview consolidado (2 colunas — ignorar)
  Pág 4 (evol.):   Evolução patrimonial mensal (tabela)
  Pág 5 (compos.): Distribuição por mercado + estratégia + rent. por estratégia
  Pág 6 (atrib.):  Gráfico de atribuição (ignorar)
  Pág 7-8 (pos.):  Posição detalhada — preço, qtd, taxa, saldo (ignorar para ativos)
  Pág 8-12 (perf.): Rentabilidade completa por ativo (seção principal para ativos)
  Pág 13+:         Última página, disclaimer (ignorar)

Notas sobre o PDF:
  - Caracteres acentuados e separadores são substituídos por \\x00 pelo pdfplumber
  - Use '.' (regex) ou '.{0,3}' para absorver \\x00 em nomes/palavras
"""

import re
import logging
import os

import pdfplumber

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de parsing numérico BR
# ---------------------------------------------------------------------------

def _num(text):
    """'R$ 1.234,56' | '1,31%' | '-4,95' | '-' → float | None."""
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in ("-", "–", "—"):
        return None
    s = s.replace("R$", "").replace("%", "").strip()
    neg = s.startswith("-")
    s = s.lstrip("-").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def _date_br_to_iso_full(text: str) -> str:
    """'30/01/2026' → '2026-01-30'"""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", (text or "").strip())
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return (text or "").strip()


def _extract_pcts(line: str):
    """Extrai todos os percentuais de uma linha: '1,16% 1,16% 14,49% 30,43%' → [1.16, 1.16, 14.49, 30.43].
    Suporta '-' como valor ausente → None."""
    vals = []
    for tok in line.split():
        tok = tok.strip()
        if tok == "-":
            vals.append(None)
        elif tok.endswith("%"):
            vals.append(_num(tok))
        else:
            break  # para na primeira token não-percentual
    return vals


# ---------------------------------------------------------------------------
# Extração da capa (página 0)
# ---------------------------------------------------------------------------

def _parse_capa(text: str, pdf_path: str) -> dict:
    """
    Texto típico (\\x00 substitui caracteres acentuados):
        Relat\\x00rio\\nde Performance\\n...
        Nome CID CARVALHO DE SOUZA
        Cont\\x00 Investimento 005058054
        Per\\x00odo de 19/10/2023 \\x00 31/01/2026
    """
    meta = {
        "cliente": None,
        "conta": None,
        "segmento": None,
        "parceiro": None,
        "data_referencia": None,
        "arquivo_origem": os.path.basename(pdf_path),
    }

    # Nome do cliente
    m = re.search(r"Nome\s+([A-Z][A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ ]+)", text)
    if m:
        meta["cliente"] = m.group(1).strip()

    # Número da conta (Conta/Cont\x00 Investimento XXXXXXX)
    m = re.search(r"Cont.{0,3}\s*Investimento\s+(\d+)", text)
    if m:
        # Strip leading zeros: "005058054" → "5058054"
        meta["conta"] = str(int(m.group(1)))

    # Data de referência (data final do período)
    # "Período de DD/MM/YYYY – DD/MM/YYYY" (– pode ser \x00)
    m = re.search(
        r"Per.{0,4}\s*de\s+\d{2}/\d{2}/\d{4}\s*.{0,3}\s*(\d{2}/\d{2}/\d{4})",
        text
    )
    if m:
        meta["data_referencia"] = _date_br_to_iso_full(m.group(1))

    return meta


# ---------------------------------------------------------------------------
# Extração do resumo (páginas 1 + 2)
# ---------------------------------------------------------------------------

def _parse_resumo(p1: str, p2: str) -> dict:
    """
    P1 linha inicial: 'R$ 1.171.109,49 R$ 1.157.792,39 1,51% 1,51%'
    P1 evolução:      'Rendimento 16.825,50 16.825,50'
                      'Entrad\\x00 177,37 177,37'
    P2 períodos:      'M\\x00s R$ 16.825,50 1,51% 1,16%'
                      '12 Meses R$ 168.264,23 15,43% 14,49%'
    """
    resumo = {}

    # Patrimônio bruto + performance mês/ano da linha "R$ X R$ Y A% B%"
    m = re.search(
        r"R\$\s*([\d.,]+)\s+R\$\s*[\d.,]+\s+([\d,]+)%\s+([\d,]+)%",
        p1
    )
    if m:
        resumo["patrimonio_total_bruto"] = _num(m.group(1))
        resumo["rentabilidade_mes_pct"] = _num(m.group(2))
        resumo["rentabilidade_ano_pct"] = _num(m.group(3))

    # Rendimento (ganho mês/ano)
    m = re.search(r"Rendimento\s+([\d.,]+)\s+([\d.,]+)", p1)
    if m:
        resumo["ganho_mes_rs"] = _num(m.group(1))
        resumo["ganho_ano_rs"] = _num(m.group(2))

    # Entradas/Movimentações
    m = re.search(r"Entrad.{0,1}\s+([\d.,]+)\s+([\d.,]+)", p1)
    if m:
        resumo["movimentacoes_mes_rs"] = _num(m.group(1))
        resumo["movimentacoes_ano_rs"] = _num(m.group(2))

    # Rentabilidades por período da P2
    def _period(label_re):
        return re.search(
            label_re + r"\s+R\$\s*([\d.,]+)\s+([\d,]+)%\s+([\d,]+)%",
            p2, re.IGNORECASE
        )

    m = _period(r"M.{0,2}s")
    if m:
        if "rentabilidade_mes_pct" not in resumo:
            resumo["rentabilidade_mes_pct"] = _num(m.group(2))
        resumo["_cdi_mes"] = _num(m.group(3))  # interno, usado abaixo

    m = _period(r"Ano")
    if m:
        if "rentabilidade_ano_pct" not in resumo:
            resumo["rentabilidade_ano_pct"] = _num(m.group(2))
        resumo["_cdi_ano"] = _num(m.group(3))

    m = _period(r"12\s+Meses")
    if m:
        resumo["rentabilidade_12m_pct"] = _num(m.group(2))
        resumo["_cdi_12m"] = _num(m.group(3))

    m = _period(r"24\s+Meses")
    if m:
        resumo["rentabilidade_24m_pct"] = _num(m.group(2))
        resumo["_cdi_24m"] = _num(m.group(3))

    # %CDI calculado (rent / cdi * 100)
    def _pct_cdi(rent_key, cdi_key):
        r = resumo.get(rent_key)
        c = resumo.get(cdi_key)
        if r is not None and c and c != 0:
            return round(r / c * 100, 2)
        return None

    resumo["pct_cdi_mes"] = _pct_cdi("rentabilidade_mes_pct", "_cdi_mes")
    resumo["pct_cdi_ano"] = _pct_cdi("rentabilidade_ano_pct", "_cdi_ano")
    resumo["pct_cdi_12m"] = _pct_cdi("rentabilidade_12m_pct", "_cdi_12m")
    resumo["pct_cdi_24m"] = _pct_cdi("rentabilidade_24m_pct", "_cdi_24m")

    # Limpar campos internos
    for k in ["_cdi_mes", "_cdi_ano", "_cdi_12m", "_cdi_24m"]:
        resumo.pop(k, None)

    # Garantir campos ausentes como None
    for k in ["patrimonio_total_bruto", "rentabilidade_mes_pct", "ganho_mes_rs",
              "rentabilidade_ano_pct", "ganho_ano_rs", "rentabilidade_12m_pct",
              "rentabilidade_24m_pct", "ganho_24m_rs", "pct_cdi_mes", "pct_cdi_ano",
              "pct_cdi_12m", "pct_cdi_24m", "movimentacoes_mes_rs",
              "movimentacoes_ano_rs", "movimentacoes_12m_rs"]:
        resumo.setdefault(k, None)

    return resumo


# ---------------------------------------------------------------------------
# Extração de benchmarks (página 2)
# ---------------------------------------------------------------------------

def _parse_benchmarks(text: str) -> dict:
    """
    Linhas: 'M\\x00s R$ 16.825,50 1,51% 1,16%' (rent%, CDI%)
            '12 Meses R$ 168.264,23 15,43% 14,49%'
    Extrai apenas CDI (único benchmark explícito no BTG).
    """
    bench = {}

    def _get_cdi(label_re):
        m = re.search(
            label_re + r"\s+R\$\s*[\d.,]+\s+[\d,]+%\s+([\d,]+)%",
            text, re.IGNORECASE
        )
        return _num(m.group(1)) if m else None

    cdi = {
        "mes": _get_cdi(r"M.{0,2}s"),
        "ano": _get_cdi(r"Ano"),
        "12m": _get_cdi(r"12\s+Meses"),
        "24m": _get_cdi(r"24\s+Meses"),
    }
    if any(v is not None for v in cdi.values()):
        bench["cdi"] = cdi

    return bench


# ---------------------------------------------------------------------------
# Extração da rentabilidade histórica mensal (página 2)
# ---------------------------------------------------------------------------

def _parse_rentabilidade_historica(text: str) -> list:
    """
    Tabela típica (14 valores: jan–dez + ano_total + acumulado):
        2026 1,51% - - - - - - - - - - -  1,51%  31,55%
        CDI  1,16% - - - - - - - - - - -  1,16%  30,49%
        % do CDI 130,17% - ...  130,17%  103,48%
        2025 1,19% 1,05% 1,09% ...  15,07%  29,59%
        CDI  ...
        % do CDI ...
    """
    MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]

    # Padrão: YYYY seguido de 14 valores (pct% ou -)
    VAL = r"(-?[\d,]+%?|-)"
    YEAR_RE = re.compile(
        r"^(\d{4})\s+" + r"\s+".join([VAL] * 14),
        re.IGNORECASE
    )
    CDI_RE = re.compile(
        r"^CDI\s+" + r"\s+".join([VAL] * 14),
        re.IGNORECASE
    )
    PCTCDI_RE = re.compile(
        r"^%\s*do\s*CDI\s+" + r"\s+".join([VAL] * 14),
        re.IGNORECASE
    )

    entries = {}  # ano → {port:[...], cdi:[...], pct_cdi:[...]}
    pending_ano = None
    pending_port = None
    pending_cdi = None

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        m = YEAR_RE.match(line)
        if m:
            pending_ano = int(m.group(1))
            pending_port = [m.group(i) for i in range(2, 16)]
            pending_cdi = None
            continue

        if pending_ano is not None:
            m = CDI_RE.match(line)
            if m:
                pending_cdi = [m.group(i) for i in range(1, 15)]
                continue

            m = PCTCDI_RE.match(line)
            if m:
                pct_cdi_vals = [m.group(i) for i in range(1, 15)]
                entries[pending_ano] = {
                    "portfolio": pending_port,
                    "cdi": pending_cdi,
                    "pct_cdi": pct_cdi_vals,
                }
                pending_ano = None
                pending_port = None
                pending_cdi = None
                continue

    result = []
    for ano in sorted(entries.keys(), reverse=True):
        e = entries[ano]
        port = e.get("portfolio", [])
        pct_cdi = e.get("pct_cdi", [])

        meses_dict = {}
        for idx, mes in enumerate(MESES):
            p_val = _num(port[idx]) if idx < len(port) else None
            c_val = _num(pct_cdi[idx]) if idx < len(pct_cdi) else None
            if p_val is not None:
                meses_dict[mes] = {
                    "portfolio_pct": p_val,
                    "pct_cdi": c_val,
                }

        ano_pct = _num(port[12]) if len(port) > 12 else None
        acum_pct = _num(port[13]) if len(port) > 13 else None

        result.append({
            "ano": ano,
            "meses": meses_dict,
            "ano_pct": ano_pct,
            "acumulada_pct": acum_pct,
        })

    return result


# ---------------------------------------------------------------------------
# Extração da evolução patrimonial (página 4)
# ---------------------------------------------------------------------------

def _parse_evolucao(text: str) -> list:
    """
    Linha típica:
        Jan/26  R$ 1.155.093,85  -R$ 809,22  R$ 0,64  R$ 1.171.109,49  R$ 16.825,50  1,51%  1,16%
    Colunas: Data | P_inicial | Movimentações | IR_Pago | P_final | Ganho | Portfólio% | CDI%
    (BTG não tem IOF — diferente da XP)
    """
    MESES = {"jan": "01", "fev": "02", "mar": "03", "abr": "04",
              "mai": "05", "jun": "06", "jul": "07", "ago": "08",
              "set": "09", "out": "10", "nov": "11", "dez": "12"}

    pattern = re.compile(
        r"([A-Za-z]{3})/(\d{2})\s+"
        r"(-?R\$\s*[\d.,]+)\s+"     # patrimônio inicial
        r"(-?R\$\s*[\d.,]+)\s+"     # movimentações
        r"(-?R\$\s*[\d.,]+)\s+"     # IR pago
        r"(-?R\$\s*[\d.,]+)\s+"     # patrimônio final
        r"(-?R\$\s*[\d.,]+)\s+"     # ganho financeiro
        r"(-?[\d,]+%?)\s+"          # portfólio %
        r"(-?[\d,]+%?)",            # CDI %
        re.IGNORECASE
    )

    evolucao = []
    for m in pattern.finditer(text):
        mes_nome = m.group(1).lower()[:3]
        ano = 2000 + int(m.group(2))
        mes_num = MESES.get(mes_nome, "??")
        evolucao.append({
            "data": f"{ano}-{mes_num}",
            "patrimonio_inicial": _num(m.group(3)),
            "movimentacoes": _num(m.group(4)),
            "ir": _num(m.group(5)),
            "iof": 0.0,  # BTG não reporta IOF separado
            "patrimonio_final": _num(m.group(6)),
            "ganho_financeiro": _num(m.group(7)),
            "rentabilidade_pct": _num(m.group(8)),
            "pct_cdi": _num(m.group(9)),
        })
    return evolucao


# ---------------------------------------------------------------------------
# Extração da composição por estratégia (página 5)
# ---------------------------------------------------------------------------

def _parse_composicao(text: str) -> list:
    """
    Seção 'Distribuição por classe de ativos':
        Pós-\\x00xado 76,97% R$ 901.370,35
        (pode ter prefixo '100%' do gráfico)

    Seção de rentabilidade (logo abaixo):
        76,97%  1,34%  1,34%  15,66%  32,90%
        Pós-\\x00xado
        R$ 901.370,35 R$ 11.559,32 ...
        CDI ...
    """
    # --- Passo 1: Extrair saldo + pct_alocacao por estratégia ---
    alloc = {}  # nome_raw → {saldo, pct}
    ALLOC_RE = re.compile(
        r"^(?:100%\s+)?(.+?)\s+([\d,]+)%\s+R\$\s*([\d.,]+)$"
    )
    # Localiza a seção "Distribuição por classe de ativos"
    start = text.find("por classe de ativos")
    if start == -1:
        start = 0
    for line in text[start:].split("\n"):
        line = line.strip()
        m = ALLOC_RE.match(line)
        if m:
            nome = m.group(1).strip()
            pct = _num(m.group(2))
            saldo = _num(m.group(3))
            if nome and nome.lower() not in ("total", "estrat\x00gi\x00", "estrat"):
                alloc[nome] = {"pct": pct, "saldo": saldo}

    # --- Passo 2: Extrair rentabilidades por estratégia ---
    rents = {}  # nome_raw → {mes, ano, 12m, acum}
    # Padrão: linha com 5 percentuais = pct_aloc mes ano 12m acum
    FIVE_PCTS = re.compile(
        r"^([\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%$"
    )
    lines = text.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        m = FIVE_PCTS.match(line)
        if m:
            # Próxima linha não-vazia = nome da estratégia
            nome_strat = None
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = lines[j].strip()
                if candidate and not candidate.startswith("R$") and not candidate.startswith("CDI"):
                    nome_strat = candidate
                    break
            if nome_strat:
                rents[nome_strat] = {
                    "mes": _num(m.group(2)),
                    "ano": _num(m.group(3)),
                    "12m": _num(m.group(4)),
                    "acum": _num(m.group(5)),
                }

    # --- Passo 3: Combinar alocação + rentabilidade ---
    # Usa distância de string para matching (estratégias têm \x00)
    def _best_match(nome_alloc, rents_dict):
        """Encontra a chave em rents_dict mais próxima de nome_alloc."""
        # Normaliza: remove \x00 e converte pra lower
        def norm(s):
            return re.sub(r"[\x00]", "", s).lower().strip()

        na = norm(nome_alloc)
        best, best_score = None, 0
        for k in rents_dict:
            nk = norm(k)
            # Conta chars em comum (simplificado)
            common = sum(1 for c in na if c in nk)
            score = common / max(len(na), len(nk), 1)
            if score > best_score:
                best_score = score
                best = k
        return best if best_score > 0.5 else None

    composicao = []
    for nome_raw, av in alloc.items():
        rent_key = _best_match(nome_raw, rents)
        rv = rents.get(rent_key, {}) if rent_key else {}

        # Limpa nome: mapeia para canônico (lida com \x00 e \ufffd)
        nome_clean = _normalize_btg_strategy(nome_raw)

        composicao.append({
            "estrategia": nome_clean,
            "saldo_bruto": av.get("saldo"),
            "pct_alocacao": av.get("pct"),
            "rent_mes_pct": rv.get("mes"),
            "rent_ano_pct": rv.get("ano"),
            "rent_12m_pct": rv.get("12m"),
            "rent_24m_pct": None,
        })

    # Ordenar por saldo decrescente
    composicao.sort(key=lambda x: (x.get("saldo_bruto") or 0), reverse=True)
    return composicao


# ---------------------------------------------------------------------------
# Extração dos ativos (páginas de rentabilidade completa, tipicamente 8-12)
# ---------------------------------------------------------------------------

# Regex de detecção de linhas
_SECTION_HDR = re.compile(
    r"Em\s+.+\s+do\s+Total\s+R\$|Em\s+Rend.{0,5}\s+Vari.{0,5}",
    re.IGNORECASE
)
_COL_HDR = re.compile(
    r"Saldo\s+Percentual\s+Saldo|Ativo\s+M.s\s+Ano|Bruto\s*\(R\$\)\s+%|"
    r"Ativo\s+Saldo\s+Bruto|Ativo\s+Dat.{0,3}\s+Inicial|Quantidade\s+Vencimento",
    re.IGNORECASE
)
_PAGE_NUM = re.compile(r"P.gina\s+\d+\s+de\s+\d+", re.IGNORECASE)
_PERIOD_HDR = re.compile(r"Per.{0,4}\s*odo\s+de\s+\d{2}/\d{2}/\d{4}", re.IGNORECASE)
_REPORT_HDR = re.compile(r"Relat.{0,4}rio\s+de\s+Performance", re.IGNORECASE)
_TOTAL_LINE = re.compile(r"^Total\s+[\d.,]")
_CDI_LINE = re.compile(r"^CDI\s+(-?[\d,]+%?|-)\s+")
_PCTCDI_LINE = re.compile(r"^%\s*do\s*CDI\s+(-?[\d,]+%?|-)")
_ABS_EARN = re.compile(
    r"^(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)$"
)
_SALDO_DATE = re.compile(
    r"^([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+(\d{2}/\d{2}/\d{4})$"
)
_SALDO_NODATE = re.compile(
    r"^([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)$"
)
# 4 percentuais (formato B — linha de rentabilidade antes do nome)
_FUND_B_RENT = re.compile(
    r"^(-?[\d,]+%)\s+(-?[\d,]+%)\s+(-?[\d,]+%)\s+(-?[\d,]+%)$"
)
# Nome + 4 percentuais (formato A — nome na mesma linha)
_FUND_A_RENT = re.compile(
    r"^(.+?)\s+(-?[\d,]+%)\s+(-?[\d,]+%)\s+(-?[\d,]+%)\s+(-?[\d,]+%)$"
)
# Nome + saldo + 2 floats + data (fundo com data)
_FUND_NAME_DATE = re.compile(
    r"^(.+?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+(\d{2}/\d{2}/\d{4})$"
)
# Nome + saldo + 2 floats sem data (ticker)
_FUND_NAME_NODATE = re.compile(
    r"^([A-Z0-9]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)$"
)
# Sub-header de estratégia: nome + saldo + 2 floats (sem data, sem %)
_STRAT_SUB = re.compile(
    r"^(.+?)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)$"
)
# Linha RF_CONT: texto opcional + 4 números (pode ter | no meio)
_RF_CONT = re.compile(
    r"^(.*?)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)\s+(-?[\d.,]+)$"
)

# Mapeamento de padrões de estratégia → nome canônico.
# O pdfplumber substitui a ligatura "fi" por \x00 e alguns acentos por U+FFFD.
# Exemplo real: "Pré-fixado" → "Pré-\x00xado", "Pós-fixado" → "Pós-\x00xado"
#               "Inflação"  → "Infla<FFFD>o", "Renda Variável" → "Rend\x00 Vari<FFFD>vel"
_STRAT_CANONICAL = [
    (re.compile(r"P.s-\x00xado", re.IGNORECASE),           "Pós-fixado"),
    (re.compile(r"Pr.{0,2}-\x00xado", re.IGNORECASE),      "Pré-fixado"),
    (re.compile(r"Infla.{0,3}o", re.IGNORECASE),           "Inflação"),
    (re.compile(r"Retorno\s+Absoluto", re.IGNORECASE),     "Retorno Absoluto (MM)"),
    (re.compile(r"Rend.\s+Vari.vel", re.IGNORECASE),       "Renda Variável"),
    (re.compile(r"Alternativo", re.IGNORECASE),             "Alternativo"),
    (re.compile(r"Previd.{0,6}ncia", re.IGNORECASE),       "Previdência"),
    (re.compile(r"Caixa", re.IGNORECASE),                   "Caixa"),
    (re.compile(r"Cont.{0,3}\s*corrente", re.IGNORECASE),  "Conta corrente"),
    (re.compile(r"Multimercado", re.IGNORECASE),            "Multimercado"),
]


def _normalize_btg_strategy(text: str) -> str:
    """Mapeia nome de estratégia BTG (possivelmente com \x00/\ufffd) para nome canônico."""
    for pattern, canonical in _STRAT_CANONICAL:
        if pattern.search(text):
            return canonical
    # Fallback: remove chars problemáticos
    return re.sub(r"[\x00\ufffd]", "", text).strip()

# Perf section start marker
_PERF_START = re.compile(
    r"A\s+rentabilidade\s+completa|Por\s+classe\s+de\s+ativos",
    re.IGNORECASE
)


def _clean_asset_name(name: str) -> str:
    """Remove fragmentos de taxa/vencimento após '|' do nome."""
    if "|" in name:
        name = name[:name.index("|")]
    return name.strip()


def _is_strategy_name(text: str) -> bool:
    """Verifica se o texto parece um nome de estratégia (não ativo)."""
    return any(p.search(text.strip()) for p, _ in _STRAT_CANONICAL)


def _parse_ativos(pages_text: list) -> list:
    """
    Extrai ativos da seção 'A rentabilidade completa'.

    Dois formatos de bloco (5 linhas cada):
      Formato A (Renda Fixa): nome_parcial + 4pct% | saldo+pct+pct+data |
                              nome_cont + 4abs | CDI% | %CDI%
      Formato B (Fundos):     4pct% | nome+saldo+pct+pct+[data] |
                              4abs | CDI% | %CDI%

    Sub-headers de estratégia: nome + saldo + float + float (sem data)
    Section headers: 'Em [Mercado] X% do Total R$ Y'
    """
    ativos = []

    # Juntar todas as páginas numa stream de linhas
    all_lines = []
    in_perf = False
    for page_text in pages_text:
        if not page_text:
            continue
        for line in page_text.split("\n"):
            line = line.strip()
            if not in_perf:
                if _PERF_START.search(line):
                    in_perf = True
                continue
            all_lines.append(line)

    if not all_lines:
        logger.debug("Seção de performance não encontrada nos ativos BTG")
        return ativos

    # State machine
    STATE_FIND = 0
    STATE_RF_SALDO = 1
    STATE_RF_CONT = 2
    STATE_FUND_NAME = 3
    STATE_ABS_EARN = 4
    STATE_WAIT_CDI = 5
    STATE_WAIT_PCTCDI = 6

    state = STATE_FIND
    cur = {}         # asset being built
    cur_strat = None
    pending_rents = None   # Format B: [mes%, ano%, 12m%, acum%]
    pending_name_a = None  # Format A: partial name
    pending_rents_a = None  # Format A: [mes%, ano%, 12m%, acum%]

    def _save_asset():
        if cur.get("nome_original") and cur.get("saldo_bruto") is not None:
            cur["nome_original"] = _clean_asset_name(cur["nome_original"])
            ativos.append(dict(cur))

    for line in all_lines:
        if not line:
            continue

        # Linhas a ignorar sempre
        if (_PAGE_NUM.match(line) or _PERIOD_HDR.match(line) or
                _REPORT_HDR.match(line) or _COL_HDR.match(line)):
            continue
        if _TOTAL_LINE.match(line):
            # Finaliza seção, reseta (não salva)
            state = STATE_FIND
            cur = {}
            continue
        if _SECTION_HDR.match(line):
            state = STATE_FIND
            cur = {}
            continue

        # --- ESTADO: WAIT_CDI ---
        if state == STATE_WAIT_CDI:
            if _CDI_LINE.match(line):
                # Extrai valores CDI (para %CDI, usaremos a linha % do CDI)
                state = STATE_WAIT_PCTCDI
                continue
            # Se não for CDI, pode ser uma linha residual: ignorar
            continue

        # --- ESTADO: WAIT_PCTCDI ---
        if state == STATE_WAIT_PCTCDI:
            if _PCTCDI_LINE.match(line):
                # Extrai %CDI: "% do CDI X% X% X% X%"
                tokens = line.split()
                # Pula "%" "do" "CDI"
                pcts = [t for t in tokens[3:] if t != "-"]
                pct_vals = [_num(t) for t in pcts[:4]]
                while len(pct_vals) < 4:
                    pct_vals.append(None)
                cur["pct_cdi_mes"] = pct_vals[0]
                cur["pct_cdi_ano"] = pct_vals[1]
                cur["pct_cdi_12m"] = pct_vals[2]
                cur["pct_cdi_acumulada"] = pct_vals[3]
                _save_asset()
                cur = {}
                state = STATE_FIND
            continue

        # --- ESTADO: ABS_EARN ---
        if state == STATE_ABS_EARN:
            m = _ABS_EARN.match(line)
            if m:
                state = STATE_WAIT_CDI
                continue
            # Linha inesperada: tenta CDI direto
            if _CDI_LINE.match(line):
                state = STATE_WAIT_PCTCDI
                continue
            # Pode ser que não há linha de abs (raro): salta para CDI
            if _PCTCDI_LINE.match(line):
                # Handle %CDI direto sem CDI anterior
                tokens = line.split()
                pcts = [t for t in tokens[3:] if t != "-"]
                pct_vals = [_num(t) for t in pcts[:4]]
                while len(pct_vals) < 4:
                    pct_vals.append(None)
                cur["pct_cdi_mes"] = pct_vals[0]
                cur["pct_cdi_ano"] = pct_vals[1]
                cur["pct_cdi_12m"] = pct_vals[2]
                cur["pct_cdi_acumulada"] = pct_vals[3]
                _save_asset()
                cur = {}
                state = STATE_FIND
            continue

        # --- ESTADO: RF_CONT ---
        if state == STATE_RF_CONT:
            m = _RF_CONT.match(line)
            if m:
                # Extrair nome continuation (antes do primeiro '|' ou antes dos números)
                name_raw = m.group(1).strip()
                if name_raw.startswith("|"):
                    name_cont = ""
                elif "|" in name_raw:
                    name_cont = name_raw[:name_raw.index("|")].strip()
                else:
                    name_cont = name_raw.strip()

                # Montar nome completo
                base = pending_name_a or cur.get("nome_original", "")
                if name_cont:
                    # Se base termina com '-', concatenar sem espaço
                    if base.endswith("-") or base.endswith(" -"):
                        cur["nome_original"] = base + name_cont
                    else:
                        cur["nome_original"] = (base + " " + name_cont).strip()
                else:
                    cur["nome_original"] = base

                pending_name_a = None
                state = STATE_WAIT_CDI
                continue
            # Linha inesperada no RF_CONT: pode ser CDI
            if _CDI_LINE.match(line):
                if pending_name_a:
                    cur["nome_original"] = pending_name_a
                    pending_name_a = None
                state = STATE_WAIT_PCTCDI
                continue
            continue

        # --- ESTADO: RF_SALDO ---
        if state == STATE_RF_SALDO:
            m = _SALDO_DATE.match(line)
            if m:
                cur["saldo_bruto"] = _num(m.group(1))
                cur["pct_alocacao"] = _num(m.group(3))  # %PL
                cur["quantidade"] = None
                state = STATE_RF_CONT
                continue
            # Linha inesperada (ex: nome continuation): acumular
            continue

        # --- ESTADO: FUND_NAME ---
        if state == STATE_FUND_NAME:
            # Tenta: nome + saldo + pct + pct + data
            m = _FUND_NAME_DATE.match(line)
            if m:
                cur["nome_original"] = m.group(1).strip()
                cur["saldo_bruto"] = _num(m.group(2))
                cur["pct_alocacao"] = _num(m.group(4))  # %PL (3º número = %sub)
                cur["quantidade"] = None
                cur["rent_mes_pct"] = _num(pending_rents[0]) if pending_rents else None
                cur["rent_ano_pct"] = _num(pending_rents[1]) if pending_rents else None
                cur["rent_12m_pct"] = _num(pending_rents[2]) if pending_rents else None
                cur["rent_acumulada_pct"] = _num(pending_rents[3]) if pending_rents else None
                cur["estrategia"] = cur_strat
                cur["pct_cdi_mes"] = None
                cur["pct_cdi_ano"] = None
                cur["pct_cdi_12m"] = None
                cur["pct_cdi_acumulada"] = None
                pending_rents = None
                state = STATE_ABS_EARN
                continue

            # Tenta: ticker (4 chars + 2 dígitos) + saldo + 2 floats (sem data)
            m = _FUND_NAME_NODATE.match(line)
            if m:
                cur["nome_original"] = m.group(1).strip()
                cur["saldo_bruto"] = _num(m.group(2))
                cur["pct_alocacao"] = _num(m.group(4))  # último float = %PL
                cur["quantidade"] = None
                cur["rent_mes_pct"] = _num(pending_rents[0]) if pending_rents else None
                cur["rent_ano_pct"] = _num(pending_rents[1]) if pending_rents else None
                cur["rent_12m_pct"] = _num(pending_rents[2]) if pending_rents else None
                cur["rent_acumulada_pct"] = _num(pending_rents[3]) if pending_rents else None
                cur["estrategia"] = cur_strat
                cur["pct_cdi_mes"] = None
                cur["pct_cdi_ano"] = None
                cur["pct_cdi_12m"] = None
                cur["pct_cdi_acumulada"] = None
                pending_rents = None
                state = STATE_ABS_EARN
                continue
            continue

        # --- ESTADO: FIND ---
        assert state == STATE_FIND

        # CDI / %CDI soltos (transição de página)
        if _CDI_LINE.match(line):
            continue
        if _PCTCDI_LINE.match(line):
            continue

        # Verificar sub-header: nome + 3 números (sem data, sem %)
        m = _STRAT_SUB.match(line)
        if m:
            name_part = m.group(1).strip()
            if _is_strategy_name(name_part):
                cur_strat = _normalize_btg_strategy(name_part)
                continue

        # Formato B: linha com apenas 4 percentuais
        m = _FUND_B_RENT.match(line)
        if m:
            pending_rents = [m.group(i) for i in range(1, 5)]
            cur = {"estrategia": cur_strat}
            state = STATE_FUND_NAME
            continue

        # Formato A: nome + 4 percentuais
        m = _FUND_A_RENT.match(line)
        if m:
            pending_name_a = m.group(1).strip()
            pending_rents_a = [m.group(i) for i in range(2, 6)]
            cur = {
                "nome_original": pending_name_a,
                "estrategia": cur_strat,
                "saldo_bruto": None,
                "quantidade": None,
                "pct_alocacao": None,
                "rent_mes_pct": _num(pending_rents_a[0]),
                "rent_ano_pct": _num(pending_rents_a[1]),
                "rent_12m_pct": _num(pending_rents_a[2]),
                "rent_acumulada_pct": _num(pending_rents_a[3]),
                "pct_cdi_mes": None,
                "pct_cdi_ano": None,
                "pct_cdi_12m": None,
                "pct_cdi_acumulada": None,
            }
            pending_rents_a = None
            state = STATE_RF_SALDO
            continue

    return ativos


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def parse_btg_performance(pdf_path: str) -> dict:
    """
    Extrai dados do relatório BTG Performance.

    Args:
        pdf_path: Caminho para o arquivo PDF.

    Returns:
        Dict no schema consolidador-v2.
    """
    logger.info(f"Parsing BTG Performance: {os.path.basename(pdf_path)}")

    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")

    n = len(pages_text)
    logger.debug(f"Total de páginas: {n}")

    # ---- META (capa — página 0) ----
    meta = _parse_capa(pages_text[0] if pages_text else "", pdf_path)

    # ---- RESUMO (página 1 + 2) ----
    p1 = pages_text[1] if n > 1 else ""
    p2 = pages_text[2] if n > 2 else ""
    resumo = _parse_resumo(p1, p2)

    # ---- BENCHMARKS (página 2) ----
    benchmarks = _parse_benchmarks(p2)

    # ---- RENTABILIDADE HISTÓRICA (página 2) ----
    rent_hist = _parse_rentabilidade_historica(p2)

    # ---- EVOLUÇÃO PATRIMONIAL (página 4) ----
    p4 = pages_text[4] if n > 4 else ""
    evolucao = _parse_evolucao(p4)

    # ---- COMPOSIÇÃO (página 5) ----
    p5 = pages_text[5] if n > 5 else ""
    composicao = _parse_composicao(p5)

    # ---- ATIVOS (páginas 7 em diante — busca pela seção de performance) ----
    ativos = _parse_ativos(pages_text[7:] if n > 7 else [])

    result = {
        "$schema": "consolidador-v2",
        "meta": {
            "cliente": meta.get("cliente"),
            "conta": meta.get("conta"),
            "corretora": "BTG",
            "segmento": meta.get("segmento"),
            "parceiro": meta.get("parceiro"),
            "data_referencia": meta.get("data_referencia"),
            "tipo_relatorio": "btg_performance",
            "arquivo_origem": meta.get("arquivo_origem"),
        },
        "resumo_carteira": resumo,
        "benchmarks": benchmarks,
        "estatistica_historica": None,
        "composicao_por_estrategia": composicao,
        "rentabilidade_historica_mensal": rent_hist,
        "evolucao_patrimonial": evolucao,
        "ativos": ativos,
        "movimentacoes": [],
    }

    n_ativos = len(ativos)
    patrimonio = resumo.get("patrimonio_total_bruto") or 0
    logger.info(
        f"BTG {meta.get('conta')} — {n_ativos} ativos | R$ {patrimonio:,.2f}"
    )

    return result
