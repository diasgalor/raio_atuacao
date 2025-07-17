import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import folium
from folium.plugins import MarkerCluster
import math
from unidecode import unidecode
import xml.etree.ElementTree as ET
from streamlit_folium import st_folium

# CSS para design minimalista
st.markdown("""
    <style>
    body {
        background-color: #f5f5f5;
        font-family: 'Arial', sans-serif;
    }
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .stSelectbox, .stMultiSelect {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 5px;
        padding: 10px;
    }
    .stExpander {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .stMarkdown h3 {
        color: #333333;
        font-size: 18px;
        margin-bottom: 10px;
    }
    .stButton>button {
        background-color: #e0e0e0;
        color: #333333;
        border: none;
        border-radius: 5px;
        padding: 8px 16px;
    }
    .stButton>button:hover {
        background-color: #d0d0d0;
    }
    </style>
""", unsafe_allow_html=True)

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor e especialista para visualizar as unidades atendidas e o raio de atuação no mapa.", unsafe_allow_html=True)

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

            geometry = None
            polygon_elem = placemark.find('.//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if polygon_elem is not None:
                coords_text = polygon_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                try:
                    geometry = gpd.GeoSeries([Point(c[0], c[1]) for c in coords]).unary_union.convex_hull
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords_text = line_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                try:
                    geometry = gpd.GeoSeries([Point(c[0], c[1]) for c in coords]).unary_union
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords_text = point_elem.text.strip()
                coords = tuple(map(float, coords_text.split(',')))
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

# Função para normalizar texto
def normalize_str(s):
    return unidecode(str(s).strip().upper())

# Upload de arquivos
kml_file = st.file_uploader("📂 Upload KML", type=['kml'])
xlsx_file = st.file_uploader("📊 Upload Excel", type=['xlsx', 'xls'])

if kml_file and xlsx_file:
    try:
        # Leitura do KML
        kml_content = kml_file.read().decode('utf-8')
        gdf_kml = extrair_dados_kml(kml_content)
        gdf_kml['geometry'] = gdf_kml['geometry'].to_crs(epsg=4326)
        gdf_kml[['Longitude', 'Latitude']] = gdf_kml.geometry.apply(lambda p: pd.Series([p.centroid.x, p.centroid.y]))
        gdf_kml['UNIDADE_normalized'] = gdf_kml['Name'].apply(normalize_str)

        # Exibir metadados do KML (excluindo a coluna geometry)
        with st.expander("🔍 Metadados do KML"):
            st.write("**Colunas disponíveis no KML:**")
            st.write(gdf_kml.columns.tolist())
            st.write("**Primeiras linhas do KML (sem coluna geometry):**")
            non_geometry_columns = [col for col in gdf_kml.columns if col != 'geometry']
            st.dataframe(gdf_kml[non_geometry_columns].head())

        # Selecionar coluna com nomes das unidades/fazendas
        kml_name_column = st.selectbox(
            "Selecione a coluna do KML com os nomes das unidades/fazendas:",
            gdf_kml.columns.tolist(),
            index=gdf_kml.columns.tolist().index('NOME_FAZ' if 'NOME_FAZ' in gdf_kml.columns else 'Name') if 'NOME_FAZ' in gdf_kml.columns or 'Name' in gdf_kml.columns else 0
        )
        gdf_kml['UNIDADE_normalized'] = gdf_kml[kml_name_column].apply(normalize_str)

        # Leitura da planilha de analistas
        df_analistas = pd.read_excel(xlsx_file)
        df_analistas.columns = df_analistas.columns.str.strip().str.upper()

        # Verificar colunas esperadas
        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']
        missing_columns = [col for col in expected_columns if col not in df_analistas.columns]
        if missing_columns:
            st.error(f"O arquivo Excel está faltando as colunas: {', '.join(missing_columns)}")
            st.stop()

        # Processar coordenadas
        try:
            df_analistas[['LAT', 'LON']] = df_analistas['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        except Exception as e:
            st.error("Erro ao processar COORDENADAS_CIDADE. Use o formato 'latitude, longitude'.")
            st.stop()

        df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE'].apply(normalize_str)
        df_analistas['ESPECIALISTA'] = df_analistas['ESPECIALISTA'].apply(normalize_str)
        df_analistas['GESTOR'] = df_analistas['GESTOR'].apply(normalize_str)
        df_analistas['CIDADE_BASE'] = df_analistas['CIDADE_BASE'].apply(normalize_str)

        # Verificar coluna FAZENDA
        if 'FAZENDA' in df_analistas.columns:
            df_analistas['FAZENDA_normalized'] = df_analistas['FAZENDA'].apply(normalize_str)
            st.write("Coluna FAZENDA encontrada no Excel. Usando para correspondência.")

        # Função para calcular distância haversine
        def haversine(lon1, lat1, lon2, lat2):
            R = 6371
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        # Junta coordenadas da unidade
        df_merge = df_analistas.merge(gdf_kml[['UNIDADE_normalized', 'Latitude', 'Longitude', 'geometry']], left_on='UNIDADE_normalized', right_on='UNIDADE_normalized', how='left')
        df_merge = df_merge.dropna(subset=['Latitude', 'Longitude'])

        # Agrupa por especialista
        resultados = []
        for (gestor, esp), df_sub in df_merge.groupby(['GESTOR', 'ESPECIALISTA']):
            cidade_base = df_sub['CIDADE_BASE'].iloc[0]
            base_coords = df_sub[['LAT', 'LON']].iloc[0]
            unidades = []
            distancias = []
            geometries = []

            for _, row in df_sub.iterrows():
                unidades.append(row['UNIDADE'])
                dist = haversine(base_coords['LON'], base_coords['LAT'], row['Longitude'], row['Latitude'])
                distancias.append((row['UNIDADE'], dist))
                if row['geometry'] is not None:
                    geometries.append(row['geometry'])

            medias = sum([d[1] for d in distancias]) / len(distancias) if distancias else 0
            max_dist = max([d[1] for d in distancias]) if distancias else 0

            resultados.append({
                'GESTOR': gestor,
                'ESPECIALISTA': esp,
                'CIDADE_BASE': cidade_base,
                'LAT': base_coords['LAT'],
                'LON': base_coords['LON'],
                'UNIDADES_ATENDIDAS': unidades,
                'DIST_MEDIA': round(medias, 1),
                'DIST_MAX': round(max_dist, 1),
                'DETALHES': distancias,
                'GEOMETRIES': geometries
            })

        resultados = pd.DataFrame(resultados)

        # Interface: seleção por gestor → especialista
        col1, col2 = st.columns([1, 1], gap="small")
        with col1:
            gestores = sorted(resultados['GESTOR'].unique())
            gestor_selecionado = st.selectbox("Gestor", options=gestores, format_func=lambda x: x.title())
        with col2:
            especialistas_filtrados = resultados[resultados['GESTOR'] == gestor_selecionado]
            nomes_especialistas = sorted(especialistas_filtrados['ESPECIALISTA'].unique())
            especialista_selecionado = st.selectbox("Especialista", options=nomes_especialistas, format_func=lambda x: x.title())

        # Filtra o DataFrame
        df_final = resultados[
            (resultados['GESTOR'] == gestor_selecionado) &
            (resultados['ESPECIALISTA'] == especialista_selecionado)
        ]

        # Exibir card do especialista
        if not df_final.empty:
            row = df_final.iloc[0]
            with st.expander(f"{row['ESPECIALISTA'].title()} - {row['CIDADE_BASE'].title()}", expanded=True):
                st.markdown(f"**Unidades Atendidas:** {len(row['UNIDADES_ATENDIDAS'])}")
                st.markdown(f"**Distância Média:** {row['DIST_MEDIA']} km")
                st.markdown(f"**Raio de Atuação (Máxima):** {row['DIST_MAX']} km")
                st.markdown("**Detalhes das Unidades:**")
                st.table(pd.DataFrame(row['DETALHES'], columns=['Unidade', 'Distância (km)']).sort_values('Distância (km)'))

            # Criação do mapa
            m = folium.Map(location=[row['LAT'], row['LON']], zoom_start=8, tiles="cartodbpositron")
            marker_cluster = MarkerCluster().add_to(m)

            popup_text = (
                f"<b>Especialista:</b> {row['ESPECIALISTA'].title()}<br>"
                f"<b>Gestor:</b> {row['GESTOR'].title()}<br>"
                f"<b>Cidade Base:</b> {row['CIDADE_BASE'].title()}<br>"
                f"<b>Unidades:</b> {', '.join(row['UNIDADES_ATENDIDAS'])}<br>"
                f"<b>Raio de Atuação:</b> {row['DIST_MAX']} km"
            )
            folium.Marker(
                location=[row['LAT'], row['LON']],
                popup=folium.Popup(popup_text, max_width=300),
                icon=folium.Icon(color='blue', icon='user')
            ).add_to(marker_cluster)

            for geom in row['GEOMETRIES']:
                folium.GeoJson(
                    geom,
                    style_function=lambda x: {'fillColor': '#4CAF50', 'color': '#4CAF50', 'fillOpacity': 0.1, 'weight': 1}
                ).add_to(m)

            folium.Circle(
                location=[row['LAT'], row['LON']],
                radius=row['DIST_MAX'] * 1000,
                color='#2196F3',
                fill=True,
                fill_opacity=0.1,
                weight=1,
                popup=f"Raio de atuação: {row['DIST_MAX']} km"
            ).add_to(m)

            st.subheader("Mapa")
            st_folium(m, width=1000, height=500)

        else:
            st.warning("Nenhum dado encontrado para o especialista selecionado.")

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload dos arquivos KML e Excel para continuar.")
