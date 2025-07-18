import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import math
from unidecode import unidecode
import xml.etree.ElementTree as ET

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# FUNÇÕES DE SUPORTE
@st.cache_data
def carregar_dados_excel(caminho_arquivo_excel):
    return pd.read_excel(caminho_arquivo_excel)

@st.cache_data
def carregar_kml(caminho_kml):
    tree = ET.parse(caminho_kml)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}

    nomes, coordenadas = [], []
    for placemark in root.findall(".//kml:Placemark", ns):
        nome = placemark.find("kml:name", ns).text
        coords = placemark.find(".//kml:coordinates", ns).text.strip().split(",")
        nomes.append(nome)
        coordenadas.append((float(coords[0]), float(coords[1])))

    df = pd.DataFrame({
        "FAZENDA": nomes,
        "LONGITUDE": [c[0] for c in coordenadas],
        "LATITUDE": [c[1] for c in coordenadas]
    })
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.LONGITUDE, df.LATITUDE))

def normalizar(texto):
    return unidecode(str(texto)).strip().upper()

def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# CAMINHOS
CAMINHO_EXCEL = "dados.xlsx"
CAMINHO_KML = "mapa.kml"

# CARGA DOS DADOS
df = carregar_dados_excel(CAMINHO_EXCEL)
gdf_fazendas = carregar_kml(CAMINHO_KML)

# NORMALIZAÇÃO
df["UNIDADE_normalized"] = df["UNIDADE"].apply(normalizar)
df["CIDADE_BASE_normalized"] = df["CIDADE_BASE"].apply(normalizar)
gdf_fazendas["FAZENDA_normalized"] = gdf_fazendas["FAZENDA"].apply(normalizar)

# UI - SELEÇÃO
fazenda_selecionada = st.sidebar.selectbox("Selecione uma Fazenda", gdf_fazendas["FAZENDA"].unique())
linha_fazenda = gdf_fazendas[gdf_fazendas["FAZENDA"] == fazenda_selecionada].iloc[0]
coord_fazenda = (linha_fazenda.LATITUDE, linha_fazenda.LONGITUDE)

# DISTÂNCIA ATÉ CIDADES BASE
df["DISTANCIA"] = df.apply(lambda row: haversine(
    linha_fazenda.LONGITUDE, linha_fazenda.LATITUDE,
    float(str(row["COORDENADAS_CIDADE"]).split(",")[1]),
    float(str(row["COORDENADAS_CIDADE"]).split(",")[0])
), axis=1)

cidade_mais_proxima = df.loc[df["DISTANCIA"].idxmin()]
cidade_nome = cidade_mais_proxima["CIDADE_BASE"]
dist_min_km = round(cidade_mais_proxima["DISTANCIA"], 1)

# ANÁLISE DE COBERTURA
unidade = linha_fazenda["FAZENDA_normalized"].split()[0]
analistas_atendem = df[df["UNIDADE_normalized"] == unidade]["ESPECIALISTA"].unique()
analistas_cidade = df[df["CIDADE_BASE_normalized"] == normalizar(cidade_nome)]["ESPECIALISTA"].unique()

# CATEGORIAS
analistas_moradores_e_atendem = list(set(analistas_cidade) & set(analistas_atendem))
analistas_moradores_sem_atender = list(set(analistas_cidade) - set(analistas_atendem))

# LAYOUT COM CONTAINERS
with st.container():
    st.subheader(f"📍 Fazenda selecionada: {fazenda_selecionada}")

    mapa = folium.Map(location=coord_fazenda, zoom_start=8)
    MarkerCluster().add_to(mapa)
    folium.Marker(location=coord_fazenda, popup=fazenda_selecionada, icon=folium.Icon(color="green")).add_to(mapa)

    for _, row in df.iterrows():
        try:
            lat, lon = map(float, str(row["COORDENADAS_CIDADE"]).split(",")[::-1])
            cor = "blue" if row["ESPECIALISTA"] in analistas_moradores_e_atendem else "red"
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                popup=row["ESPECIALISTA"],
                color=cor,
                fill=True
            ).add_to(mapa)
        except:
            continue

    st_folium(mapa, width=1000, height=600)

# EXIBIÇÃO DE RESULTADOS
st.markdown(f"### 🗺️ Cidade mais próxima da fazenda: `{cidade_nome}` ({dist_min_km} km)")
st.markdown(f"### 🟢 Analistas que moram na cidade mais próxima **e atendem esta fazenda:**")
if analistas_moradores_e_atendem:
    st.markdown("- " + "<br>- ".join(analistas_moradores_e_atendem), unsafe_allow_html=True)
else:
    st.markdown("❌ Nenhum analista mora nessa cidade e atende esta fazenda.")

st.markdown(f"### 🟡 Analistas que moram na cidade mais próxima **mas não atendem esta fazenda:**")
if analistas_moradores_sem_atender:
    st.markdown("- " + "<br>- ".join(analistas_moradores_sem_atender), unsafe_allow_html=True)
else:
    st.markdown("✅ Nenhum analista mora nessa cidade sem atender esta fazenda.")
