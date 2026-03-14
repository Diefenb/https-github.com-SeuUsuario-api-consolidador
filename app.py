"""
Consolidador de Carteiras — Capital Investimentos
Interface Streamlit — fluxo: Upload → Processar → Dashboard
"""

import os
import sys
import tempfile
import traceback
from collections import defaultdict
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Path dos módulos internos ─────────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "Consolidador_V3", "src")))

from consolidator import consolidate
from importer import import_manual_json
from normalizer import normalize
from parsers import UnknownFormatError, detect_and_parse
from report_generator import generate_report

# ── Módulos de projeção (importação lazy para não bloquear o app) ─────────────
def _import_projecao():
    try:
        from enricher import enrich_portfolio
        from projector import project_portfolio
        return enrich_portfolio, project_portfolio
    except Exception as e:
        return None, None


# =============================================================================
# DESIGN TOKENS
# =============================================================================

_C = {
    "sidebar":       "#0D1B3E",
    "accent":        "#1A56DB",
    "bg":            "#F8FAFC",
    "card":          "#FFFFFF",
    "border":        "#E2E8F0",
    "text":          "#0F172A",
    "text_sub":      "#475569",
    "text_muted":    "#94A3B8",
    "positive":      "#16A34A",
    "negative":      "#DC2626",
    "neutral":       "#64748B",
    "chart_line":    "#1A56DB",
    "chart_fill":    "rgba(26,86,219,0.07)",
    "chart_cdi":     "#94A3B8",
    "chart_grid":    "#F1F5F9",
}

_MESES_ABR = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_MESES_KEY = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"]


# =============================================================================
# CSS
# =============================================================================

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="st-"] {{
    font-family: 'Inter', sans-serif;
    font-variant-numeric: tabular-nums;
}}
.stApp {{ background-color: {_C['bg']}; }}

/* ── Sidebar escura ── */
section[data-testid="stSidebar"] > div:first-child {{
    background-color: {_C['sidebar']};
    border-right: none;
}}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown span,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] div[data-testid="stText"] {{
    color: #CBD5E1 !important;
}}
section[data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,0.10) !important;
    margin: 10px 0;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] button {{
    background: rgba(255,255,255,0.08);
    color: #E2E8F0;
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    width: 100%;
    transition: background 0.15s;
}}
section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {{
    background: rgba(255,255,255,0.15);
    color: #FFFFFF;
    border-color: rgba(255,255,255,0.25);
}}

/* ── Logo ── */
.sidebar-logo {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #FFFFFF;
    line-height: 1.3;
    padding: 6px 0 2px 0;
}}
.sidebar-logo small {{
    display: block;
    font-size: 9px;
    font-weight: 400;
    letter-spacing: 2.8px;
    color: {_C['text_muted']};
    margin-top: 3px;
}}

/* ── Nav items ── */
.nav-item {{
    padding: 9px 12px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    color: #94A3B8;
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    gap: 9px;
    border-left: 3px solid transparent;
}}
.nav-item.active {{
    background: rgba(255,255,255,0.10);
    border-left-color: {_C['accent']};
    color: #FFFFFF;
}}

/* ── Card cliente sidebar ── */
.sidebar-client {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 8px;
    padding: 12px 14px;
    margin: 4px 0;
}}
.sidebar-client .cl-label {{
    font-size: 10px;
    letter-spacing: 1.2px;
    color: {_C['text_muted']};
    text-transform: uppercase;
    margin-bottom: 5px;
}}
.sidebar-client .cl-name {{
    font-size: 13px;
    font-weight: 600;
    color: #E2E8F0;
    margin-bottom: 2px;
}}
.sidebar-client .cl-date {{
    font-size: 11px;
    color: {_C['text_muted']};
}}

/* ── Cards de métrica ── */
.cards-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}}
.metric-card {{
    background: {_C['card']};
    border: 1px solid {_C['border']};
    border-radius: 10px;
    padding: 20px 22px;
    box-shadow: 0 1px 3px rgba(15,23,42,0.05);
}}
.metric-label {{
    font-size: 11px;
    font-weight: 500;
    color: {_C['neutral']};
    text-transform: uppercase;
    letter-spacing: 0.7px;
    margin-bottom: 10px;
}}
.metric-value {{
    font-size: 24px;
    font-weight: 600;
    color: {_C['text']};
    line-height: 1.1;
    margin-bottom: 5px;
}}
.metric-delta {{
    font-size: 12px;
    font-weight: 500;
}}
.metric-delta.positive {{ color: {_C['positive']}; }}
.metric-delta.negative {{ color: {_C['negative']}; }}
.metric-delta.neutral  {{ color: {_C['neutral']}; }}

/* ── Títulos de seção ── */
.section-title {{
    font-size: 13px;
    font-weight: 600;
    color: {_C['text']};
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid {_C['border']};
}}

/* ── Badges ── */
.badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.2px;
    line-height: 1.6;
}}
.badge-xp   {{ background: #DBEAFE; color: #1E40AF; }}
.badge-btg  {{ background: #FEF3C7; color: #92400E; }}
.badge-json {{ background: #F3E8FF; color: #6B21A8; }}
.badge-ok   {{ background: #DCFCE7; color: #166534; }}
.badge-err  {{ background: #FEE2E2; color: #991B1B; }}

/* ── Linha de arquivo ── */
.file-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 14px;
    background: {_C['card']};
    border: 1px solid {_C['border']};
    border-radius: 7px;
    margin-bottom: 6px;
    font-size: 13px;
    color: #374151;
}}
.file-row .fname {{ flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

/* ── Dropzone maior ── */
section[data-testid="stFileUploadDropzone"] {{
    background: {_C['card']};
    border: 2px dashed #CBD5E1;
    border-radius: 10px;
    min-height: 130px;
    transition: all 0.2s ease;
}}
section[data-testid="stFileUploadDropzone"]:hover {{
    border-color: {_C['accent']};
    background: #EFF6FF;
}}

/* ── Botão primário ── */
div[data-testid="stButton"] button[kind="primary"] {{
    background-color: {_C['sidebar']};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    font-size: 14px;
    padding: 0.5rem 1.5rem;
    transition: background 0.2s;
}}
div[data-testid="stButton"] button[kind="primary"]:hover {{
    background-color: {_C['accent']};
}}

/* ── Botão secundário (fora da sidebar) ── */
div[data-testid="stMainBlockContainer"] div[data-testid="stButton"] button[kind="secondary"] {{
    background: transparent;
    color: {_C['sidebar']};
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    font-weight: 500;
    font-size: 14px;
    transition: all 0.2s;
}}
div[data-testid="stMainBlockContainer"] div[data-testid="stButton"] button[kind="secondary"]:hover {{
    background: {_C['bg']};
    border-color: {_C['sidebar']};
}}

/* ── Download button ── */
div[data-testid="stDownloadButton"] button {{
    background-color: {_C['sidebar']} !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    transition: background 0.2s !important;
}}
div[data-testid="stDownloadButton"] button:hover {{
    background-color: {_C['accent']} !important;
}}

/* ── DataFrame ── */
div[data-testid="stDataFrame"] {{
    border: 1px solid {_C['border']};
    border-radius: 8px;
    overflow: hidden;
}}

/* ── Alertas e feedback ── */
div[data-testid="stAlert"] {{ border-radius: 8px; font-size: 14px; }}

/* ── Padding superior ── */
div[data-testid="stAppViewContainer"] > section > div:first-child {{ padding-top: 1.5rem; }}

/* ── Projeção D0 ── */
.proj-aviso {{
    background: #FEF9C3;
    border: 1px solid #FDE047;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
    color: #713F12;
    margin-bottom: 16px;
}}
.proj-ancora {{
    font-size: 12px;
    color: {_C['text_sub']};
    margin-bottom: 8px;
}}
.badge-proj-alta   {{ background: #DCFCE7; color: #166534; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-proj-media  {{ background: #FEF9C3; color: #713F12; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-proj-baixa  {{ background: #FEE2E2; color: #991B1B; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.badge-proj-sem    {{ background: #F1F5F9; color: #475569; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
</style>
"""


# =============================================================================
# FORMATAÇÃO
# =============================================================================

def _brl(v) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v, sign=True) -> str:
    if v is None:
        return "—"
    s = "+" if (v > 0 and sign) else ""
    return f"{s}{v:.2f}%".replace(".", ",")


def _cls(v) -> str:
    if v is None:
        return "neutral"
    return "positive" if v > 0 else ("negative" if v < 0 else "neutral")


# =============================================================================
# SIDEBAR
# =============================================================================

def _sidebar():
    view    = st.session_state.get("view", "upload")
    cliente = st.session_state.get("cliente_nome", "")
    data_r  = st.session_state.get("data_ref", "")

    with st.sidebar:
        st.markdown(
            '<div class="sidebar-logo">CAPITAL<br>INVESTIMENTOS'
            '<small>CONSOLIDADOR INTERNO</small></div>',
            unsafe_allow_html=True,
        )
        st.divider()

        u_cls = "nav-item active" if view == "upload"    else "nav-item"
        d_cls = "nav-item active" if view == "dashboard" else "nav-item"
        st.markdown(
            f'<div class="{u_cls}">&#8679;&nbsp; Upload / Importação</div>'
            f'<div class="{d_cls}">&#9635;&nbsp; Dashboard</div>',
            unsafe_allow_html=True,
        )

        if view == "dashboard" and cliente:
            st.divider()
            st.markdown(
                f'<div class="sidebar-client">'
                f'<div class="cl-label">Cliente</div>'
                f'<div class="cl-name">{cliente}</div>'
                f'<div class="cl-date">{data_r}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")
            if st.button("&#8617; Nova Importação", use_container_width=True):
                _reset_state()
                st.rerun()


# =============================================================================
# CARDS DE MÉTRICA
# =============================================================================

def _cards_dashboard(dados):
    contas = dados.get("contas", [])
    total  = dados.get("patrimonio_total_consolidado", 0) or 0
    n      = len(contas)

    # Média ponderada por patrimônio
    peso_total = sum(c.get("patrimonio_bruto") or 0 for c in contas)
    if peso_total > 0:
        rent_mes = sum((c.get("rentabilidade_mes_pct") or 0) * (c.get("patrimonio_bruto") or 0) for c in contas) / peso_total
        pct_cdi  = sum((c.get("pct_cdi_mes") or 0) * (c.get("patrimonio_bruto") or 0) for c in contas) / peso_total
    else:
        rent_mes = pct_cdi = None

    rc = _cls(rent_mes)
    cc = _cls(pct_cdi)
    cdi_txt = f"{pct_cdi:.0f}% do CDI" if pct_cdi is not None else "—"

    st.markdown(f"""
    <div class="cards-grid">
      <div class="metric-card">
        <div class="metric-label">AuM Total Consolidado</div>
        <div class="metric-value">{_brl(total)}</div>
        <div class="metric-delta neutral">{n} conta(s)</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Rentabilidade Bruta do Mês</div>
        <div class="metric-value {rc}">{_pct(rent_mes)}</div>
        <div class="metric-delta neutral">média pond. por PL</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">% CDI no Mês</div>
        <div class="metric-value {cc}">{cdi_txt}</div>
        <div class="metric-delta neutral">média pond. por PL</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Contas Consolidadas</div>
        <div class="metric-value">{n}</div>
        <div class="metric-delta neutral">XP + BTG</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def _cards_upload(uploaded_files, historico, erros):
    n_arq  = len(uploaded_files) if uploaded_files else 0
    n_err  = len(erros)
    ultima = historico[-1]["horario"] if historico else "—"

    corretoras = set()
    for f in (uploaded_files or []):
        n = f.name.lower()
        if "relatorio" in n or "btg" in n:
            corretoras.add("BTG")
        elif "xperformance" in n or "xp" in n:
            corretoras.add("XP")
    n_corr = len(corretoras) if n_arq else 0

    err_cor = _C["negative"] if n_err else _C["positive"]
    err_txt = "sem erros" if not n_err else "atenção necessária"

    st.markdown(f"""
    <div class="cards-grid">
      <div class="metric-card">
        <div class="metric-label">Arquivos Carregados</div>
        <div class="metric-value">{n_arq if n_arq else "—"}</div>
        <div class="metric-delta neutral">prontos para processar</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Corretoras Detectadas</div>
        <div class="metric-value">{n_corr if n_arq else "—"}</div>
        <div class="metric-delta neutral">por nome de arquivo</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Última Consolidação</div>
        <div class="metric-value" style="font-size:20px">{ultima}</div>
        <div class="metric-delta neutral">nesta sessão</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Erros</div>
        <div class="metric-value" style="color:{err_cor}">{n_err}</div>
        <div class="metric-delta neutral">{err_txt}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# =============================================================================
# GRÁFICOS
# =============================================================================

def _chart_evolucao(dados):
    """Gráfico de área: evolução patrimonial consolidada (soma das contas por mês)."""
    evolucao_por_conta = dados.get("evolucao_por_conta", []) or []

    soma = defaultdict(float)
    for bloco in evolucao_por_conta:
        for entry in bloco.get("evolucao_patrimonial", []) or []:
            data = entry.get("data")
            pf   = entry.get("patrimonio_final")
            if data and pf is not None:
                soma[data] += pf

    if len(soma) < 2:
        st.info("Dados insuficientes para o gráfico de evolução (mínimo 2 meses).")
        return

    datas   = sorted(soma.keys())
    valores = [soma[d] for d in datas]

    def _lbl(d):
        try:
            a, m = d.split("-")
            return f"{_MESES_ABR[int(m) - 1]}/{a[2:]}"
        except Exception:
            return d

    labels = [_lbl(d) for d in datas]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels,
        y=valores,
        mode="lines",
        name="Carteira",
        line=dict(color=_C["chart_line"], width=2.5),
        fill="tozeroy",
        fillcolor=_C["chart_fill"],
        hovertemplate="%{x}<br><b>%{text}</b><extra></extra>",
        text=[_brl(v) for v in valores],
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=False, tickfont=dict(size=11, color=_C["neutral"])),
        yaxis=dict(
            showgrid=True,
            gridcolor=_C["chart_grid"],
            tickfont=dict(size=11, color=_C["neutral"]),
            tickformat=",.0f",
            tickprefix="R$ ",
        ),
        showlegend=False,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _chart_rent_mensal(dados):
    """Gráfico de barras: rentabilidade mensal — últimos 6 meses, média entre contas."""
    rent_por_conta = dados.get("rentabilidade_por_conta", []) or []

    # Agrega por (ano, mes_key) → lista de valores
    agg = defaultdict(list)
    for bloco in rent_por_conta:
        for ano_bloco in bloco.get("rentabilidade_historica_mensal", []) or []:
            ano   = ano_bloco.get("ano")
            meses = ano_bloco.get("meses") or {}
            for mk, mv in meses.items():
                if mv and mv.get("portfolio_pct") is not None:
                    agg[(ano, mk)].append(mv["portfolio_pct"])

    if not agg:
        st.info("Sem histórico mensal disponível.")
        return

    # Ordena e pega últimos 6
    todos    = sorted(agg.keys(), key=lambda x: (x[0], _MESES_KEY.index(x[1]) if x[1] in _MESES_KEY else 99))
    ultimos  = todos[-6:]
    labels   = [f"{_MESES_ABR[_MESES_KEY.index(mk)] if mk in _MESES_KEY else mk}/{str(an)[2:]}" for an, mk in ultimos]
    valores  = [round(sum(agg[k]) / len(agg[k]), 2) for k in ultimos]
    cores    = [_C["positive"] if v >= 0 else _C["negative"] for v in valores]
    textos   = [_pct(v) for v in valores]

    fig = go.Figure(go.Bar(
        x=labels,
        y=valores,
        marker_color=cores,
        text=textos,
        textposition="outside",
        textfont=dict(size=11, color="#374151"),
        hovertemplate="%{x}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=24, b=0),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=False, tickfont=dict(size=11, color=_C["neutral"])),
        yaxis=dict(showgrid=False, visible=False),
        showlegend=False,
        bargap=0.4,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# =============================================================================
# TABELAS
# =============================================================================

def _tabela_contas(dados):
    contas = dados.get("contas", [])
    if not contas:
        return
    total = dados.get("patrimonio_total_consolidado", 0) or 1

    rows = []
    for c in sorted(contas, key=lambda x: x.get("patrimonio_bruto") or 0, reverse=True):
        pat = c.get("patrimonio_bruto") or 0
        rows.append({
            "Corretora":  c.get("corretora", "—"),
            "Conta":      str(c.get("conta", "—")),
            "Patrimônio": pat,
            "% Carteira": round(pat / total * 100, 1) if total else None,
            "Rent. Mês":  c.get("rentabilidade_mes_pct"),
            "% CDI Mês":  c.get("pct_cdi_mes"),
            "Ganho Mês":  c.get("ganho_mes_rs"),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Patrimônio": st.column_config.NumberColumn("Patrimônio (R$)", format="R$ %.2f"),
            "% Carteira": st.column_config.NumberColumn("% Carteira",     format="%.1f%%"),
            "Rent. Mês":  st.column_config.NumberColumn("Rent. Mês (%)",  format="%.2f%%"),
            "% CDI Mês":  st.column_config.NumberColumn("% CDI",          format="%.0f%%"),
            "Ganho Mês":  st.column_config.NumberColumn("Ganho Mês (R$)", format="R$ %.2f"),
        },
    )


def _tabela_alocacao(dados):
    comp  = dados.get("alocacao_por_estrategia", []) or []
    total = dados.get("patrimonio_total_consolidado", 0) or 1

    if not comp:
        return

    rows = []
    for item in comp:
        saldo = item.get("saldo_bruto") or 0
        rows.append({
            "Estratégia": item.get("estrategia", "—"),
            "Saldo (R$)": saldo,
            "% Carteira": round(saldo / total * 100, 1),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Saldo (R$)": st.column_config.NumberColumn("Saldo (R$)", format="R$ %.2f"),
            "% Carteira": st.column_config.NumberColumn("% Carteira", format="%.1f%%"),
        },
    )


# =============================================================================
# PROCESSAMENTO
# =============================================================================

def _processar_arquivos(uploaded_files):
    relatorios = []
    historico  = []
    erros      = []
    n          = len(uploaded_files)

    progress = st.progress(0, text="Iniciando...")
    for i, file in enumerate(uploaded_files):
        progress.progress(i / n, text=f"Processando {file.name}…")
        tmp_path = None
        try:
            ext = os.path.splitext(file.name)[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(file.getbuffer())
                tmp_path = tmp.name

            if ext == ".json":
                parsed = import_manual_json(tmp_path)
            elif ext == ".pdf":
                parsed = detect_and_parse(tmp_path)
            else:
                raise ValueError(f"Formato não suportado: {ext}")

            norm = normalize(parsed)
            relatorios.append(norm)

            meta = norm.get("meta", {})
            historico.append({
                "horario":   datetime.now().strftime("%H:%M"),
                "arquivo":   file.name,
                "corretora": meta.get("corretora", "—"),
                "conta":     str(meta.get("conta", "—")),
                "ativos":    len(norm.get("ativos", [])),
                "patrimonio": norm.get("resumo_carteira", {}).get("patrimonio_total_bruto"),
                "status":    "ok",
            })

        except Exception as e:
            erros.append((file.name, str(e)))
            historico.append({
                "horario": datetime.now().strftime("%H:%M"),
                "arquivo": file.name, "corretora": "—", "conta": "—",
                "ativos": 0, "patrimonio": None, "status": "erro",
            })
            traceback.print_exc()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    progress.progress(1.0, text="Concluído.")
    return relatorios, historico, erros


# =============================================================================
# VIEW: UPLOAD
# =============================================================================

def _view_upload():
    st.title("Upload / Importação")
    st.markdown(
        "<p style='font-size:14px;color:#475569;margin-top:-12px'>"
        "Carregue os relatórios PDF (XP / BTG) ou arquivos JSON.</p>",
        unsafe_allow_html=True,
    )

    historico  = st.session_state.get("historico") or []
    erros_sess = st.session_state.get("erros_sessao") or []

    # ── Inputs ──────────────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    with col1:
        cliente_nome = st.text_input(
            "Nome do Cliente",
            key="input_cliente",
            placeholder="Ex: João da Silva",
        )
    with col2:
        data_ref = st.text_input(
            "Mês/Ano de Referência",
            key="input_data",
            value=st.session_state.get("data_ref") or datetime.now().strftime("%m/%Y"),
        )

    # ── Dropzone ─────────────────────────────────────────────────────────────
    uploaded_files = st.file_uploader(
        "Arraste e solte os arquivos",
        type=["pdf", "json"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    # Lista de arquivos com badge de corretora
    if uploaded_files:
        st.markdown("**Arquivos prontos para processamento:**")
        for f in uploaded_files:
            n = f.name.lower()
            if "relatorio" in n or "btg" in n:
                badge = "<span class='badge badge-btg'>BTG</span>"
            elif "xperformance" in n or "xp" in n:
                badge = "<span class='badge badge-xp'>XP</span>"
            elif n.endswith(".json"):
                badge = "<span class='badge badge-json'>JSON</span>"
            else:
                badge = "<span class='badge badge-btg'>PDF</span>"
            st.markdown(
                f"<div class='file-row'>"
                f"<span class='fname'>{f.name}</span>{badge}"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown("")

    # ── Cards de status ───────────────────────────────────────────────────────
    _cards_upload(uploaded_files, historico, erros_sess)

    # ── Botão de ação ─────────────────────────────────────────────────────────
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        processar = st.button("Consolidar Carteiras", type="primary", use_container_width=True)

    if processar:
        if not uploaded_files:
            st.error("Carregue ao menos um arquivo PDF antes de continuar.")
        elif not (cliente_nome or "").strip():
            st.warning("Insira o nome do cliente.")
        else:
            with st.spinner("Processando arquivos…"):
                relatorios, hist_novo, erros = _processar_arquivos(uploaded_files)

            st.session_state["cliente_nome"] = (cliente_nome or "").strip()
            st.session_state["data_ref"]     = data_ref
            st.session_state["erros_sessao"] = erros
            st.session_state["historico"]    = (st.session_state.get("historico") or []) + hist_novo

            for nome_arq, err in erros:
                st.error(f"Erro em **{nome_arq}**: {err}")

            if relatorios:
                try:
                    dados = consolidate(
                        reports=relatorios,
                        cliente=(cliente_nome or "").strip(),
                        data_referencia=data_ref,
                    )

                    output_dir = os.path.join(os.path.dirname(__file__), "output", "relatorios")
                    os.makedirs(output_dir, exist_ok=True)
                    excel_path = os.path.join(
                        output_dir,
                        f"Relatorio_{(cliente_nome or '').strip().replace(' ', '_')}.xlsx",
                    )
                    generate_report(dados, excel_path)
                    with open(excel_path, "rb") as f:
                        excel_bytes = f.read()

                    st.session_state["dados_consolidados"] = dados
                    st.session_state["relatorios_individuais"] = relatorios
                    st.session_state["excel_bytes"]        = excel_bytes
                    st.session_state["excel_filename"]     = (
                        f"Consolidado_{(cliente_nome or '').strip().replace(' ', '_')}.xlsx"
                    )
                    st.session_state["view"] = "dashboard"
                    st.rerun()

                except Exception as e:
                    st.error(f"Erro na consolidação: {e}")
                    traceback.print_exc()

    # ── Histórico da sessão ───────────────────────────────────────────────────
    if historico:
        st.divider()
        st.markdown("<div class='section-title'>Histórico desta sessão</div>", unsafe_allow_html=True)
        rows = []
        for h in reversed(historico):
            rows.append({
                "Horário":    h["horario"],
                "Arquivo":    h["arquivo"],
                "Corretora":  h["corretora"],
                "Conta":      h["conta"],
                "Ativos":     h["ativos"],
                "Patrimônio": h.get("patrimonio"),
                "Status":     "OK" if h["status"] == "ok" else "Erro",
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Patrimônio": st.column_config.NumberColumn("Patrimônio (R$)", format="R$ %.2f"),
            },
        )


# =============================================================================
# VIEW: POSIÇÕES D0 (Projeção Pro-Rata-Die)
# =============================================================================

def _posicoes_d0_section(relatorios: list[dict]):
    """
    Seção expansível no dashboard que exibe posições projetadas para D0.
    Recebe a lista de relatórios normalizados (pré-consolidação).
    """
    with st.expander("Posições Estimadas D0 (Pro-Rata-Die)", expanded=False):
        st.markdown(
            '<div class="proj-aviso">'
            '<b>Estimativa</b> — valores projetados com base em taxas de mercado. '
            'Não substitui o relatório oficial da corretora. '
            'Valores brutos (sem considerar IR/IOF no resgate).'
            '</div>',
            unsafe_allow_html=True,
        )

        enrich_fn, project_fn = _import_projecao()
        if enrich_fn is None:
            st.warning("Módulos de projeção não disponíveis. Verifique a instalação de `rapidfuzz`, `bizdays` e `yfinance`.")
            return

        data_hoje = date.today()
        todos_projetados = []

        for rel in relatorios:
            data_ancora_str = rel.get("meta", {}).get("data_referencia", "")
            if not data_ancora_str:
                continue

            with st.spinner(f"Projetando {rel.get('meta', {}).get('corretora', '?')} {rel.get('meta', {}).get('conta', '?')}…"):
                try:
                    enriched = enrich_fn(rel, use_cvm=True)
                    projected = project_fn(enriched, data_hoje=data_hoje)
                    todos_projetados.append(projected)
                except Exception as e:
                    st.warning(f"Erro ao projetar conta {rel.get('meta', {}).get('conta', '?')}: {e}")
                    continue

        if not todos_projetados:
            st.info("Nenhuma projeção disponível.")
            return

        # Agregar PL total
        pl_ancora_total = sum(p.get("projecao_d0", {}).get("pl_ancora", 0) or 0 for p in todos_projetados)
        pl_estimado_total = sum(p.get("projecao_d0", {}).get("pl_estimado", 0) or 0 for p in todos_projetados)
        var_rs = pl_estimado_total - pl_ancora_total
        var_pct = (pl_estimado_total / pl_ancora_total - 1) * 100 if pl_ancora_total > 0 else 0.0

        # Cards de resumo
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("PL Estimado Hoje", _brl(pl_estimado_total))
        with c2:
            st.metric("PL Âncora (último rel.)", _brl(pl_ancora_total))
        with c3:
            sinal = "+" if var_rs >= 0 else ""
            st.metric("Variação (R$)", f"{sinal}{_brl(var_rs).replace('R$ ', '')}", delta=None)
        with c4:
            sinal = "+" if var_pct >= 0 else ""
            st.metric("Variação (%)", f"{sinal}{var_pct:.2f}%".replace(".", ","))

        # Data da âncora mais antiga
        datas_ancora = [
            p.get("projecao_d0", {}).get("data_ancora", "")
            for p in todos_projetados
            if p.get("projecao_d0", {}).get("data_ancora")
        ]
        if datas_ancora:
            data_ancora_ref = min(datas_ancora)
            try:
                d_anc = date.fromisoformat(data_ancora_ref)
                du = sum(p.get("projecao_d0", {}).get("dias_uteis_projetados", 0) or 0 for p in todos_projetados)
                du_med = du // len(todos_projetados) if todos_projetados else 0
                st.markdown(
                    f'<div class="proj-ancora">'
                    f'Âncora: <b>{d_anc.strftime("%d/%m/%Y")}</b> — '
                    f'Projeção: <b>{data_hoje.strftime("%d/%m/%Y")}</b> — '
                    f'~{du_med} dias úteis projetados'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            except Exception:
                pass

        # Tabela de ativos projetados
        rows = []
        for projected in todos_projetados:
            meta = projected.get("meta", {})
            corretora = meta.get("corretora", "?")
            conta = meta.get("conta", "?")

            for ativo in projected.get("ativos", []):
                res = ativo.get("_proj_resultado", {})
                projecao_meta = ativo.get("_projecao", {})

                saldo_anc = ativo.get("saldo_bruto", 0) or 0
                saldo_proj = res.get("saldo_projetado")
                var_r = res.get("variacao_rs")
                var_p = res.get("variacao_pct")
                confianca = res.get("confianca", "nenhuma")
                metodo = res.get("metodo", "sem_projecao")
                detalhe = res.get("detalhe", "")

                badge = {
                    "alta": "Alta",
                    "media": "Média",
                    "baixa": "Baixa",
                    "nenhuma": "—",
                }.get(confianca, "—")

                rows.append({
                    "Corretora": corretora,
                    "Conta": conta,
                    "Estratégia": ativo.get("estrategia", ""),
                    "Ativo": ativo.get("nome_original", ""),
                    "Âncora (R$)": saldo_anc,
                    "Estimativa D0 (R$)": saldo_proj if saldo_proj is not None else saldo_anc,
                    "Var. (R$)": var_r,
                    "Var. (%)": var_p,
                    "Método": metodo,
                    "Confiança": badge,
                })

        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Âncora (R$)": st.column_config.NumberColumn("Âncora (R$)", format="R$ %.2f"),
                    "Estimativa D0 (R$)": st.column_config.NumberColumn("Estimativa D0 (R$)", format="R$ %.2f"),
                    "Var. (R$)": st.column_config.NumberColumn("Var. (R$)", format="R$ %.2f"),
                    "Var. (%)": st.column_config.NumberColumn("Var. (%)", format="%.4f%%"),
                },
            )

            # Cobertura
            n_total = len(rows)
            n_proj = sum(1 for r in rows if r["Método"] != "sem_projecao")
            n_sem = n_total - n_proj
            cob_pct = n_proj / n_total * 100 if n_total else 0

            st.markdown(
                f"**Cobertura:** {n_proj}/{n_total} ativos com projeção ({cob_pct:.0f}%) — "
                f"{n_sem} exibidos com saldo âncora",
            )


# =============================================================================
# VIEW: DASHBOARD
# =============================================================================

def _view_dashboard():
    dados       = st.session_state["dados_consolidados"]
    excel_bytes = st.session_state.get("excel_bytes")
    excel_fname = st.session_state.get("excel_filename", "Consolidado.xlsx")
    cliente     = st.session_state.get("cliente_nome", "")
    data_ref    = st.session_state.get("data_ref", "")

    st.title(f"Dashboard — {cliente}")
    st.markdown(
        f"<p style='font-size:14px;color:#475569;margin-top:-12px'>Referência: {data_ref}</p>",
        unsafe_allow_html=True,
    )

    # ── 4 Cards ──────────────────────────────────────────────────────────────
    _cards_dashboard(dados)

    # ── Gráficos ─────────────────────────────────────────────────────────────
    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown("<div class='section-title'>Evolução Patrimonial</div>", unsafe_allow_html=True)
        _chart_evolucao(dados)

    with col_right:
        st.markdown("<div class='section-title'>Rentabilidade Mês a Mês</div>", unsafe_allow_html=True)
        _chart_rent_mensal(dados)

    st.divider()

    # ── Tabelas ───────────────────────────────────────────────────────────────
    col_t1, col_t2 = st.columns([3, 2])
    with col_t1:
        st.markdown("<div class='section-title'>Patrimônio por Conta</div>", unsafe_allow_html=True)
        _tabela_contas(dados)

    with col_t2:
        st.markdown("<div class='section-title'>Alocação por Estratégia</div>", unsafe_allow_html=True)
        _tabela_alocacao(dados)

    st.divider()

    # ── Ações ─────────────────────────────────────────────────────────────────
    col_dl, col_nova, _ = st.columns([1, 1, 2])
    with col_dl:
        if excel_bytes:
            st.download_button(
                label="Download Excel",
                data=excel_bytes,
                file_name=excel_fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with col_nova:
        if st.button("Nova Importação", type="secondary", use_container_width=True):
            _reset_state()
            st.rerun()

    # ── Projeção D0 ───────────────────────────────────────────────────────────
    relatorios_ind = st.session_state.get("relatorios_individuais") or []
    if relatorios_ind:
        st.markdown("")
        _posicoes_d0_section(relatorios_ind)


# =============================================================================
# UTILITÁRIOS DE ESTADO
# =============================================================================

def _reset_state():
    for k in ("dados_consolidados", "excel_bytes", "excel_filename", "relatorios_individuais"):
        st.session_state[k] = None
    for k in ("historico", "erros_sessao"):
        st.session_state[k] = []
    st.session_state["view"] = "upload"


def _init_state():
    defaults = {
        "view":                    "upload",
        "dados_consolidados":      None,
        "relatorios_individuais":  None,
        "excel_bytes":             None,
        "excel_filename":          "Consolidado.xlsx",
        "cliente_nome":            "",
        "data_ref":                datetime.now().strftime("%m/%Y"),
        "historico":               [],
        "erros_sessao":            [],
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    st.set_page_config(
        page_title="Consolidador — Capital Investimentos",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)
    _init_state()
    _sidebar()

    view = st.session_state.get("view", "upload")
    if view == "dashboard" and st.session_state.get("dados_consolidados"):
        _view_dashboard()
    else:
        _view_upload()


if __name__ == "__main__":
    main()
