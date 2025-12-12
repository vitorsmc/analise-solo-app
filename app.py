import streamlit as st
import pdfplumber
import re
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Análise de Solo Pro", page_icon="🌱")

st.title("🌱 Gerador de Relatórios de Solo")
st.markdown("Faça o upload do PDF e receba o relatório processado.")

# --- REFERÊNCIAS ---
REFERENCIAS = {
    "0-20": { "P": 17.0, "K": 0.35, "Ca": 2.0, "Mg": 0.5, "S": 15.0, "B": 0.5, "Fe": 25.0, "Mn": 8.0, "Cu": 1.2, "Zn": 1.25, "CTC": 5.0 },
    "20-40": { "P": 30.0, "K": 0.38, "Ca": 3.71, "Mg": 1.11, "S": 15.0, "B": 0.6, "Fe": 30.0, "Mn": 8.0, "Cu": 1.2, "Zn": 1.25, "CTC": 9.6 }
}

def processar_pdf(arquivo):
    mapa_amostras = {}
    resultados = {}
    debug_info = []

    with pdfplumber.open(arquivo) as pdf:
        # 1. PEGAR OS IDS E PROFUNDIDADES NO TEXTO (Isso já estava funcionando)
        texto_pag1 = pdf.pages[0].extract_text()
        for linha in texto_pag1.split('\n'):
            # Procura por "Reg. No XXXXXX" e a profundidade
            match = re.search(r'Reg.*?(\d+).*?(\d{1,2}-\d{1,2})cm', linha)
            if match:
                id_amostra = match.group(1)
                profundidade = match.group(2)
                
                # Normaliza a chave da referencia
                ref_key = "20-40" if "20-40" in profundidade else "0-20"
                mapa_amostras[id_amostra] = ref_key
                resultados[id_amostra] = {} # Inicializa dict
    
    if not mapa_amostras:
        st.error("❌ Não encontrei nenhum número de registro (Reg. Nº) no rodapé do PDF.")
        return None, None

    # 2. EXTRAIR DADOS DA TABELA
    with pdfplumber.open(arquivo) as pdf:
        tabelas = pdf.pages[0].extract_tables()
        tabela_principal = max(tabelas, key=len) # Pega a maior tabela
        
        # DEBUG: Guardar a tabela bruta para ver se precisar
        debug_info = tabela_principal

        # -- NOVA LÓGICA DE DETECÇÃO DE CABEÇALHO --
        header_idx = -1
        col_indices = {} # {indice_coluna: id_amostra}
        
        ids_para_achar = set(mapa_amostras.keys())
        
        for i, row in enumerate(tabela_principal):
            # Limpa a linha para string, remove Nones
            row_str = [str(c).strip() if c else "" for c in row]
            
            # Verifica se algum dos IDs que achamos no texto está nesta linha
            # Intersecção entre IDs procurados e valores da linha
            ids_na_linha = [val for val in row_str if val in ids_para_achar]
            
            if ids_na_linha:
                header_idx = i
                # Mapear qual coluna pertence a qual ID
                for col_ix, cell_val in enumerate(row_str):
                    if cell_val in ids_para_achar:
                        col_indices[col_ix] = cell_val
                break
        
        if header_idx == -1:
            st.error("❌ Achei os IDs no texto, mas NÃO achei eles na tabela. Verifique se a tabela do PDF é editável.")
            return None, debug_info

        # 3. LER AS LINHAS DE DADOS
        # Mapeamento de nomes (mais flexível)
        params_map = {
            "P": "P", "FOSFORO": "P",
            "K": "K", "POTASSIO": "K",
            "CA": "Ca", "CALCIO": "Ca",
            "MG": "Mg", "MAGNESIO": "Mg",
            "FE": "Fe", "FERRO": "Fe",
            "MN": "Mn", "MANGANES": "Mn",
            "CU": "Cu", "COBRE": "Cu",
            "ZN": "Zn", "ZINCO": "Zn",
            "B": "B", "BORO": "B",
            "S": "S", "ENXOFRE": "S",
            "CTC": "CTC", "C.T.C": "CTC"
        }

        for row in tabela_principal[header_idx+1:]:
            if not row[0]: continue
            
            # Limpeza do nome do parâmetro (pega primeira palavra, upper case)
            # Ex: "pH (em água)" -> "PH" | "P (ppm)" -> "P"
            nome_original = str(row[0]).strip()
            # Pega o que está antes do parenteses e tira espaços
            nome_chave = nome_original.split('(')[0].strip().upper() 
            
            # Tenta achar no mapa, se não der, tenta match parcial
            param_oficial = params_map.get(nome_chave)
            
            # Fallback: Se não achou exato, procura substring (ex: "C.T.C. Efetiva")
            if not param_oficial:
                for k, v in params_map.items():
                    if k in nome_chave:
                        param_oficial = v
                        break
            
            if param_oficial:
                for col_ix, id_amostra in col_indices.items():
                    valor_raw = row[col_ix]
                    if valor_raw:
                        try:
                            val = float(str(valor_raw).replace(',', '.'))
                            if param_oficial == "K": val = val / 391.0
                            resultados[id_amostra][param_oficial] = val
                        except:
                            pass # Valor não numérico, ignora

    return resultados, debug_info

def gerar_pdf(resultados, mapa_amostras):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Relatório Técnico de Análise de Solo", styles['Title']))
    elements.append(Spacer(1, 20))

    if not resultados:
        elements.append(Paragraph("Erro: Sem dados extraídos.", styles['Normal']))
        doc.build(elements)
        buffer.seek(0)
        return buffer

    for id_amostra, dados in resultados.items():
        if not dados: continue # Pula amostras vazias
        
        prof = mapa_amostras.get(id_amostra, "?")
        ref = REFERENCIAS.get(prof, REFERENCIAS["0-20"])
        
        elements.append(Paragraph(f"<b>Amostra: {id_amostra}</b> ({prof} cm)", styles['Heading2']))
        elements.append(Spacer(1, 5))

        data = [['Parâmetro', 'Unid.', 'Lab', 'Meta', 'Dif.']]
        
        for p in ['P','K','Ca','Mg','S','B','Fe','Mn','Cu','Zn','CTC']:
            if p in dados:
                v_lab = dados[p]
                v_ref = ref.get(p, 0)
                dif = v_lab - v_ref
                unid = "cmol" if p in ['K','Ca','Mg','CTC'] else "mg"
                
                # Estilo condicional (apenas visual no texto)
                sinal = "+" if dif > 0 else ""
                
                row = [p, unid, f"{v_lab:.2f}", f"{v_ref:.2f}", f"{sinal}{dif:.2f}"]
                data.append(row)

        t = Table(data, colWidths=[80,50,60,60,60])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.Color(0.2, 0.4, 0.2)), # Verde escuro
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- FRONTEND ---
uploaded_file = st.file_uploader("Arraste o PDF aqui", type="pdf")
debug_mode = st.checkbox("Modo Debug (Mostrar tabela bruta)")

if uploaded_file:
    if st.button("Gerar Relatório"):
        res, debug_table = processar_pdf(uploaded_file)
        
        if res:
            pdf_bytes = gerar_pdf(res, res.keys()) # Passando keys como mapa simples temporario
            st.success("Relatório gerado!")
            st.download_button("📥 Baixar PDF", pdf_bytes, "relatorio_solo.pdf", "application/pdf")
            
            # Preview rápido na tela
            st.write("### Prévia dos Resultados:")
            st.json(res)
        
        if debug_mode and debug_table:
            st.warning("⚠️ Visualização da Tabela Bruta (Debug):")
            st.dataframe(debug_table)
