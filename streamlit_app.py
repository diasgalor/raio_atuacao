import xml.etree.ElementTree as ET
from streamlit_folium import st_folium
import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
import folium
from folium.plugins import MarkerCluster
import math
from unidecode import unidecode
import json
from shapely.geometry import shape
from fuzzywuzzy import fuzz
import plotly.express as px

PASTEL_COLORS = [
    "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
    "#dcd3ff", "#baffea", "#ffd6e0", "#e2f0cb", "#b5ead7"
]

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Upload de arquivos na sidebar
st.sidebar.header("Upload de Arquivos")
kml_file = st.sidebar.file_uploader("📂 Upload KML", type=["kml"])
xlsx_file = st.sidebar.file_uploader("📊 Upload Excel", type=["xlsx", "xls"])

# CSS ajustado para responsividade total
st.markdown("""
   <style>
   html, body, .stApp {
       background-color: #f7f8fa;
       font-family: 'Inter', 'Arial', sans-serif !important;
       width: 100%;
       margin: 0 auto;
       padding: 20px;
       box-sizing: border-box;
   }
   .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput {
       background: #fff;
       border: 1.5px solid #dbeafe !important;
       border-radius: 8px !important;
       padding: 8px !important;
       font-size: 14px !important;
       box-shadow: 0 2px 6px rgba(93, 188, 252, 0.07);
       width: 100%;
   }
   .stExpander {
       background-color: #f7f7fc !important;
       border: 1.5px solid #dbeafe !important;
       border-radius: 12px !important;
       box-shadow: 0 4px 12px rgba(93, 188, 252, 0.08);
       margin-bottom: 8px !important;
       padding: 15px;
   }
   .metric-card {
       background: linear-gradient(135deg, #f8fafc 60%, #dbeafe 100%);
       border-radius: 12px;
       padding: 12px;
       margin-bottom: 12px;
       box-shadow: 0 2px 8px rgba(93, 188, 252, 0.08);
       border: 1.2px solid #b6e0fe;
       text-align: center;
       width: 100%;
   }
   .metric-title {
       font-size: 14px;
       color: #82a1b7;
       margin-bottom: 4px;
   }
   .metric-value {
       font-size: 18px;
       font-weight: 700;
       color: #22577A;
   }
   .stButton>button {
       background: linear-gradient(90deg, #b5ead7 0, #bae1ff 100%);
       color: #22577A;
       border: none;
       border-radius: 8px;
       padding: 8px 16px;
       font-size: 14px;
       font-weight: 500;
       margin-top: 8px;
       width: 100%;
   }
   .stButton>button:hover {
       background: linear-gradient(90deg, #dbeafe 0, #ffd6e0 100%);
   }
   .stData {
       border-radius: 10px !important;
       border: 1.5px solid #dbeafe !important;
   }
   .stFolium {
       margin: 0 !important;
       padding: 0 !important;
   }
   @media screen and (max-width: 1024px) {
       .stApp { padding: 15px !important; }
       .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput { 
           font-size: 13px !important; 
           padding: 7px !important; 
       }
       .metric-card { padding: 10px !important; }
       .metric-title { font-size: 13px; }
       .metric-value { font-size: 16px; }
   }
   @media screen and (max-width: 768px) {
       .stApp { padding: 10px !important; }
       .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput { 
           font-size: 12px !important; 
           padding: 6px !important; 
       }
       .metric-card { padding: 8px !important; }
       .metric-title { font-size: 12px; }
       .metric-value { font-size: 15px; }
       .stButton>button { font-size: 12px; padding: 6px 12px; }
   }
   @media screen and (max-width: 480px) {
       .stApp { padding: 8px !important; }
       .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput { 
           font-size: 11px !important; 
           padding: 5px !important; 
       }
       .metric-card { padding: 6px !important; }
       .metric-title { font-size: 11px; }
       .metric-value { font-size: 14px; }
       .stButton>button { font-size: 11px; padding: 5px 10px; }
   }
   </style>
""", unsafe_allow_html=True)

st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor, especialista e fazenda (unidade) para visualizar as unidades atendidas, distâncias e o raio de atuação no mapa. Use 'Todos' para ver a visão consolidada.")

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
                coords_text = polygon_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                try:
                    from shapely.geometry import Polygon
                    geometry = Polygon([(c[0], c[1]) for c in coords]).centroid
                except Exception as geom_e:
                    st.markdown(
                        f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                        f'⚠️ Erro ao criar geometria para placemark {props.get("Name", "Sem Nome")}: {geom_e}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    geometry = None

            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords_text = line_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                try:
                    from shapely.geometry import LineString
                    geometry = LineString([(c[0], c[1]) for c in coords]).centroid
                except Exception as geom_e:
                    st.markdown(
                        f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                        f'⚠️ Erro ao criar geometria para placemark {props.get("Name", "Sem Nome")}: {geom_e}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    geometry = None

            point_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
            if point_elem is not None:
                coords_text = point_elem.text.strip()
                coords = tuple(map(float, coords_text.split(',')))
                try:
                    geometry = Point(coords[0], coords[1])
                except Exception as geom_e:
                    st.markdown(
                        f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                        f'⚠️ Erro ao criar geometria para placemark {props.get("Name", "Sem Nome")}: {geom_e}'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                    geometry = None

            if geometry:
                unidade = props.get('NOME_FAZ', props.get('Name', 'Sem Nome'))
                if unidade in dados:
                    dados[unidade]['geometries'].append(geometry)
                    dados[unidade]['props'].update(props)
                else:
                    dados[unidade] = {'geometries': [geometry], 'props': props}

        if not dados:
            st.markdown(
                '<div style="background-color:#fff3cd;padding:12px;border-radius:8px;border-left:6px solid #ffca28;">'
                '⚠️ Nenhuma geometria válida encontrada no KML.'
                '</div>',
                unsafe_allow_html=True
            )
            return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

        dados_gdf = []
        for unidade, info in dados.items():
            try:
                consolidated_geometry = unary_union(info['geometries'])
                dados_gdf.append({
                    **info['props'],
                    'Name': unidade,
                    'geometry': consolidated_geometry
                })
            except Exception as e:
                st.markdown(
                    f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                    f'⚠️ Erro ao consolidar geometria para unidade {unidade}: {e}'
                    f'</div>',
                    unsafe_allow_html=True
                )

        gdf = gpd.GeoDataFrame(dados_gdf, crs="EPSG:4326")
        return gdf

    except Exception as e:
        st.markdown(
            f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
            f'❌ Erro ao processar KML: {str(e)}'
            f'</div>',
            unsafe_allow_html=True
        )
        return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

def normalize_str(s):
    return unidecode(str(s).strip().upper())

# Definir df_analistas globalmente
df_analistas = None

if kml_file and xlsx_file:
    try:
        kml_content = kml_file.read().decode('utf-8')
        gdf_kml = extrair_dados_kml(kml_content)
        gdf_kml['geometry'] = gdf_kml['geometry'].to_crs(epsg=4326)
        gdf_kml[['Longitude', 'Latitude']] = gdf_kml.geometry.apply(lambda p: pd.Series([p.centroid.x, p.centroid.y]))
        gdf_kml['UNIDADE_normalized'] = gdf_kml['NOME_FAZ'].apply(normalize_str)

        df_analistas = pd.read_excel(xlsx_file)
        df_analistas.columns = df_analistas.columns.str.strip().str.upper()

        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']
        missing_columns = [col for col in expected_columns if col not in df_analistas.columns]
        if missing_columns:
            st.markdown(
                f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                f'❌ O arquivo Excel está faltando as colunas: {", ".join(missing_columns)}'
                f'</div>',
                unsafe_allow_html=True
            )
            st.stop()

        try:
            df_analistas['COORDENADAS_CIDADE'] = df_analistas['COORDENADAS_CIDADE'].str.lstrip("'")
            df_analistas[['LAT', 'LON']] = df_analistas['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        except Exception as e:
            st.markdown(
                f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                f'❌ Erro ao processar COORDENADAS_CIDADE. Use o formato "latitude,longitude" ou "\'latitude,longitude".'
                f'</div>',
                unsafe_allow_html=True
            )
            st.stop()

        df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE'].apply(normalize_str)
        df_analistas['ESPECIALISTA'] = df_analistas['ESPECIALISTA'].apply(normalize_str)
        df_analistas['GESTOR'] = df_analistas['GESTOR'].apply(normalize_str)
        df_analistas['CIDADE_BASE'] = df_analistas['CIDADE_BASE'].apply(normalize_str)

        def haversine(lon1, lat1, lon2, lat2):
            R = 6371
            lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        df_analistas_grouped = df_analistas.groupby(['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'LAT', 'LON'])['UNIDADE_normalized'].apply(set).reset_index()
        df_analistas_grouped['UNIDADE_normalized'] = df_analistas_grouped['UNIDADE_normalized'].apply(list)

        df_merge = df_analistas_grouped.explode('UNIDADE_normalized').merge(
            gdf_kml[['UNIDADE_normalized', 'Latitude', 'Longitude', 'geometry']],
            on='UNIDADE_normalized',
            how='left'
        )
        df_merge = df_merge.dropna(subset=['Latitude', 'Longitude'])

        resultados = []
        for (gestor, esp), df_sub in df_merge.groupby(['GESTOR', 'ESPECIALISTA']):
            cidade_base = df_sub['CIDADE_BASE'].iloc[0]
            base_coords = df_sub[['LAT', 'LON']].iloc[0]
            unidades = list(set(df_sub['UNIDADE_normalized'].dropna()))
            distancias = []
            geometries = []

            for unidade in unidades:
                df_unidade = df_sub[df_sub['UNIDADE_normalized'] == unidade]
                if not df_unidade.empty:
                    lat = df_unidade['Latitude'].iloc[0]
                    lon = df_unidade['Longitude'].iloc[0]
                    dist = haversine(base_coords['LON'], base_coords['LAT'], lon, lat)
                    distancias.append((unidade, round(dist, 1)))
                    geometries.append(df_unidade['geometry'].iloc[0])

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
                'GEOMETRIES': geometries if geometries else None
            })
        resultados = pd.DataFrame(resultados)

        col1, _, _ = st.columns([1, 1, 1], gap="medium")
        with col1:
            st.markdown("### Seleção")
            gestores = sorted(resultados['GESTOR'].unique())
            gestor_selecionado = st.selectbox("Gestor", options=gestores, format_func=lambda x: x.title())
            especialistas_filtrados = resultados[resultados['GESTOR'] == gestor_selecionado]
            nomes_especialistas = ['Todos'] + sorted(especialistas_filtrados['ESPECIALISTA'].unique())
            especialista_selecionado = st.selectbox("Especialista", options=nomes_especialistas, format_func=lambda x: x.title())

            unidades_filtradas = []
            if especialista_selecionado == 'Todos':
                for ulist in especialistas_filtrados['UNIDADES_ATENDIDAS']:
                    unidades_filtradas.extend(ulist)
            else:
                for ulist in especialistas_filtrados[especialistas_filtrados['ESPECIALISTA'] == especialista_selecionado]['UNIDADES_ATENDIDAS']:
                    unidades_filtradas.extend(ulist)
            unidades_filtradas = sorted(list(set(unidades_filtradas)))
            fazenda_opcoes = ['Todos'] + [u.title() for u in unidades_filtradas]
            fazenda_selecionada = st.selectbox("Fazenda", options=fazenda_opcoes)

        def unidade_match(unitlist):
            if fazenda_selecionada == 'Todos':
                return True
            return normalize_str(fazenda_selecionada) in [normalize_str(u) for u in unitlist]

        mask = (resultados['GESTOR'] == gestor_selecionado)
        if especialista_selecionado != 'Todos':
            mask = mask & (resultados['ESPECIALISTA'] == especialista_selecionado)
        resultados_filtrados = resultados[mask]
        if fazenda_selecionada != 'Todos':
            resultados_filtrados = resultados_filtrados[resultados_filtrados['UNIDADES_ATENDIDAS'].apply(unidade_match)]

        if not resultados_filtrados.empty:
            if especialista_selecionado == 'Todos':
                with st.expander("🔍 Todos os especialistas do gestor selecionado", expanded=True):
                    total_unidades = sum([len(row['UNIDADES_ATENDIDAS']) for _, row in resultados_filtrados.iterrows()])
                    dist_medias = [row["DIST_MEDIA"] for _, row in resultados_filtrados.iterrows()]
                    dist_maximos = [row["DIST_MAX"] for _, row in resultados_filtrados.iterrows()]
                    cols = st.columns(3)
                    cols[0].markdown(
                        f'<div class="metric-card"><div class="metric-title">Unidades Atendidas</div><div class="metric-value">{total_unidades}</div></div>',
                        unsafe_allow_html=True
                    )
                    cols[1].markdown(
                        f'<div class="metric-card"><div class="metric-title">Distância Média Geral</div><div class="metric-value">{round(sum(dist_medias) / len(dist_medias),1) if dist_medias else 0} km</div></div>',
                        unsafe_allow_html=True
                    )
                    cols[2].markdown(
                        f'<div class="metric-card"><div class="metric-title">Maior Raio</div><div class="metric-value">{max(dist_maximos) if dist_maximos else 0} km</div></div>',
                        unsafe_allow_html=True
                    )

                    detalhes = []
                    for _, row in resultados_filtrados.iterrows():
                        for unidade, dist in row['DETALHES']:
                            detalhes.append((row['ESPECIALISTA'].title(), unidade.title(), dist))
                    detalhes_df = pd.DataFrame(detalhes, columns=['Especialista', 'Fazenda', 'Distância (km)'])
                    st.markdown("**Detalhes por Especialista/Fazenda**")
                    st.dataframe(detalhes_df, hide_index=True, use_container_width=True)

                    m = folium.Map(location=[-14.2, -53.2], zoom_start=5.5, tiles="cartodbpositron")
                    marker_cluster = MarkerCluster().add_to(m)
                    for idx, (_, row) in enumerate(resultados_filtrados.iterrows()):
                        color = PASTEL_COLORS[idx % len(PASTEL_COLORS)]
                        folium.Marker(
                            location=[row['LAT'], row['LON']],
                            popup=folium.Popup(
                                f"<b>Especialista:</b> {row['ESPECIALISTA'].title()}<br>"
                                f"<b>Gestor:</b> {gestor_selecionado.title()}<br>"
                                f"<b>Cidade Base:</b> {row['CIDADE_BASE'].title()}<br>"
                                f"<b>Unidades:</b> {', '.join([u.title() for u in row['UNIDADES_ATENDIDAS']])}<br>"
                                f"<b>Raio de Atuação:</b> {row['DIST_MAX']} km",
                                max_width=220
                            ),
                            icon=folium.Icon(color="blue", icon="user", prefix="fa", icon_color=color)
                        ).add_to(marker_cluster)
                        for unidade in row['UNIDADES_ATENDIDAS'][:50]:
                            df_unidade = gdf_kml[gdf_kml['UNIDADE_normalized'] == unidade]
                            if not df_unidade.empty:
                                lat = df_unidade['Latitude'].iloc[0]
                                lon = df_unidade['Longitude'].iloc[0]
                                folium.Marker(
                                    location=[lat, lon],
                                    popup=folium.Popup(f"Unidade: {unidade.title()}", max_width=200),
                                    icon=folium.Icon(color="green", icon="map-marker", prefix="fa", icon_color=color)
                                ).add_to(marker_cluster)
                    st.subheader("Mapa")
                    st_folium(m, height=600, use_container_width=True)
            else:
                row = resultados_filtrados.iloc[0].to_dict()
                with st.expander(f"🔍 {row['ESPECIALISTA'].title()} - {row['CIDADE_BASE'].title()}", expanded=True):
                    cols = st.columns(3)
                    cols[0].markdown(
                        f'<div class="metric-card"><div class="metric-title">Unidades Atendidas</div>'
                        f'<div class="metric-value">{len(row["UNIDADES_ATENDIDAS"])}</div></div>',
                        unsafe_allow_html=True
                    )
                    cols[1].markdown(
                        f'<div class="metric-card"><div class="metric-title">Distância Média</div>'
                        f'<div class="metric-value">{row["DIST_MEDIA"]} km</div></div>',
                        unsafe_allow_html=True
                    )
                    cols[2].markdown(
                        f'<div class="metric-card"><div class="metric-title">Raio Máximo</div>'
                        f'<div class="metric-value">{row["DIST_MAX"]} km</div></div>',
                        unsafe_allow_html=True
                    )

                    detalhes_df = pd.DataFrame([(row['ESPECIALISTA'].title(), unidade.title(), dist) for unidade, dist in row['DETALHES']],
                                              columns=['Especialista', 'Fazenda', 'Distância (km)'])
                    st.markdown("**Detalhes por Fazenda (Unidade)**")
                    st.dataframe(detalhes_df, hide_index=True, use_container_width=True)

                    m = folium.Map(location=[row['LAT'], row['LON']], zoom_start=8, tiles="cartodbpositron")
                    marker_cluster = MarkerCluster().add_to(m)
                    folium.Marker(
                        location=[row['LAT'], row['LON']],
                        popup=folium.Popup(
                            f"<b>Especialista:</b> {row['ESPECIALISTA'].title()}<br>"
                            f"<b>Gestor:</b> {gestor_selecionado.title()}<br>"
                            f"<b>Cidade Base:</b> {row['CIDADE_BASE'].title()}<br>"
                            f"<b>Unidades:</b> {', '.join([u.title() for u in row['UNIDADES_ATENDIDAS']])}<br>"
                            f"<b>Raio de Atuação:</b> {row['DIST_MAX']} km",
                            max_width=220
                        ),
                        icon=folium.Icon(color="blue", icon="user", prefix="fa", icon_color="#2196F3")
                    ).add_to(marker_cluster)
                    for unidade in row['UNIDADES_ATENDIDAS'][:50]:
                        df_unidade = gdf_kml[gdf_kml['UNIDADE_normalized'] == unidade]
                        if not df_unidade.empty:
                            lat = df_unidade['Latitude'].iloc[0]
                            lon = df_unidade['Longitude'].iloc[0]
                            folium.Marker(
                                location=[lat, lon],
                                popup=folium.Popup(f"Unidade: {unidade.title()}", max_width=200),
                                icon=folium.Icon(color="green", icon="map-marker", prefix="fa", icon_color="#4CAF50")
                            ).add_to(marker_cluster)
                    folium.Circle(
                        location=[row['LAT'], row['LON']],
                        radius=row['DIST_MAX'] * 1000,
                        color='#2196F3',
                        fill=True,
                        fill_opacity=0.14,
                        weight=2,
                        popup=f"Raio de atuação: {row['DIST_MAX']} km"
                    ).add_to(m)
                    st.subheader("Mapa")
                    st_folium(m, height=600, use_container_width=True)
        else:
            st.markdown(
                '<div style="background-color:#fff3cd;padding:12px;border-radius:8px;border-left:6px solid #ffca28;">'
                '⚠️ Nenhum dado encontrado para o filtro selecionado.'
                '</div>',
                unsafe_allow_html=True
            )
    except Exception as e:
        st.markdown(
            f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
            f'❌ Erro ao processar os arquivos: {str(e)}'
            f'</div>',
            unsafe_allow_html=True
        )
else:
    st.info("ℹ️ Por favor, faça upload dos arquivos KML e Excel na barra lateral para continuar.")
