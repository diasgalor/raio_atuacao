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

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Faça upload do **arquivo KML** da localização das unidades e da **planilha Excel** com analistas e gestores.")

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

# Função para normalizar texto
def normalize_str(s):
    return unidecode(str(s).strip().upper())

# Upload de arquivos
kml_file = st.file_uploader("📂 Faça upload do arquivo KML", type=['kml'])
xlsx_file = st.file_uploader("📊 Faça upload da tabela de analistas (Excel)", type=['xlsx', 'xls'])

if kml_file and xlsx_file:
    try:
        # Leitura do KML
        kml_content = kml_file.read().decode('utf-8')
        gdf_kml = extrair_dados_kml(kml_content)
        gdf_kml['geometry'] = gdf_kml['geometry'].to_crs(epsg=4326)
        gdf_kml[['Longitude', 'Latitude']] = gdf_kml.geometry.apply(lambda p: pd.Series([p.centroid.x, p.centroid.y]))
        gdf_kml['UNIDADE_normalized'] = gdf_kml['Name'].apply(normalize_str)

        # Exibir metadados do KML (excluindo a coluna geometry)
        st.subheader("Metadados do KML")
        st.write("Colunas disponíveis no KML:")
        st.write(gdf_kml.columns.tolist())
        st.write("Primeiras linhas do KML (sem coluna geometry):")
        non_geometry_columns = [col for col in gdf_kml.columns if col != 'geometry']
        st.dataframe(gdf_kml[non_geometry_columns].head())

        # Selecionar coluna com nomes das unidades/fazendas
        kml_name_column = st.selectbox(
            "Selecione a coluna do KML que contém os nomes das unidades/fazendas:",
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

        # Agrupa e calcula distâncias por especialista
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
        col1, col2 = st.columns(2)
        with col1:
            gestores = sorted(resultados['GESTOR'].unique())
            gestor_selecionado = st.selectbox("👨‍💼 Selecione o Gestor", options=gestores)
        with col2:
            especialistas_filtrados = resultados[resultados['GESTOR'] == gestor_selecionado]
            nomes_especialistas = sorted(especialistas_filtrados['ESPECIALISTA'].unique())
            especialistas_selecionados = st.multiselect(
                "👨‍🔬 Selecione os Especialistas (ou deixe vazio para todos)",
                options=nomes_especialistas,
                default=nomes_especialistas
            )

        # Filtra o DataFrame com base nas seleções
        df_final = resultados[
            (resultados['GESTOR'] == gestor_selecionado) &
            (resultados['ESPECIALISTA'].isin(especialistas_selecionados))
        ]

        # Criação do mapa
        m = folium.Map(location=[df_final['LAT'].mean(), df_final['LON'].mean()], zoom_start=5)
        marker_cluster = MarkerCluster().add_to(m)

        for _, row in df_final.iterrows():
            popup_text = (
                f"<b>Especialista:</b> {row['ESPECIALISTA']}<br>"
                f"<b>Gestor:</b> {row['GESTOR']}<br>"
                f"<b>Cidade Base:</b> {row['CIDADE_BASE']}<br>"
                f"<b>Unidades:</b> {', '.join(row['UNIDADES_ATENDIDAS'])}<br>"
                f"<b>Distância Média:</b> {row['DIST_MEDIA']} km<br>"
                f"<b>Distância Máxima:</b> {row['DIST_MAX']} km"
            )
            folium.Marker(
                location=[row['LAT'], row['LON']],
                popup=folium.Popup(popup_text, max_width=300),
                icon=folium.Icon(color='blue', icon='user')
            ).add_to(marker_cluster)

            # Adicionar limites das unidades
            for geom in row['GEOMETRIES']:
                folium.GeoJson(
                    geom,
                    style_function=lambda x: {'fillColor': 'green', 'color': 'green', 'fillOpacity': 0.1}
                ).add_to(m)

            # Adicionar círculo de raio de atuação
            folium.Circle(
                location=[row['LAT'], row['LON']],
                radius=row['DIST_MAX'] * 1000,
                color='blue',
                fill=True,
                fill_opacity=0.2,
                popup=f"Raio de atuação: {row['DIST_MAX']} km"
            ).add_to(m)

        # Exibir o mapa
        st.subheader(f"🗺️ Mapa das Unidades Atendidas ({len(df_final)} especialistas)")
        st_folium(m, width=1000, height=600)

        # Exibir tabela resumo
        st.subheader("Resumo dos Especialistas")
        for _, row in df_final.iterrows():
            with st.expander(f"🔎 {row['ESPECIALISTA']} - {row['CIDADE_BASE']}"):
                st.markdown(f"**Unidades Atendidas:** {len(row['UNIDADES_ATENDIDAS'])}")
                st.table(pd.DataFrame(row['DETALHES'], columns=['Unidade', 'Distância (km)']).sort_values('Distância (km)'))

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("🔄 Aguarde o upload dos arquivos KML e Excel para continuar.")
