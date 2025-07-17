import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
from streamlit_folium import st_folium

# ================================
# CONFIGURAÇÃO INICIAL
# ================================
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")
st.title("📍 Raio de Atuação dos Analistas")

# ================================
# CARREGAR DADOS
# ================================
@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_analistas.xlsx")  # substitua pelo nome correto
    # Corrige colunas de coordenadas
    df[['LAT', 'LON']] = df['COORDENADAS_CIDADE'].str.split(",", expand=True).astype(float)
    df['ESPECIALISTA'] = df['ESPECIALISTA'].str.strip().str.upper()
    df['GESTOR'] = df['GESTOR'].str.strip().str.upper()
    return df

df = carregar_dados()

# ================================
# BARRAS DE FILTRO
# ================================
col1, col2 = st.columns(2)
with col1:
    gestor_selecionado = st.selectbox("Selecione o GESTOR", options=df['GESTOR'].unique())
with col2:
    especialistas = df[df['GESTOR'] == gestor_selecionado]['ESPECIALISTA'].unique()
    especialista_selecionado = st.selectbox("Selecione o ESPECIALISTA", options=especialistas)

# Filtra o DataFrame com base nas seleções
df_filtro = df[(df['GESTOR'] == gestor_selecionado) & (df['ESPECIALISTA'] == especialista_selecionado)]

# ================================
# CRIAÇÃO DO MAPA
# ================================
m = folium.Map(location=[df_filtro['LAT'].mean(), df_filtro['LON'].mean()], zoom_start=5)
marker_cluster = MarkerCluster().add_to(m)

for _, row in df_filtro.iterrows():
    popup_text = f"""
    <b>Unidade:</b> {row['UNIDADE']}<br>
    <b>Cidade Base:</b> {row['CIDADE_BASE']}<br>
    <b>Especialista:</b> {row['ESPECIALISTA']}<br>
    <b>Gestor:</b> {row['GESTOR']}
    """
    folium.Marker(
        location=[row['LAT'], row['LON']],
        popup=folium.Popup(popup_text, max_width=300),
        icon=folium.Icon(color='blue', icon='user')
    ).add_to(marker_cluster)

# ================================
# EXIBIR O MAPA NO STREAMLIT
# ================================
st_folium(m, width=1000, height=600)
