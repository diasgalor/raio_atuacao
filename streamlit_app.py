import streamlit as st
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
import math
import pandas as pd
import numpy as np
from streamlit_folium import st_folium

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Título da aplicação
st.title("Raio de Atuação dos Analistas")

# Upload do arquivo KML
uploaded_kml = st.file_uploader("Faça upload do arquivo KML", type=["kml"])

# Upload da tabela de analistas (Excel)
uploaded_table = st.file_uploader("Faça upload da tabela de analistas (Excel)", type=["xlsx", "xls"])

if uploaded_kml and uploaded_table:
    try:
        # Ler o arquivo KML
        gdf = gpd.read_file(uploaded_kml, driver='KML')

        # Ler a tabela de analistas (Excel)
        df_analistas = pd.read_excel(uploaded_table)

        # Verificar colunas esperadas
        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']
        if not all(col in df_analistas.columns for col in expected_columns):
            st.error("O arquivo Excel deve conter as colunas: GESTOR, ESPECIALISTA, CIDADE_BASE, UNIDADE, COORDENADAS_CIDADE")
            st.stop()

        # Dividir COORDENADAS_CIDADE em Latitude e Longitude
        try:
            df_analistas[['Latitude', 'Longitude']] = df_analistas['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        except Exception as e:
            st.error("Erro ao processar COORDENADAS_CIDADE. Use o formato 'latitude, longitude'.")
            st.stop()

        # Função para determinar a zona UTM com base na longitude
        def get_utm_zone(longitude):
            zone_number = int((longitude + 180) / 6) + 1
            hemisphere = 'S' if df_analistas['Latitude'].mean() < 0 else 'N'
            return f"EPSG:327{zone_number}" if hemisphere == 'S' else f"EPSG:326{zone_number}"

        # Reprojetar o GeoDataFrame para o sistema UTM
        utm_crs = get_utm_zone(df_analistas['Longitude'].mean())
        gdf_utm = gdf.to_crs(utm_crs)

        # Calcular centroides no CRS projetado
        gdf_utm['centroide'] = gdf_utm.geometry.centroid
        gdf['centroide'] = gdf_utm['centroide'].to_crs(gdf.crs)  # Reprojetar de volta para WGS84
        gdf['centroide_lat'] = gdf['centroide'].y
        gdf['centroide_lon'] = gdf['centroide'].x

        # Função de distância haversine (em km)
        def haversine(lon1, lat1, lon2, lat2):
            R = 6371  # raio da Terra em km
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        # Criar mapa centrado na média das coordenadas dos analistas
        centro_mapa = [df_analistas['Latitude'].mean(), df_analistas['Longitude'].mean()]
        m = folium.Map(location=centro_mapa, zoom_start=6)

        # Adicionar cluster de marcadores
        marker_cluster = MarkerCluster().add_to(m)

        # Adicionar marcadores para cada analista
        for idx, row in df_analistas.iterrows():
            especialista = row['ESPECIALISTA']
            cidade_base = row['CIDADE_BASE']
            unidades = row['UNIDADE'].split(',') if ',' in row['UNIDADE'] else [row['UNIDADE']]
            lat = row['Latitude']
            lon = row['Longitude']

            # Criar ponto para o analista
            ponto_analista = Point(lon, lat)

            # Calcular distâncias e raios
            popup_text = f"<b>Especialista:</b> {especialista}<br><b>Cidade Base:</b> {cidade_base}<br>"
            max_raio_km = 0

            for unidade in unidades:
                unidade = unidade.strip()
                gdf_unidade = gdf[gdf['Name'] == unidade]
                if not gdf_unidade.empty:
                    centroide = gdf_unidade.iloc[0]['centroide']
                    dist_km = haversine(lon, lat, centroide.x, centroide.y)
                    raio_km = dist_km  # Raio baseado na distância (ajuste se necessário)
                    max_raio_km = max(max_raio_km, raio_km)
                    popup_text += f"<b>Unidade {unidade}:</b> Distância ao centro: {dist_km:.2f} km<br>"

                    # Verificar se o analista está dentro do polígono da unidade
                    geom_mask = gdf_unidade.geometry.values[0]
                    is_within = geom_mask.contains(ponto_analista)
                    popup_text += f"<b>Dentro de {unidade}?</b> {'Sim' if is_within else 'Não'}<br>"

                    # Adicionar limites da unidade ao mapa
                    folium.GeoJson(
                        geom_mask,
                        tooltip=unidade,
                        style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.1}
                    ).add_to(m)
                else:
                    popup_text += f"<b>Unidade {unidade}:</b> Não encontrada no KML<br>"
                    st.warning(f"Unidade {unidade} não encontrada no KML.")

            # Adicionar círculo de raio de atuação
            folium.Circle(
                location=[lat, lon],
                radius=max_raio_km * 1000,  # Converter km para metros
                color='blue',
                fill=True,
                fill_opacity=0.2,
                popup=f"Raio de atuação: {max_raio_km:.2f} km"
            ).add_to(m)

            # Adicionar marcador do analista
            folium.Marker(
                location=[lat, lon],
                popup=popup_text,
                tooltip=especialista,
                icon=folium.Icon(color='blue', icon='user')
            ).add_to(marker_cluster)

        # Exibir o mapa no Streamlit
        st.subheader("Mapa Interativo")
        st_folium(m, width=700, height=500)

        # Exibir a tabela de analistas
        st.subheader("Tabela de Analistas")
        st.dataframe(df_analistas[['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']])

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload do arquivo KML e da tabela de analistas (Excel) para começar.")
