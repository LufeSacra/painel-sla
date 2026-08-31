import streamlit as st
import datetime
import unicodedata
import polars as pl
import pandas as pd
import io

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Painel de SLA Diário - Regional BA",
    page_icon="🚀",
    layout="wide"
)

# Funções de normalização e leitura (Motor Polars / Fastexcel / Pandas)
def normalizar_texto(s) -> str:
    if s is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip().upper()

def normalizar_coluna(col: str) -> str:
    s = col.replace("\ufeff", "").strip()
    nfkd = unicodedata.normalize("NFKD", s)
    sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return sem_acento.replace(" ", "_")

def ler_arquivo_bytes(uploaded_file, mapa_colunas_obrigatorias):
    if uploaded_file is None:
        return pl.DataFrame()
    
    bytes_data = uploaded_file.read()
    nome_arq = uploaded_file.name.lower()
    abas_df = []

    try:
        if nome_arq.endswith(".csv"):
            try:
                df = pl.read_csv(io.BytesIO(bytes_data), separator=";", infer_schema_length=0)
            except Exception:
                df = pl.read_csv(io.BytesIO(bytes_data), separator=",", infer_schema_length=0)
            df = df.select(pl.all().cast(pl.Utf8, strict=False))
            abas_df.append(df)
        else:
            # Motor ultrarrápido fastexcel para ler todas as abas direto em Polars
            import fastexcel
            wb = fastexcel.read_excel(io.BytesIO(bytes_data))
            for aba in wb.sheet_names:
                df_aba = wb.load_sheet(aba).to_polars()
                if not df_aba.is_empty():
                    df_aba = df_aba.select(pl.all().cast(pl.Utf8, strict=False))
                    abas_df.append(df_aba)
        
        if not abas_df:
            return pl.DataFrame()
        
        df = pl.concat(abas_df, how="diagonal")
        
    except Exception as e:
        # Fallback de segurança caso o fastexcel precise do Pandas
        try:
            import pandas as pd
            dict_dfs = pd.read_excel(io.BytesIO(bytes_data), sheet_name=None, dtype=str)
            for df_pd in dict_dfs.values():
                if not df_pd.empty:
                    df_aba = pl.from_pandas(df_pd).select(pl.all().cast(pl.Utf8, strict=False))
                    abas_df.append(df_aba)
            df = pl.concat(abas_df, how="diagonal") if abas_df else pl.DataFrame()
        except Exception as err:
            st.error(f"Erro ao ler o arquivo {uploaded_file.name}: {err}")
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

# Layout Visual no Streamlit
st.title("🚀 Painel de SLA Diário - Regional BA")
st.markdown("Basta carregar os arquivos gerados no JMS.")

with st.sidebar:
    st.header("⚙️ Configurações")
    data_sla = st.date_input("📅 Data de Referência do SLA", datetime.date.today(), disabled=True)
    st.info("SLA DO DIA.")

st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    file_bip = st.file_uploader("01. BIPAGEM SC (00h à 06h)", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
    file_ent = st.file_uploader("03. GESTÃO DE BASES", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
with col2:
    file_d1 = st.file_uploader("02. ENTREGA REALIZADA", type=["xlsx", "xls", "csv"], accept_multiple_files=True)
    file_prz = st.file_uploader("4. TABELA DE PRAZOS / CEPS", type=["xlsx", "xls", "csv"])

st.markdown("---")

if st.button("⚡ Processar Relatórios com Alta Velocidade", type="primary", use_container_width=True):
    if not file_bip or not file_d1 or not file_ent or not file_prz:
        st.warning("⚠️ Por favor, anexe arquivos em **todos** os 4 campos antes de processar.")
    else:
        with st.spinner("Processando dados em alta velocidade com Polars... Aguarde."):
            t_inicio = datetime.datetime.now()
            hoje_str = data_sla.strftime("%Y-%m-%d")
            sufixo_dia = data_sla.strftime("%d%m")

            # 1. Leitura de Prazos
            df_prazos = ler_arquivo_bytes(file_prz, ["派件城市Cidade_de_entrega", "派件州Estado_de_entrega", "调整后时效Prazo_ajustado"])

            # 2. Leitura de Gestão de Bases
            dfs_ent = [ler_arquivo_bytes(f, ["Número_de_pedido_JMS", "Marca_de_assinatura", "Responsável_pela_entrega"]) for f in file_ent]
            df_entregas = pl.concat(dfs_ent, how="diagonal") if dfs_ent else pl.DataFrame()

            # 3. Leitura de Entrega Realizada
            dfs_d1 = [ler_arquivo_bytes(f, ["Remessa", "Data_prevista_de_entrega", "Regional_de_entrega", "Entregador", "Cidade_Destino", "Base_de_entrega", "Marca_de_assinatura", "Responsavel_Entrega"]) for f in file_d1]
            df_d1 = pl.concat(dfs_d1, how="diagonal") if dfs_d1 else pl.DataFrame()

            # 4. Leitura de Bipagem
            dfs_bip = [ler_arquivo_bytes(f, ["Número_de_pedido_JMS", "CEP_destino", "Parada_anterior_ou_próxima", "Base_Destino", "Base_de_escaneamento", "Município_de_Destino", "Estado_da_cidade_de_destino"]) for f in file_bip]
            df_bipagem = pl.concat(dfs_bip, how="diagonal") if dfs_bip else pl.DataFrame()

            if df_bipagem.is_empty() or df_d1.is_empty() or df_entregas.is_empty() or df_prazos.is_empty():
                st.error("❌ Erro: Alguma das bases veio vazia ou com colunas incompatíveis.")
            else:
                # Cruzamentos de Alta Velocidade
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

                def limpar_nulos(col_name):
                    return pl.when(pl.col(col_name).is_in(["", "nan", "None"])).then(None).otherwise(pl.col(col_name))

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

                tempo_total = (datetime.datetime.now() - t_inicio).total_seconds()
                st.success(f"✅ Processamento concluído em {tempo_total:.2f} segundos!")

                # Métricas na Tela
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Bipagem SC", f"{len(df_p1_filtrado):,}".replace(",", "."))
                m2.metric("Entrega Realizada", f"{len(df_d1_filtrado):,}".replace(",", "."))
                m3.metric("Total Unificado", f"{len(df_final):,}".replace(",", "."))
                m4.metric("Pendentes Sem Status", f"{len(df_pendentes):,}".replace(",", "."))

                # Conversão para download em CSV
                csv_final = df_final.to_pandas().to_csv(index=False, sep=";").encode("utf-8-sig")
                csv_pendentes = df_pendentes.to_pandas().to_csv(index=False, sep=";").encode("utf-8-sig")

                st.markdown("---")
                st.subheader("📥 Baixar Resultados Prontos")
                
                dcol1, dcol2 = st.columns(2)
                with dcol1:
                    st.download_button(
                        label="💾 Baixar Base Geral Unificada",
                        data=csv_final,
                        file_name=f"base_sla_unificada_final_{sufixo_dia}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with dcol2:
                    st.download_button(
                        label="💾 Baixar Pedidos Pendentes (Sem Status)",
                        data=csv_pendentes,
                        file_name=f"pedidos_pendentes_sem_status_{sufixo_dia}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                # Exibição de Abas com Amostra das Tabelas
                tab1, tab2 = st.tabs(["📋 Prévia - Pendentes Sem Status", "📊 Prévia - Base Geral Unificada"])
                with tab1:
                    st.dataframe(df_pendentes.head(100).to_pandas(), use_container_width=True)
                with tab2:
                    st.dataframe(df_final.head(100).to_pandas(), use_container_width=True)
