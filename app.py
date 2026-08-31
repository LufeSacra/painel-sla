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
    """Lê um único arquivo forçando o motor Calamine para economizar memória na nuvem."""
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
            df = pl.read_excel(bytes_data, engine="calamine")
            
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return pl.DataFrame()

    if df.is_empty():
        return pl.DataFrame()

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

def processar_lista_arquivos(lista_arquivos, colunas_obrigatorias):
    """Lê vários arquivos da mesma caixinha e empilha todos em um só DataFrame."""
    if not lista_arquivos:
        return pl.DataFrame()
    
    dfs = []
    for arquivo in lista_arquivos:
        df = ler_arquivo_bytes(arquivo, colunas_obrigatorias)
        if not df.is_empty():
            dfs.append(df)
    
    if dfs:
        # how="diagonal" empilha de forma inteligente mesmo se a ordem das colunas mudar
        return pl.concat(dfs, how="diagonal") 
    return pl.DataFrame()

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
st.title("📦 Painel de SLA")
st.markdown("CARREGAR NA BARRA LATERAL OS ARQUIVOS BAIXADOS DO JMS")
# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
    data_hoje_br = datetime.datetime.now(fuso_br).date()
    
    data_sla = st.date_input("📅 Data de Referência do SLA", data_hoje_br, disabled=True)
    
    st.divider()
    
    st.subheader("Anexar Relatórios")
    st.caption("Arraste aqui os arquivos para dentro da caixa correspondente.")
    
    # accept_multiple_files=True permite jogar vários arquivos de uma vez
    arquivo_entregas = st.file_uploader("Carregue os arquivos: Gestão de Bases", type=["xlsx", "csv"], accept_multiple_files=True)
    arquivo_bipagens = st.file_uploader("Carregue os arquivos: Bipagens SC 00h à 06h", type=["xlsx", "csv"], accept_multiple_files=True)
    arquivo_prazo = st.file_uploader("Carregue os arquivos: Prazos por CEP's", type=["xlsx", "csv"], accept_multiple_files=True)
    arquivo_entrega_realizada = st.file_uploader("Carregue os arquivos: Entrega realizada "(SLA)" ", type=["xlsx", "csv"], accept_multiple_files=True)

# ==========================================
# PROCESSAMENTO
# ==========================================
if st.button("🚀 Processar SLA do Dia", use_container_width=True, type="primary"):
    
    # Verifica se pelo menos um arquivo foi colocado em CADA uma das 4 caixas
    if arquivo_entregas and arquivo_bipagens and arquivo_prazo and arquivo_entrega_realizada:
        with st.spinner("Empilhando arquivos e cruzando dados... Isso pode levar alguns segundos."):
            
            colunas_entregas = ["ID Pedido", "Data Entrega", "Status"] 
            colunas_bipagens = ["ID Pedido", "Data Bipagem", "Operador"]
            colunas_prazo = ["ID Pedido", "Data Limite"] 
            colunas_realizada = ["ID Pedido", "Data Conclusao"] 
            
            # O processador agora junta todos os arquivos de cada caixa antes de continuar
            df_entregas = processar_lista_arquivos(arquivo_entregas, colunas_entregas)
            df_bipagens = processar_lista_arquivos(arquivo_bipagens, colunas_bipagens)
            df_prazo = processar_lista_arquivos(arquivo_prazo, colunas_prazo)
            df_realizada = processar_lista_arquivos(arquivo_entrega_realizada, colunas_realizada)
            
            if not df_entregas.is_empty() and not df_bipagens.is_empty() and not df_prazo.is_empty() and not df_realizada.is_empty():
                
                # Exemplo de Cruzamento (Merge) via Polars
                df_final = df_entregas.join(df_bipagens, on="ID Pedido", how="left")
                # Aqui você pode adicionar as lógicas de join com df_prazo e df_realizada depois
                
                st.success("✅ Processamento concluído com sucesso!")
                
                st.dataframe(df_final.head(10))
                
                csv = df_final.write_csv(separator=";")
                st.download_button(
                    label="📥 Baixar Relatório Final (CSV)",
                    data=csv,
                    file_name=f"SLA_Final_{data_hoje_br.strftime('%d%m%Y')}.csv",
                    mime="text/csv",
                    type="primary"
                )
            else:
                st.error("Algumas planilhas estão vazias ou não possuem as colunas obrigatórias.")
    else:
        st.warning("⚠️ Por favor, anexe pelo menos um arquivo em TODAS as 4 caixas na barra lateral antes de processar.")
