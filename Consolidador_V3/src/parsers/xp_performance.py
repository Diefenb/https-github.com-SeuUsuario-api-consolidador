"""
Parser determinístico para XP Performance (Relatório de Investimentos XP).
Custo zero — usa pdfplumber + regex. Sem IA, sem API.

Estrutura do PDF (observada via inspeção):
  Pág 1 (capa):    conta, parceiro, data, segmento
  Pág 2 (resumo):  patrimônio, rentabilidade, benchmarks, estatística, resumo
  Pág 3 (rent.):   rentabilidade histórica mensal por ano
  Pág 4 (evol.):   evolução patrimonial por período
  Pág 5 (compos.): composição por estratégia
  Pág 6 (perf.):   rentabilidade por classe (ignoramos — redundante com pág 5)
  Pág 7+ (pos.):   posição detalhada dos ativos (multi-página)
  Últimas (mov.):  movimentações da conta
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
    """'R$ 1.234,56' | '1,31%' | '-4,95' → float. None se inválido."""
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


def _date_br_month_to_iso(text: str) -> str:
    """'jan./26' | 'fev./25' → '2026-01'"""
    MESES = {
        "jan": "01", "fev": "02", "mar": "03", "abr": "04",
        "mai": "05", "jun": "06", "jul": "07", "ago": "08",
        "set": "09", "out": "10", "nov": "11", "dez": "12",
    }
    m = re.match(r"([a-z]{3})\.?/(\d{2,4})", (text or "").strip().lower())
    if m:
        mes_num = MESES.get(m.group(1), "??")
        ano = int(m.group(2))
        if ano < 100:
            ano += 2000
        return f"{ano:04d}-{mes_num}"
    return (text or "").strip()


# ---------------------------------------------------------------------------
# Extração da capa (página 1)
# ---------------------------------------------------------------------------

def _parse_capa(text: str, arquivo_origem: str) -> dict:
    """
    Texto típico:
        Relatório de Investimentos
        Conta Parceiro Data de Referência
        8660669 Guilherme Barbosa 30/01/2026
        Exclusive
    """
    meta = {
        "cliente": None,
        "conta": None,
        "segmento": None,
        "parceiro": None,
        "data_referencia": None,
        "arquivo_origem": os.path.basename(arquivo_origem),
    }

    # Conta + Parceiro + Data numa linha
    m = re.search(
        r"(\d{5,10})\s+([A-ZÀ-Úa-zà-ú][\w À-Úà-ú]+?)\s+(\d{2}/\d{2}/\d{4})",
        text
    )
    if m:
        meta["conta"] = m.group(1)
        meta["parceiro"] = m.group(2).strip()
        meta["data_referencia"] = _date_br_to_iso_full(m.group(3))

    # Segmento
    seg = re.search(r"\b(Exclusive|Signature|Private|One)\b", text)
    if seg:
        meta["segmento"] = seg.group(1)

    return meta


# ---------------------------------------------------------------------------
# Extração do resumo da carteira (página 2 — texto)
# ---------------------------------------------------------------------------

def _parse_resumo(text: str) -> dict:
    """
    Extrai patrimônio, rentabilidade, ganhos do bloco de resumo.
    """
    resumo = {}

    # Patrimônio Total Bruto — o valor pode estar na linha seguinte ao label
    m = re.search(r"PATRIM.+?BRUTO:.*?(R\$\s*[\d.,]+)", text, re.DOTALL | re.IGNORECASE)
    if m:
        resumo["patrimonio_total_bruto"] = _num(m.group(1))

    # Bloco tabela: Período | Ganho | Rent | %CDI | Mov
    # Linha MÊS:  R$ 3.305,60  1,31%  112,83%  R$ 0,00
    def _parse_periodo(label):
        pattern = (
            rf"{label}\s+"
            r"(R\$\s*[\d.,]+)\s+"    # ganho
            r"([\d,]+%?)\s+"          # rentabilidade
            r"([\d,]+%?)\s+"          # %CDI
            r"(-?R?\$?\s*[\d.,]+)"    # movimentações
        )
        return re.search(pattern, text, re.IGNORECASE)

    m = _parse_periodo("M[ÊE]S")
    if m:
        resumo["ganho_mes_rs"] = _num(m.group(1))
        resumo["rentabilidade_mes_pct"] = _num(m.group(2))
        resumo["pct_cdi_mes"] = _num(m.group(3))
        resumo["movimentacoes_mes_rs"] = _num(m.group(4))

    m = _parse_periodo("ANO")
    if m:
        resumo["ganho_ano_rs"] = _num(m.group(1))
        resumo["rentabilidade_ano_pct"] = _num(m.group(2))
        resumo["pct_cdi_ano"] = _num(m.group(3))
        resumo["movimentacoes_ano_rs"] = _num(m.group(4))

    m = _parse_periodo("12M")
    if m:
        resumo["rentabilidade_12m_pct"] = _num(m.group(2))
        resumo["pct_cdi_12m"] = _num(m.group(3))
        resumo["movimentacoes_12m_rs"] = _num(m.group(4))

    m = _parse_periodo("24M")
    if m:
        resumo["ganho_24m_rs"] = _num(m.group(1))
        resumo["rentabilidade_24m_pct"] = _num(m.group(2))
        resumo["pct_cdi_24m"] = _num(m.group(3))

    return resumo


# ---------------------------------------------------------------------------
# Extração de benchmarks (página 2 — texto)
# ---------------------------------------------------------------------------

def _parse_benchmarks(text: str) -> dict:
    """
    Benchmarks: CDI, Ibovespa, IPCA, Dólar — Mês/Ano/12M/24M
    Linha típica: 'CDI 1,16% 1,16% 14,49% 26,99%'
    Usa padrão flexible para não depender de caracteres especiais.
    """
    bench = {}

    def _extract(label_re, chave):
        m = re.search(
            label_re + r"\s+(-?[\d,]+%?)\s+(-?[\d,]+%?)\s+(-?[\d,]+%?)\s+(-?[\d,]+%?)",
            text, re.IGNORECASE
        )
        if m:
            bench[chave] = {
                "mes": _num(m.group(1)),
                "ano": _num(m.group(2)),
                "12m": _num(m.group(3)),
                "24m": _num(m.group(4)),
            }

    _extract(r"CDI", "cdi")
    _extract(r"Ibovespa", "ibovespa")
    _extract(r"IPCA", "ipca")
    # Dólar: usa padrão encoding-agnostic (ó pode variar conforme PDF)
    _extract(r"[Dd][^\s]{0,3}lar", "dolar")

    return bench


# ---------------------------------------------------------------------------
# Extração de estatística histórica (página 2 — TABELAS)
# ---------------------------------------------------------------------------

def _parse_estatistica_from_tables(page) -> dict:
    """
    Usa extract_tables() para pegar a tabela de estatísticas.
    No layout do PDF, os valores ficam em células com label+valor embutidos:
      'Meses Positivos\\n24'  |  ''  |  'Meses Negativos\\n0'
    """
    stat = {}
    try:
        tables = page.extract_tables()
    except Exception:
        return stat

    for table in tables:
        for row in table:
            for cell in (row or []):
                if not cell:
                    continue
                c = str(cell)

                m = re.search(r"Meses Positivos[\s\n]+(\d+)", c)
                if m:
                    stat["meses_positivos"] = int(m.group(1))

                m = re.search(r"Meses Negativos[\s\n]+(\d+)", c)
                if m:
                    stat["meses_negativos"] = int(m.group(1))

                m = re.search(r"Retorno Mensal M[áa]ximo[\s\n]+([\d,]+%?)", c)
                if m:
                    stat["retorno_mensal_max_pct"] = _num(m.group(1))

                m = re.search(r"Retorno Mensal M[íi]nimo[\s\n]+([\d,]+%?)", c)
                if m:
                    stat["retorno_mensal_min_pct"] = _num(m.group(1))

                m = re.search(r"Meses Acima do CDI[\s\n]+(\d+)", c)
                if m:
                    stat["meses_acima_cdi"] = int(m.group(1))

                m = re.search(r"Meses Abaixo do CDI[\s\n]+(\d+)", c)
                if m:
                    stat["meses_abaixo_cdi"] = int(m.group(1))

                m = re.search(r"Volatilidade\([\w\s]+12M\)[\s\n]+([\d,]+%?)", c)
                if m:
                    stat["volatilidade_12m_pct"] = _num(m.group(1))

                m = re.search(r"Volatilidade\([\w\s]+24M\)[\s\n]+([\d,]+%?)", c)
                if m:
                    stat["volatilidade_24m_pct"] = _num(m.group(1))

    return stat


# ---------------------------------------------------------------------------
# Extração de rentabilidade histórica mensal (página 3)
# ---------------------------------------------------------------------------

def _parse_rentabilidade_historica(text: str) -> list:
    """
    Sequência no texto:
        Portfólio 1,31% - - - - - - - - - - - 1,31% 61,39%
        2026
        %CDI 112,83% - - - - - - - - - - - 112,83% 108,56%
        Portfólio 1,13% 1,10% ... 14,36% 59,29%
        2025
        %CDI 111,49% ...

    Nota: o ANO aparece APÓS a linha Portfólio, não antes.
    Usamos state machine: Portfolio → Year → CDI → repete.
    """
    MESES_ABBR = ["jan", "fev", "mar", "abr", "mai", "jun",
                  "jul", "ago", "set", "out", "nov", "dez"]

    VAL = r"([\d,]+%?|-)"
    PORT_RE = re.compile(
        r"Portf[óo]lio\s+" + r"\s+".join([VAL] * 14), re.IGNORECASE
    )
    CDI_RE = re.compile(
        r"%CDI\s+" + r"\s+".join([VAL] * 14), re.IGNORECASE
    )
    ANO_RE = re.compile(r"^(\d{4})$")

    lines = text.split("\n")
    entries = {}  # ano → {"portfolio": [...], "cdi": [...]}

    state = "want_portfolio"
    pending_port = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if state == "want_portfolio":
            m = PORT_RE.search(line)
            if m:
                pending_port = [m.group(i) for i in range(1, 15)]
                state = "want_year"

        elif state == "want_year":
            m = ANO_RE.match(line)
            if m:
                ano = int(m.group(1))
                if ano not in entries:
                    entries[ano] = {}
                entries[ano]["portfolio"] = pending_port
                pending_port = None
                state = "want_cdi"
            else:
                # Outra linha de portfólio antes do ano? Improvável, mas trata
                m2 = PORT_RE.search(line)
                if m2:
                    pending_port = [m2.group(i) for i in range(1, 15)]

        elif state == "want_cdi":
            m = CDI_RE.search(line)
            if m:
                # Encontrar o ano associado (o último adicionado sem cdi)
                for ano in sorted(entries.keys(), reverse=True):
                    if "cdi" not in entries[ano]:
                        entries[ano]["cdi"] = [m.group(i) for i in range(1, 15)]
                        break
                state = "want_portfolio"

    # Montar estrutura final
    result = []
    for ano in sorted(entries.keys(), reverse=True):
        e = entries[ano]
        port = e.get("portfolio", [])
        cdi = e.get("cdi", [])

        meses_dict = {}
        for idx, mes in enumerate(MESES_ABBR):
            p_val = _num(port[idx]) if idx < len(port) else None
            c_val = _num(cdi[idx]) if idx < len(cdi) else None
            if p_val is not None or c_val is not None:
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
      'jan./26 R$ 293.401,15 R$ 0,00 R$ 0,00 R$ 0,00 R$ 296.706,75 R$ 3.305,60 1,31% 112,83%'
    """
    evolucao = []
    MESES = {
        "jan": "01", "fev": "02", "mar": "03", "abr": "04",
        "mai": "05", "jun": "06", "jul": "07", "ago": "08",
        "set": "09", "out": "10", "nov": "11", "dez": "12",
    }
    pattern = re.compile(
        r"([a-z]{3,4})\.?/(\d{2})\s+"
        r"(-?R\$\s*[\d.,]+)\s+"    # patrimônio inicial
        r"(-?R\$\s*[\d.,]+)\s+"    # movimentações
        r"(-?R\$\s*[\d.,]+)\s+"    # IR
        r"(-?R\$\s*[\d.,]+)\s+"    # IOF
        r"(-?R\$\s*[\d.,]+)\s+"    # patrimônio final
        r"(-?R\$\s*[\d.,]+)\s+"    # ganho financeiro
        r"(-?[\d,]+%?)\s+"         # rent %
        r"(-?[\d,]+%?)",           # %CDI
        re.IGNORECASE
    )
    for m in pattern.finditer(text):
        mes_nome = m.group(1).lower()[:3]
        ano = 2000 + int(m.group(2))
        mes_num = MESES.get(mes_nome, "??")
        evolucao.append({
            "data": f"{ano}-{mes_num}",
            "patrimonio_inicial": _num(m.group(3)),
            "movimentacoes": _num(m.group(4)),
            "ir": _num(m.group(5)),
            "iof": _num(m.group(6)),
            "patrimonio_final": _num(m.group(7)),
            "ganho_financeiro": _num(m.group(8)),
            "rentabilidade_pct": _num(m.group(9)),
            "pct_cdi": _num(m.group(10)),
        })
    return evolucao


# ---------------------------------------------------------------------------
# Extração da composição por estratégia (página 5)
# ---------------------------------------------------------------------------

def _parse_composicao(text: str) -> list:
    """
    Linha típica:
      'Pós Fixado (93,44%) R$ 277.240,24 1,33% 1,33% 13,37% 24,40%'
      'Caixa (0,00%) R$ 0,31 - - - -'
    """
    composicao = []
    pattern = re.compile(
        r"([A-ZÀ-Úa-zà-ú ]+?)\s*\(([\d,]+)%\)\s+"
        r"(R\$\s*[\d.,]+)\s+"
        r"([\d,]+%?|-)\s+([\d,]+%?|-)\s+([\d,]+%?|-)\s+([\d,]+%?|-)"
    )
    for m in pattern.finditer(text):
        composicao.append({
            "estrategia": m.group(1).strip(),
            "saldo_bruto": _num(m.group(3)),
            "pct_alocacao": _num(m.group(2)),
            "rent_mes_pct": _num(m.group(4)),
            "rent_ano_pct": _num(m.group(5)),
            "rent_12m_pct": _num(m.group(6)),
            "rent_24m_pct": _num(m.group(7)),
        })
    return composicao


# ---------------------------------------------------------------------------
# Extração dos ativos (páginas 7+)
# ---------------------------------------------------------------------------

def _parse_ativos(pages_text: str) -> list:
    """
    Extrai ativos da seção POSIÇÃO DETALHADA.

    Linhas de sub-header (estratégia) → tem '-' no lugar de quantidade:
      'Pós Fixado R$ 277.240,24 - 93,44% 1,33% 114,13% ...'

    Linhas de ativo com quantidade numérica:
      'LCA Bancoob - JUN/2027 - 95,00% CDI R$ 37.685,31 35 12,70% ...'

    Linhas com nome quebrado em duas linhas (ex: nome de ativo longo):
      Linha 1: 'LCA BANCO COOPERATIVO SICOOB - JAN/2030 -'
      Linha 2: 'R$ 112.844,22 99 38,03% ...'    ← dados numéricos
      Linha 3: '100,00% CDI'                     ← final do nome (IGNORAR → trailing fragment)

    Tratamento: buffer acumula linha 1, combina com linha 2 → match.
    Linha 3 ('100,00% CDI') é identificada como trailing fragment e descartada.
    """
    ativos = []
    estrategia_atual = None

    # Localizar início da seção
    start = pages_text.find("POSIÇÃO DETALHADA DOS ATIVOS")
    if start == -1:
        start = pages_text.find("POSIÇÃO DETALHADA")
    if start == -1:
        return ativos

    texto = pages_text[start:]
    end = texto.find("MOVIMENTAÇÕES")
    if end != -1:
        texto = texto[:end]

    lines = texto.split("\n")

    # Linhas a ignorar
    IGNORAR = {
        "POSIÇÃO DETALHADA DOS ATIVOS", "POSIÇÃO DETALHADA",
        "PRECIFICAÇÃO DE RENDA FIXA: A MERCADO",
        "MÊS ATUAL ANO 24 MESES",
        "Estratégia Saldo Bruto Qtd. %Aloc. Rent. %CDI Rent. %CDI Rent. %CDI",
    }
    IGNORAR_PREFIXO = ("Aviso!", "Relatório informativo", "Data de referência", "*Aviso")

    # Padrão sub-header (estratégia): sem quantidade (tem '-')
    STRAT_RE = re.compile(
        r"^(.+?)\s+R\$\s*([\d.,]+)\s+-\s+([\d,]+)%\s+"
        r"(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%"
    )

    # Padrão ativo: com quantidade numérica
    ATIVO_RE = re.compile(
        r"^(.+?)\s+R\$\s*([\d.,]+)\s+([\d.,]+)\s+([\d,]+)%\s+"
        r"(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%\s+(-?[\d,]+)%"
    )

    buffer = ""
    skip_next = False  # Para descartar trailing fragments após nome quebrado

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            buffer = ""
            continue  # Não resetar skip_next: trailing fragment pode vir após linha vazia

        # Ignorar cabeçalhos/rodapés
        if line in IGNORAR:
            continue
        if any(line.startswith(p) for p in IGNORAR_PREFIXO):
            continue
        if re.match(r"^\d{2}$", line):  # Número de página isolado
            continue

        # Trailing fragment após nome quebrado: "100,00% CDI" é continuação do nome
        if skip_next:
            skip_next = False
            if not STRAT_RE.match(line) and not ATIVO_RE.match(line):
                # É continuação do nome — APPEND ao último ativo
                if ativos:
                    ativos[-1]["nome_original"] = ativos[-1]["nome_original"] + " " + line
                continue

        candidate = (buffer + " " + line).strip() if buffer else line

        # Tentar match de estratégia (sub-header)
        m = STRAT_RE.match(candidate)
        if m:
            estrategia_atual = m.group(1).strip()
            # Remover prefixo numérico/percentual do nome da estratégia
            estrategia_atual = re.sub(r"^\d[\d,./]*%?\s*", "", estrategia_atual).strip()
            buffer = ""
            skip_next = False
            continue

        # Tentar match de ativo
        m = ATIVO_RE.match(candidate)
        if m:
            nome = m.group(1).strip()
            # Remover prefixo numérico/percentual que veio de buffer anterior
            nome = re.sub(r"^\d[\d,.]*%?\s*[A-Za-z]*\s*", "", nome).strip() if buffer else nome

            # Quantidade: pdfplumber pode usar ponto decimal inglês para grandes
            qtd_str = m.group(3).replace(",", ".")
            try:
                qtd = float(qtd_str)
            except ValueError:
                qtd = None

            ativos.append({
                "nome_original": nome,
                "estrategia": estrategia_atual,
                "saldo_bruto": _num(m.group(2)),
                "quantidade": qtd,
                "pct_alocacao": _num(m.group(4)),
                "rent_mes_pct": _num(m.group(5)),
                "pct_cdi_mes": _num(m.group(6)),
                "rent_ano_pct": _num(m.group(7)),
                "pct_cdi_ano": _num(m.group(8)),
                "rent_24m_pct": _num(m.group(9)),
                "pct_cdi_24m": _num(m.group(10)),
                "rent_12m_pct": None,
                "pct_cdi_12m": None,
            })

            # Se o buffer foi utilizado, a linha seguinte pode ser trailing fragment
            if buffer:
                skip_next = True
            buffer = ""
            continue

        # Nenhum match: acumular no buffer (possível nome quebrado)
        if buffer:
            buffer = candidate
        else:
            buffer = line

    return ativos


# ---------------------------------------------------------------------------
# Extração de movimentações (últimas páginas)
# ---------------------------------------------------------------------------

def _parse_movimentacoes(text: str) -> list:
    """
    Linha típica:
      '13/01/2026 15/01/2026 Devolução Tx de Distr V8 Cash Platinum FIF R$ 0,08 R$ 0,31'
    """
    movs = []
    start = text.find("MOVIMENTAÇÕES DA CONTA")
    if start == -1:
        start = text.find("MOVIMENTAÇÕES")
    if start == -1:
        return movs

    texto = text[start:]

    # dd/mm/yyyy  dd/mm/yyyy  histórico  valor  saldo
    pattern = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"(.+?)\s+"
        r"(-?R\$\s*[\d.,]+)\s+"
        r"(-?R\$\s*[\d.,]+)"
    )
    for m in pattern.finditer(texto):
        movs.append({
            "data_mov": _date_br_to_iso_full(m.group(1)),
            "data_liq": _date_br_to_iso_full(m.group(2)),
            "historico": m.group(3).strip(),
            "valor": _num(m.group(4)),
            "saldo": _num(m.group(5)),
        })
    return movs


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def parse_xp_performance(pdf_path: str) -> dict:
    """
    Extrai dados do relatório XP Performance.

    Args:
        pdf_path: Caminho para o arquivo PDF.

    Returns:
        Dict no schema consolidador-v2.
    """
    logger.info(f"Parsing XP Performance: {os.path.basename(pdf_path)}")

    pages_text = []
    page_objs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
            page_objs.append(page)

    n_pages = len(pages_text)
    logger.debug(f"Total de páginas: {n_pages}")

    # ---- META (capa — página 0) ----
    meta = _parse_capa(pages_text[0] if pages_text else "", pdf_path)

    # ---- RESUMO (página 1) ----
    resumo_text = pages_text[1] if n_pages > 1 else ""
    resumo = _parse_resumo(resumo_text)

    # ---- BENCHMARKS (página 1 — texto) ----
    benchmarks = _parse_benchmarks(resumo_text)

    # ---- ESTATÍSTICA (página 1 — tabelas) ----
    estatistica = _parse_estatistica_from_tables(page_objs[1]) if n_pages > 1 else {}

    # ---- RENTABILIDADE HISTÓRICA (página 2) ----
    rent_text = pages_text[2] if n_pages > 2 else ""
    rentabilidade_hist = _parse_rentabilidade_historica(rent_text)

    # ---- EVOLUÇÃO PATRIMONIAL (página 3) ----
    evol_text = pages_text[3] if n_pages > 3 else ""
    evolucao = _parse_evolucao(evol_text)

    # ---- COMPOSIÇÃO (página 4) ----
    comp_text = pages_text[4] if n_pages > 4 else ""
    composicao = _parse_composicao(comp_text)

    # ---- ATIVOS (página 6 em diante — índice 6) ----
    # Página 5 (índice 5) é "Performance" — redundante, ignorar
    ativos_text = "\n".join(pages_text[6:])
    ativos = _parse_ativos(ativos_text)

    # ---- MOVIMENTAÇÕES (buscar nas últimas páginas) ----
    mid = max(6, n_pages - 4)
    mov_text = "\n".join(pages_text[mid:])
    movimentacoes = _parse_movimentacoes(mov_text)

    result = {
        "$schema": "consolidador-v2",
        "meta": {
            "cliente": meta.get("cliente"),
            "conta": meta.get("conta"),
            "corretora": "XP",
            "segmento": meta.get("segmento"),
            "parceiro": meta.get("parceiro"),
            "data_referencia": meta.get("data_referencia"),
            "tipo_relatorio": "xp_performance",
            "arquivo_origem": meta.get("arquivo_origem"),
        },
        "resumo_carteira": resumo,
        "benchmarks": benchmarks,
        "estatistica_historica": estatistica,
        "composicao_por_estrategia": composicao,
        "rentabilidade_historica_mensal": rentabilidade_hist,
        "evolucao_patrimonial": evolucao,
        "ativos": ativos,
        "movimentacoes": movimentacoes,
    }

    n_ativos = len(ativos)
    patrimonio = resumo.get("patrimonio_total_bruto", 0) or 0
    logger.info(
        f"XP {meta.get('conta')} — {n_ativos} ativos | R$ {patrimonio:,.2f}"
    )

    return result
