"""
historico.py — Reconstrução histórica diária do portfólio consolidado.

Usa os dados mensais de evolucao_patrimonial (âncoras reais do relatório da
corretora) e distribui o rendimento intra-mês via interpolação geométrica,
gerando uma série diária contínua e suave que:

  1. Começa exatamente no patrimonio_inicial do primeiro mês.
  2. Termina exatamente no patrimonio_final de cada mês (âncoras reais).
  3. Suaviza a curva dentro de cada mês usando crescimento geométrico constante
     — equivalente a assumir taxa diária uniforme dentro do mês.

Esta abordagem é honesta: os pontos de ancoragem (mês a mês) são dados reais
da corretora; apenas a forma da curva dentro de cada mês é estimada.

Saída por dia útil:
    data          — ISO date
    pl            — patrimônio estimado (R$)
    rent_dia_rs   — variação absoluta vs. dia anterior (R$)
    rent_dia_pct  — variação percentual vs. dia anterior (%)
    rent_acum_pct — variação acumulada desde o início do período (%)
"""

import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Calendário de dias úteis
# ─────────────────────────────────────────────────────────────────────────────

def _dias_uteis_mes(ano: int, mes: int) -> list[date]:
    """
    Retorna a lista de dias úteis de um mês.
    Tenta usar bizdays/ANBIMA; cai para Seg-Sex sem feriados.
    """
    d_ini = date(ano, mes, 1)
    d_fim = date(ano, mes, monthrange(ano, mes)[1])

    try:
        from bizdays import Calendar
        cal = Calendar.load("ANBIMA")
        return [d for d in cal.seq(d_ini, d_fim) if d >= d_ini]
    except Exception:
        pass

    dias = []
    d = d_ini
    while d <= d_fim:
        if d.weekday() < 5:
            dias.append(d)
        d += timedelta(days=1)
    return dias


# ─────────────────────────────────────────────────────────────────────────────
# Interpolação geométrica
# ─────────────────────────────────────────────────────────────────────────────

def _interpolar_geo(p0: float, pf: float, n: int) -> list[float]:
    """
    Gera n valores diários entre p0 (exclusive) e pf (inclusive)
    usando taxa diária geométrica constante: taxa = (pf/p0)^(1/n) - 1.

    O último ponto é forçado a pf para eliminar erros de ponto flutuante.
    """
    if n <= 0 or p0 <= 0 or pf <= 0:
        return [pf] * max(n, 0)

    taxa = (pf / p0) ** (1 / n) - 1
    pls = []
    pl = p0
    for _ in range(n):
        pl *= 1.0 + taxa
        pls.append(pl)

    if pls:
        pls[-1] = pf  # âncora exata

    return pls


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador principal
# ─────────────────────────────────────────────────────────────────────────────

def reconstruct_daily(evolucao_por_conta: list[dict]) -> list[dict]:
    """
    Reconstrói o histórico diário consolidado a partir de evolucao_por_conta.

    Args:
        evolucao_por_conta: dados["evolucao_por_conta"] do consolidator.
            Cada elemento: {
                "corretora": str,
                "conta": str,
                "evolucao_patrimonial": [
                    {"data": "YYYY-MM", "patrimonio_inicial": float, "patrimonio_final": float, ...}
                ]
            }

    Returns:
        Lista ordenada por data ASC de registros diários:
        [
            {
                "data": "YYYY-MM-DD",
                "pl": float,
                "rent_dia_rs": float,
                "rent_dia_pct": float,   # % vs. dia anterior
                "rent_acum_pct": float,  # % acumulado desde início do período
            },
            ...
        ]
        Retorna [] se não há dados suficientes.
    """
    if not evolucao_por_conta:
        return []

    # ── Consolidar patrimônio por mês (somar todas as contas) ─────────────────
    mes_inicial: dict[str, float] = defaultdict(float)
    mes_final:   dict[str, float] = defaultdict(float)

    for conta in evolucao_por_conta:
        for entry in conta.get("evolucao_patrimonial", []) or []:
            mes = (entry.get("data") or "")[:7]  # "YYYY-MM"
            if len(mes) != 7 or "-" not in mes:
                continue
            mes_inicial[mes] += entry.get("patrimonio_inicial") or 0.0
            mes_final[mes]   += entry.get("patrimonio_final")   or 0.0

    if not mes_final:
        return []

    meses = sorted(mes_final.keys())

    # ── Gerar série diária ────────────────────────────────────────────────────
    registros: list[dict] = []
    pl_base:     Optional[float] = None
    pl_anterior: Optional[float] = None

    for mes in meses:
        try:
            ano, m = int(mes[:4]), int(mes[5:7])
        except ValueError:
            logger.warning(f"Mês inválido ignorado: {mes}")
            continue

        p0 = mes_inicial[mes]
        pf = mes_final[mes]

        if p0 <= 0 or pf <= 0:
            logger.debug(f"Mês {mes} ignorado (p0={p0}, pf={pf})")
            continue

        dias = _dias_uteis_mes(ano, m)
        n    = len(dias)
        if n == 0:
            continue

        # Primeira iteração: definir base de comparação acumulada
        if pl_base is None:
            pl_base = p0
        if pl_anterior is None:
            pl_anterior = p0

        pls_dia = _interpolar_geo(p0, pf, n)

        for i, d in enumerate(dias):
            pl_hoje       = pls_dia[i]
            rent_dia_rs   = pl_hoje - pl_anterior
            rent_dia_pct  = (pl_hoje / pl_anterior - 1.0) * 100.0 if pl_anterior > 0 else 0.0
            rent_acum_pct = (pl_hoje / pl_base    - 1.0) * 100.0 if pl_base    > 0 else 0.0

            registros.append({
                "data":          d.isoformat(),
                "pl":            round(pl_hoje,       2),
                "rent_dia_rs":   round(rent_dia_rs,   2),
                "rent_dia_pct":  round(rent_dia_pct,  6),
                "rent_acum_pct": round(rent_acum_pct, 4),
            })
            pl_anterior = pl_hoje

    if registros:
        logger.info(
            f"Histórico reconstruído: {len(registros)} dias úteis | "
            f"{meses[0]} → {meses[-1]}"
        )

    return registros
