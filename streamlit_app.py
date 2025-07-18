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

# Configuração da página (PRIMEIRA INSTRUÇÃO)
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Upload de arquivos na sidebar
st.sidebar.header("Upload de Arquivos")
kml_file = st.sidebar.file_uploader("📂 Upload KML", type=['kml'])
xlsx_file = st.sidebar.file_uploader("📊 Upload Excel", type=['xlsx', 'xls'])

# CSS responsivo para design minimalista, adaptado para celular
st.markdown("""
    <style>
    body {
        background-color: #f5f5f5;
        font-family: 'Arial', sans-serif;
    }
    .stApp {
        max-width: 100%;
        margin: 0;
        padding: 10px;
    }
    .stSelectbox {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 5px;
        padding: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        font-size: 14px;
    }
    .stExpander {
        background-color: #fafafa;
        border: 2px solid #2196F3;
        border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
        margin-bottom: 10px;
        padding: 10px;
    }
    .chart-container {
        background-color: #ffffff;
        border: 2px solid #2196F3;
        border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
        padding: 10px;
        margin-bottom: 10px;
        width: 100%;
        height: auto;
    }
    .stMarkdown h3 {
        color: #333333;
        font-size: 16px;
        margin-bottom: 8px;
    }
    .stButton>button {
        background-color: #e0e0e0;
        color: #333333;
        border: none;
        border-radius: 4px;
        padding: 6px 12px;
        font-size: 14px;
    }
    .stButton>button:hover {
        background-color: #d0d0d0;
    }
    /* Media query para telas menores (celulares) */
    @media (max-width: 768px) {
        .stApp {
            padding: 5px;
        }
        .stSelectbox, .stButton>button {
            font-size: 12px;
            padding: 6px;
        }
        .stExpander {
            padding: 8px;
        }
        .stMarkdown h3 {
            font-size: 14px;
        }
        .chart-container {
            padding: 8px;
        }
        /* Empilhar colunas em telas pequenas */
        [class*="stColumn"] {
            width: 100% !important;
            margin-bottom: 10px;
        }
    }
    </style>
""", unsafe_allow_html=True)

# Título e descrição
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor e especialista (ou 'Todos') para visualizar as unidades atendidas, distâncias e o raio de atuação no mapa.", unsafe_allow_html=True)

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
                    distancias.append((unidade, dist))
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

        # Interface: seleção por gestor e especialista + gráfico de distribuição
        col1, col2 = st.columns([1, 1], gap="medium")
        with col1:
            st.markdown("### Seleção")
            gestores = sorted(resultados['GESTOR'].unique())
            gestor_selecionado = st.selectbox("Gestor", options=gestores, format_func=lambda x: x.title())
            especialistas_filtrados = resultados[resultados['GESTOR'] == gestor_selecionado]
            nomes_especialistas = ['Todos'] + sorted(especialistas_filtrados['ESPECIALISTA'].unique())
            especialista_selecionado = st.selectbox("Especialista", options=nomes_especialistas, format_func=lambda x: x.title())
        
        with col2:
            st.markdown("### Distâncias das Unidades")
            
            # Preparar dados para o gráfico
            if especialista_selecionado == 'Todos':
                # Para "Todos", mostrar top 10 unidades com maior distância, colorido por especialista
                df_plot = pd.DataFrame()
                for _, row in resultados[resultados['GESTOR'] == gestor_selecionado].iterrows():
                    for unidade, distancia in row['DETALHES']:
                        df_plot = pd.concat([df_plot, pd.DataFrame({
                            'Unidade': [unidade],
                            'Distância (km)': [distancia],
                            'Especialista': [row['ESPECIALISTA']]
                        })])
                
                if not df_plot.empty:
                    df_plot = df_plot.sort_values('Distância (km)', ascending=False).head(10)
                    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                    st.bar_chart(df_plot, x='Unidade', y='Distância (km)', color='Especialista', use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.warning("Nenhum dado disponível para o gestor selecionado.")
            else:
                # Para um especialista específico, mostrar todas as unidades com distâncias
                df_especialista = resultados[
                    (resultados['GESTOR'] == gestor_selecionado) &
                    (resultados['ESPECIALISTA'] == especialista_selecionado)
                ]
                
                if not df_especialista.empty:
                    df_plot = pd.DataFrame(df_especialista.iloc[0]['DETALHES'], columns=['Unidade', 'Distância (km)'])
                    df_plot = df_plot.sort_values('Distância (km)', ascending=False)
                    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
                    st.bar_chart(df_plot, x='Unidade', y='Distância (km)', color='#2196F3', use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.warning("Nenhum dado disponível para o especialista selecionado.")

        # Filtra o DataFrame
        if especialista_selecionado == 'Todos':
            df_final = resultados[resultados['GESTOR'] == gestor_selecionado]
            # Consolidar dados de todos os especialistas
            if not df_final.empty:
                unidades = []
                distancias = []
                geometries = []
                lats = []
                lons = []
                for _, row in df_final.iterrows():
                    unidades.extend(row['UNIDADES_ATENDIDAS'])
                    distancias.extend(row['DETALHES'])
                    if row['GEOMETRIES'] is not None:  # Corrigido para GEOMETRIES
                        geometries.extend(row['GEOMETRIES'])
                    lats.append(row['LAT'])
                    lons.append(row['LON'])

                unidades = list(set(unidades))  # Remover duplicatas
                distancias = list(set(distancias))  # Remover duplicatas
                medias = sum([d[1] for d in distancias]) / len(distancias) if distancias else 0
                max_dist = max([d[1] for d in distancias]) if distancias else 0
                # Calcular centroide médio para o mapa
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
            consolidated_data = df_final.iloc[0].to_dict() if not df_final.empty else None

        # Exibir card do especialista
        if consolidated_data:
            row = consolidated_data
            with st.expander(f"{row['ESPECIALISTA'].title()} - {row['CIDADE_BASE'].title()}", expanded=True):
                st.markdown(f"**Unidades Atendidas:** {len(row['UNIDADES_ATENDIDAS'])}")
                st.markdown(f"**Distância Média:** {row['DIST_MEDIA']} km")
                st.markdown(f"**Raio de Atuação (Máxima):** {row['DIST_MAX']} km")
                st.markdown("**Detalhes das Unidades:**")
                detalhes_df = pd.DataFrame(row['DETALHES'], columns=['Unidade', 'Distância (km)']).sort_values('Distância (km)', ascending=False)
                st.table(detalhes_df)

            # Criação do mapa com tamanho ajustado para celular
            m = folium.Map(location=[row['LAT'], row['LON']], zoom_start=8, tiles="cartodbpositron", attr='© OpenStreetMap')
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
                popup=folium.Popup(popup_text, max_width=200),  # Reduzido para celular
                icon=folium.Icon(color='blue', icon='user')
            ).add_to(marker_cluster)

            # Verificar e adicionar geometrias válidas
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
            st_folium(m, width=100, height=300)  # Ajustado para celular

        else:
            st.warning("Nenhum dado encontrado para o especialista selecionado.")

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload dos arquivos KML e Excel na barra lateral para continuar.")
