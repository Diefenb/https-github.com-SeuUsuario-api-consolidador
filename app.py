import os
import sys
import tempfile
import traceback
import streamlit as st
from datetime import datetime

# Adicionar a pasta Consolidador_V3/src no path para importar os módulos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'Consolidador_V3', 'src')))

from consolidator import consolidate
from normalizer import normalize
from report_generator import generate_report
from parsers import detect_and_parse, UnknownFormatError
from importer import import_manual_json

# Configuração da página
st.set_page_config(
    page_title="API Consolidador",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilos Customizados (CSS Injetado)
CSS_INJECT = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

html, body, [class*="st-"] {
    font-family: 'Inter', sans-serif;
    font-variant-numeric: tabular-nums;
}

.stApp {
    background-color: #F8FAFC;
}

div[data-testid="stExpander"], div[data-testid="stMetric"], div.card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    box-shadow: 0px 1px 3px rgba(15, 23, 42, 0.05);
    padding: 16px;
    margin-bottom: 16px;
}

div[data-testid="stMetricValue"] {
    color: #0D1B3E;
    font-weight: 600;
    font-size: 28px;
}

div[data-testid="stMetricDelta"] svg {
    display: none;
}

section[data-testid="stFileUploadDropzone"] {
    background-color: #FFFFFF;
    border: 2px dashed #CBD5E1;
    border-radius: 8px;
    transition: all 0.2s ease;
}
section[data-testid="stFileUploadDropzone"]:hover {
    border-color: #1A56DB;
    background-color: #EFF6FF;
}

div[data-testid="stButton"] button[kind="primary"] {
    background-color: #0D1B3E;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    padding: 0.5rem 1rem;
    transition: all 0.2s ease;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
    background-color: #1A56DB;
    box-shadow: 0 4px 6px -1px rgba(26, 86, 219, 0.1);
}

div[data-testid="stButton"] button[kind="secondary"] {
    background-color: transparent;
    color: #0D1B3E;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    font-weight: 500;
}
div[data-testid="stButton"] button[kind="secondary"]:hover {
    background-color: #F8FAFC;
    border-color: #0D1B3E;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    overflow: hidden;
}

section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}

h1, h2, h3 {
    color: #0F172A;
}
p.subtitle {
    font-size: 14px;
    font-weight: 500;
    color: #475569;
    letter-spacing: 0.2px;
}
</style>
"""
st.markdown(CSS_INJECT, unsafe_allow_html=True)

# Barra Lateral
with st.sidebar:
    st.markdown("### 📊 API Consolidador")
    st.markdown("<p class='subtitle'>Versão Interna - API Capital</p>", unsafe_allow_html=True)
    st.divider()
    st.markdown("**Instruções:**")
    st.markdown("1. Preencha o nome do cliente.")
    st.markdown("2. Selecione a data de referência.")
    st.markdown("3. Faça upload dos relatórios em PDF (XP/BTG) ou dados extraídos (JSON).")
    st.markdown("4. Clique em **Consolidar Carteiras**.")

# Título Principal
st.title("Consolidador de Carteiras")
st.markdown("<p class='subtitle'>Integração de relatórios XP e geração de excel consolidado.</p>", unsafe_allow_html=True)

# Formulário de Entrada
with st.form("upload_form"):
    col1, col2 = st.columns([2, 1])
    with col1:
        cliente_nome = st.text_input("Nome do Cliente", placeholder="Ex: João da Silva")
    with col2:
        mes_atual = datetime.now().strftime("%m/%Y")
        data_ref = st.text_input("Mês/Ano de Referência", value=mes_atual)
    
    uploaded_files = st.file_uploader(
        "Arraste os arquivos das contas (PDFs XP/BTG ou estruturado JSON)", 
        type=["pdf", "json"], 
        accept_multiple_files=True
    )
    
    submitted = st.form_submit_button("Consolidar Carteiras", type="primary")

# Lógica de Processamento
if submitted:
    if not uploaded_files:
        st.error("❌ Por favor, envie ao menos um relatório em PDF antes de consolidar.")
    elif not cliente_nome.strip():
        st.warning("⚠️ Insira o nome do cliente.")
    else:
        with st.spinner("⚙️ Processando arquivos..."):
            relatorios_normalizados = []
            erros = []
            
            # Para cada PDF
            for file in uploaded_files:
                try:
                    # Salvar temporário para o parser ler
                    ext = os.path.splitext(file.name)[1].lower()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp.write(file.getbuffer())
                        tmp_path = tmp.name
                    
                    # 1. Parsear o arquivo
                    if ext == ".json":
                        parsed_data = import_manual_json(tmp_path)
                    elif ext == ".pdf":
                        # Auto-detecção de formato pelo conteúdo do PDF
                        parsed_data = detect_and_parse(tmp_path)
                    else:
                        raise ValueError("Formato de arquivo não suportado.")
                    
                    # 2. Normalizar o dado parsed
                    norm_data = normalize(parsed_data)
                    relatorios_normalizados.append(norm_data)
                    
                    os.unlink(tmp_path) # Cleanup
                except Exception as e:
                    erros.append((file.name, str(e)))
                    traceback.print_exc()

            if erros:
                for nome_arq, err in erros:
                    st.error(f"❌ Erro ao processar o arquivo **{nome_arq}**: {err}")
            
            if relatorios_normalizados:
                st.success(f"✅ Sucesso! {len(relatorios_normalizados)} contas processadas.")
                
                try:
                    # 3. Consolidar os dados
                    dados_consolidados = consolidate(
                        reports=relatorios_normalizados,
                        cliente=cliente_nome,
                        data_referencia=data_ref
                    )
                    
                    # 4. Exibição na Interface
                    st.markdown("### Resumo do Cliente")
                    
                    # Cards
                    col_patrimonio, col_contas = st.columns(2)
                    total_bruto = dados_consolidados.get('patrimonio_total_consolidado', 0)
                    
                    with col_patrimonio:
                        st.metric(
                            label="AuM Total Consolidado", 
                            value=f"R$ {total_bruto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        )
                    with col_contas:
                        st.metric(label="Contas Processadas", value=len(dados_consolidados.get('contas', [])))
                    
                    # Tabela de contas
                    st.markdown("#### Detalhamento por Conta")
                    import pandas as pd
                    contas_df = pd.DataFrame(dados_consolidados.get('contas', []))
                    if not contas_df.empty:
                        fmt_cols = ['patrimonio_bruto', 'rentabilidade_mes_pct', 'pct_cdi_mes']
                        st.dataframe(
                            contas_df[['corretora', 'conta', 'patrimonio_bruto', 'rentabilidade_mes_pct', 'pct_cdi_mes']], 
                            use_container_width=True
                        )
                    
                    # 5. Gerar Relatório Excel
                    output_dir = os.path.join(os.path.dirname(__file__), 'output', 'relatorios')
                    os.makedirs(output_dir, exist_ok=True)
                    excel_path = os.path.join(output_dir, f"Relatorio_{cliente_nome.replace(' ', '_')}.xlsx")
                    
                    generate_report(dados_consolidados, excel_path)
                    
                    with open(excel_path, "rb") as f:
                        file_data = f.read()
                    
                    st.download_button(
                        label="📥 Baixar Excel Consolidado",
                        data=file_data,
                        file_name=f"Consolidado_{cliente_nome.replace(' ', '_')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"❌ Erro na consolidação ou geração do relatório: {e}")
                    traceback.print_exc()
