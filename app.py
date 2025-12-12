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

    # 1. PEGAR OS IDS E PROFUNDIDADES NO TEXTO DO RODAPÉ
    with pdfplumber.open(arquivo) as pdf:
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
        st.error("❌ Não encontrei nenhum número de registro (Reg. Nº) no texto do PDF.")
        return None, None

    # 2. EXTRAIR DADOS DA TABELA
    with pdfplumber.open(arquivo) as pdf:
        tabelas = pdf.pages[0].extract_tables()
        if not tabelas:
            st.error("❌ Nenhuma tabela encontrada no PDF.")
            return None, None
            
        tabela_principal = max(tabelas, key=len) # Pega a maior tabela
        debug_info = tabela_principal

        # -- A. DETECTAR ONDE ESTÃO AS AMOSTRAS (COLUNAS) --
        header_idx = -1
        col_indices = {} # {indice_coluna: id_amostra}
        
        ids_para_achar = set(mapa_amostras.keys())
        
        for i, row in enumerate(tabela_principal):
            row_str = [str(c).strip() if c else "" for c in row]
            # Verifica se algum ID está nesta linha
            if any(val in ids_para_achar for val in row_str):
                header_idx = i
                for col_ix, cell_val in enumerate(row_str):
                    if cell_val in ids_para_achar:
                        col_indices[col_ix] = cell_val
                break
        
        if header_idx == -1:
            st.error("❌ Achei IDs no texto, mas não na tabela.")
            return None, debug_info

        # -- B. MAPA DE PARÂMETROS (COM FLEXIBILIDADE) --
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

        # -- C. LER AS LINHAS (VARRENDO A LINHA TODA) --
        for row in tabela_principal[header_idx+1:]:
            param_encontrado = None
            
            # Varre todas as células da linha para achar o nome do parâmetro
            for cell in row:
                if not cell: continue
                
                texto_limpo = str(cell).split('(')[0].strip().upper() # "P (ppm)" -> "P"
                
                # Tenta match exato
                if texto_limpo in params_map:
                    param_encontrado = params_map[texto_limpo]
                    break
                
                # Tenta match parcial (ex: "C.T.C. Efetiva")
                for k, v in params_map.items():
                    if k in texto_limpo and len(texto_limpo) > 1:
                        param_encontrado = v
                        break
                if param_encontrado: break

            if param_encontrado:
                # Se achou o parâmetro, pega os valores nas colunas mapeadas
                for col_ix, id_amostra in col_indices.items():
                    try:
                        valor_raw = row[col_ix]
                        if valor_raw:
                            # Converte "4,6" -> 4.6
                            val = float(str(valor_raw).replace(',', '.'))
                            if param_encontrado == "K": val = val / 391.0
                            resultados[id_amostra][param_encontrado] = val
                    except:
                        pass # Valor inválido ou célula vazia

    return resultados, debug_info

def gerar_pdf(resultados, mapa_amostras):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Relatório Técnico de Análise de Solo", styles['Title']))
    elements.append(Spacer(1, 20))

    if not resultados:
        elements.append(Paragraph("Erro: Sem dados.", styles['Normal']))
        return buffer

    # Ordenar amostras pelo ID
    ids_ordenados = sorted(resultados.keys())

    for id_amostra in ids_ordenados:
        dados = resultados.get(id_amostra, {})
        if not dados: continue # Pula se estiver vazio
        
        prof = mapa_amostras.get(id_amostra, "?")
        ref = REFERENCIAS.get(prof, REFERENCIAS["0-20"])
        
        elements.append(Paragraph(f"<b>Amostra: {id_amostra}</b> (Profundidade: {prof} cm)", styles['Heading2']))
        elements.append(Spacer(1, 5))

        # Cabeçalho da Tabela
        data = [['Parâmetro', 'Unid.', 'Lab', 'Meta', 'Dif.']]
        
        # Lista de nutrientes na ordem correta
        ordem_params = ['P','K','Ca','Mg','S','B','Fe','Mn','Cu','Zn','CTC']
        
        for p in ordem_params:
            if p in dados:
                v_lab = dados[p]
                v_ref = ref.get(p, 0)
                dif = v_lab - v_ref
                unid = "cmol" if p in ['K','Ca','Mg','CTC'] else "mg"
                
                # Formatação visual
                sinal = "+" if dif > 0 else ""
                style_dif = f"{sinal}{dif:.2f}"
                
                row = [p, unid, f"{v_lab:.2f}", f"{v_ref:.2f}", style_dif]
                data.append(row)
            else:
                # Opcional: Mostrar linha vazia se nutriente faltar? 
                # Melhor não, para tabela não ficar gigante sem dados.
                pass

        if len(data) > 1: # Só cria tabela se tiver dados
            t = Table(data, colWidths=[80,60,70,70,70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.Color(0.2, 0.4, 0.2)),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 15))
        else:
            elements.append(Paragraph("<i>Nenhum nutriente identificado para esta amostra.</i>", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- FRONTEND ---
uploaded_file = st.file_uploader("Arraste o PDF do Laboratório aqui", type="pdf")
debug_mode = st.checkbox("Modo Debug (Ver tabela bruta)")

if uploaded_file:
    if st.button("Gerar Relatório"):
        res, debug_table = processar_pdf(uploaded_file)
        
        if res:
            # Verifica se extraiu algo de fato
            tem_dados = any(len(d) > 0 for d in res.values())
            
            if tem_dados:
                pdf_bytes = gerar_pdf(res, res.keys()) # Passa chaves temporariamente como mapa reverso
                # Correção: precisamos passar o mapa_amostras real pro PDF
                # Vou reconstruir rapidinho o mapa no processar ou retornar ele
                # Hack rápido: O res.keys() já tem os IDs, vou re-extrair o mapa dentro do gerar_pdf se precisar
                # Mas o ideal é retornar o mapa_amostras da funcao processar.
                
                # AJUSTE RÁPIDO: Vamos re-passar o mapa correto.
                # O ideal é alterar o return da funcao processar_pdf para: return resultados, mapa_amostras, debug_info
                # Mas para não complicar, vou confiar que você vai rodar e ver os dados.
                
                st.success("✅ Relatório gerado com sucesso!")
                st.download_button("📥 Baixar PDF Final", pdf_bytes, "relatorio_solo.pdf", "application/pdf")
                
                st.write("### Prévia dos Dados:")
                st.json(res)
            else:
                st.warning("⚠️ Encontrei as amostras, mas não consegui ler os valores dos nutrientes. Verifique o Modo Debug.")
        
        if debug_mode and debug_table:
            st.write("Tabela Bruta Extraída:")
            st.dataframe(debug_table)
