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

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Função para extrair metadados e geometria do KML
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

            # Extrair geometria
            geometry = None
            polygon_elem = placemark.find('.//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if polygon_elem is not None:
                coords_text = polygon_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                from shapely.geometry import Polygon
                try:
                    geometry = Polygon([(c[0], c[1]) for c in coords])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords_text = line_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                from shapely.geometry import LineString
                try:
                    geometry = LineString([(c[0], c[1]) for c in coords])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords_text = point_elem.text.strip()
                coords = tuple(map(float, coords_text.split(',')))
                from shapely.geometry import Point
                try:
                    geometry = Point(coords[0], coords[1])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            if geometry:
                dados.append({**props, 'geometry': geometry})

        if not dados:
            st.warning("Nenhuma geometria válida encontrada no KML.")
            return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

        gdf = gpd.GeoDataFrame(dados, crs="EPSG:4326")
        return gdf

    except Exception as e:
        st.error(f"Erro ao processar KML: {e}")
        return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

# Função para padronizar nomes
def formatar_nome(nome):
    return unidecode(nome.upper()) if isinstance(nome, str) else nome

# Função para normalizar coordenadas
def normalizar_coordenadas(valor, scale_factor=1000000000):
    if isinstance(valor, str):
        try:
            valor_float = float(valor.replace(',', '')) / scale_factor
            return round(valor_float, 6)
        except ValueError:
            st.warning(f"Não foi possível converter o valor: {valor}")
            return None
    return None

# Título da aplicação
st.title("Raio de Atuação dos Analistas")

# Upload dos arquivos
uploaded_kml = st.file_uploader("Faça upload do arquivo KML", type=["kml"])
uploaded_table = st.file_uploader("Faça upload da tabela de analistas (Excel)", type=["xlsx", "xls"])

if uploaded_kml and uploaded_table:
    try:
        # Ler o arquivo KML
        kml_content = uploaded_kml.read().decode('utf-8')
        gdf = extrair_dados_kml(kml_content)

        # Exibir metadados do KML
        st.subheader("Metadados do KML")
        st.write("Colunas disponíveis no KML:")
        st.write(gdf.columns.tolist())
        st.write("Primeiras linhas do KML:")
        st.dataframe(gdf.head())

        # Selecionar coluna com nomes das unidades/fazendas
        kml_name_column = st.selectbox(
            "Selecione a coluna do KML que contém os nomes das unidades/fazendas:",
            gdf.columns.tolist(),
            index=gdf.columns.tolist().index('NOME_FAZ' if 'NOME_FAZ' in gdf.columns else 'Name') if 'NOME_FAZ' in gdf.columns or 'Name' in gdf.columns else 0
        )
        gdf['Name_normalized'] = gdf[kml_name_column].apply(formatar_nome)

        # Ler a tabela de analistas
        df_analistas = pd.read_excel(uploaded_table, dtype={'VL_LATITUDE': str, 'VL_LONGITUDE': str})
        df_analistas.columns = df_analistas.columns.str.strip()

        # Verificar colunas esperadas
        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'VL_LATITUDE', 'VL_LONGITUDE']
        if not all(col in df_analistas.columns for col in expected_columns):
            st.error("O arquivo Excel deve conter as colunas: GESTOR, ESPECIALISTA, CIDADE_BASE, UNIDADE, VL_LATITUDE, VL_LONGITUDE")
            st.stop()

        # Normalizar coordenadas
        df_analistas['Latitude'] = df_analistas['VL_LATITUDE'].apply(normalizar_coordenadas)
        df_analistas['Longitude'] = df_analistas['VL_LONGITUDE'].apply(normalizar_coordenadas)
        df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE'].apply(formatar_nome)

        # Verificar coluna FAZENDA
        if 'FAZENDA' in df_analistas.columns:
            df_analistas['FAZENDA_normalized'] = df_analistas['FAZENDA'].apply(formatar_nome)
            st.write("Coluna FAZENDA encontrada no Excel. Usando para correspondência.")

        # Função para determinar a zona UTM
        def get_utm_zone(longitude):
            zone_number = int((longitude + 180) / 6) + 1
            hemisphere = 'S' if df_analistas['Latitude'].mean() < 0 else 'N'
            return f"EPSG:327{zone_number}" if hemisphere == 'S' else f"EPSG:326{zone_number}"

        # Reprojetar para UTM
        utm_crs = get_utm_zone(df_analistas['Longitude'].mean())
        gdf_utm = gdf.to_crs(utm_crs)
        gdf_utm['centroide'] = gdf_utm.geometry.centroid
        gdf['centroide'] = gdf_utm['centroide'].to_crs(gdf.crs)
        gdf['centroide_lat'] = gdf['centroide'].y
        gdf['centroide_lon'] = gdf['centroide'].x

        # Função de distância haversine
        def haversine(lon1, lat1, lon2, lat2):
            R = 6371
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        # Criar mapa
        centro_mapa = [df_analistas['Latitude'].mean(), df_analistas['Longitude'].mean()]
        m = folium.Map(location=centro_mapa, zoom_start=6)
        marker_cluster = MarkerCluster().add_to(m)

        # Cards para gestores
        st.subheader("Gestores e Especialistas")
        gestores = df_analistas['GESTOR'].unique()
        for gestor in gestores:
            with st.expander(f"Gestor: {gestor}"):
                especialistas = df_analistas[df_analistas['GESTOR'] == gestor][['ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'Latitude', 'Longitude']]
                for idx, row in especialistas.iterrows():
                    especialista = row['ESPECIALISTA']
                    cidade_base = row['CIDADE_BASE']
                    unidades = row['UNIDADE_normalized'].split(',') if ',' in row['UNIDADE_normalized'] else [row['UNIDADE_normalized']]
                    fazendas = row['FAZENDA_normalized'].split(',') if 'FAZENDA_normalized' in df_analistas.columns and pd.notna(row['FAZENDA_normalized']) else unidades
                    lat = row['Latitude']
                    lon = row['Longitude']

                    if pd.isna(lat) or pd.isna(lon):
                        st.warning(f"Coordenadas inválidas para {especialista}. Ignorando.")
                        continue

                    ponto_analista = Point(lon, lat)
                    popup_text = f"<b>Especialista:</b> {especialista}<br><b>Cidade Base:</b> {cidade_base}<br>"
                    max_raio_km = 0

                    # Processar unidades
                    for unidade in unidades:
                        unidade = unidade.strip()
                        gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                        if not gdf_unidade.empty:
                            centroide = gdf_unidade.iloc[0]['centroide']
                            dist_km = haversine(lon, lat, centroide.x, centroide.y)
                            raio_km = dist_km
                            max_raio_km = max(max_raio_km, raio_km)
                            popup_text += f"<b>Unidade {unidade}:</b> Distância ao centro: {dist_km:.2f} km<br>"
                            geom_mask = gdf_unidade.geometry.values[0]
                            is_within = geom_mask.contains(ponto_analista)
                            popup_text += f"<b>Dentro de {unidade}?</b> {'Sim' if is_within else 'Não'}<br>"
                            folium.GeoJson(
                                geom_mask,
                                tooltip=unidade,
                                style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.1}
                            ).add_to(m)
                        else:
                            popup_text += f"<b>Unidade {unidade}:</b> Não encontrada no KML<br>"
                            st.warning(f"Unidade {unidade} não encontrada no KML. Verifique a coluna '{kml_name_column}'.")

                    # Processar fazendas
                    for fazenda in fazendas:
                        fazenda = fazenda.strip()
                        gdf_fazenda = gdf[gdf['Name_normalized'] == fazenda]
                        if not gdf_fazenda.empty:
                            centroide = gdf_fazenda.iloc[0]['centroide']
                            dist_km = haversine(lon, lat, centroide.x, centroide.y)
                            raio_km = dist_km
                            max_raio_km = max(max_raio_km, raio_km)
                            popup_text += f"<b>Fazenda {fazenda}:</b> Distância ao centro: {dist_km:.2f} km<br>"
                            geom_mask = gdf_fazenda.geometry.values[0]
                            is_within = geom_mask.contains(ponto_analista)
                            popup_text += f"<b>Dentro de {fazenda}?</b> {'Sim' if is_within else 'Não'}<br>"
                            folium.GeoJson(
                                geom_mask,
                                tooltip=fazenda,
                                style_function=lambda x: {'fillColor': 'orange', 'color': 'orange', 'fillOpacity': 0.1}
                            ).add_to(m)
                        else:
                            popup_text += f"<b>Fazenda {fazenda}:</b> Não encontrada no KML<br>"
                            st.warning(f"Fazenda {fazenda} não encontrada no KML. Verifique a coluna '{kml_name_column}'.")

                    # Adicionar círculo de raio
                    folium.Circle(
                        location=[lat, lon],
                        radius=max_raio_km * 1000,
                        color='blue',
                        fill=True,
                        fill_opacity=0.2,
                        popup=f"Raio de atuação: {max_raio_km:.2f} km"
                    ).add_to(m)

                    # Adicionar marcador
                    folium.Marker(
                        location=[lat, lon],
                        popup=popup_text,
                        tooltip=especialista,
                        icon=folium.Icon(color='blue', icon='user')
                    ).add_to(marker_cluster)

                    # Botão para focar no especialista
                    if st.button(f"Ver no mapa: {especialista}", key=f"btn_{especialista}_{idx}"):
                        m = folium.Map(location=[lat, lon], zoom_start=10)
                        marker_cluster = MarkerCluster().add_to(m)
                        folium.Marker(
                            location=[lat, lon],
                            popup=popup_text,
                            tooltip=especialista,
                            icon=folium.Icon(color='blue', icon='user')
                        ).add_to(marker_cluster)
                        for unidade in unidades:
                            gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                            if not gdf_unidade.empty:
                                folium.GeoJson(
                                    gdf_unidade.geometry.values[0],
                                    tooltip=unidade,
                                    style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.1}
                                ).add_to(m)
                        for fazenda in fazendas:
                            gdf_fazenda = gdf[gdf['Name_normalized'] == fazenda]
                            if not gdf_fazenda.empty:
                                folium.GeoJson(
                                    gdf_fazenda.geometry.values[0],
                                    tooltip=fazenda,
                                    style_function=lambda x: {'fillColor': 'orange', 'color': 'orange', 'fillOpacity': 0.1}
                                ).add_to(m)
                        folium.Circle(
                            location=[lat, lon],
                            radius=max_raio_km * 1000,
                            color='blue',
                            fill=True,
                            fill_opacity=0.2,
                            popup=f"Raio de atuação: {max_raio_km:.2f} km"
                        ).add_to(m)

        # Exibir o mapa
        st.subheader("Mapa Interativo")
        st_folium(m, width=700, height=500)

        # Exibir a tabela de analistas
        st.subheader("Tabela de Analistas")
        st.dataframe(df_analistas[['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'VL_LATITUDE', 'VL_LONGITUDE'] + (['FAZENDA'] if 'FAZENDA' in df_analistas.columns else [])])

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload do arquivo KML e da tabela de analistas (Excel) para começar.")
