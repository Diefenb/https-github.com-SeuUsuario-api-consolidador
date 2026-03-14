"""
cvm_funds.py — Cotas de fundos via CVM Dados Abertos.

Fluxos:
1. fetch_fund_nav(cnpj, data)    — cota do fundo em determinada data
2. ensure_cadastral_cache()      — baixa/atualiza registro_classe.csv da CVM
3. find_cnpj_by_name(nome)       — fuzzy match nome → CNPJ
"""

import csv
import io
import logging
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests

from .cache import SQLiteCache

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_CADASTRAL_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_classe.csv"
_INF_DIARIO_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"

_CADASTRAL_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "market_data" / "cvm_cadastral_cache.csv"
)

# Cache em memória do cadastral (carregado sob demanda)
_cadastral_df: Optional[list[dict]] = None
_cadastral_loaded_at: Optional[date] = None


# ─────────────────────────────────────────────────────────────────────────────
# Cadastral CVM
# ─────────────────────────────────────────────────────────────────────────────

def ensure_cadastral_cache(force: bool = False) -> bool:
    """
    Garante que o arquivo cadastral CVM existe e está atualizado (< 7 dias).
    Retorna True se o arquivo está disponível, False se falhou.
    """
    _CADASTRAL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not force and _CADASTRAL_PATH.exists():
        age = date.today() - date.fromtimestamp(_CADASTRAL_PATH.stat().st_mtime)
        if age.days < 7:
            return True

    logger.info("Baixando registro_classe.csv da CVM…")
    try:
        resp = requests.get(_CADASTRAL_URL, timeout=_TIMEOUT, stream=True)
        resp.raise_for_status()
        _CADASTRAL_PATH.write_bytes(resp.content)
        logger.info(f"Cadastral CVM salvo: {_CADASTRAL_PATH} ({len(resp.content)//1024} KB)")
        return True
    except Exception as e:
        logger.warning(f"Falha ao baixar cadastral CVM: {e}")
        return _CADASTRAL_PATH.exists()


def _load_cadastral() -> list[dict]:
    """Carrega o CSV cadastral da CVM em memória (cache lazy)."""
    global _cadastral_df, _cadastral_loaded_at

    today = date.today()
    if _cadastral_df is not None and _cadastral_loaded_at == today:
        return _cadastral_df

    if not _CADASTRAL_PATH.exists():
        if not ensure_cadastral_cache():
            return []

    try:
        registros = []
        with open(_CADASTRAL_PATH, encoding="latin-1", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            for row in reader:
                situacao = row.get("Situacao", row.get("SITUACAO", "")).strip().upper()
                if "FUNCIONAMENTO NORMAL" in situacao or "EM FUNCIONAMENTO" in situacao:
                    registros.append({
                        "cnpj": row.get("CNPJ_Classe", row.get("CNPJ_CLASSE", "")).strip(),
                        "nome": row.get("Denominacao_Social", row.get("DENOMINACAO_SOCIAL", "")).strip(),
                        "tipo": row.get("Tipo_Ativo", row.get("TIPO_ATIVO", "")).strip(),
                    })
        _cadastral_df = registros
        _cadastral_loaded_at = today
        logger.info(f"Cadastral CVM carregado: {len(registros)} fundos ativos")
        return registros
    except Exception as e:
        logger.error(f"Erro ao carregar cadastral CVM: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy match nome → CNPJ
# ─────────────────────────────────────────────────────────────────────────────

_ABREVIACOES = [
    (r"\bCI\b", "CAPITAL INVESTIMENTO"),
    (r"\bFIC\b", "FUNDO DE INVESTIMENTO EM COTAS"),
    (r"\bFIF\b", "FUNDO DE INVESTIMENTO FINANCEIRO"),
    (r"\bFIM\b", "FUNDO DE INVESTIMENTO MULTIMERCADO"),
    (r"\bFIRF\b", "FUNDO DE INVESTIMENTO RENDA FIXA"),
    (r"\bFIA\b", "FUNDO DE INVESTIMENTO EM ACOES"),
    (r"\bFIDC\b", "FUNDO DE INVESTIMENTO EM DIREITOS CREDITORIOS"),
    (r"\bCP\b", "CREDITO PRIVADO"),
    (r"\bLP\b", "LONGO PRAZO"),
    (r"\bRF\b", "RENDA FIXA"),
    (r"\bRL\b", "RESPONSABILIDADE LIMITADA"),
    (r"\bMM\b", "MULTIMERCADO"),
]


def _normalizar_nome(nome: str) -> str:
    nome = nome.upper().strip()
    # Remover acentos básicos
    for a, b in [("Ã", "A"), ("Á", "A"), ("Â", "A"), ("É", "E"), ("Ê", "E"),
                 ("Í", "I"), ("Ó", "O"), ("Ô", "O"), ("Õ", "O"), ("Ú", "U"),
                 ("Ç", "C")]:
        nome = nome.replace(a, b)
    # Expandir abreviações
    for pattern, replacement in _ABREVIACOES:
        nome = re.sub(pattern, replacement, nome)
    return nome


def find_cnpj_by_name(nome_pdf: str) -> tuple[Optional[str], float]:
    """
    Faz fuzzy match do nome do fundo no PDF contra o cadastral CVM.

    Returns:
        (cnpj, score) onde score é 0-100. None se abaixo do threshold mínimo.
    """
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        logger.warning("rapidfuzz não instalado — fuzzy match desabilitado")
        return None, 0.0

    fundos = _load_cadastral()
    if not fundos:
        return None, 0.0

    nome_norm = _normalizar_nome(nome_pdf)
    nomes_cvm = [_normalizar_nome(f["nome"]) for f in fundos]

    # WRatio é o mais robusto para strings de comprimento diferente
    match = process.extractOne(
        nome_norm,
        nomes_cvm,
        scorer=fuzz.WRatio,
        score_cutoff=60,
    )

    if match is None:
        return None, 0.0

    matched_nome, score, idx = match
    cnpj = fundos[idx]["cnpj"]
    return cnpj, float(score)


# ─────────────────────────────────────────────────────────────────────────────
# Cotas diárias (inf_diario)
# ─────────────────────────────────────────────────────────────────────────────

def _cvm_diario_url(ano: int, mes: int) -> str:
    return _INF_DIARIO_URL.format(yyyymm=f"{ano}{mes:02d}")


def _fetch_cotas_mes(cnpj: str, ano: int, mes: int) -> dict[str, float]:
    """Baixa o arquivo mensal CVM e extrai as cotas do CNPJ."""
    url = _cvm_diario_url(ano, mes)
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            nome_csv = zf.namelist()[0]
            with zf.open(nome_csv) as f:
                content = f.read().decode("latin-1")

        cotas = {}
        reader = csv.DictReader(io.StringIO(content), delimiter=";")
        for row in reader:
            cnpj_row = row.get("CNPJ_FUNDO", "").strip().replace(".", "").replace("/", "").replace("-", "")
            cnpj_clean = cnpj.strip().replace(".", "").replace("/", "").replace("-", "")
            if cnpj_row == cnpj_clean:
                data = row.get("DT_COMPTC", "").strip()
                vl_quota = row.get("VL_QUOTA", "").strip().replace(",", ".")
                if data and vl_quota:
                    try:
                        cotas[data] = float(vl_quota)
                    except ValueError:
                        pass
        return cotas

    except Exception as e:
        logger.warning(f"Falha ao buscar cotas CVM {ano}/{mes} para {cnpj}: {e}")
        return {}


def fetch_fund_nav(
    cnpj: str,
    data_ancora: date,
    data_hoje: date,
    cache: Optional[SQLiteCache] = None,
) -> tuple[Optional[float], Optional[float]]:
    """
    Retorna (cota_ancora, cota_hoje) para o fundo identificado pelo CNPJ.
    Busca do cache primeiro, depois da CVM.

    Returns:
        (cota_ancora, cota_mais_recente) — pode ser None se não disponível
    """
    if cache is None:
        cache = SQLiteCache()

    data_ancora_iso = data_ancora.isoformat()
    data_hoje_iso = data_hoje.isoformat()

    cota_ancora = cache.get_cota(cnpj, data_ancora_iso)
    cota_hoje = None

    # Para cota_hoje: tentar o dia mais recente disponível (CVM é D+1)
    # Procurar nos últimos 5 dias úteis
    for delta in range(1, 6):
        tentativa = (data_hoje - timedelta(days=delta)).isoformat()
        cota_hoje = cache.get_cota(cnpj, tentativa)
        if cota_hoje is not None:
            break

    if cota_ancora is None or cota_hoje is None:
        # Buscar meses necessários da CVM
        meses_necessarios = set()
        d = data_ancora
        while d <= data_hoje:
            meses_necessarios.add((d.year, d.month))
            d = d.replace(day=1) + timedelta(days=32)
            d = d.replace(day=1)

        for ano, mes in sorted(meses_necessarios):
            logger.info(f"Buscando cotas CVM {ano}/{mes:02d} para {cnpj}")
            cotas = _fetch_cotas_mes(cnpj, ano, mes)
            if cotas:
                cache.set_cotas_bulk(cnpj, cotas)

        # Re-tentar do cache
        cota_ancora = cache.get_cota(cnpj, data_ancora_iso)
        if cota_ancora is None:
            # Tentar dias próximos à âncora
            for delta in range(1, 6):
                tentativa = (data_ancora + timedelta(days=delta)).isoformat()
                cota_ancora = cache.get_cota(cnpj, tentativa)
                if cota_ancora is not None:
                    break

        for delta in range(1, 6):
            tentativa = (data_hoje - timedelta(days=delta)).isoformat()
            cota_hoje = cache.get_cota(cnpj, tentativa)
            if cota_hoje is not None:
                break

    return cota_ancora, cota_hoje


def fetch_fund_nav_series(
    cnpj: str,
    data_inicio: date,
    data_fim: date,
    cache: Optional[SQLiteCache] = None,
) -> dict[str, float]:
    """
    Retorna série completa de NAVs para o CNPJ entre data_inicio e data_fim.
    Usa cache SQLite; baixa apenas os meses ausentes da CVM.

    Returns:
        {date_iso: nav_value}  ex: {"2025-11-03": 42.1234, ...}
    """
    if cache is None:
        cache = SQLiteCache()

    # Determinar meses necessários
    meses = set()
    d = date(data_inicio.year, data_inicio.month, 1)
    while d <= data_fim:
        meses.add((d.year, d.month))
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)

    # Para cada mês, verificar cache e baixar se necessário
    for ano, mes in sorted(meses):
        primeiro_dia = date(ano, mes, 1)
        # Checar se já temos dados no cache para este mês/CNPJ
        cached = cache.get_cotas_range(cnpj, primeiro_dia.isoformat(), date(ano, mes, 28).isoformat())
        if not cached:
            logger.info(f"Baixando cotas CVM {ano}/{mes:02d} para {cnpj}")
            cotas = _fetch_cotas_mes(cnpj, ano, mes)
            if cotas:
                cache.set_cotas_bulk(cnpj, cotas)

    # Ler série completa do cache
    return cache.get_cotas_range(cnpj, data_inicio.isoformat(), data_fim.isoformat())
