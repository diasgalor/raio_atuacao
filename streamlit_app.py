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
import plotly.express as px

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Upload
st.sidebar.header("Upload de Arquivos")
kml_file = st.sidebar.file_uploader("\ud83d\udcc2 Upload KML", type=['kml'])
xlsx_file = st.sidebar.file_uploader("\ud83d\udcc8 Upload Excel", type=['xlsx', 'xls'])

# CSS Customizado
st.markdown("""
<style>
body { background-color: #f5f5f5; font-family: 'Arial', sans-serif; }
.stApp { max-width: 1200px; margin: 0 auto; }
.stSelectbox, .stExpander { background-color: #ffffff; border-radius: 8px; }
.chart-container { background-color: #ffffff; border: 2px solid #2196F3; border-radius: 8px; padding: 15px; }
.element-container:has(.stPlotlyChart) { margin-bottom: 0px !important; }
</style>
""", unsafe_allow_html=True)

st.title("\ud83d\udccd Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor e especialista (ou 'Todos') para visualizar as unidades atendidas.")

# Função para normalizar texto
def normalize_str(s):
    return unidecode(str(s).strip().upper())

# Função para extrair dados do KML
def extrair_dados_kml(kml_content):
    try:
        tree = ET.fromstring(kml_content)
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        dados = {}
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
                geometry = unary_union([Point(c[0], c[1]) for c in coords]).convex_hull

            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords = tuple(map(float, point_elem.text.strip().split(',')))
                geometry = Point(coords[0], coords[1])

            if geometry:
                unidade = props.get('NOME_FAZ', props.get('Name', 'Sem Nome'))
                if unidade in dados:
                    dados[unidade]['geometries'].append(geometry)
                    dados[unidade]['props'].update(props)
                else:
                    dados[unidade] = {'geometries': [geometry], 'props': props}

        dados_gdf = []
        for unidade, info in dados.items():
            geometry = unary_union(info['geometries'])
            dados_gdf.append({**info['props'], 'Name': unidade, 'geometry': geometry})

        return gpd.GeoDataFrame(dados_gdf, crs="EPSG:4326")
    except Exception as e:
        st.error(f"Erro ao processar KML: {e}")
        return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

# Haversine
def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

if kml_file and xlsx_file:
    try:
        kml_content = kml_file.read().decode('utf-8')
        gdf_kml = extrair_dados_kml(kml_content)
        gdf_kml[['Longitude', 'Latitude']] = gdf_kml.geometry.centroid.apply(lambda p: pd.Series([p.x, p.y]))
        gdf_kml['UNIDADE_normalized'] = gdf_kml['NOME_FAZ'].apply(normalize_str)

        df = pd.read_excel(xlsx_file)
        df.columns = df.columns.str.upper().str.strip()

        df['COORDENADAS_CIDADE'] = df['COORDENADAS_CIDADE'].str.lstrip("'")
        df[['LAT', 'LON']] = df['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        df['UNIDADE_normalized'] = df['UNIDADE'].apply(normalize_str)
        df['GESTOR'] = df['GESTOR'].apply(normalize_str)
        df['ESPECIALISTA'] = df['ESPECIALISTA'].apply(normalize_str)

        df = df.groupby(['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'LAT', 'LON'])['UNIDADE_normalized'].apply(set).reset_index()
        df['UNIDADE_normalized'] = df['UNIDADE_normalized'].apply(list)

        df_merge = df.explode('UNIDADE_normalized').merge(
            gdf_kml[['UNIDADE_normalized', 'Latitude', 'Longitude', 'geometry']],
            on='UNIDADE_normalized', how='left'
        ).dropna(subset=['Latitude', 'Longitude'])

        resultados = []
        for (gestor, esp), grupo in df_merge.groupby(['GESTOR', 'ESPECIALISTA']):
            base = grupo[['LAT', 'LON']].iloc[0]
            distancias = [
                (row['UNIDADE_normalized'], haversine(base['LON'], base['LAT'], row['Longitude'], row['Latitude']))
                for _, row in grupo.iterrows()
            ]
            geometries = grupo['geometry'].dropna().tolist()
            resultados.append({
                'GESTOR': gestor,
                'ESPECIALISTA': esp,
                'CIDADE_BASE': grupo['CIDADE_BASE'].iloc[0],
                'LAT': base['LAT'],
                'LON': base['LON'],
                'UNIDADES_ATENDIDAS': grupo['UNIDADE_normalized'].unique().tolist(),
                'DIST_MEDIA': round(sum(d[1] for d in distancias)/len(distancias), 0),
                'DIST_MAX': round(max(d[1] for d in distancias), 0),
                'DETALHES': [(u, round(d, 0)) for u, d in distancias],
                'GEOMETRIES': geometries
            })

        resultados = pd.DataFrame(resultados)

        col1, col2 = st.columns([1, 1])
        with col1:
            gestores = sorted(resultados['GESTOR'].unique())
            gestor_selecionado = st.selectbox("Gestor", gestores)
            especialistas = ['Todos'] + sorted(resultados[resultados['GESTOR'] == gestor_selecionado]['ESPECIALISTA'].unique())
            especialista_selecionado = st.selectbox("Especialista", especialistas)

        with col2:
            if especialista_selecionado == 'Todos':
                df_plot = pd.DataFrame()
                for _, row in resultados[resultados['GESTOR'] == gestor_selecionado].iterrows():
                    for unidade, dist in row['DETALHES']:
                        df_plot = pd.concat([df_plot, pd.DataFrame({
                            'Unidade': [unidade],
                            'Distância (km)': [dist],
                            'Especialista': [row['ESPECIALISTA']]
                        })])
                df_plot = df_plot.sort_values('Distância (km)', ascending=False).head(10)
            else:
                row = resultados[(resultados['GESTOR'] == gestor_selecionado) &
                                 (resultados['ESPECIALISTA'] == especialista_selecionado)].iloc[0]
                df_plot = pd.DataFrame(row['DETALHES'], columns=['Unidade', 'Distância (km)'])

            fig = px.bar(df_plot, x='Unidade', y='Distância (km)',
                         color='Especialista' if especialista_selecionado == 'Todos' else None,
                         text='Distância (km)', height=400)
            fig.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), yaxis_title=None, xaxis_title=None)
            st.plotly_chart(fig, use_container_width=True)

        row = resultados[(resultados['GESTOR'] == gestor_selecionado) &
                         (resultados['ESPECIALISTA'] == especialista_selecionado)].iloc[0] if especialista_selecionado != 'Todos' else resultados[resultados['GESTOR'] == gestor_selecionado].iloc[0]

        with st.expander(f"{row['ESPECIALISTA'].title()} - {row['CIDADE_BASE'].title()}", expanded=True):
            st.markdown(f"**Unidades Atendidas:** {len(row['UNIDADES_ATENDIDAS'])}")
            st.markdown(f"**Distância Média:** {int(row['DIST_MEDIA'])} km")
            st.markdown(f"**Raio Máximo:** {int(row['DIST_MAX'])} km")
            st.table(pd.DataFrame(row['DETALHES'], columns=['Unidade', 'Distância (km)']))

        m = folium.Map(location=[row['LAT'], row['LON']], zoom_start=8, tiles="cartodbpositron")
        marker_cluster = MarkerCluster().add_to(m)
        folium.Marker(
            location=[row['LAT'], row['LON']],
            popup=f"Base: {row['CIDADE_BASE'].title()}",
            icon=folium.Icon(color='blue')
        ).add_to(marker_cluster)

        for geom in row['GEOMETRIES']:
            if geom is not None:
                folium.GeoJson(
                    geom,
                    style_function=lambda x: {'fillColor': '#4CAF50', 'color': '#4CAF50', 'fillOpacity': 0.1, 'weight': 1}
                ).add_to(m)

        folium.Circle(
            location=[row['LAT'], row['LON']],
            radius=row['DIST_MAX'] * 1000,
            color='#2196F3', fill=True, fill_opacity=0.1
        ).add_to(m)

        st.subheader("Mapa")
        st_folium(m, width=800, height=500)

    except Exception as e:
        st.error(f"Erro: {str(e)}")
else:
    st.info("Envie os arquivos KML e Excel na barra lateral para iniciar.")
