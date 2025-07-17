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

def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

def gerar_cor_unica(lista_unidades):
    cores = []
    random.seed(42)  # Para cores consistentes entre execuções
    for _ in range(len(lista_unidades)):
        r = random.randint(100, 200)
        g = random.randint(100, 200)
        b = random.randint(100, 200)
        cores.append(f"#{r:02x}{g:02x}{b:02x}")
    return dict(zip(lista_unidades, cores))

def get_utm_zone(longitude, latitude):
    zone_number = int((longitude + 180) / 6) + 1
    hemisphere = 'S' if latitude < 0 else 'N'
    return f"EPSG:327{zone_number:02d}" if hemisphere == 'S' else f"EPSG:326{zone_number:02d}"

st.title("Raio de Atuação dos Analistas")

uploaded_kml = st.file_uploader("Faça upload do arquivo KML", type=["kml"])
uploaded_table = st.file_uploader("Faça upload da tabela de analistas (Excel)", type=["xlsx", "xls"])

if uploaded_kml and uploaded_table:
    try:
        with st.spinner("Processando arquivos..."):
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
                df_analistas[['Latitude', 'Longitude']] = (
                    df_analistas['COORDENADAS_CIDADE']
                    .str.split(',', expand=True)
                    .apply(lambda x: x.str.strip())
                    .astype(float)
                )
            except Exception:
                st.error("Erro ao processar COORDENADAS_CIDADE. Use o formato 'latitude, longitude'.")
                st.stop()

            df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE'].apply(formatar_nome)
            if 'FAZENDA' in df_analistas.columns:
                df_analistas['FAZENDA_normalized'] = df_analistas['FAZENDA'].apply(formatar_nome)

            utm_crs = get_utm_zone(df_analistas['Longitude'].mean(), df_analistas['Latitude'].mean())
            gdf_utm = gdf.to_crs(utm_crs)
            gdf_utm['centroide'] = gdf_utm.geometry.centroid
            gdf['centroide'] = gdf_utm['centroide'].to_crs(gdf.crs)
            gdf['centroide_lat'] = gdf['centroide'].y
            gdf['centroide_lon'] = gdf['centroide'].x

            # Preparar cores para unidades
            todas_unidades = list(set(df_analistas['UNIDADE_normalized'].str.split(',').explode().str.strip()))
            cores_unidades = gerar_cor_unica(todas_unidades)

            # Filtro para especialistas
            especialistas_list = sorted(df_analistas['ESPECIALISTA'].unique())
            selecionados = st.multiselect("Selecione um ou mais especialistas para exibir (ou deixe vazio para todos)", especialistas_list)

            if selecionados:
                df_exibir = df_analistas[df_analistas['ESPECIALISTA'].isin(selecionados)]
            else:
                df_exibir = df_analistas.copy()

            # Agrupar df_analistas por GESTOR, ESPECIALISTA, CIDADE_BASE, Latitude, Longitude,
# agregando as UNIDADES numa lista única por especialista
df_agrupado = (
    df_analistas.groupby(
        ['GESTOR', 'ESPECIALISTA', 'CIDADE_BASE', 'Latitude', 'Longitude'], dropna=False
    )['UNIDADE_normalized']
    .apply(lambda x: ','.join(sorted(set([u.strip() for sublist in x.str.split(',') for u in sublist]))))
    .reset_index()
)

st.subheader("Resumo e Detalhes por Gestor e Especialista")

# Filtrar especialistas selecionados se houver filtro
if selecionados:
    df_agrupado = df_agrupado[df_agrupado['ESPECIALISTA'].isin(selecionados)]

for gestor in sorted(df_agrupado['GESTOR'].unique()):
    with st.expander(f"Gestor: {gestor}"):
        df_gestor = df_agrupado[df_agrupado['GESTOR'] == gestor]
        
        # Número de especialistas
        st.write(f"**Número de Especialistas:** {len(df_gestor)}")
        
        for _, row in df_gestor.iterrows():
            especialista = row['ESPECIALISTA']
            cidade_base = row['CIDADE_BASE']
            lat, lon = row['Latitude'], row['Longitude']
            unidades = [u.strip() for u in row['UNIDADE_normalized'].split(',')]

            # Calcular distâncias para cada unidade
            distancias_unidades = []
            for unidade in unidades:
                gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                if not gdf_unidade.empty:
                    centroide = gdf_unidade.iloc[0]['centroide']
                    dist_km = haversine(lon, lat, centroide.x, centroide.y)
                    distancias_unidades.append((unidade, dist_km))
            
            # Exibir card do especialista com as métricas
            with st.expander(f"Especialista: {especialista} (Cidade Base: {cidade_base})"):
                cols = st.columns(3)
                cols[0].metric("Unidades Atendidas", len(unidades))
                if distancias_unidades:
                    media = sum(d[1] for d in distancias_unidades) / len(distancias_unidades)
                    max_dist = max(d[1] for d in distancias_unidades)
                    cols[1].metric("Distância Média (km)", f"{media:.1f}")
                    cols[2].metric("Distância Máxima (km)", f"{max_dist:.1f}")
                
                df_dist = pd.DataFrame(distancias_unidades, columns=['Unidade', 'Distância (km)'])
                st.table(df_dist.style.format({'Distância (km)': '{:.2f}'}))

            # Criar mapa ao final, só com os especialistas filtrados
            centro_mapa = [df_analistas['Latitude'].mean(), df_analistas['Longitude'].mean()]
            m = folium.Map(location=centro_mapa, zoom_start=6)
            marker_cluster = MarkerCluster().add_to(m)

            for idx, row in df_exibir.iterrows():
                especialista = row['ESPECIALISTA']
                cidade_base = row['CIDADE_BASE']
                unidades = [u.strip() for u in row['UNIDADE_normalized'].split(',')]
                lat, lon = row['Latitude'], row['Longitude']
                if pd.isna(lat) or pd.isna(lon):
                    continue

                popup_text = f"<b>Especialista:</b> {especialista}<br><b>Cidade Base:</b> {cidade_base}<br>"
                distancias_especialista = []

                for unidade in unidades:
                    gdf_unidade = gdf[gdf['Name_normalized'] == unidade]
                    if not gdf_unidade.empty:
                        geom_uniao = gdf_unidade.geometry.unary_union
                        centroide = gdf_unidade.iloc[0]['centroide']
                        dist_km = haversine(lon, lat, centroide.x, centroide.y)
                        distancias_especialista.append(dist_km)

                        folium.PolyLine(
                            locations=[[lat, lon], [centroide.y, centroide.x]],
                            color=cores_unidades[unidade],
                            weight=2,
                            opacity=0.7,
                            tooltip=f"{especialista} → {unidade}: {dist_km:.1f} km",
                        ).add_to(m)

                        folium.Circle(
                            location=[lat, lon],
                            radius=dist_km * 1000,
                            color=cores_unidades[unidade],
                            fill=True,
                            fill_opacity=0.1,
                            tooltip=f"Raio para {unidade}: {dist_km:.1f} km",
                        ).add_to(m)

                        popup_text += f"<b>{unidade}</b>: {dist_km:.2f} km<br>"

                        folium.GeoJson(
                            geom_uniao,
                            tooltip=unidade,
                            style_function=lambda x, cor=cores_unidades[unidade]: {
                                "fillColor": cor,
                                "color": cor,
                                "fillOpacity": 0.2,
                            },
                        ).add_to(m)

                folium.Marker(
                    [lat, lon],
                    popup=folium.Popup(popup_text, max_width=300),
                    tooltip=especialista,
                    icon=folium.Icon(color="blue", icon="user"),
                ).add_to(marker_cluster)

            # Legenda de cores
            legend_html = """
                <div style="
                    position: fixed;
                    bottom: 50px;
                    left: 50px;
                    width: 200px;
                    max-height: 250px;
                    overflow-y: auto;
                    border:2px solid grey;
                    background-color:white;
                    padding: 10px;
                    font-size: 14px;
                    z-index:9999;
                ">
                <b>Legenda de Unidades</b><br>
            """
            for unidade, cor in list(cores_unidades.items())[:10]:
                legend_html += f'<span style="display:inline-block;width:12px;height:12px;background-color:{cor};margin-right:6px;"></span> {unidade[:15]}<br>'

            if len(cores_unidades) > 10:
                legend_html += f'<i>+ {len(cores_unidades) - 10} outras unidades</i>'

            legend_html += "</div>"
            m.get_root().html.add_child(folium.Element(legend_html))

            st.subheader("Mapa Interativo")
            st_folium(m, width=1200, height=800)

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload do arquivo KML e da tabela de analistas (Excel) para começar.")
