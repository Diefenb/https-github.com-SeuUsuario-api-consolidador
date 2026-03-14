"""
historico.py — Reconstrução histórica diária real do portfólio consolidado.

Usa dados reais de mercado por tipo de ativo:
  cdi_pct      → BACEN SGS série 12 (taxa diária real)
  cdi_spread   → BACEN série 12 + spread anual convertido para diário
  ipca_spread  → BACEN série 433 (IPCA mensal) + spread diário
  prefixado    → fórmula exata (1+taxa)^(1/252)
  fundo_cota   → CVM inf_diario NAVs (se CNPJ disponível) ou CDI fallback
  rv_preco     → yfinance preços históricos ou CDI fallback
  sem_projecao → CDI fallback

Algoritmo: inicia do saldo real em data_ancora e reconstrói retroativamente
cada ativo usando as taxas/preços/NAVs reais de cada dia útil.
"""

import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from market_data.cache import SQLiteCache
from market_data.bacen import fetch_cdi_range, fetch_ipca_ultimos, cdi_taxa_diaria
from market_data.cvm_funds import fetch_fund_nav_series
from market_data.rv_prices import fetch_price_series

logger = logging.getLogger(__name__)

_CDI_FALLBACK = 0.0555  # taxa diária % fallback (≈14,75% a.a.)


# ─────────────────────────────────────────────────────────────────────────────
# Calendário de dias úteis
# ─────────────────────────────────────────────────────────────────────────────

def _dias_uteis_entre(data_ini: date, data_fim: date) -> list[date]:
    """Retorna lista de dias úteis (Seg-Sex) entre data_ini e data_fim (inclusive)."""
    try:
        from bizdays import Calendar
        cal = Calendar.load("ANBIMA")
        return [d for d in cal.seq(data_ini, data_fim) if d >= data_ini]
    except Exception:
        pass
    dias = []
    d = data_ini
    while d <= data_fim:
        if d.weekday() < 5:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def _du_no_mes(ano: int, mes: int) -> int:
    """Conta dias úteis (Seg-Sex) em um mês."""
    d = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    return sum(1 for _ in _dias_uteis_entre(d, fim))


# ─────────────────────────────────────────────────────────────────────────────
# Reconstrução por ativo (retrocede da âncora)
# ─────────────────────────────────────────────────────────────────────────────

def _reconstruir_ativo(
    saldo_ancora: float,
    projecao: dict,
    dias_uteis: list[date],          # ASC, o ÚLTIMO elemento = data_ancora
    taxas_cdi: dict[str, float],     # {date_iso: taxa_pct_diaria} BACEN série 12
    ipca_mensal: dict[str, float],   # {YYYY-MM: pct_mensal}
    nav_serie: dict[str, float],     # {date_iso: nav}  — pode ser {}
    price_serie: dict[str, float],   # {date_iso: price} — pode ser {}
) -> dict[str, float]:
    """
    Reconstrói {date_iso: saldo} retrocedendo da data_ancora.
    O último elemento de dias_uteis corresponde a saldo_ancora.
    """
    if not dias_uteis or saldo_ancora <= 0:
        return {}

    tipo = projecao.get("tipo_projecao", "sem_projecao")
    saldo = saldo_ancora
    serie: dict[str, float] = {dias_uteis[-1].isoformat(): saldo}

    for i in range(len(dias_uteis) - 1, 0, -1):
        d_hoje = dias_uteis[i]
        d_ant  = dias_uteis[i - 1]
        iso    = d_hoje.isoformat()

        if tipo == "cdi_pct":
            pct = projecao.get("pct_cdi") or 100.0
            taxa_dia = taxas_cdi.get(iso, _CDI_FALLBACK) / 100.0 * pct / 100.0
            saldo = saldo / (1.0 + taxa_dia)

        elif tipo == "cdi_spread":
            spread_aa = projecao.get("spread_aa") or 0.0
            taxa_cdi  = taxas_cdi.get(iso, _CDI_FALLBACK) / 100.0
            taxa_sprd = (1.0 + spread_aa / 100.0) ** (1.0 / 252.0) - 1.0
            saldo = saldo / (1.0 + taxa_cdi + taxa_sprd)

        elif tipo == "ipca_spread":
            spread_aa = projecao.get("spread_aa") or 0.0
            mes_key   = d_hoje.strftime("%Y-%m")
            ipca_mes  = ipca_mensal.get(mes_key, 0.0) or 0.0
            du_mes    = _du_no_mes(d_hoje.year, d_hoje.month) or 21
            taxa_ipca = (1.0 + ipca_mes / 100.0) ** (1.0 / du_mes) - 1.0
            taxa_sprd = (1.0 + spread_aa / 100.0) ** (1.0 / 252.0) - 1.0
            saldo = saldo / (1.0 + taxa_ipca + taxa_sprd)

        elif tipo == "prefixado":
            taxa_aa = projecao.get("taxa_prefixada_aa") or 0.0
            taxa_dia = (1.0 + taxa_aa / 100.0) ** (1.0 / 252.0) - 1.0
            saldo = saldo / (1.0 + taxa_dia)

        elif tipo == "fundo_cota" and nav_serie:
            nav_hoje = nav_serie.get(iso)
            nav_ant  = nav_serie.get(d_ant.isoformat())
            if nav_hoje and nav_ant and nav_hoje > 0:
                saldo = saldo * (nav_ant / nav_hoje)
            else:
                # CDI fallback para dias sem NAV
                taxa_dia = taxas_cdi.get(iso, _CDI_FALLBACK) / 100.0
                saldo = saldo / (1.0 + taxa_dia)

        elif tipo == "rv_preco" and price_serie:
            p_hoje = price_serie.get(iso)
            p_ant  = price_serie.get(d_ant.isoformat())
            if p_hoje and p_ant and p_hoje > 0:
                saldo = saldo * (p_ant / p_hoje)
            else:
                taxa_dia = taxas_cdi.get(iso, _CDI_FALLBACK) / 100.0
                saldo = saldo / (1.0 + taxa_dia)

        else:
            # sem_projecao ou dado indisponível → CDI fallback
            taxa_dia = taxas_cdi.get(iso, _CDI_FALLBACK) / 100.0
            saldo = saldo / (1.0 + taxa_dia)

        serie[d_ant.isoformat()] = max(0.0, saldo)

    return serie


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────────────────────────────────────

def reconstruct_from_assets(
    dados: dict,
    cache: Optional[SQLiteCache] = None,
) -> list[dict]:
    """
    Reconstrói histórico diário real do portfólio consolidado.

    Args:
        dados: dict do consolidator (dados_consolidados em session state).
               Precisa de: data_referencia, ativos_consolidados (com _projecao),
               evolucao_por_conta (para determinar data_inicio).

    Returns:
        Lista ASC de registros diários:
        [{"data", "pl", "rent_dia_rs", "rent_dia_pct", "rent_acum_pct"}, ...]
    """
    if cache is None:
        cache = SQLiteCache()

    # ── Data âncora e data início ─────────────────────────────────────────────
    data_ancora_str = dados.get("data_referencia", "")
    if not data_ancora_str:
        logger.warning("data_referencia não encontrada")
        return []
    try:
        data_ancora = date.fromisoformat(data_ancora_str)
    except ValueError:
        logger.warning(f"data_referencia inválida: {data_ancora_str}")
        return []

    # data_inicio: mês mais antigo do evolucao_patrimonial
    data_inicio = _determinar_inicio(dados.get("evolucao_por_conta", []), data_ancora)

    logger.info(f"Reconstruindo {data_inicio} → {data_ancora}")

    # ── Ativos com _projecao ──────────────────────────────────────────────────
    ativos = [
        a for a in (dados.get("ativos_consolidados") or [])
        if a.get("_projecao") and (a.get("saldo_bruto") or 0) > 0
    ]

    if not ativos:
        logger.warning("Nenhum ativo enriquecido — usando reconstrução mensal fallback")
        return _fallback_mensal(dados.get("evolucao_por_conta", []))

    # ── Dias úteis do período ─────────────────────────────────────────────────
    dias_uteis = _dias_uteis_entre(data_inicio, data_ancora)
    if len(dias_uteis) < 2:
        return []

    # ── Buscar dados de mercado ───────────────────────────────────────────────
    logger.info(f"Buscando CDI {data_inicio} → {data_ancora}")
    taxas_cdi = fetch_cdi_range(data_inicio, data_ancora, cache=cache)

    logger.info("Buscando IPCA mensal")
    ipca_lista = fetch_ipca_ultimos(n=36, cache=cache)
    ipca_mensal: dict[str, float] = {e["data"]: e["valor_pct"] for e in ipca_lista}

    # NAVs de fundos com CNPJ
    nav_por_cnpj: dict[str, dict[str, float]] = {}
    price_por_ticker: dict[str, dict[str, float]] = {}

    cnpjs_unicos = {
        a["_projecao"]["cnpj"]
        for a in ativos
        if a["_projecao"].get("tipo_projecao") == "fundo_cota"
        and a["_projecao"].get("cnpj")
    }
    for cnpj in cnpjs_unicos:
        logger.info(f"Buscando NAVs CVM para {cnpj}")
        serie = fetch_fund_nav_series(cnpj, data_inicio, data_ancora, cache=cache)
        if serie:
            nav_por_cnpj[cnpj] = serie
            logger.info(f"  → {len(serie)} NAVs disponíveis")

    tickers_unicos = {
        a["_projecao"]["ticker"]
        for a in ativos
        if a["_projecao"].get("tipo_projecao") == "rv_preco"
        and a["_projecao"].get("ticker")
    }
    for ticker in tickers_unicos:
        logger.info(f"Buscando preços para {ticker}")
        serie = fetch_price_series(ticker, data_inicio, data_ancora, cache=cache)
        if serie:
            price_por_ticker[ticker] = serie
            logger.info(f"  → {len(serie)} preços disponíveis")

    # ── Reconstruir cada ativo ────────────────────────────────────────────────
    pl_por_dia: dict[str, float] = defaultdict(float)
    n_ativos = len(ativos)
    n_com_dados_reais = 0

    for ativo in ativos:
        saldo   = ativo.get("saldo_bruto", 0.0) or 0.0
        proj    = ativo.get("_projecao", {})
        tipo    = proj.get("tipo_projecao", "sem_projecao")
        cnpj    = proj.get("cnpj")
        ticker  = proj.get("ticker")

        nav_s   = nav_por_cnpj.get(cnpj, {}) if cnpj else {}
        price_s = price_por_ticker.get(ticker, {}) if ticker else {}

        if tipo in ("fundo_cota",) and nav_s:
            n_com_dados_reais += 1
        elif tipo in ("rv_preco",) and price_s:
            n_com_dados_reais += 1
        elif tipo in ("cdi_pct", "cdi_spread", "ipca_spread", "prefixado"):
            n_com_dados_reais += 1

        serie = _reconstruir_ativo(saldo, proj, dias_uteis, taxas_cdi, ipca_mensal, nav_s, price_s)
        for d_iso, val in serie.items():
            pl_por_dia[d_iso] += val

    logger.info(
        f"Ativos com dados reais: {n_com_dados_reais}/{n_ativos} | "
        f"Dias reconstruídos: {len(pl_por_dia)}"
    )

    # ── Montar série diária ───────────────────────────────────────────────────
    datas_ord  = sorted(pl_por_dia.keys())
    if not datas_ord:
        return []

    pl_base    = pl_por_dia[datas_ord[0]]
    pl_anterior = pl_base
    registros  = []

    for iso in datas_ord:
        pl_hoje       = pl_por_dia[iso]
        rent_dia_rs   = pl_hoje - pl_anterior
        rent_dia_pct  = (pl_hoje / pl_anterior - 1.0) * 100.0 if pl_anterior > 0 else 0.0
        rent_acum_pct = (pl_hoje / pl_base    - 1.0) * 100.0 if pl_base    > 0 else 0.0

        registros.append({
            "data":          iso,
            "pl":            round(pl_hoje,       2),
            "rent_dia_rs":   round(rent_dia_rs,   2),
            "rent_dia_pct":  round(rent_dia_pct,  6),
            "rent_acum_pct": round(rent_acum_pct, 4),
        })
        pl_anterior = pl_hoje

    return registros


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _determinar_inicio(evolucao_por_conta: list[dict], data_ancora: date) -> date:
    """Determina data_inicio como primeiro dia do mês mais antigo do evolucao."""
    meses = []
    for conta in evolucao_por_conta:
        for entry in conta.get("evolucao_patrimonial", []) or []:
            mes = (entry.get("data") or "")[:7]
            if len(mes) == 7:
                meses.append(mes)
    if meses:
        primeiro_mes = sorted(meses)[0]
        try:
            ano, m = int(primeiro_mes[:4]), int(primeiro_mes[5:7])
            return date(ano, m, 1)
        except ValueError:
            pass
    # fallback: 12 meses antes da âncora
    return date(data_ancora.year - 1, data_ancora.month, 1)


def _fallback_mensal(evolucao_por_conta: list[dict]) -> list[dict]:
    """
    Fallback para quando não há _projecao nos ativos.
    Usa interpolação geométrica entre âncoras mensais (método antigo).
    """
    from calendar import monthrange

    mes_inicial: dict[str, float] = defaultdict(float)
    mes_final:   dict[str, float] = defaultdict(float)

    for conta in evolucao_por_conta:
        for entry in conta.get("evolucao_patrimonial", []) or []:
            mes = (entry.get("data") or "")[:7]
            if len(mes) != 7:
                continue
            mes_inicial[mes] += entry.get("patrimonio_inicial") or 0.0
            mes_final[mes]   += entry.get("patrimonio_final")   or 0.0

    if not mes_final:
        return []

    meses      = sorted(mes_final.keys())
    registros: list[dict] = []
    pl_base:    Optional[float] = None
    pl_anterior: Optional[float] = None

    for mes in meses:
        try:
            ano, m = int(mes[:4]), int(mes[5:7])
        except ValueError:
            continue

        p0 = mes_inicial[mes]
        pf = mes_final[mes]
        if p0 <= 0 or pf <= 0:
            continue

        d_ini = date(ano, m, 1)
        d_fim = date(ano, m, monthrange(ano, m)[1])
        dias  = _dias_uteis_entre(d_ini, d_fim)
        n     = len(dias)
        if n == 0:
            continue

        if pl_base is None:
            pl_base = p0
        if pl_anterior is None:
            pl_anterior = p0

        taxa = (pf / p0) ** (1 / n) - 1
        pl = p0
        for i, d in enumerate(dias):
            pl *= (1.0 + taxa)
            if i == n - 1:
                pl = pf
            rent_dia_rs   = pl - pl_anterior
            rent_dia_pct  = (pl / pl_anterior - 1.0) * 100.0 if pl_anterior > 0 else 0.0
            rent_acum_pct = (pl / pl_base    - 1.0) * 100.0 if pl_base    > 0 else 0.0
            registros.append({
                "data":          d.isoformat(),
                "pl":            round(pl, 2),
                "rent_dia_rs":   round(rent_dia_rs, 2),
                "rent_dia_pct":  round(rent_dia_pct, 6),
                "rent_acum_pct": round(rent_acum_pct, 4),
            })
            pl_anterior = pl

    return registros


# ─────────────────────────────────────────────────────────────────────────────
# Compatibilidade com a versão antiga
# ─────────────────────────────────────────────────────────────────────────────

def reconstruct_daily(evolucao_por_conta: list[dict]) -> list[dict]:
    """Alias para compatibilidade — usa fallback mensal."""
    return _fallback_mensal(evolucao_por_conta)
