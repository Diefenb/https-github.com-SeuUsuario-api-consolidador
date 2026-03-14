"""
projector.py — Projeção pro-rata-die de posições a partir da âncora.

Recebe posições enriquecidas (com _projecao) e dados de mercado,
retorna posições com saldo_projetado e variacao_pct estimados.

IMPORTANTE: todos os valores projetados são ESTIMATIVAS e devem ser
exibidos com o aviso adequado na UI.
"""

import logging
from datetime import date, timedelta
from typing import Optional

from market_data.cache import SQLiteCache
from market_data.bacen import fetch_cdi_range, fetch_ipca_ultimos, cdi_taxa_diaria
from market_data.cvm_funds import fetch_fund_nav
from market_data.rv_prices import fetch_price_pair

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Calendário de dias úteis (aproximado — sem feriados específicos)
# ─────────────────────────────────────────────────────────────────────────────

def _dias_uteis_entre(data_ini: date, data_fim: date) -> list[date]:
    """
    Retorna lista de dias úteis (Seg-Sex) entre data_ini (exclusive) e data_fim (inclusive).
    Tenta usar bizdays com calendário ANBIMA; fallback: apenas Seg-Sex.
    """
    try:
        from bizdays import Calendar
        cal = Calendar.load("ANBIMA")
        seq = cal.seq(data_ini, data_fim)
        # seq inclui data_ini — remover se necessário
        return [d for d in seq if d > data_ini]
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"bizdays falhou, usando Seg-Sex: {e}")

    # Fallback: Seg-Sex sem feriados
    dias = []
    d = data_ini + timedelta(days=1)
    while d <= data_fim:
        if d.weekday() < 5:
            dias.append(d)
        d += timedelta(days=1)
    return dias


def _count_dias_uteis(data_ini: date, data_fim: date) -> int:
    return len(_dias_uteis_entre(data_ini, data_fim))


# ─────────────────────────────────────────────────────────────────────────────
# Fórmulas de projeção
# ─────────────────────────────────────────────────────────────────────────────

def _projetar_cdi_pct(
    saldo_ancora: float,
    data_ancora: date,
    data_hoje: date,
    pct_cdi: float,
    taxas_cdi: dict[str, float],
) -> float:
    """
    Projeção CDI percentual.
    pct_cdi: ex. 115.0 para 115% do CDI.
    taxas_cdi: {data_iso: taxa_aa_pct}
    """
    fator = 1.0
    dias = _dias_uteis_entre(data_ancora, data_hoje)

    for d in dias:
        taxa_aa = taxas_cdi.get(d.isoformat())
        if taxa_aa is None:
            # Usar taxa mais recente disponível como aproximação
            datas_disponiveis = sorted(taxas_cdi.keys())
            if datas_disponiveis:
                taxa_aa = taxas_cdi[datas_disponiveis[-1]]
            else:
                # Fallback: 0.0555% ao dia ≈ 14.75% a.a. (SELIC aproximada)
                taxa_aa = 0.0555
                logger.warning(f"CDI nao disponivel para {d}, usando fallback {taxa_aa}%")

        # taxa_aa é a taxa DIÁRIA em % (série 12 BACEN)
        daily_cdi = cdi_taxa_diaria(taxa_aa)
        fator_dia = 1.0 + daily_cdi * (pct_cdi / 100.0)
        fator *= fator_dia

    return saldo_ancora * fator


def _projetar_cdi_spread(
    saldo_ancora: float,
    data_ancora: date,
    data_hoje: date,
    spread_aa: float,
    taxas_cdi: dict[str, float],
) -> float:
    """
    Projeção CDI + spread (ex: CDI + 0,50%).
    """
    fator = 1.0
    dias = _dias_uteis_entre(data_ancora, data_hoje)

    for d in dias:
        # taxa_aa é a taxa DIÁRIA em % (série 12 BACEN)
        taxa_aa = taxas_cdi.get(d.isoformat(), 0.0555)
        daily_cdi = cdi_taxa_diaria(taxa_aa)
        daily_spread = (1 + spread_aa / 100) ** (1 / 252) - 1
        fator *= 1.0 + daily_cdi + daily_spread

    return saldo_ancora * fator


def _projetar_ipca_spread(
    saldo_ancora: float,
    data_ancora: date,
    data_hoje: date,
    spread_aa: float,
    ipca_mensal: list[dict],
) -> float:
    """
    Projeção IPCA + spread.
    ipca_mensal: [{"data": "YYYY-MM", "valor_pct": 0.16}, ...]
    """
    dias_uteis = _count_dias_uteis(data_ancora, data_hoje)
    if dias_uteis == 0:
        return saldo_ancora

    # Fator IPCA: calcular a partir dos meses cobertos
    fator_ipca = _calcular_fator_ipca(data_ancora, data_hoje, ipca_mensal)

    # Fator spread: pro-rata em dias úteis
    fator_spread = (1 + spread_aa / 100) ** (dias_uteis / 252)

    return saldo_ancora * fator_ipca * fator_spread


def _calcular_fator_ipca(
    data_ancora: date,
    data_hoje: date,
    ipca_mensal: list[dict],
) -> float:
    """Calcula o fator IPCA acumulado entre duas datas usando dados mensais."""
    if not ipca_mensal:
        return 1.0

    # Converter para dict {YYYY-MM: valor_pct}
    ipca_dict: dict[str, float] = {}
    for entry in ipca_mensal:
        mes = entry.get("data", "")[:7]
        val = entry.get("valor_pct", 0.0)
        if mes:
            ipca_dict[mes] = val

    fator = 1.0
    d = date(data_ancora.year, data_ancora.month, 1)

    while d <= date(data_hoje.year, data_hoje.month, 1):
        mes_key = d.strftime("%Y-%m")
        ipca_mes = ipca_dict.get(mes_key)

        if ipca_mes is not None:
            # Determinar a fração do mês que está no período
            # Mes completo → usar 100%; meses parciais → pro-rata por dias corridos
            import calendar
            dias_no_mes = calendar.monthrange(d.year, d.month)[1]

            if d.year == data_ancora.year and d.month == data_ancora.month:
                # Primeiro mês: fração do mês restante
                dia_inicio = data_ancora.day
                dias_restantes = dias_no_mes - dia_inicio
                fracao = dias_restantes / dias_no_mes
            elif d.year == data_hoje.year and d.month == data_hoje.month:
                # Último mês: fração do mês decorrida
                fracao = data_hoje.day / dias_no_mes
            else:
                # Mês completo
                fracao = 1.0

            fator *= (1 + ipca_mes / 100) ** fracao
        else:
            # Mês sem dado: usar último IPCA disponível como proxy
            if ipca_dict:
                ultimo = ipca_dict[max(ipca_dict.keys())]
                fator *= (1 + ultimo / 100) ** (1 / 12)

        # Avançar para o próximo mês
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)

    return fator


def _projetar_prefixado(
    saldo_ancora: float,
    data_ancora: date,
    data_hoje: date,
    taxa_aa: float,
) -> float:
    """Projeção prefixada simples."""
    dias_uteis = _count_dias_uteis(data_ancora, data_hoje)
    if dias_uteis == 0:
        return saldo_ancora
    fator = (1 + taxa_aa / 100) ** (dias_uteis / 252)
    return saldo_ancora * fator


def _projetar_fundo(
    saldo_ancora: float,
    cota_ancora: float,
    cota_hoje: float,
) -> float:
    """Projeção por cota de fundo."""
    if cota_ancora <= 0:
        return saldo_ancora
    cotas_possuidas = saldo_ancora / cota_ancora
    return cotas_possuidas * cota_hoje


def _projetar_rv(
    saldo_ancora: float,
    preco_ancora: float,
    preco_hoje: float,
) -> float:
    """Projeção por preço de ativo de renda variável."""
    if preco_ancora <= 0:
        return saldo_ancora
    qtd = saldo_ancora / preco_ancora
    return qtd * preco_hoje


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────────────────────────────────────

def project_portfolio(
    relatorio: dict,
    data_hoje: Optional[date] = None,
    cache: Optional[SQLiteCache] = None,
) -> dict:
    """
    Projeta todos os ativos de um relatório para D0.

    Args:
        relatorio: JSON canônico com ativos enriquecidos (campo _projecao).
        data_hoje: Data alvo da projeção (padrão: hoje).
        cache: Cache SQLite compartilhado.

    Returns:
        Dict com os mesmos dados + campo 'projecao_d0' contendo:
            - saldo_projetado por ativo
            - variacao_pct por ativo
            - pl_estimado_total
            - data_ancora, data_projecao, dias_uteis_projetados
            - cobertura: % de ativos com projeção
    """
    if data_hoje is None:
        data_hoje = date.today()
    if cache is None:
        cache = SQLiteCache()

    data_ancora_str = relatorio.get("meta", {}).get("data_referencia", "")
    if not data_ancora_str:
        return _sem_projecao(relatorio, "data_referencia não encontrada")

    try:
        data_ancora = date.fromisoformat(data_ancora_str)
    except ValueError:
        return _sem_projecao(relatorio, f"data_referencia inválida: {data_ancora_str}")

    if data_ancora >= data_hoje:
        return _sem_projecao(relatorio, "data_ancora >= data_hoje — sem projeção necessária")

    dias_uteis = _count_dias_uteis(data_ancora, data_hoje)
    logger.info(f"Projetando {len(relatorio.get('ativos', []))} ativos | âncora {data_ancora} → {data_hoje} ({dias_uteis} du)")

    # Carregar dados de mercado uma vez
    taxas_cdi = fetch_cdi_range(data_ancora, data_hoje, cache=cache)
    ipca_mensal = fetch_ipca_ultimos(cache=cache)

    ativos_originais = relatorio.get("ativos", [])
    ativos_projetados = []
    pl_estimado = 0.0
    pl_ancora = 0.0
    n_com_projecao = 0
    n_sem_projecao = 0

    for ativo in ativos_originais:
        saldo_ancora = ativo.get("saldo_bruto", 0.0) or 0.0
        pl_ancora += saldo_ancora
        projecao_meta = ativo.get("_projecao", {})
        tipo = projecao_meta.get("tipo_projecao", "sem_projecao")

        saldo_proj = None
        metodo = tipo
        detalhe = ""

        try:
            if tipo == "cdi_pct":
                pct_cdi = projecao_meta.get("pct_cdi") or 100.0
                saldo_proj = _projetar_cdi_pct(saldo_ancora, data_ancora, data_hoje, pct_cdi, taxas_cdi)
                detalhe = f"{pct_cdi:.0f}% CDI"

            elif tipo == "cdi_spread":
                spread = projecao_meta.get("spread_aa") or 0.0
                saldo_proj = _projetar_cdi_spread(saldo_ancora, data_ancora, data_hoje, spread, taxas_cdi)
                detalhe = f"CDI + {spread:.2f}%"

            elif tipo == "ipca_spread":
                spread = projecao_meta.get("spread_aa") or 0.0
                saldo_proj = _projetar_ipca_spread(saldo_ancora, data_ancora, data_hoje, spread, ipca_mensal)
                detalhe = f"IPCA + {spread:.2f}%"

            elif tipo == "prefixado":
                taxa = projecao_meta.get("taxa_prefixada_aa") or 0.0
                saldo_proj = _projetar_prefixado(saldo_ancora, data_ancora, data_hoje, taxa)
                detalhe = f"{taxa:.2f}% a.a."

            elif tipo == "fundo_cota":
                cnpj = projecao_meta.get("cnpj")
                if cnpj:
                    cota_anc, cota_hj = fetch_fund_nav(cnpj, data_ancora, data_hoje, cache=cache)
                    if cota_anc and cota_hj:
                        saldo_proj = _projetar_fundo(saldo_ancora, cota_anc, cota_hj)
                        detalhe = f"cota {cota_hj:.6f}"
                    else:
                        detalhe = "cota não disponível"
                else:
                    detalhe = "CNPJ não mapeado"

            elif tipo == "rv_preco":
                ticker = projecao_meta.get("ticker")
                if ticker:
                    preco_anc, preco_hj = fetch_price_pair(ticker, data_ancora, data_hoje, cache=cache)
                    if preco_anc and preco_hj:
                        saldo_proj = _projetar_rv(saldo_ancora, preco_anc, preco_hj)
                        detalhe = f"{ticker} R$ {preco_hj:.2f}"
                    else:
                        detalhe = "preço não disponível"

        except Exception as e:
            logger.warning(f"Erro ao projetar '{ativo.get('nome_original', '')}': {e}")
            saldo_proj = None

        if saldo_proj is not None and saldo_proj > 0:
            variacao_rs = saldo_proj - saldo_ancora
            variacao_pct = (saldo_proj / saldo_ancora - 1) * 100 if saldo_ancora > 0 else 0.0
            n_com_projecao += 1
            pl_estimado += saldo_proj
        else:
            variacao_rs = None
            variacao_pct = None
            n_sem_projecao += 1
            pl_estimado += saldo_ancora  # usar âncora como fallback

        ativo_proj = dict(ativo)
        ativo_proj["_proj_resultado"] = {
            "saldo_projetado": round(saldo_proj, 2) if saldo_proj is not None else None,
            "variacao_rs": round(variacao_rs, 2) if variacao_rs is not None else None,
            "variacao_pct": round(variacao_pct, 4) if variacao_pct is not None else None,
            "metodo": metodo,
            "detalhe": detalhe,
            "confianca": projecao_meta.get("confianca", "nenhuma"),
        }
        ativos_projetados.append(ativo_proj)

    variacao_total = pl_estimado - pl_ancora
    variacao_total_pct = (pl_estimado / pl_ancora - 1) * 100 if pl_ancora > 0 else 0.0

    resultado = dict(relatorio)
    resultado["ativos"] = ativos_projetados
    resultado["projecao_d0"] = {
        "data_ancora": data_ancora.isoformat(),
        "data_projecao": data_hoje.isoformat(),
        "dias_uteis_projetados": dias_uteis,
        "pl_ancora": round(pl_ancora, 2),
        "pl_estimado": round(pl_estimado, 2),
        "variacao_rs": round(variacao_total, 2),
        "variacao_pct": round(variacao_total_pct, 4),
        "n_ativos_com_projecao": n_com_projecao,
        "n_ativos_sem_projecao": n_sem_projecao,
        "cobertura_pct": round(n_com_projecao / max(1, len(ativos_originais)) * 100, 1),
        "aviso": "Estimativa — não substitui o relatório oficial da corretora",
    }

    return resultado


def _sem_projecao(relatorio: dict, motivo: str) -> dict:
    logger.warning(f"Projeção não realizada: {motivo}")
    resultado = dict(relatorio)
    resultado["projecao_d0"] = {
        "erro": motivo,
        "pl_estimado": None,
    }
    return resultado
