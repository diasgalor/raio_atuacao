import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
import folium
from folium.plugins import MarkerCluster
import math
from unidecode import unidecode
import xml.etree.ElementTree as ET
from streamlit_folium import st_folium
import json

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

st.title("Raio de Atuação dos Analistas")

# Upload dos arquivos
with st.sidebar:
    kml_file = st.file_uploader("Arquivo KML das Unidades", type=["kml"])
    xlsx_file = st.file_uploader("Planilha Excel dos Analistas", type=["xlsx"])
    geojson_file = st.file_uploader("GeoJSON com Cidades Base", type=["geojson", "json"])

if kml_file and xlsx_file and geojson_file:
    try:
        # ========================
        # Leitura e normalização
        # ========================
        tree = ET.parse(kml_file)
        root = tree.getroot()
        namespaces = {'kml': 'http://www.opengis.net/kml/2.2'}

        placemarks = root.findall('.//kml:Placemark', namespaces)
        dados = []
        for placemark in placemarks:
            nome = placemark.find('kml:name', namespaces).text
            polygon = placemark.find('.//kml:coordinates', namespaces)
            if polygon is not None:
                coords_text = polygon.text.strip().split()
                coords = [tuple(map(float, coord.split(',')[:2])) for coord in coords_text]
                if len(coords) > 2:
                    poly = gpd.GeoSeries([gpd.Polygon(coords)], crs="EPSG:4326")[0]
                    dados.append({"name": nome, "geometry": poly})

        gdf_unidades = gpd.GeoDataFrame(dados, crs="EPSG:4326")
        gdf_unidades["UNIDADE_normalized"] = gdf_unidades["name"].apply(lambda x: unidecode(x.upper().strip()))

        df_analistas = pd.read_excel(xlsx_file)
        df_analistas["UNIDADE_normalized"] = df_analistas["UNIDADE"].apply(lambda x: unidecode(str(x).upper().strip()))

        # ========================
        # Mapa interativo
        # ========================
        with st.container():
            st.subheader("📍 Mapa de Unidades e Analistas")
            mapa = folium.Map(location=[-16.5, -52], zoom_start=5)

            # Unidades
            for _, row in gdf_unidades.iterrows():
                folium.GeoJson(row["geometry"], name=row["UNIDADE_normalized"]).add_to(mapa)

            # Agrupar analistas por cidade base
            analistas_coords = []
            for _, row in df_analistas.iterrows():
                try:
                    lat, lon = map(float, str(row["COORDENADAS_CIDADE"]).split(","))
                    analistas_coords.append((lat, lon, row["ESPECIALISTA"], row["UNIDADE_normalized"]))
                except:
                    continue

            cluster = MarkerCluster().add_to(mapa)
            for lat, lon, nome, unidade in analistas_coords:
                folium.Marker(location=[lat, lon], popup=f"{nome} - {unidade}").add_to(cluster)

            st_folium(mapa, width=1000, height=500)

        # ========================
        # Gráfico por maior distância
        # ========================
        st.subheader("📊 Maior Distância por Analista/Unidade")

        df_analistas["LAT"] = df_analistas["COORDENADAS_CIDADE"].apply(lambda x: float(str(x).split(",")[0]))
        df_analistas["LON"] = df_analistas["COORDENADAS_CIDADE"].apply(lambda x: float(str(x).split(",")[1]))
        df_analistas["geometry"] = [Point(lon, lat) for lat, lon in zip(df_analistas["LAT"], df_analistas["LON"])]
        gdf_analistas = gpd.GeoDataFrame(df_analistas, geometry="geometry", crs="EPSG:4326")

        resultados = []
        for _, row in gdf_analistas.iterrows():
            unidade = row["UNIDADE_normalized"]
            cidade_geom = row["geometry"]

            unidade_geom = gdf_unidades[gdf_unidades["UNIDADE_normalized"] == unidade]
            if not unidade_geom.empty:
                dist_km = cidade_geom.distance(unidade_geom.geometry.iloc[0].centroid) * 111
                resultados.append({
                    "ESPECIALISTA": row["ESPECIALISTA"],
                    "UNIDADE": unidade,
                    "DISTANCIA_KM": round(dist_km, 2)
                })

        df_dist = pd.DataFrame(resultados)

        # Mostrar apenas a maior distância por analista/unidade
        df_max = df_dist.groupby(["ESPECIALISTA", "UNIDADE"]).agg({"DISTANCIA_KM": "max"}).reset_index()
        st.dataframe(df_max)

        # ========================
        # Cidades base mais próximas das unidades
        # ========================
        cidades_data = json.load(geojson_file)
        cidades_df = pd.DataFrame([
            {
                "CIDADE": f["properties"]["name"],
                "LAT": f["geometry"]["coordinates"][1],
                "LON": f["geometry"]["coordinates"][0],
            }
            for f in cidades_data["features"]
        ])

        cidades_df["geometry"] = [Point(lon, lat) for lon, lat in zip(cidades_df["LON"], cidades_df["LAT"])]
        gdf_cidades = gpd.GeoDataFrame(cidades_df, geometry="geometry", crs="EPSG:4326")

        st.subheader("🏙️ Cidade base mais próxima de cada unidade")

        resultados = []
        for unidade_norm, unidade_geom in gdf_unidades.groupby("UNIDADE_normalized"):
            ponto_central = unidade_geom.geometry.iloc[0].centroid
            distancias = gdf_cidades.geometry.distance(ponto_central)
            idx_min = distancias.idxmin()
            cidade_info = gdf_cidades.loc[idx_min]
            distancia_km = distancias[idx_min] * 111
            resultados.append({
                "UNIDADE": unidade_norm,
                "CIDADE_MAIS_PROXIMA": cidade_info["CIDADE"],
                "DISTANCIA_KM": round(distancia_km, 2),
            })

        df_resultado = pd.DataFrame(resultados).sort_values("DISTANCIA_KM")
        st.dataframe(df_resultado)

        # ========================
        # Analistas que moram em cidades que não atendem
        # ========================
        st.subheader("🚫 Analistas que moram em cidades que não atendem")

        analistas_cidade = df_analistas.copy()
        analistas_cidade["UNIDADE_DO_CIDADE_BASE"] = None

        for i, row in analistas_cidade.iterrows():
            cidade_point = row["geometry"]
            for _, unidade_row in gdf_unidades.iterrows():
                if unidade_row.geometry.contains(cidade_point):
                    analistas_cidade.at[i, "UNIDADE_DO_CIDADE_BASE"] = unidade_row["UNIDADE_normalized"]
                    break

        filtro = analistas_cidade["UNIDADE_normalized"] != analistas_cidade["UNIDADE_DO_CIDADE_BASE"]
        st.dataframe(analistas_cidade[filtro][["ESPECIALISTA", "CIDADE_BASE", "UNIDADE", "UNIDADE_DO_CIDADE_BASE"]])

    except Exception as e:
        st.error(f"Erro ao processar os dados: {e}")
