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

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Upload de arquivos na sidebar
st.sidebar.header("Upload de Arquivos")
kml_file = st.sidebar.file_uploader("📂 Upload KML", type=['kml'])
xlsx_file = st.sidebar.file_uploader("📊 Upload Excel", type=['xlsx', 'xls'])

# CSS para design minimalista com ajustes para mobile
st.markdown("""
   <style>
   body {
       background-color: #f5f5f5;
       font-family: 'Arial', sans-serif;
   }
   .stApp {
       max-width: 1200px;
       margin: 0 auto;
       padding: 20px;
   }
   .stSelectbox {
       background-color: #ffffff;
       border: 1px solid #e0e0e0;
       border-radius: 5px;
       padding: 8px;
       box-shadow: 0 2px 6px rgba(0,0,0,0.1);
       font-size: 14px;
   }
   .stExpander {
       background-color: #ffffff;
       border: 1px solid #e0e0e0;
       border-radius: 8px;
       box-shadow: 0 2px 8px rgba(0,0,0,0.1);
       margin-bottom: 10px;
       padding: 15px;
   }
   .metric-card {
       background-color: #f8f9fa;
       border-radius: 8px;
       padding: 15px;
       margin-bottom: 10px;
       box-shadow: 0 1px 3px rgba(0,0,0,0.1);
   }
   .metric-title {
       font-size: 14px;
       color: #6c757d;
       margin-bottom: 5px;
   }
   .metric-value {
       font-size: 18px;
       font-weight: bold;
       color: #212529;
   }
   .stButton>button {
       background-color: #e0e0e0;
       color: #333333;
       border: none;
       border-radius: 5px;
       padding: 8px 16px;
       font-size: 14px;
   }
   .stButton>button:hover {
       background-color: #d0d0d0;
   }
   @media screen and (max-width: 600px) {
       .stApp {
           padding: 10px !important;
           max-width: 100%;
       }
       .stSelectbox {
           font-size: 12px;
           padding: 6px;
       }
       .stExpander {
           padding: 10px !important;
       }
       .metric-card {
           padding: 10px !important;
       }
       .metric-title {
           font-size: 12px;
       }
       .metric-value {
           font-size: 16px;
       }
       .stButton>button {
           font-size: 12px;
           padding: 6px 12px;
       }
       [class*="stColumn"] {
           width: 100% !important;
           margin-bottom: 10px;
       }
   }
   </style>
""", unsafe_allow_html=True)

# Título e descrição
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor e especialista (ou 'Todos') para visualizar as unidades atendidas, distâncias e o raio de atuação no mapa.")

# Função para extrair metadados e geometria do KML
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
                    geometry = Polygon([(c[0], c[1]) for c in coords])
                except Exception as geom_e:
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords_text = line_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                try:
                    from shapely.geometry import LineString
                    geometry = LineString([(c[0], c[1]) for c in coords])
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
                unidade = props.get('NOME_FAZ', props.get('Name', 'Sem Nome'))
                if unidade in dados:
                    dados[unidade]['geometries'].append(geometry)
                    dados[unidade]['props'].update(props)
                else:
                    dados[unidade] = {'geometries': [geometry], 'props': props}

        if not dados:
            st.warning("Nenhuma geometria válida encontrada no KML.")
            return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

        # Consolidar geometrias por unidade
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
                st.warning(f"Erro ao consolidar geometria para unidade {unidade}: {e}")

        gdf = gpd.GeoDataFrame(dados_gdf, crs="EPSG:4326")
        return gdf

    except Exception as e:
        st.error(f"Erro ao processar KML: {e}")
        return gpd.GeoDataFrame(columns=['Name', 'geometry'], crs="EPSG:4326")

# Função para normalizar texto
def normalize_str(s):
    return unidecode(str(s).strip().upper())

if kml_file and xlsx_file:
    try:
        # Leitura do KML
        kml_content = kml_file.read().decode('utf-8')
        gdf_kml = extrair_dados_kml(kml_content)
        gdf_kml['geometry'] = gdf_kml['geometry'].to_crs(epsg=4326)
        gdf_kml[['Longitude', 'Latitude']] = gdf_kml.geometry.apply(lambda p: pd.Series([p.centroid.x, p.centroid.y]))
        gdf_kml['UNIDADE_normalized'] = gdf_kml['NOME_FAZ'].apply(normalize_str)

        # Leitura da planilha de analistas
        df_analistas = pd.read_excel(xlsx_file)
        df_analistas.columns = df_analistas.columns.str.strip().str.upper()

        # Verificar colunas esperadas
        expected_columns = ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'UNIDADE', 'COORDENADAS_CIDADE']
        missing_columns = [col for col in expected_columns if col not in df_analistas.columns]
        if missing_columns:
            st.error(f"O arquivo Excel está faltando as colunas: {', '.join(missing_columns)}")
            st.stop()

        # Processar coordenadas, removendo aspas simples
        try:
            df_analistas['COORDENADAS_CIDADE'] = df_analistas['COORDENADAS_CIDADE'].str.lstrip("'")
            df_analistas[['LAT', 'LON']] = df_analistas['COORDENADAS_CIDADE'].str.split(',', expand=True).astype(float)
        except Exception as e:
            st.error("Erro ao processar COORDENADAS_CIDADE. Use o formato 'latitude,longitude' ou '\'latitude,longitude'.")
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

        # Agrupar unidades no Excel por especialista
        df_analistas = df_analistas.groupby(['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'LAT', 'LON'])['UNIDADE_normalized'].apply(set).reset_index()
        df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE_normalized'].apply(list)

        # Junta coordenadas da unidade
        df_merge = df_analistas.explode('UNIDADE_normalized').merge(
            gdf_kml[['UNIDADE_normalized', 'Latitude', 'Longitude', 'geometry']],
            on='UNIDADE_normalized',
            how='left'
        )
        df_merge = df_merge.dropna(subset=['Latitude', 'Longitude'])

        # Agrupa por especialista
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
                    geometries.extend(df_unidade['geometry'].dropna().tolist())

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

        # Interface: seleção por gestor e especialista
        col1, col2 = st.columns([1, 1], gap="medium")
        with col1:
            st.markdown("### Seleção")
            gestores = sorted(resultados['GESTOR'].unique())
            gestor_selecionado = st.selectbox("Gestor", options=gestores, format_func=lambda x: x.title())
            especialistas_filtrados = resultados[resultados['GESTOR'] == gestor_selecionado]
            nomes_especialistas = ['Todos'] + sorted(especialistas_filtrados['ESPECIALISTA'].unique())
            especialista_selecionado = st.selectbox("Especialista", options=nomes_especialistas, format_func=lambda x: x.title())

        # Exibir card do especialista
        if kml_file and xlsx_file:
            if especialista_selecionado == 'Todos':
                df_final = resultados[resultados['GESTOR'] == gestor_selecionado]
                if not df_final.empty:
                    unidades = []
                    distancias = []
                    geometries = []
                    lats = []
                    lons = []
                    for _, row in df_final.iterrows():
                        unidades.extend(row['UNIDADES_ATENDIDAS'])
                        distancias.extend([(row['ESPECIALISTA'], unidade, round(dist, 1)) for unidade, dist in row['DETALHES']])
                        if row['GEOMETRIES'] is not None:
                            geometries.extend(row['GEOMETRIES'])
                        lats.append(row['LAT'])
                        lons.append(row['LON'])

                    unidades = list(set(unidades))
                    distancias = list(set(distancias))
                    medias = sum([d[2] for d in distancias]) / len(distancias) if distancias else 0
                    max_dist = max([d[2] for d in distancias]) if distancias else 0
                    lat_central = sum(lats) / len(lats) if lats else 0
                    lon_central = sum(lons) / len(lons) if lons else 0

                    consolidated_data = {
                        'ESPECIALISTA': 'Todos',
                        'CIDADE_BASE': 'Consolidado',
                        'LAT': lat_central,
                        'LON': lon_central,
                        'UNIDADES_ATENDIDAS': unidades,
                        'DIST_MEDIA': round(medias, 1),
                        'DIST_MAX': round(max_dist, 1),
                        'DETALHES': distancias,
                        'GEOMETRIES': geometries if geometries else None
                    }
                else:
                    consolidated_data = None
            else:
                df_final = resultados[
                    (resultados['GESTOR'] == gestor_selecionado) &
                    (resultados['ESPECIALISTA'] == especialista_selecionado)
                ]
                if not df_final.empty:
                    row = df_final.iloc[0].to_dict()
                    row['DETALHES'] = [(row['ESPECIALISTA'], unidade, round(dist, 1)) for unidade, dist in row['DETALHES']]
                    consolidated_data = row
                else:
                    consolidated_data = None

            if consolidated_data:
                row = consolidated_data
                with st.expander(f"🔍 {row['ESPECIALISTA'].title()} - {row['CIDADE_BASE'].title()}", expanded=True):
                    # Layout de métricas em cards
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown('<div class="metric-card"><div class="metric-title">Unidades Atendidas</div>'
                                   f'<div class="metric-value">{len(row["UNIDADES_ATENDIDAS"])}</div></div>', 
                                   unsafe_allow_html=True)
                    
                    with col2:
                        st.markdown('<div class="metric-card"><div class="metric-title">Distância Média</div>'
                                   f'<div class="metric-value">{row["DIST_MEDIA"]} km</div></div>', 
                                   unsafe_allow_html=True)
                    
                    with col3:
                        st.markdown('<div class="metric-card"><div class="metric-title">Raio Máximo</div>'
                                   f'<div class="metric-value">{row["DIST_MAX"]} km</div></div>', 
                                   unsafe_allow_html=True)

                    # Tabela de detalhes
                    st.markdown("**Detalhes por Unidade**")
                    detalhes_df = pd.DataFrame(
                        row['DETALHES'], 
                        columns=['Especialista', 'Unidade', 'Distância (km)']
                    )
                    st.dataframe(
                        detalhes_df,
                        column_config={
                            "Especialista": st.column_config.TextColumn("Especialista", width="medium"),
                            "Unidade": st.column_config.TextColumn("Unidade", width="large"),
                            "Distância (km)": st.column_config.NumberColumn(
                                "Distância (km)",
                                format="%.1f km",
                                width="small"
                            )
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                # Criação do mapa
                m = folium.Map(location=[row['LAT'], row['LON']], zoom_start=8, tiles="cartodbpositron")
                marker_cluster = MarkerCluster().add_to(m)

                popup_text = (
                    f"<b>Especialista:</b> {row['ESPECIALISTA'].title()}<br>"
                    f"<b>Gestor:</b> {gestor_selecionado.title()}<br>"
                    f"<b>Cidade Base:</b> {row['CIDADE_BASE'].title()}<br>"
                    f"<b>Unidades:</b> {', '.join(row['UNIDADES_ATENDIDAS'])}<br>"
                    f"<b>Raio de Atuação:</b> {row['DIST_MAX']} km"
                )
                folium.Marker(
                    location=[row['LAT'], row['LON']],
                    popup=folium.Popup(popup_text, max_width=200),
                    icon=folium.Icon(color='blue', icon='user')
                ).add_to(marker_cluster)

                geometries = row.get('GEOMETRIES', [])
                if isinstance(geometries, list) and geometries and any(g is not None and not g.is_empty for g in geometries):
                    for geom in geometries:
                        if geom is not None and not geom.is_empty:
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
                st_folium(m, width=100, height=400)  # Aumentado de 300px para 400px

            else:
                st.warning("Nenhum dado encontrado para o especialista selecionado.")
    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload dos arquivos KML e Excel na barra lateral para continuar.")
