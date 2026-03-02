"""
Consolidador — Extrator de PDFs de relatórios de corretoras.

Converte PDFs de relatórios (XP Performance, BTG/API Capital Performance)
em JSON estruturado seguindo o schema consolidador-v2.

Usa Claude API (Sonnet 4.5) para extração via visão computacional.
Otimizado para custo: filtra páginas sem dados (capas, disclaimers).
"""

import base64
import json
import logging
import os
import time
from pathlib import Path

import fitz  # PyMuPDF
import jsonschema
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Diretório raiz do projeto
PROJECT_ROOT = Path(__file__).parent.parent

# Caminhos
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "consolidador_v2.json"
PROMPTS_DIR = PROJECT_ROOT / "config" / "prompts"

# Modelo Claude
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 16000

# Rastreamento de custos (preços Sonnet 4.5 por milhão de tokens)
PRICE_INPUT_PER_M = 3.00   # $3/M input tokens
PRICE_OUTPUT_PER_M = 15.00  # $15/M output tokens

# Acumulador global de custos
_total_cost = {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "calls": 0}


def get_total_cost() -> dict:
    """Retorna o custo acumulado de todas as chamadas à API."""
    return dict(_total_cost)


def _load_schema() -> dict:
    """Carrega o JSON Schema do disco."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt(report_type: str, schema: dict) -> str:
    """Carrega o prompt de extração e injeta o schema."""
    prompt_map = {
        "xp_performance": "xp_performance.txt",
        "btg_api_performance": "btg_performance.txt",
    }
    
    filename = prompt_map.get(report_type)
    if not filename:
        raise ValueError(f"Tipo de relatório não suportado: {report_type}")
    
    prompt_path = PROMPTS_DIR / filename
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()
    
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    return template.replace("{schema}", schema_str)


def detect_report_type(pdf_path: str) -> str:
    """
    Detecta o tipo de relatório analisando o texto das primeiras páginas.

    Retorna: "xp_performance" | "btg_api_performance" | "xp_posicao_consolidada"
    """
    doc = fitz.open(pdf_path)
    raw_text = ""
    for i in range(min(3, len(doc))):
        raw_text += doc[i].get_text()
    doc.close()

    # Normalizar: remover quebras de linha e múltiplos espaços
    import re as _re
    text = _re.sub(r'\s+', ' ', raw_text).lower()

    if "relatório de investimentos" in text or "xperformance" in text.replace(" ", ""):
        if "posição consolidada" in text:
            return "xp_posicao_consolidada"
        return "xp_performance"

    if "api capital" in text or "relatório de performance" in text:
        return "btg_api_performance"

    if "btg pactual" in text:
        return "btg_api_performance"

    raise ValueError(
        f"Formato de relatório não reconhecido: {pdf_path}. "
        "Suportados: XP Performance, BTG/API Capital Performance."
    )


def _should_skip_page(page: fitz.Page, page_num: int) -> bool:
    """
    Decide se uma página deve ser pulada (não enviada à API).
    
    Pula:
    - Disclaimers / notas legais
    - Páginas quase vazias (< 5 linhas de texto)
    """
    text = page.get_text().lower().strip()
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    
    # Página quase vazia
    if len(lines) < 3:
        return True
    
    # Disclaimers (última página tipicamente)
    disclaimer_keywords = [
        "este material foi elaborado",
        "ouvidoria",
        "informações legais",
        "a xp investimentos corretora",
        "este relatório é destinado",
        "sac ",
        "www.xpi.com.br",
    ]
    if any(kw in text for kw in disclaimer_keywords):
        # Verificar se tem dados reais também (às vezes disclaimer + dados)
        has_data = any(c in text for c in ["r$", "saldo bruto", "rent.", "%"])
        if not has_data:
            return True
    
    return False


def _render_pages(pdf_path: str, dpi: int = 200) -> list[tuple[int, str]]:
    """
    Renderiza páginas relevantes do PDF como imagens base64.
    Pula capas/disclaimers para economizar tokens.
    
    Retorna lista de (page_num, base64_png).
    """
    doc = fitz.open(pdf_path)
    images = []
    skipped = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        if _should_skip_page(page, page_num):
            skipped.append(page_num + 1)
            continue
        
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        images.append((page_num + 1, b64))
    
    doc.close()
    
    total = len(images) + len(skipped)
    logger.info(f"Renderizadas {len(images)}/{total} páginas (puladas: {skipped or 'nenhuma'})")
    return images


def _call_claude(images: list[tuple[int, str]], prompt: str) -> tuple[str, dict]:
    """
    Envia imagens e prompt ao Claude API.
    
    Retorna (response_text, usage_info).
    """
    client = Anthropic()
    
    content = []
    for page_num, img_b64 in images:
        content.append({
            "type": "text",
            "text": f"[Página {page_num}]",
        })
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": img_b64,
            },
        })
    
    content.append({
        "type": "text",
        "text": prompt,
    })
    
    logger.info(f"Enviando {len(images)} páginas ao Claude ({CLAUDE_MODEL})...")
    start_time = time.time()
    
    # Retry com backoff exponencial para erros 5xx
    max_retries = 5
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "user", "content": content}
                ],
            )
            break  # Sucesso
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            if "502" in error_str or "500" in error_str or "529" in error_str or "overloaded" in error_str:
                wait = min(2 ** attempt * 2, 30)
                logger.warning(f"Tentativa {attempt+1}/{max_retries} falhou ({e.__class__.__name__}). Aguardando {wait}s...")
                time.sleep(wait)
            else:
                raise  # Erro não-retriável
    else:
        raise last_error  # Todas as tentativas falharam
    
    elapsed = time.time() - start_time
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "elapsed_s": round(elapsed, 1),
    }
    
    # Calcular custo
    cost = (usage["input_tokens"] / 1_000_000 * PRICE_INPUT_PER_M +
            usage["output_tokens"] / 1_000_000 * PRICE_OUTPUT_PER_M)
    usage["cost_usd"] = round(cost, 4)
    
    # Acumular
    _total_cost["input_tokens"] += usage["input_tokens"]
    _total_cost["output_tokens"] += usage["output_tokens"]
    _total_cost["usd"] += cost
    _total_cost["calls"] += 1
    
    logger.info(
        f"Resposta em {elapsed:.1f}s | "
        f"Tokens: {usage['input_tokens']:,} in + {usage['output_tokens']:,} out | "
        f"Custo: ${cost:.4f} | "
        f"Acumulado: ${_total_cost['usd']:.4f}"
    )
    
    return response.content[0].text, usage


def _parse_json_response(response_text: str) -> dict:
    """Parseia a resposta do Claude como JSON."""
    text = response_text.strip()
    
    if text.startswith("```"):
        first_nl = text.index("\n")
        last_fence = text.rfind("```")
        if last_fence > first_nl:
            text = text[first_nl + 1:last_fence].strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON: {e}")
        logger.error(f"Primeiros 500 chars: {text[:500]}")
        raise ValueError(f"Resposta do Claude não é JSON válido: {e}") from e


def _validate_schema(data: dict, schema: dict) -> list[str]:
    """Valida os dados contra o JSON Schema. Retorna lista de erros."""
    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(data):
        path = " → ".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        errors.append(f"[{path}] {error.message}")
    return errors


def _post_validate(data: dict) -> list[str]:
    """Validações de negócio pós-extração. Retorna lista de warnings."""
    warnings = []
    
    resumo = data.get("resumo_carteira", {})
    patrimonio = resumo.get("patrimonio_total_bruto")
    
    if patrimonio is None or patrimonio <= 0:
        warnings.append("ERRO: patrimonio_total_bruto ausente ou inválido")
        return warnings
    
    # 1. Soma de estratégias ≈ patrimônio total
    estrategias = data.get("composicao_por_estrategia", [])
    soma_estrategias = 0
    if estrategias:
        soma_estrategias = sum(e.get("saldo_bruto", 0) for e in estrategias)
        diff = abs(soma_estrategias - patrimonio)
        if diff > 1.0:
            warnings.append(
                f"Soma estratégias (R$ {soma_estrategias:,.2f}) ≠ patrimônio total "
                f"(R$ {patrimonio:,.2f}), diff: R$ {diff:,.2f}"
            )
    
    # 2. Soma de ativos ≈ referência
    ativos = data.get("ativos", [])
    if ativos:
        soma_ativos = sum(a.get("saldo_bruto", 0) for a in ativos)
        target = soma_estrategias if estrategias else patrimonio
        diff = abs(soma_ativos - target)
        if diff > 1.0:
            warnings.append(
                f"Soma ativos (R$ {soma_ativos:,.2f}) ≠ ref (R$ {target:,.2f}), diff: R$ {diff:,.2f}"
            )
    
    # 3. % alocação ≈ 100%
    if estrategias:
        soma_pct = sum(e.get("pct_alocacao", 0) for e in estrategias)
        if abs(soma_pct - 100.0) > 0.05:
            warnings.append(f"Soma % alocação = {soma_pct:.2f}% (esperado ≈ 100%)")
    
    # 4. Nenhum ativo com saldo null
    for i, ativo in enumerate(ativos):
        if ativo.get("saldo_bruto") is None:
            warnings.append(f"Ativo [{i}] '{ativo.get('nome_original', '?')}' tem saldo_bruto null")
    
    # 5. Benchmarks
    benchmarks = data.get("benchmarks", {})
    cdi = benchmarks.get("cdi", {})
    if not cdi or cdi.get("mes") is None:
        warnings.append("Benchmark CDI mês não preenchido")
    
    # 6. Evolução patrimonial
    for ep in data.get("evolucao_patrimonial", []):
        pi = ep.get("patrimonio_inicial", 0)
        mov = ep.get("movimentacoes", 0)
        ir = ep.get("ir", 0)
        iof = ep.get("iof", 0)
        pf = ep.get("patrimonio_final", 0)
        ganho = ep.get("ganho_financeiro", 0)
        
        if pi > 0 and pf > 0:
            calculado = pi + mov + ganho + ir + iof
            diff = abs(calculado - pf)
            if diff > 1.0:
                warnings.append(
                    f"Evolução {ep.get('data', '?')}: calc R$ {calculado:,.2f} ≠ "
                    f"final R$ {pf:,.2f} (diff R$ {diff:,.2f})"
                )
    
    return warnings


def extract_pdf(pdf_path: str) -> dict:
    """
    Extrai dados de um PDF de relatório de corretora.
    
    Retorna dict com dados extraídos no formato consolidador-v2.
    """
    pdf_path = str(Path(pdf_path).resolve())
    filename = Path(pdf_path).name
    
    logger.info(f"{'='*60}")
    logger.info(f"Extraindo: {filename}")
    logger.info(f"{'='*60}")
    
    start_time = time.time()
    
    # 1. Detectar tipo
    report_type = detect_report_type(pdf_path)
    logger.info(f"Tipo detectado: {report_type}")
    
    # 2. Carregar schema e prompt
    schema = _load_schema()
    prompt = _load_prompt(report_type, schema)
    
    # 3. Renderizar páginas (com filtragem)
    images = _render_pages(pdf_path)
    
    # 4. Chamar Claude API
    response_text, usage = _call_claude(images, prompt)
    
    # 5. Parsear JSON
    data = _parse_json_response(response_text)
    
    # 6. Garantir metadados
    if "meta" not in data:
        data["meta"] = {}
    data["meta"]["tipo_relatorio"] = report_type
    data["meta"]["arquivo_origem"] = filename
    if "corretora" not in data["meta"]:
        data["meta"]["corretora"] = "XP" if "xp" in report_type else "BTG"
    # XP Performance não mostra nome do titular — forçar null para não copiar o parceiro
    if report_type == "xp_performance":
        data["meta"]["cliente"] = None
    data["$schema"] = "consolidador-v2"
    
    # 7. Validar schema
    schema_errors = _validate_schema(data, schema)
    if schema_errors:
        logger.warning(f"Erros de schema ({len(schema_errors)}):")
        for err in schema_errors[:10]:
            logger.warning(f"  - {err}")
        if len(schema_errors) > 10:
            logger.warning(f"  ... e mais {len(schema_errors) - 10}")
    
    # 8. Validações de negócio
    biz_warnings = _post_validate(data)
    if biz_warnings:
        logger.warning(f"Warnings de validação ({len(biz_warnings)}):")
        for w in biz_warnings:
            logger.warning(f"  ⚠ {w}")
    
    # 9. Resumo
    elapsed = time.time() - start_time
    n_ativos = len(data.get("ativos", []))
    n_mov = len(data.get("movimentacoes", []))
    patrimonio = data.get("resumo_carteira", {}).get("patrimonio_total_bruto", 0)
    
    logger.info(f"Extração concluída em {elapsed:.1f}s:")
    logger.info(f"  Conta: {data.get('meta', {}).get('conta', '?')}")
    logger.info(f"  Patrimônio: R$ {patrimonio:,.2f}")
    logger.info(f"  Ativos: {n_ativos} | Movimentações: {n_mov}")
    logger.info(f"  Erros schema: {len(schema_errors)} | Warnings: {len(biz_warnings)}")
    logger.info(f"  Tokens: {usage['input_tokens']:,} in + {usage['output_tokens']:,} out = ${usage['cost_usd']:.4f}")
    
    return data
