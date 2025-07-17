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
import random

# Configurações básicas
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# CSS simples para design minimalista
st.markdown("""
<style>
    .stMetric {
        background-color: #f5f5f5;
        border-radius: 8px;
        padding: 10px 20px;
        margin-bottom: 10px;
    }
    .stTabs [role="tablist"] button[aria-selected="true"] {
        background-color: #007acc !important;
        color: white !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

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

def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def gerar_cor_unica(lista_unidades):
    cores = []
    random.seed(42)  # cores consistentes
    for _ in range(len(lista_unidades)):
        r = random.randint(100, 200)
        g = random.randint(100, 200)
        b = random.randint(100, 200)
        cores.append(f"#{r:02x}{g:02x}{b:02x}")
    return dict(zip(lista_unidades, cores))

st.title("Raio de Atuação dos Analistas")

uploaded_kml = st.file_uploader("Faça upload do arquivo KML", type=["kml"])
uploaded_table = st.file_uploader("Faça upload da tabela de analistas (Excel)", type=["xlsx", "xls"])

if uploaded_kml and uploaded_table:
    try:
        kml_content = uploaded_kml.read().decode('utf-8')
        gdf = extrair_dados_kml(kml_content)
        
        kml_name_column = 'NOME_FAZ' if 'NOME_FAZ' in gdf.columns else 'Name'
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

        centro_mapa = [df_analistas['Latitude'].mean(), df_analistas['Longitude'].mean()]
        m = folium.Map(location=centro_mapa, zoom_start=6)
        marker_cluster = MarkerCluster().add_to(m)

        todas_unidades = list(set([u for sublist in df_analistas['UNIDADE_normalized'].str.split(',').explode() for u in sublist]))
        cores_unidades = gerar_cor_unica(todas_unidades)

        # Agrupar especialistas (sem duplicação)
        df_agrupado = (
            df_analistas.groupby(
                ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'Latitude', 'Longitude'], dropna=False
            )['UNIDADE_normalized']
            .apply(lambda x: ','.join(sorted(set([u.strip() for sublist in x.str.split(',') for u in sublist]))))
            .reset_index()
        )

        # Filtros laterais para gestores e especialistas
        gestores_disponiveis = sorted(df_agrupado['GESTOR'].unique())
        gestor_selecionado = st.sidebar.selectbox("Selecione o Gestor", gestores_disponiveis)

        df_gestor = df_agrupado[df_agrupado['GESTOR'] == gestor_selecionado]

        especialistas_disponiveis = sorted(df_gestor['ESPECIALISTA'].unique())
        especialistas_selecionados = st.sidebar.multiselect(
            "Selecione Especialista(s) (ou deixe vazio para todos)", especialistas_disponiveis, default=especialistas_disponiveis
        )

        if especialistas_selecionados:
            df_gestor = df_gestor[df_gestor['ESPECIALISTA'].isin(especialistas_selecionados)]

        st.subheader(f"Resumo e Detalhes - Gestor: {gestor_selecionado}")

        # Mostrar número de especialistas
        st.markdown(f"**Número de Especialistas:** {len(df_gestor)}")

        # Criar tabs para especialistas
        tabs = st.tabs(df_gestor['ESPECIALISTA'].tolist())

        for tab, (_, row) in zip(tabs, df_gestor.iterrows()):
            with tab:
                especialista = row['ESPECIALISTA']
                cidade_base = row['CIDADE_BASE']
                lat, lon = row['Latitude'], row['Longitude']
                unidades = [u.strip() for u in row['UNIDADE_normalized'].split(',')]

                distancias_unidades = []
                for unidade in unidades:
                    gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                    if not gdf_unidade.empty:
                        centroide = gdf_unidade.iloc[0]['centroide']
                        dist_km = haversine(lon, lat, centroide.x, centroide.y)
                        distancias_unidades.append((unidade, dist_km))

                cols = st.columns(3)
                cols[0].metric("Unidades Atendidas", len(unidades))
                if distancias_unidades:
                    media = sum(d[1] for d in distancias_unidades) / len(distancias_unidades)
                    max_dist = max(d[1] for d in distancias_unidades)
                    cols[1].metric("Distância Média (km)", f"{media:.1f}")
                    cols[2].metric("Distância Máxima (km)", f"{max_dist:.1f}")

                df_dist = pd.DataFrame(distancias_unidades, columns=['Unidade', 'Distância (km)'])
                st.table(df_dist.style.format({'Distância (km)': '{:.2f}'}))

                # Adicionar no mapa linhas e círculos para o especialista
                for unidade, dist_km in distancias_unidades:
                    gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                    if gdf_unidade.empty:
                        continue
                    centroide = gdf_unidade.iloc[0]['centroide']
                    folium.PolyLine(
                        locations=[[lat, lon], [centroide.y, centroide.x]],
                        color=cores_unidades.get(unidade, '#000000'),
                        weight=2,
                        opacity=0.7,
                        tooltip=f"{especialista} → {unidade}: {dist_km:.1f} km"
                    ).add_to(m)
                    folium.Circle(
                        location=[lat, lon],
                        radius=dist_km * 1000,
                        color=cores_unidades.get(unidade, '#000000'),
                        fill=True,
                        fill_opacity=0.1,
                        tooltip=f"Raio para {unidade}: {dist_km:.1f} km"
                    ).add_to(m)
                    folium.GeoJson(
                        gdf_unidade.geometry.values[0],
                        tooltip=unidade,
                        style_function=lambda x, cor=cores_unidades.get(unidade, '#000000'): {
                            'fillColor': cor,
                            'color': cor,
                            'fillOpacity': 0.2
                        }
                    ).add_to(m)

                folium.Marker(
                    [lat, lon],
                    popup=f"<b>{especialista}</b><br>Cidade Base: {cidade_base}",
                    tooltip=especialista,
                    icon=folium.Icon(color='blue', icon='user')
                ).add_to(marker_cluster)

        # Legenda das cores
        legend_html = '''
            <div style="position: fixed; 
                        bottom: 50px; left: 50px; width: 180px; height: auto;
                        border:2px solid grey; z-index:9999; font-size:14px;
                        background-color:white;
                        padding: 10px;">
                <b>Legenda de Unidades</b><br>
        '''
        for unidade, cor in list(cores_unidades.items())[:10]:
            legend_html += f'<i class="fa fa-square" style="color:{cor}"></i> {unidade[:15]}...<br>'
        if len(cores_unidades) > 10:
            legend_html += f'<i>+ {len(cores_unidades)-10} outras unidades</i>'
        legend_html += '</div>'
        m.get_root().html.add_child(folium.Element(legend_html))

        st.subheader("Mapa Interativo")
        st_folium(m, width=1200, height=800)

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {e}")

else:
    st.info("Por favor, faça upload do arquivo KML e da tabela de analistas (Excel) para começar.")
