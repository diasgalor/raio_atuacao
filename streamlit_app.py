import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import xml.etree.ElementTree as ET
from shapely.geometry import Point
import math
from unidecode import unidecode

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")
st.title("📍 Raio de Atuação dos Analistas")

# Função para normalizar texto
def normalize_str(s):
    return unidecode(str(s).strip().upper())

# Função para converter coordenadas do KML
def parse_kml(file):
    tree = ET.parse(file)
    root = tree.getroot()
    namespace = {"kml": "http://www.opengis.net/kml/2.2"}

    data = []
    for placemark in root.findall(".//kml:Placemark", namespace):
        name_elem = placemark.find("kml:name", namespace)
        name = name_elem.text if name_elem is not None else ""

        coord_elem = placemark.find(".//kml:coordinates", namespace)
        if coord_elem is not None:
            coords_text = coord_elem.text.strip()
            lon, lat, *_ = map(float, coords_text.split(","))
            data.append({
                "UNIDADE": normalize_str(name),
                "Latitude": lat,
                "Longitude": lon
            })

    return pd.DataFrame(data)

# Upload dos arquivos
kml_file = st.file_uploader("📂 Faça upload do arquivo KML", type="kml")
excel_file = st.file_uploader("📂 Faça upload da tabela de analistas (Excel)", type=["xlsx", "xls"])

if kml_file and excel_file:
    try:
        # Processa KML
        df_kml = parse_kml(kml_file)
        df_kml["UNIDADE_normalized"] = df_kml["UNIDADE"].apply(normalize_str)

        # Processa Excel
        df_analistas = pd.read_excel(excel_file)
        for col in ['UNIDADE', 'ESPECIALISTA', 'GESTOR', 'CIDADE_BASE']:
            df_analistas[col] = df_analistas[col].astype(str).apply(normalize_str)
        df_analistas["UNIDADE_normalized"] = df_analistas["UNIDADE"].apply(normalize_str)

        # Junta com coordenadas
        df_joined = pd.merge(df_analistas, df_kml, on="UNIDADE_normalized", how="left")

        # Agrupa para remover duplicações por unidade
        df_agrupado = (
            df_joined
            .groupby(['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'Latitude', 'Longitude'])
            .agg(UNIDADES=('UNIDADE', lambda x: list(set(x))),
                 QTD=('UNIDADE', lambda x: len(set(x))))
            .reset_index()
        )

        # Interface com seleção
        gestores_disponiveis = sorted(df_agrupado['GESTOR'].unique())
        gestor_selecionado = st.selectbox("👤 Selecione o GESTOR", gestores_disponiveis)

        df_filtrado = df_agrupado[df_agrupado['GESTOR'] == gestor_selecionado]

        especialistas = sorted(df_filtrado['ESPECIALISTA'].unique())
        especialistas_selecionados = st.multiselect(
            "👨‍🔧 Selecione um ou mais Especialistas (ou deixe vazio para todos)",
            especialistas
        )

        if especialistas_selecionados:
            df_final = df_filtrado[df_filtrado["ESPECIALISTA"].isin(especialistas_selecionados)]
        else:
            df_final = df_filtrado

        # Mapa
        m = folium.Map(location=[-12, -54], zoom_start=5)
        marker_cluster = MarkerCluster().add_to(m)

        for _, row in df_final.iterrows():
            for unidade in row['UNIDADES']:
                lat = row['Latitude']
                lon = row['Longitude']
                popup_text = (
                    f"<b>Gestor:</b> {row['GESTOR']}<br>"
                    f"<b>Especialista:</b> {row['ESPECIALISTA']}<br>"
                    f"<b>Unidade:</b> {unidade}<br>"
                    f"<b>Cidade Base:</b> {row['CIDADE_BASE']}"
                )
                folium.Marker(location=[lat, lon], popup=popup_text).add_to(marker_cluster)

        st.subheader(f"🗺️ Mapa das Unidades Atendidas ({len(df_final)} especialistas)")
        st_data = st_folium(m, width=1000, height=600)

        # Tabela resumo
        for _, row in df_final.iterrows():
            with st.expander(f"🔎 {row['ESPECIALISTA']} - {row['CIDADE_BASE']}"):
                unidades = row['UNIDADES']
                num = len(unidades)
                st.markdown(f"**Unidades Atendidas:** {num}")
                st.table(pd.DataFrame({'Unidade': unidades}))

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {e}")
else:
    st.info("🔁 Aguarde o upload do KML e da planilha de analistas para continuar.")
