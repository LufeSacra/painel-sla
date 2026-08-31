import streamlit as st
import polars as pl
import io
import datetime
import unicodedata

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Painel de SLA", page_icon="📦", layout="wide")

# ==========================================
# FUNÇÕES DE APOIO (IDÊNTICAS AO VS CODE)
# ==========================================
def normalizar_texto(s) -> str:
    if s is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip().upper()

def normalizar_coluna(col: str) -> str:
    """Remove BOM, acentos, espaços e padroniza os nomes das colunas conforme o VS Code."""
    s = str(col).replace("\ufeff", "").strip()
    nfkd = unicodedata.normalize("NFKD", s)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return sem_acento.replace(" ", "_")

def limpar_nulos(col_name):
    """Helper para limpar 'falsos nulos' para o coalesce."""
    return pl.when(pl.col(col_name).is_in(["", "nan", "None"])).then(None).otherwise(pl.col(col_name))

def ler_arquivo_bytes(uploaded_file, mapa_colunas_obrigatorias):
    """Lê todas as abas usando fastexcel adaptado para Streamlit."""
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
            df = df.select(pl.all().cast(pl.Utf8, strict=False))
        else:
            # BLOCO EXCEL: LER TODAS AS ABAS com fastexcel (AGORA COM OS BYTES PUROS)
            import fastexcel
            wb = fastexcel.read_excel(bytes_data)
            abas_df = []
            for aba in wb.sheet_names:
                df_aba = wb.load_sheet(aba).to_polars()
                if not df_aba.is_empty():
                    df_aba = df_aba.select(pl.all().cast(pl.Utf8, strict=False))
                    abas_df.append(df_aba)
            
            if abas_df:
                df = pl.concat(abas_df, how="diagonal")
            else:
                df = pl.DataFrame()
            
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return pl.DataFrame()

    if df.is_empty():
        return pl.DataFrame()

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
                if col_norm.lower() in col_real.lower():
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
            
    except Exception as e:
        st.error(f"Erro ao ler o arquivo {uploaded_file.name}: {e}")
        return pl.DataFrame()

    if df.is_empty():
        return pl.DataFrame()

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
                if col_norm.lower() in col_real.lower():
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
    """Lê e empilha todos os arquivos jogados na mesma caixa."""
    if not lista_arquivos:
        return pl.DataFrame()
    dfs = []
    for arquivo in lista_arquivos:
        df = ler_arquivo_bytes(arquivo, colunas_obrigatorias)
        if not df.is_empty():
            dfs.append(df)
    if dfs:
        return pl.concat(dfs, how="diagonal") 
    return pl.DataFrame()

# ==========================================
# INTERFACE DO USUÁRIO
# ==========================================
st.title("📦 Painel de SLA - Regional BA")
st.markdown("CARREGAR NA BARRA LATERAL OS ARQUIVOS BAIXADOS DO JMS")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    fuso_br = datetime.timezone(datetime.timedelta(hours=-3))
    data_hoje_br = datetime.datetime.now(fuso_br).date()
    hoje_str = data_hoje_br.strftime("%Y-%m-%d")
    sufixo_dia = data_hoje_br.strftime("%d%m")
    
    data_sla = st.date_input("📅 Data de Referência do SLA", data_hoje_br, disabled=True)
    
    st.divider()
    
    st.subheader("Anexar Relatórios")
    st.caption("Você pode arrastar VÁRIOS arquivos para dentro da caixa correspondente.")
    arquivo_entrega_realizada = st.file_uploader("Carregue os arquivos: Entrega realizada SLA", type=["xlsx", "csv"], accept_multiple_files=True)
    arquivo_bipagens = st.file_uploader("Carregue os arquivos: Bipagens SC 00h à 06h", type=["xlsx", "csv"], accept_multiple_files=True)
    arquivo_entregas = st.file_uploader("Carregue os arquivos: Gestão de Bases", type=["xlsx", "csv"], accept_multiple_files=True)
    arquivo_prazo = st.file_uploader("Carregue os arquivos: Prazos por CEP's", type=["xlsx", "csv"], accept_multiple_files=True)
   

# ==========================================
# PROCESSAMENTO MEGAMATCH (VS CODE LOGIC)
# ==========================================
if st.button("🚀 Processar SLA do Dia", use_container_width=True, type="primary"):
    
    if arquivo_entregas and arquivo_bipagens and arquivo_prazo and arquivo_entrega_realizada:
        with st.spinner("⏳ Empilhando arquivos e aplicando regras de negócio da BA..."):
            
            # --- Definição exata das colunas obrigatórias do VS Code ---
            colunas_bipagem = ["Número_de_pedido_JMS", "CEP_destino", "Parada_anterior_ou_próxima", "Base_Destino", "Base_de_escaneamento", "Município_de_Destino", "Estado_da_cidade_de_destino"]
            colunas_d1 = ["Remessa", "Data_prevista_de_entrega", "Regional_de_entrega", "Entregador", "Cidade_Destino", "Base_de_entrega", "Marca_de_assinatura", "Responsavel_Entrega"]
            colunas_entregas = ["Número_de_pedido_JMS", "Marca_de_assinatura", "Responsável_pela_entrega"]
            colunas_prazos = ["派件城市Cidade_de_entrega", "派件州Estado_de_entrega", "调整后时效Prazo_ajustado"]
            
            # --- Leitura Otimizada ---
            df_bipagem = processar_lista_arquivos(arquivo_bipagens, colunas_bipagem)
            df_d1 = processar_lista_arquivos(arquivo_entrega_realizada, colunas_d1)
            df_entregas = processar_lista_arquivos(arquivo_entregas, colunas_entregas)
            df_prazos = processar_lista_arquivos(arquivo_prazo, colunas_prazos)
            
            if not df_bipagem.is_empty() and not df_d1.is_empty() and not df_entregas.is_empty() and not df_prazos.is_empty():
                
                # --- 03. Gestão de Bases ---
                df_ent_consolidada = (
                    df_entregas
                    .filter(pl.col("Número_de_pedido_JMS").is_not_null() & (pl.col("Número_de_pedido_JMS") != "") & (pl.col("Número_de_pedido_JMS") != "None") & (pl.col("Número_de_pedido_JMS") != "nan"))
                    .group_by("Número_de_pedido_JMS")
                    .agg([
                        pl.col("Marca_de_assinatura").max().alias("Status_Base"),
                        pl.col("Responsável_pela_entrega").max().alias("Resp_Base")
                    ])
                    .rename({"Número_de_pedido_JMS": "PedidoJMS_join"})
                )

                # --- Tabela de Prazos ---
                mapa_cidades = {c: normalizar_texto(c) for c in df_prazos["派件城市Cidade_de_entrega"].unique().to_list() if c}
                mapa_estados = {e: normalizar_texto(e) for e in df_prazos["派件州Estado_de_entrega"].unique().to_list() if e}

                df_prazos_dim = (
                    df_prazos
                    .with_columns([
                        pl.col("派件城市Cidade_de_entrega").replace(mapa_cidades).alias("Cidade_Norm"),
                        pl.col("派件州Estado_de_entrega").replace(mapa_estados).alias("Estado_Norm"),
                        pl.col("调整后时效Prazo_ajustado").cast(pl.Float64, strict=False).alias("PRAZO_FINAL")
                    ])
                    .group_by(["Cidade_Norm", "Estado_Norm"])
                    .agg(pl.col("PRAZO_FINAL").min())
                )

                # --- 01. BIPAGEM SC ---
                mapa_bip_cidades = {c: normalizar_texto(c) for c in df_bipagem["Município_de_Destino"].unique().to_list() if c}
                mapa_bip_estados = {e: normalizar_texto(e) for e in df_bipagem["Estado_da_cidade_de_destino"].unique().to_list() if e}

                dest_ba_fec = ["ATALAIA", "BARRA DE SAO MIGUEL", "CAJUEIRO", "CAPELA", "FELIZ DESERTO", "MACEIO", "MATRIZ DE CAMARAGIBE", "PINDOBA", "VICOSA"]
                dest_dc_mcz = ["ATALAIA", "BARRA DE SAO MIGUEL", "CAJUEIRO", "CAPELA", "FELIZ DESERTO", "MACEIO", "MATRIZ DE CAMARAGIBE", "PINDOBA", "RIBEIRA DO POMBAL", "VICOSA"]
                dest_se_aju = ["ESTANCIA", "ARACAJU", "PALMEIRA DOS INDIOS"]

                df_p1_filtrado = (
                    df_bipagem
                    .with_columns([
                        pl.col("Município_de_Destino").replace(mapa_bip_cidades).alias("Cidade_Norm"),
                        pl.col("Estado_da_cidade_de_destino").replace(mapa_bip_estados).alias("Estado_Norm"),
                        pl.col("Número_de_pedido_JMS").cast(pl.Utf8).str.strip_chars().alias("Remessa_join")
                    ])
                    .join(df_prazos_dim, on=["Cidade_Norm", "Estado_Norm"], how="left")
                    .join(df_ent_consolidada, left_on="Remessa_join", right_on="PedidoJMS_join", how="left")
                    .filter(
                        pl.col("CEP_destino").is_not_null() &
                        (pl.col("CEP_destino") != "") &
                        (~pl.col("Número_de_pedido_JMS").str.contains("-")) &
                        (pl.col("Parada_anterior_ou_próxima") != "BA VDC") &
                        (pl.col("Parada_anterior_ou_próxima") == pl.col("Base_Destino")) &
                        (
                            ((pl.col("Base_de_escaneamento") == "SE AJU") & (pl.col("Estado_da_cidade_de_destino") == "SE") & (pl.col("PRAZO_FINAL") == 0)) |
                            ((pl.col("Base_de_escaneamento") == "BA FEC") & (pl.col("Estado_da_cidade_de_destino") == "BA") & (pl.col("PRAZO_FINAL") == 0)) |
                            ((pl.col("Base_de_escaneamento") == "BA FEC") & (pl.col("Município_de_Destino") == "Feira de Santana")) |
                            ((pl.col("Base_de_escaneamento") == "BA FEC") & pl.col("Base_Destino").is_in(["DEL -AL", "PAV -BA"]) & pl.col("Cidade_Norm").is_in(dest_ba_fec)) |
                            ((pl.col("Base_de_escaneamento") == "DC MCZ-AL") & pl.col("Base_Destino").is_in(["CAL -AL", "CRP -AL", "JGA -AL", "F MCZ-AL", "MDC -AL", "JCN -AL"]) & pl.col("Cidade_Norm").is_in(dest_dc_mcz)) |
                            ((pl.col("Base_de_escaneamento") == "SE AJU") & pl.col("Base_Destino").is_in(["F EST-SE", "CDM -SE", "BUG -SE", "PMI -AL", "F CDM-SE"]) & pl.col("Cidade_Norm").is_in(dest_se_aju))
                        )
                    )
                    .select([
                        pl.col("Número_de_pedido_JMS").alias("Remessa"),
                        pl.lit(hoje_str).alias("Data_Previsao"),
                        pl.col("Município_de_Destino").alias("Cidade"),
                        pl.col("Base_Destino").alias("Base_Entrega"),
                        pl.col("Estado_da_cidade_de_destino").alias("Estado"),
                        pl.col("Resp_Base").alias("Entregador"),
                        pl.col("Status_Base").alias("Status_Bruto"),
                        pl.lit("BIPAGEM SC (00h à 06h)").alias("Origem")
                    ])
                )

                # --- 02. ENTREGA REALIZADA ---
                df_d1_filtrado = (
                    df_d1
                    .with_columns([
                        pl.col("Data_prevista_de_entrega").cast(pl.Utf8).str.slice(0, 10).alias("Data_Prev_Str"),
                        pl.col("Remessa").cast(pl.Utf8).str.strip_chars().alias("Remessa_join")
                    ])
                    .filter((pl.col("Data_Prev_Str") == hoje_str) & (pl.col("Regional_de_entrega") == "BA"))
                    .join(df_ent_consolidada, left_on="Remessa_join", right_on="PedidoJMS_join", how="left")
                    .with_columns([
                        limpar_nulos("Entregador").alias("Entregador"),
                        limpar_nulos("Responsavel_Entrega").alias("Responsavel_Entrega"),
                        limpar_nulos("Marca_de_assinatura").alias("Marca_de_assinatura")
                    ])
                    .select([
                        pl.col("Remessa"),
                        pl.col("Data_Prev_Str").alias("Data_Previsao"),
                        pl.col("Cidade_Destino").alias("Cidade"),
                        pl.col("Base_de_entrega").alias("Base_Entrega"),
                        pl.col("Regional_de_entrega").alias("Estado"),
                        pl.coalesce(["Entregador", "Responsavel_Entrega", "Resp_Base"]).alias("Entregador"),
                        pl.coalesce(["Marca_de_assinatura", "Status_Base"]).alias("Status_Bruto"),
                        pl.lit("ENTREGA REALIZADA").alias("Origem")
                    ])
                )

                # --- Consolidação Geral ---
                df_final = (
                    pl.concat([df_d1_filtrado, df_p1_filtrado])
                    .unique(subset=["Remessa"], keep="first")
                    .sort("Remessa")
                    .with_columns(
                        pl.when(pl.col("Status_Bruto").is_null() | (pl.col("Status_Bruto") == "") | (pl.col("Status_Bruto") == "nan") | (pl.col("Status_Bruto") == "None"))
                        .then(pl.lit("SEM_STATUS"))
                        .otherwise(pl.col("Status_Bruto"))
                        .alias("Status")
                    )
                )

                df_pendentes = (
                    df_final
                    .filter(pl.col("Status") == "SEM_STATUS")
                    .with_columns(
                        ((pl.int_range(0, pl.len()) // 1000) + 1).cast(pl.Utf8).map_elements(lambda x: f"Lista {x}", return_dtype=pl.Utf8).alias("Lista")
                    )
                    .select(["Lista", "Remessa", "Origem", "Base_Entrega", "Cidade", "Estado"])
                )

                st.success(f"✅ Processamento Concluído! \n\n**Base Final:** {len(df_final):,} linhas | **Pendentes:** {len(df_pendentes):,} linhas")
                
                # --- Botões de Download Lado a Lado ---
                col1, col2 = st.columns(2)
                
                csv_final = df_final.write_csv(separator=";")
                col1.download_button(
                    label="📥 Baixar Base Unificada (Final)",
                    data=csv_final,
                    file_name=f"base_sla_unificada_final_{sufixo_dia}.csv",
                    mime="text/csv",
                    type="primary"
                )
                
                csv_pendentes = df_pendentes.write_csv(separator=";")
                col2.download_button(
                    label="📥 Baixar Pendentes Sem Status",
                    data=csv_pendentes,
                    file_name=f"pedidos_pendentes_sem_status_{sufixo_dia}.csv",
                    mime="text/csv"
                )
                
            else:
                st.error("❌ Algumas planilhas estão vazias ou não possuem as colunas obrigatórias após a leitura.")
    else:
        st.warning("⚠️ Por favor, anexe pelo menos um arquivo em TODAS as 4 caixas na barra lateral antes de processar.")
