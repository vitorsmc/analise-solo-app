import streamlit as st
import pdfplumber
import pandas as pd
import re
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Análise de Solo Auto", page_icon="🌱")

st.title("🌱 Gerador de Relatórios de Solo")
st.markdown("""
Faça o upload do PDF do laboratório e receba o relatório técnico comparativo instantaneamente.
""")

# --- SUAS CONSTANTES E FUNÇÕES (DO SCRIPT ANTERIOR) ---
# (Cole aqui o dicionário REFERENCIAS e a lógica de interpretação)
REFERENCIAS = {
    "0-20": { "P": 17.0, "K": 0.35, "Ca": 2.0, "Mg": 0.5, "S": 15.0, "B": 0.5, "Fe": 25.0, "Mn": 8.0, "Cu": 1.2, "Zn": 1.25, "CTC": 5.0 },
    "20-40": { "P": 30.0, "K": 0.38, "Ca": 3.71, "Mg": 1.11, "S": 15.0, "B": 0.6, "Fe": 30.0, "Mn": 8.0, "Cu": 1.2, "Zn": 1.25, "CTC": 9.6 }
}

def processar_pdf_em_memoria(arquivo_upload):
    """Lê o PDF diretamente da memória (buffer)"""
    dados_brutos = []
    mapa_amostras = {}
    
    # pdfplumber aceita objetos de arquivo (bytes)
    with pdfplumber.open(arquivo_upload) as pdf:
        primeira_pagina = pdf.pages[0]
        texto = primeira_pagina.extract_text()
        tabelas = primeira_pagina.extract_tables()

        # --- Lógica de REGEX (Mesma do script anterior) ---
        linhas_texto = texto.split('\n')
        for linha in linhas_texto:
            match = re.search(r'Reg.*?(\d{6}).*?(\d{1,2}-\d{1,2})cm', linha)
            if match:
                id_amostra = match.group(1)
                profundidade = match.group(2)
                if "0-20" in profundidade: ref_key = "0-20"
                elif "20-40" in profundidade: ref_key = "20-40"
                else: ref_key = "0-20"
                mapa_amostras[id_amostra] = ref_key

        # --- Lógica da Tabela (Mesma do script anterior) ---
        tabela_principal = max(tabelas, key=len)
        header_row_idx = -1
        ids_colunas = []
        
        for i, row in enumerate(tabela_principal):
            row_clean = [str(x).strip() for x in row if x is not None]
            ids = [x for x in row_clean if x.isdigit() and len(x) == 6]
            if ids:
                header_row_idx = i
                for idx, val in enumerate(row):
                    if val and val.strip().isdigit() and len(val.strip()) == 6:
                        ids_colunas.append((idx, val.strip()))
                break
        
        resultados = {id: {} for id in mapa_amostras.keys()}
        
        parametros_interesse = {"P (ppm)": "P", "K (ppm)": "K", "Ca (meq/100mL)": "Ca", "Mg (meq100mL/)": "Mg", "Mg (meq/100mL)": "Mg", "Ferro (ppm)": "Fe", "Manganês (ppm)": "Mn", "Cobre (ppm)": "Cu", "Zinco (ppm)": "Zn", "C.T.C. Efetiva": "CTC"}
        
        def normalizar_parametro(texto_celula):
            if not texto_celula: return None
            texto_celula = texto_celula.replace('\n', ' ')
            for k, v in parametros_interesse.items():
                if k.split('(')[0] in texto_celula: return v
            if "C.T.C. (Cap. Troc." in texto_celula: return "CTC"
            return None

        if header_row_idx != -1:
            for row in tabela_principal[header_row_idx+1:]:
                param_key = normalizar_parametro(row[0])
                if param_key:
                    for col_idx, id_amostra in ids_colunas:
                        valor_raw = row[col_idx]
                        if valor_raw:
                            try:
                                valor_float = float(valor_raw.replace(',', '.'))
                                if param_key == "K": valor_float = valor_float / 391.0
                                resultados[id_amostra][param_key] = valor_float
                            except: continue
                            
    return resultados, mapa_amostras

def gerar_pdf_bytes(resultados, mapa_amostras):
    """Gera o PDF e retorna os bytes dele para download"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Relatório Técnico de Análise de Solo", styles['Title']))
    elements.append(Spacer(1, 24))

    for id_amostra, dados in resultados.items():
        profundidade = mapa_amostras.get(id_amostra, "0-20")
        ref_dados = REFERENCIAS.get(profundidade, REFERENCIAS["0-20"])
        
        elements.append(Paragraph(f"<b>Amostra: {id_amostra}</b> (Profundidade: {profundidade} cm)", styles['Heading2']))
        elements.append(Spacer(1, 6))

        data = [['Parâmetro', 'Unidade Ref.', 'Valor Lab', 'Valor Ref', 'Diferença']]
        ordem = ['P', 'K', 'Ca', 'Mg', 'S', 'B', 'Fe', 'Mn', 'Cu', 'Zn', 'CTC']
        
        for param in ordem:
            if param in dados:
                val_lab = dados[param]
                val_ref = ref_dados.get(param, 0)
                diff = val_lab - val_ref
                unidade = "cmol/dm3" if param in ['K', 'Ca', 'Mg', 'CTC'] else "mg/dm3"
                
                row = [param, unidade, f"{val_lab:.2f}", f"{val_ref:.2f}", f"{diff:+.2f}"]
                data.append(row)

        t = Table(data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 18))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- INTERFACE DO USUÁRIO ---

uploaded_file = st.file_uploader("Escolha o arquivo PDF", type="pdf")

if uploaded_file is not None:
    if st.button("Gerar Relatório"):
        with st.spinner('Processando dados...'):
            try:
                # 1. Processar
                resultados, mapa = processar_pdf_em_memoria(uploaded_file)
                
                # 2. Gerar PDF
                pdf_bytes = gerar_pdf_bytes(resultados, mapa)
                
                st.success("Relatório gerado com sucesso!")
                
                # 3. Botão de Download
                st.download_button(
                    label="📥 Baixar Relatório PDF",
                    data=pdf_bytes,
                    file_name="Relatorio_Solo_Final.pdf",
                    mime="application/pdf"
                )
                
                # (Opcional) Mostrar prévia na tela
                st.subheader("Prévia dos Dados Extraídos")
                st.json(resultados)
                
            except Exception as e:
                st.error(f"Erro ao processar o arquivo: {e}")
