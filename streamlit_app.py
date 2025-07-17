import streamlit as st
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
import math
import pandas as pd
from unidecode import unidecode
import xml.etree.ElementTree as ET
from streamlit_folium import st_folium

st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

def extrair_dados_kml(kml_content):
    try:
        tree = ET.fromstring(kml_content)
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        dados = []
        for placemark in tree.findall('.//kml:Placemark', ns):
            props = {}
            name_elem = placemark.find('kml:name', ns)
            props['Name'] = name_elem.text if name_elem is not None else None
            for simple_data in placemark.findall('.//kml:SimpleData', ns):
                props[simple_data.get('name')] = simple_data.text

            geometry = None
            polygon_elem = placemark.find('.//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if polygon_elem is not None:
                coords = [tuple(map(float, c.split(','))) for c in polygon_elem.text.strip().split()]
                from shapely.geometry import Polygon
                try:
                    geometry = Polygon([(c[0], c[1]) for c in coords])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords = [tuple(map(float, c.split(','))) for c in line_elem.text.strip().split()]
                from shapely.geometry import LineString
                try:
                    geometry = LineString([(c[0], c[1]) for c in coords])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords = tuple(map(float, point_elem.text.strip().split(',')))
                try:
                    geometry = Point(coords[0], coords[1])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
            if geometry:
                dados.append({**props, 'geometry': geometry})

        if not dados:
            st.warning("Nenhuma geometria válida encontrada no KML.")
            return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

        return gpd.GeoDataFrame(dados, crs="EPSG:4326")

    except Exception as e:
        st.error(f"Erro ao processar KML: {e}")
        return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

def formatar_nome(nome):
    return unidecode(nome.upper()) if isinstance(nome, str) else nome

st.title("Raio de Atuação dos Analistas")

uploaded_kml = st.file_uploader("Faça upload do arquivo KML", type=["kml"])
uploaded_table = st.file_uploader("Faça upload da tabela de analistas (Excel)", type=["xlsx", "xls"])

if uploaded_kml and uploaded_table:
    try:
        kml_content = uploaded_kml.read().decode('utf-8')
        gdf = extrair_dados_kml(kml_content)

        st.subheader("Metadados do KML")
        st.write("Colunas disponíveis no KML:")
        st.write(gdf.columns.tolist())
        st.write("Primeiras linhas do KML (sem coluna geometry):")
        non_geometry_columns = [col for col in gdf.columns if col != 'geometry']
        st.dataframe(gdf[non_geometry_columns].head())

        kml_name_column = st.selectbox(
            "Selecione a coluna do KML que contém os nomes das unidades/fazendas:",
            gdf.columns.tolist(),
            index=gdf.columns.tolist().index('NOME_FAZ' if 'NOME_FAZ' in gdf.columns else 'Name') if 'NOME_FAZ' in gdf.columns or 'Name' in gdf.columns else 0
        )
        gdf['Name_normalized'] = gdf[kml_name_column].apply(formatar_nome)

        df_analistas = pd.read_excel(uploaded_table)
        df_analistas.columns = df_analistas.columns.str.strip()

        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']
        missing_columns = [col for col in expected_columns if col not in df_analistas.columns]
        if missing_columns:
            st.error(f"O arquivo Excel está faltando as colunas: {', '.join(missing_columns)}")
            st.stop()

        try:
            df_analistas[['Latitude', 'Longitude']] = df_analistas['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        except Exception:
            st.error("Erro ao processar COORDENADAS_CIDADE. Use o formato 'latitude, longitude'.")
            st.stop()

        df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE'].apply(formatar_nome)
        if 'FAZENDA' in df_analistas.columns:
            df_analistas['FAZENDA_normalized'] = df_analistas['FAZENDA'].apply(formatar_nome)
            st.write("Coluna FAZENDA encontrada no Excel. Usando para correspondência.")

        def get_utm_zone(longitude):
            zone_number = int((longitude + 180) / 6) + 1
            hemisphere = 'S' if df_analistas['Latitude'].mean() < 0 else 'N'
            return f"EPSG:327{zone_number}" if hemisphere == 'S' else f"EPSG:326{zone_number}"

        utm_crs = get_utm_zone(df_analistas['Longitude'].mean())
        gdf_utm = gdf.to_crs(utm_crs)
        gdf_utm['centroide'] = gdf_utm.geometry.centroid
        gdf['centroide'] = gdf_utm['centroide'].to_crs(gdf.crs)
        gdf['centroide_lat'] = gdf['centroide'].y
        gdf['centroide_lon'] = gdf['centroide'].x

        def haversine(lon1, lat1, lon2, lat2):
            R = 6371
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            return R * 2 * math.asin(math.sqrt(a))

        centro_mapa = [df_analistas['Latitude'].mean(), df_analistas['Longitude'].mean()]
        m = folium.Map(location=centro_mapa, zoom_start=6)
        marker_cluster = MarkerCluster().add_to(m)

        st.subheader("Gestores e Especialistas")
        gestores = df_analistas['GESTOR'].unique()
        for gestor in gestores:
            with st.expander(f"Gestor: {gestor}"):
                especialistas = df_analistas[df_analistas['GESTOR'] == gestor]
                for idx, row in especialistas.iterrows():
                    especialista = row['ESPECIALISTA']
                    cidade_base = row['CIDADE_BASE']
                    unidades = [u.strip() for u in row['UNIDADE_normalized'].split(',')]
                    fazendas = [f.strip() for f in row['FAZENDA_normalized'].split(',')] if 'FAZENDA_normalized' in row and pd.notna(row['FAZENDA_normalized']) else unidades
                    lat, lon = row['Latitude'], row['Longitude']
                    if pd.isna(lat) or pd.isna(lon): continue

                    ponto_analista = Point(lon, lat)
                    popup_text = f"<b>Especialista:</b> {especialista}<br><b>Cidade Base:</b> {cidade_base}<br>"
                    max_raio_km = 0

                    for unidade in unidades:
                        gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                        if not gdf_unidade.empty:
                            centroide = gdf_unidade.iloc[0]['centroide']
                            dist_km = haversine(lon, lat, centroide.x, centroide.y)
                            max_raio_km = max(max_raio_km, dist_km)
                            geom_mask = gdf_unidade.geometry.values[0]
                            is_within = geom_mask.contains(ponto_analista)
                            popup_text += f"<b>{unidade}</b>: {dist_km:.2f} km | Dentro? {'Sim' if is_within else 'Não'}<br>"
                            folium.GeoJson(geom_mask, tooltip=unidade, style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.1}).add_to(m)

                    folium.Circle([lat, lon], radius=max_raio_km*1000, color='blue', fill=True, fill_opacity=0.2).add_to(m)
                    folium.Marker([lat, lon], popup=popup_text, tooltip=especialista, icon=folium.Icon(color='blue', icon='user')).add_to(marker_cluster)

        st.subheader("Mapa Interativo")
        st_folium(m, width=700, height=500)

        st.subheader("Tabela de Analistas")
        st.dataframe(df_analistas[['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE'] + (['FAZENDA'] if 'FAZENDA' in df_analistas.columns else [])])

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload do arquivo KML e da tabela de analistas (Excel) para começar.")
