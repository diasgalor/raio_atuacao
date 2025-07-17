import streamlit as st
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
import math
import pandas as pd
from streamlit_folium import st_folium

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Título da aplicação
st.title("Raio de Atuação dos Analistas")

# Upload do arquivo KML
uploaded_kml = st.file_uploader("Faça upload do arquivo KML", type=["kml"])

# Upload da tabela de analistas (CSV)
uploaded_table = st.file_uploader("Faça upload da tabela de analistas (CSV)", type=["csv"])

if uploaded_kml and uploaded_table:
    try:
        # Ler o arquivo KML
        gdf = gpd.read_file(uploaded_kml, driver='KML')

        # Ler a tabela de analistas
        df_analistas = pd.read_csv(uploaded_table)

        # Verificar se as colunas esperadas estão presentes
        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']
        if not all(col in df_analistas.columns for col in expected_columns):
            st.error("O CSV deve conter as colunas: GESTOR, ESPECIALISTA, CIDADE_BASE, UNIDADE, COORDENADAS_CIDADE")
            st.stop()

        # Dividir a coluna COORDENADAS_CIDADE em Latitude e Longitude
        try:
            df_analistas[['Latitude', 'Longitude']] = df_analistas['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        except Exception as e:
            st.error("Erro ao processar a coluna COORDENADAS_CIDADE. Certifique-se de que está no formato 'latitude, longitude'.")
            st.stop()

        # Função de distância haversine (em km)
        def haversine(lon1, lat1, lon2, lat2):
            R = 6371  # raio da Terra em km
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        # Calcular centroides das unidades no KML
        gdf['centroide'] = gdf.geometry.centroid
        gdf['centroide_lat'] = gdf['centroide'].y
        gdf['centroide_lon'] = gdf['centroide'].x

        # Criar mapa centrado na média das coordenadas dos analistas
        centro_mapa = [df_analistas['Latitude'].mean(), df_analistas['Longitude'].mean()]
        m = folium.Map(location=centro_mapa, zoom_start=6)

        # Adicionar cluster de marcadores
        marker_cluster = MarkerCluster().add_to(m)

        # Adicionar marcadores para cada analista
        for idx, row in df_analistas.iterrows():
            especialista = row['ESPECIALISTA']
            cidade_base = row['CIDADE_BASE']
            unidades = row['UNIDADE'].split(',') if ',' in row['UNIDADE'] else [row['UNIDADE']]  # Suporta múltiplas unidades
            lat = row['Latitude']
            lon = row['Longitude']

            # Calcular distâncias e raios para cada unidade
            popup_text = f"<b>Especialista:</b> {especialista}<br><b>Cidade Base:</b> {cidade_base}<br>"
            max_raio_km = 0  # Raio total (máximo ou soma, dependendo da lógica)
            
            for unidade in unidades:
                unidade = unidade.strip()
                gdf_unidade = gdf[gdf['Name'] == unidade]
                if not gdf_unidade.empty:
                    centroide = gdf_unidade.iloc[0]['centroide']
                    dist_km = haversine(lon, lat, centroide.x, centroide.y)
                    # Usar a distância como raio de atuação (ajuste conforme necessário)
                    raio_km = dist_km  # Ou substitua por um valor fixo, ex.: 50.0
                    max_raio_km = max(max_raio_km, raio_km)  # Usa o maior raio
                    popup_text += f"<b>Unidade {unidade}:</b> Distância ao centro: {dist_km:.2f} km<br>"
                    
                    # Adicionar limites da unidade ao mapa
                    folium.GeoJson(
                        gdf_unidade.geometry.values[0],
                        tooltip=unidade,
                        style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.1}
                    ).add_to(m)
                else:
                    popup_text += f"<b>Unidade {unidade}:</b> Não encontrada no KML<br>"
                    st.warning(f"Unidade {unidade} não encontrada no KML.")

            # Adicionar círculo de raio de atuação (usando o maior raio)
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
    st.info("Por favor, faça upload do arquivo KML e da tabela de analistas para começar.")
