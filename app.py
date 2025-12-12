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

# --- REFERÊNCIAS ---
REFERENCIAS = {
    "0-20": { "P": 17.0, "K": 0.35, "Ca": 2.0, "Mg": 0.5, "S": 15.0, "B": 0.5, "Fe": 25.0, "Mn": 8.0, "Cu": 1.2, "Zn": 1.25, "CTC": 5.0 },
    "20-40": { "P": 30.0, "K": 0.38, "Ca": 3.71, "Mg": 1.11, "S": 15.0, "B": 0.6, "Fe": 30.0, "Mn": 8.0, "Cu": 1.2, "Zn": 1.25, "CTC": 9.6 }
}

def processar_pdf(arquivo):
    mapa_amostras = {}
    resultados = {}
    debug_info = []

    # 1. PEGAR OS IDS NO TEXTO
    with pdfplumber.open(arquivo) as pdf:
        texto_pag1 = pdf.pages[0].extract_text()
        for linha in texto_pag1.split('\n'):
            match = re.search(r'Reg.*?(\d+).*?(\d{1,2}-\d{1,2})cm', linha)
            if match:
                id_amostra = match.group(1)
                prof = match.group(2)
                ref_key = "20-40" if "20-40" in prof else "0-20"
                mapa_amostras[id_amostra] = ref_key
                resultados[id_amostra] = {} 
    
    if not mapa_amostras:
        st.error("❌ Não encontrei IDs no texto.")
        return None, None, None

    # 2. EXTRAIR TABELA
    with pdfplumber.open(arquivo) as pdf:
        tabelas = pdf.pages[0].extract_tables()
        if not tabelas: return None, None, None
            
        tabela_principal = max(tabelas, key=len)
        debug_info = tabela_principal

        # Detectar colunas
        header_idx = -1
        col_indices = {}
        ids_para_achar = set(mapa_amostras.keys())
        
        for i, row in enumerate(tabela_principal):
            row_str = [str(c).strip() if c else "" for c in row]
            if any(val in ids_para_achar for val in row_str):
                header_idx = i
                for col_ix, cell_val in enumerate(row_str):
                    if cell_val in ids_para_achar:
                        col_indices[col_ix] = cell_val
                break
        
        if header_idx == -1:
            st.error("❌ IDs não encontrados na tabela.")
            return None, None, debug_info

        # MAPA DE PARÂMETROS
        # Prioridade para match exato
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
            "CTC": "CTC", "C.T.C": "CTC", "C.T.C.": "CTC"
        }

        # TERMOS PROIBIDOS (Para evitar que PST vire P, ou SB vire S)
        termos_proibidos = ["PST", "V%", "M%", "SOMA DAS BASES", "SAT"]

        for row in tabela_principal[header_idx+1:]:
            param_encontrado = None
            
            for cell in row:
                if not cell: continue
                # Limpa o texto: "P (ppm)" -> "P"
                texto_raw = str(cell).upper().replace('\n', ' ').strip()
                texto_limpo = texto_raw.split('(')[0].strip() 
                
                # Ignora se for termo proibido
                if any(proibido in texto_raw for proibido in termos_proibidos):
                    continue

                # 1. Match Exato (Prioridade)
                if texto_limpo in params_map:
                    param_encontrado = params_map[texto_limpo]
                    break
                
                # 2. Match Parcial (Cuidado com P e S)
                for k, v in params_map.items():
                    # Só aceita parcial se o nome for longo (>2 letras) para evitar falsos positivos
                    if len(k) > 2 and k in texto_limpo:
                        param_encontrado = v
                        break
                if param_encontrado: break

            if param_encontrado:
                for col_ix, id_amostra in col_indices.items():
                    # SE JÁ TEM VALOR, NÃO SOBRESCREVE (Proteção extra)
                    if param_encontrado in resultados[id_amostra]:
                        continue
                        
                    try:
                        valor_raw = row[col_ix]
                        if valor_raw:
                            val = float(str(valor_raw).replace(',', '.'))
                            # Conversão de Unidades
                            if param_encontrado == "K": val = val / 391.0
                            
                            resultados[id_amostra][param_encontrado] = val
                    except: pass

    return resultados, mapa_amostras, debug_info

def gerar_pdf(resultados, mapa_amostras):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Relatório Técnico de Análise de Solo", styles['Title']))
    elements.append(Spacer(1, 20))

    if not resultados: return buffer

    ids_ordenados = sorted(resultados.keys())

    for id_amostra in ids_ordenados:
        dados = resultados.get(id_amostra, {})
        if not dados: continue
        
        prof = mapa_amostras.get(id_amostra, "?")
        ref = REFERENCIAS.get(prof, REFERENCIAS["0-20"])
        
        elements.append(Paragraph(f"<b>Amostra: {id_amostra}</b> ({prof} cm)", styles['Heading2']))
        elements.append(Spacer(1, 5))

        data = [['Parâmetro', 'Unid.', 'Lab', 'Meta', 'Dif.']]
        ordem_params = ['P','K','Ca','Mg','S','B','Fe','Mn','Cu','Zn','CTC']
        
        for p in ordem_params:
            if p in dados:
                v_lab = dados[p]
                v_ref = ref.get(p, 0)
                dif = v_lab - v_ref
                unid = "cmol" if p in ['K','Ca','Mg','CTC'] else "mg"
                
                # Formatação Inteligente
                if p == 'K': # Potássio com 3 casas decimais
                    v_lab_str = f"{v_lab:.3f}"
                else:
                    v_lab_str = f"{v_lab:.2f}"
                
                sinal = "+" if dif > 0 else ""
                row = [p, unid, v_lab_str, f"{v_ref:.2f}", f"{sinal}{dif:.2f}"]
                data.append(row)

        if len(data) > 1:
            t = Table(data, colWidths=[80,60,70,70,70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.Color(0.2, 0.4, 0.2)),
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
uploaded_file = st.file_uploader("PDF do Laboratório", type="pdf")

if uploaded_file:
    if st.button("Gerar Relatório"):
        res, mapa, debug_table = processar_pdf(uploaded_file)
        
        if res and any(res.values()):
            pdf_bytes = gerar_pdf(res, mapa)
            st.success("✅ Relatório Corrigido!")
            st.download_button("📥 Baixar PDF", pdf_bytes, "relatorio_solo_v3.pdf", "application/pdf")
            st.json(res)
        else:
            st.error("Erro na leitura.")
            if debug_table: st.dataframe(debug_table)
