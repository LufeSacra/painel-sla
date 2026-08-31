import streamlit as st
import polars as pl
import io
import datetime

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Painel de SLA", page_icon="📦", layout="wide")

# ==========================================
# FUNÇÕES DE APOIO
# ==========================================
def normalizar_coluna(nome):
    if not nome:
        return ""
    return str(nome).strip().lower()

def ler_arquivo_bytes(uploaded_file, mapa_colunas_obrigatorias):
    """Lê o arquivo carregado forçando o motor Calamine para economizar memória na nuvem."""
    if uploaded_file is None:
        return pl.DataFrame()
    
    bytes_data = uploaded_file.read()
    nome_arq = uploaded_file.name.lower()
    
    try:
        if nome_arq.endswith(".csv"):
            try:
                df = pl.read_csv(io.BytesIO(bytes_data), separator=";", infer_schema_length=0)
            except Exception:
                df = pl.read_csv(io.BytesIO(bytes_data), separator=",", infer_schema_length=0)
        else:
            # Lendo Excel com o motor de altíssima performance e baixo consumo de memória
            df = pl.read_excel(bytes_data, engine="calamine")
            
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return pl.DataFrame()

    if df.is_empty():
        return pl.DataFrame()

    # Transforma todas as colunas em texto para evitar erros de tipagem
    df = df.select(pl.all().cast(pl.Utf8, strict=False))

    novos_nomes = {c: normalizar_coluna(c) for c in df.columns}
    df = df.rename(novos_nomes)

    cols_selecionar = []
    renomear_alvo = {}
    
    for col_desejada in mapa_colunas_obrigatorias:
        col_norm = normalizar_coluna(col_desejada)
        if col_norm in df.columns:
            cols_selecionar.append(col_norm)
            renomear_alvo[col_norm] = col_desejada
        else:
            encontrou = False
            for col_real in df.columns:
                if col_norm in col_real:
                    cols_selecionar.append(col_real)
                    renomear_alvo[col_real] = col_desejada
                    encontrou = True
                    break
            
            if not encontrou:
                df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(col_norm))
                cols_selecionar.append(col_norm)
                renomear_alvo[col_norm] = col_desejada

    if cols_selecionar:
        return df.select(cols_selecionar).rename(renomear_alvo)
    
    return pl.DataFrame()

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
st.title("📦 Painel de SLA")
st.markdown("CARREGAR OS ARQUIVOS EXTARÍDOS DO JMS.")
st.info("SLA DO DIA")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Força o fuso horário (UTC-3)
    fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
    data_hoje_br = datetime.datetime.now(fuso_br).date()
    
    # Calendário bloqueado na data de hoje
    data_sla = st.date_input("📅 Data de Referência do SLA", data_hoje_br, disabled=True)
    
    st.divider()
    
    st.subheader("Anexar Relatórios")
    arquivo_entregas = st.file_uploader("Upload do Relatório de Entregas", type=["xlsx", "csv"])
    arquivo_bipagens = st.file_uploader("Upload do Relatório de Bipagens", type=["xlsx", "csv"])
    arquivo_prazo = st.file_uploader("Upload do Relatório de Prazos", type=["xlsx", "csv"])
    arquivo_entrega_realizada = st.file_uploader("Upload do Relatório de Entregas Realizadas", type=["xlsx", "csv"])

# ==========================================
# PROCESSAMENTO
# ==========================================
if st.button("🚀 Processar SLA do Dia", use_container_width=True, type="primary"):
    # Agora ele exige que as 4 caixas estejam preenchidas
    if arquivo_entregas and arquivo_bipagens and arquivo_prazo and arquivo_entrega_realizada:
        with st.spinner("Lendo arquivos e cruzando dados... Isso pode levar alguns segundos."):
            
            # --- Suas colunas obrigatórias ---
            colunas_entregas = ["ID Pedido", "Data Entrega", "Status"] 
            colunas_bipagens = ["ID Pedido", "Data Bipagem", "Operador"]
            colunas_prazo = ["ID Pedido", "Data Limite"] # Altere conforme sua planilha
            colunas_realizada = ["ID Pedido", "Data Conclusao"] # Altere conforme sua planilha
            
            # Lendo os 4 arquivos com a função otimizada
            df_entregas = ler_arquivo_bytes(arquivo_entregas, colunas_entregas)
            df_bipagens = ler_arquivo_bytes(arquivo_bipagens, colunas_bipagens)
            df_prazo = ler_arquivo_bytes(arquivo_prazo, colunas_prazo)
            df_realizada = ler_arquivo_bytes(arquivo_entrega_realizada, colunas_realizada)
