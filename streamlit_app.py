import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from unidecode import unidecode
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, LineString, Point, MultiPolygon
from shapely.ops import unary_union
import requests
import time
import math
import json
from shapely.geometry import shape
from fuzzywuzzy import fuzz
from streamlit_folium import st_folium
import sqlite3

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# Carregar CSS externo
try:
    with open("styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.warning("Arquivo styles.css não encontrado. Usando estilo padrão.")
    # Definir um CSS mínimo para evitar que o layout quebre
    st.markdown("""
        <style>
        .stApp {
            background-color: #f7f8fa;
            font-family: Arial, sans-serif;
        }
        .stSelectbox, .stSlider {
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 5px;
        }
        .stButton>button {
            background: #007bff;
            color: white;
            border-radius: 5px;
            padding: 8px 16px;
        }
        </style>
    """, unsafe_allow_html=True)

# ... O resto do código permanece exatamente como está ...
# (A partir de `def extrair_dados_kml(kml_bytes):` até o final)

# Mapeamento de códigos IBGE para UFs
UF_MAP = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"
}

@st.cache_data
def normalize_str(s):
    """Normaliza strings, preservando acentos para consistência."""
    try:
        return str(s).strip().upper() if pd.notna(s) else "DESCONHECIDO"
    except Exception:
        logger.error(f"Erro ao normalizar string: {s}")
        return "DESCONHECIDO"

@st.cache_data
def haversine_m(lon1, lat1, lon2, lat2):
    """Calcula distância em metros usando a fórmula de Haversine."""
    try:
        R = 6371000  # Raio da Terra em metros
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlon, dlat = lon2 - lon1, lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    except Exception as e:
        logger.error(f"Erro no cálculo de Haversine: {e}")
        return None

@st.cache_data
def extrair_dados_kml(kml_bytes):
    """Extrai dados de um arquivo KML e retorna um GeoDataFrame."""
    try:
        if not kml_bytes:
            st.error("Arquivo KML vazio ou inválido.")
            logger.error("Arquivo KML vazio ou inválido.")
            return gpd.GeoDataFrame(columns=['Name', 'geometry', 'UNIDADE_normalized'], crs="EPSG:4326")

        kml_string = kml_bytes.decode("utf-8")
        tree = ET.fromstring(kml_string)
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        dados = {}

        for placemark in tree.findall(".//kml:Placemark", ns):
            props = {sd.get("name"): sd.text for sd in placemark.findall(".//kml:SimpleData", ns)}
            props["Name"] = placemark.find("kml:name", ns).text if placemark.find("kml:name", ns) is not None else "Sem Nome"
            nome_faz = props.get("NOME_FAZ", props["Name"])
            props["UNIDADE_normalized"] = normalize_str(nome_faz)

            geometry = None
            for geom_type, tag in [
                ("Polygon", ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates"),
                ("LineString", ".//kml:LineString/kml:coordinates"),
                ("Point", ".//kml:Point/kml:coordinates")
            ]:
                elem = placemark.find(tag, ns)
                if elem is not None:
                    coords = [tuple(map(float, c.split(","))) for c in elem.text.strip().split()]
                    try:
                        geometry = {
                            "Polygon": Polygon([(c[0], c[1]) for c in coords]),
                            "LineString": LineString([(c[0], c[1]) for c in coords]),
                            "Point": Point(coords[0])
                        }[geom_type]
                        break
                    except Exception as e:
                        st.warning(f"Erro ao criar geometria para {props['Name']}: {e}")
                        logger.error(f"Erro ao criar geometria para {props['Name']}: {e}")
                        continue

            if geometry:
                unidade = props["UNIDADE_normalized"]
                dados.setdefault(unidade, {"geometries": [], "props": {}})["geometries"].append(geometry)
                dados[unidade]["props"].update(props)

        if not dados:
            st.error("Nenhuma geometria válida encontrada no KML.")
            logger.error("Nenhuma geometria válida encontrada no KML.")
            return gpd.GeoDataFrame(columns=['Name', 'geometry', 'UNIDADE_normalized'], crs="EPSG:4326")

        gdf_data = [
            {
                "Name": unidade,
                "geometry": unary_union(info["geometries"]),
                "NOME_FAZ": info["props"].get("NOME_FAZ", info["props"].get("Name", "Desconhecida")),
                "UNIDADE_normalized": info["props"]["UNIDADE_normalized"],
                **info["props"]
            } for unidade, info in dados.items()
        ]
        gdf = gpd.GeoDataFrame(gdf_data, crs="EPSG:4326")

        # Reprojetar para UTM
        if not gdf.empty:
            gdf_temp = gdf.to_crs(epsg=3857)
            lon_mean = gdf_temp.geometry.centroid.x.mean()
            utm_zone = int((lon_mean / 111320 + 180) / 6) + 1
            utm_crs = f"EPSG:327{utm_zone}" if gdf_temp.geometry.centroid.y.mean() < 0 else f"EPSG:326{utm_zone}"
            gdf = gdf.to_crs(utm_crs)
            st.write(f"Geometrias reprojetadas para CRS: {utm_crs}")
            logger.info(f"Geometrias reprojetadas para CRS: {utm_crs}")

        st.write("Valores de UNIDADE_normalized no KML:", gdf["UNIDADE_normalized"].unique().tolist())
        logger.info(f"Valores de UNIDADE_normalized no KML: {gdf['UNIDADE_normalized'].unique().tolist()}")
        return gdf
    except Exception as e:
        st.error(f"Erro ao processar KML: {e}")
        logger.error(f"Erro ao processar KML: {e}")
        return gpd.GeoDataFrame(columns=['Name', 'geometry', 'UNIDADE_normalized'], crs="EPSG:4326")

@st.cache_data
def criar_banco():
    """Cria o banco de dados SQLite e suas tabelas."""
    try:
        conn = sqlite3.connect('mapa_dados.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS especialistas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE, gestor TEXT, cidade_base TEXT,
                latitude_base REAL, longitude_base REAL
            )''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fazendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_fazenda TEXT, especialista_id INTEGER,
                geometria_json TEXT, latitude_centroide REAL, longitude_centroide REAL,
                FOREIGN KEY (especialista_id) REFERENCES especialistas (id)
            )''')
        conn.commit()
        conn.close()
        return "Banco de dados criado com sucesso!"
    except Exception as e:
        logger.error(f"Erro ao criar banco: {e}")
        return f"Erro ao criar banco: {e}"

@st.cache_data
def migrar(kml_file, xlsx_file):
    """Migra dados de KML e Excel para o banco SQLite."""
    try:
        conn = sqlite3.connect('mapa_dados.db')
        cursor = conn.cursor()

        # Processar Excel
        df_analistas = pd.read_excel(xlsx_file)
        expected_cols = ["GESTOR", "ESPECIALISTA", "CIDADE_BASE", "UNIDADE", "COORDENADAS_CIDADE"]
        if not all(col in df_analistas.columns for col in expected_cols):
            missing = [col for col in expected_cols if col not in df_analistas.columns]
            st.error(f"Colunas faltando no Excel: {missing}")
            logger.error(f"Colunas faltando no Excel: {missing}")
            conn.close()
            return None, None, f"Erro: Colunas faltando no Excel: {missing}"

        df_analistas["LAT_BASE"] = pd.to_numeric(df_analistas["COORDENADAS_CIDADE"].astype(str).str.split(",", expand=True)[0], errors="coerce")
        df_analistas["LON_BASE"] = pd.to_numeric(df_analistas["COORDENADAS_CIDADE"].astype(str).str.split(",", expand=True)[1], errors="coerce")
        df_analistas["UNIDADE_normalized"] = df_analistas["UNIDADE"].apply(normalize_str)
        st.write("Valores de UNIDADE_normalized no Excel:", df_analistas["UNIDADE_normalized"].unique().tolist())
        logger.info(f"Valores de UNIDADE_normalized no Excel: {df_analistas['UNIDADE_normalized'].unique().tolist()}")

        for _, row in df_analistas.drop_duplicates(subset=["ESPECIALISTA"]).iterrows():
            cursor.execute(
                "INSERT OR IGNORE INTO especialistas (nome, gestor, cidade_base, latitude_base, longitude_base) VALUES (?, ?, ?, ?, ?)",
                (normalize_str(row["ESPECIALISTA"]), normalize_str(row["GESTOR"]), normalize_str(row["CIDADE_BASE"]), row["LAT_BASE"], row["LON_BASE"])
            )
        conn.commit()

        # Processar KML
        gdf_kml = extrair_dados_kml(kml_file.read())
        if gdf_kml.empty:
            conn.close()
            return df_analistas, gdf_kml, "Erro: Nenhum dado válido extraído do KML."

        df_merged = pd.merge(df_analistas, gdf_kml, left_on="UNIDADE_normalized", right_on="UNIDADE_normalized", how="inner")
        if df_merged.empty:
            st.error("Nenhuma correspondência entre Excel e KML. Verifique os nomes em UNIDADE e NOME_FAZ.")
            logger.error("Merge vazio entre Excel e KML.")
            conn.close()
            return df_analistas, gdf_kml, "Erro: Nenhuma correspondência encontrada."

        for _, row in df_merged.iterrows():
            cursor.execute("SELECT id FROM especialistas WHERE nome = ?", (normalize_str(row["ESPECIALISTA"]),))
            result = cursor.fetchone()
            if result:
                especialista_id = result[0]
                geometry = gpd.GeoSeries([row["geometry"]], crs=gdf_kml.crs).to_crs("EPSG:4326").iloc[0]
                cursor.execute(
                    "INSERT INTO fazendas (nome_fazenda, especialista_id, geometria_json, latitude_centroide, longitude_centroide) VALUES (?, ?, ?, ?, ?)",
                    (row["NOME_FAZ"], especialista_id, geometry.to_json(), geometry.centroid.y, geometry.centroid.x)
                )
        conn.commit()
        conn.close()
        return df_analistas, gdf_kml, f"{len(df_analistas.drop_duplicates('ESPECIALISTA'))} especialistas e {len(df_merged)} fazendas inseridos!"
    except Exception as e:
        st.error(f"Erro ao migrar dados: {e}")
        logger.error(f"Erro ao migrar dados: {e}")
        return None, None, f"Erro ao migrar dados: {e}"

@st.cache_data
def get_route(start_lon, start_lat, end_lon, end_lat):
    """Obtém rota entre dois pontos usando a API OSRM."""
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            logger.error(f"Erro na API OSRM: status {response.status_code}")
            return None
        routes = response.json().get("routes", [])
        if not routes:
            logger.error("Nenhuma rota encontrada pela API OSRM.")
            return None
        return [(point[1], point[0]) for point in routes[0]["geometry"]["coordinates"]]
    except Exception as e:
        logger.error(f"Erro ao obter rota: {e}")
        return None

def criar_mapa_analistas(df_analistas, gdf_kml, gestor, especialista, mostrar_rotas):
    """Cria mapa interativo com analistas e fazendas."""
    if gdf_kml.empty or df_analistas.empty:
        st.error("Dados de fazendas ou analistas vazios.")
        logger.error("Dados de fazendas ou analistas vazios.")
        return None

    df_analistas = df_analistas.copy()
    df_analistas["UNIDADE_normalized"] = df_analistas["UNIDADE"].apply(normalize_str)
    gdf_kml["Longitude_Unidade"] = gdf_kml.geometry.centroid.x
    gdf_kml["Latitude_Unidade"] = gdf_kml.geometry.centroid.y

    df_merged = pd.merge(
        df_analistas,
        gdf_kml[["UNIDADE_normalized", "Latitude_Unidade", "Longitude_Unidade", "geometry", "NOME_FAZ"]],
        on="UNIDADE_normalized",
        how="inner"
    )
    if df_merged.empty:
        st.error("Nenhuma correspondência entre analistas e fazendas.")
        logger.error("Nenhuma correspondência entre analistas e fazendas.")
        return None

    df_merged["DISTANCIA_KM"] = df_merged.apply(
        lambda row: haversine_m(row["LON_BASE"], row["LAT_BASE"], row["Longitude_Unidade"], row["Latitude_Unidade"]) / 1000,
        axis=1
    )

    cores = ["#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231", "#911EB4", "#46F0F0", "#F032E6"]
    cor_especialista = {esp: cores[i % len(cores)] for i, esp in enumerate(df_merged["ESPECIALISTA"].unique())}
    df_merged["COR"] = df_merged["ESPECIALISTA"].map(cor_especialista)

    df_filtrado = df_merged[df_merged["GESTOR"].eq(gestor) if gestor != "Todos" else slice(None)]
    df_filtrado = df_filtrado[df_filtrado["ESPECIALISTA"].eq(especialista) if especialista != "Todos" else slice(None)]

    if df_filtrado.empty:
        st.warning("Nenhum resultado para os filtros selecionados.")
        logger.warning("Nenhum resultado para os filtros selecionados.")
        return None

    mapa = folium.Map(location=[df_filtrado["Latitude_Unidade"].mean(), df_filtrado["Longitude_Unidade"].mean()], zoom_start=7, tiles="openstreetmap")
    colaboradores_cluster = MarkerCluster(name="Colaboradores").add_to(mapa)
    fazendas_group = folium.FeatureGroup(name="Fazendas").add_to(mapa)
    rotas_group = folium.FeatureGroup(name="Rotas").add_to(mapa)

    popup_css = """
    <style>
        .leaflet-popup-content { font-family: Arial, sans-serif; font-size: 14px; padding: 10px; }
        .leaflet-popup-content b { color: #00497a; }
    </style>
    """
    mapa.get_root().html.add_child(folium.Element(popup_css))

    for _, row in df_filtrado.groupby(["ESPECIALISTA", "CIDADE_BASE", "LAT_BASE", "LON_BASE", "COR"]).agg(
        RAIO_MAXIMO_KM=("DISTANCIA_KM", "max"),
        DIST_MEDIA_KM=("DISTANCIA_KM", "mean"),
        UNIDADES=("UNIDADE", lambda x: list(x.unique()))
    ).reset_index().iterrows():
        popup_html = (
            f"<b>Especialista:</b> {row['ESPECIALISTA'].title()}<br>"
            f"<b>Cidade Base:</b> {row['CIDADE_BASE'].title()}<br>"
            f"<b>Raio Máximo:</b> {row['RAIO_MAXIMO_KM']:.1f} km<br>"
            f"<b>Distância Média:</b> {row['DIST_MEDIA_KM']:.1f} km<br>"
            f"<b>Unidades:</b> {', '.join(row['UNIDADES'][:5]) + ('...' if len(row['UNIDADES']) > 5 else '')}"
        )
        folium.Circle(
            location=[row["LAT_BASE"], row["LON_BASE"]],
            radius=row["RAIO_MAXIMO_KM"] * 1000,
            color=row["COR"],
            fill=True,
            fill_opacity=0.15
        ).add_to(mapa)
        folium.Marker(
            location=[row["LAT_BASE"], row["LON_BASE"]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color="white", icon_color=row["COR"], icon="user", prefix="fa")
        ).add_to(colaboradores_cluster)

    for _, row in df_filtrado.iterrows():
        if isinstance(row["geometry"], (Polygon, MultiPolygon)):
            coords = [list(row["geometry"].exterior.coords)] if isinstance(row["geometry"], Polygon) else [list(poly.exterior.coords) for poly in row["geometry"].geoms]
            for coord in coords:
                folium.Polygon(
                    locations=[(lat, lon) for lon, lat in coord],
                    color=row["COR"],
                    fill=True,
                    fill_opacity=0.3,
                    popup=f"<b>Fazenda:</b> {row['NOME_FAZ'].title()}<br><b>Atendida por:</b> {row['ESPECIALISTA'].title()}"
                ).add_to(fazendas_group)

        popup_html = (
            f"<b>Fazenda:</b> {row['NOME_FAZ'].title()}<br>"
            f"<b>Cidade:</b> {row['CIDADE_BASE'].title()}<br>"
            f"<b>Especialista:</b> {row['ESPECIALISTA'].title()}<br>"
            f"<b>Distância:</b> {row['DISTANCIA_KM']:.1f} km"
        )
        folium.Marker(
            location=[row["Latitude_Unidade"], row["Longitude_Unidade"]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color="white", icon_color=row["COR"], icon="home", prefix="fa")
        ).add_to(fazendas_group)

        if mostrar_rotas:
            route = get_route(row["LON_BASE"], row["LAT_BASE"], row["Longitude_Unidade"], row["Latitude_Unidade"])
            if route:
                folium.PolyLine(route, color=row["COR"], weight=2.5).add_to(rotas_group)

    legenda_html = '<div style="position: fixed; bottom: 10px; left: 10px; background: white; padding: 10px; border-radius: 8px;">' \
                   '<b>Legenda</b><br>' + \
                   ''.join(f'<i class="fa fa-circle" style="color:{cor}"></i> {esp.title()}<br>' for esp, cor in cor_especialista.items() if esp in df_filtrado["ESPECIALISTA"].unique()) + \
                   '</div>'
    mapa.get_root().html.add_child(folium.Element(legenda_html))
    folium.LayerControl().add_to(mapa)
    return mapa

# Título
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Visualize o raio de atuação de analistas, fazendas e cidades próximas.")

# Abas
tab1, tab2, tab3 = st.tabs(["📤 Upload e Migração", "🗺️ Mapa de Analistas", "🏙️ Cidades Próximas"])

# Aba 1: Upload e Migração
with tab1:
    st.header("📤 Upload e Migração de Dados")
    kml_file = st.file_uploader("📍 Arquivo KML", type=["kml"], key="kml_upload")
    xlsx_file = st.file_uploader("📊 Arquivo Excel", type=["xlsx"], key="xlsx_upload")
    if st.button("🚀 Migrar Dados"):
        if kml_file and xlsx_file:
            with st.spinner("Migrando dados..."):
                result = criar_banco()
                st.success(result)
                df_analistas, gdf_kml, msg = migrar(kml_file, xlsx_file)
                if df_analistas is not None:
                    st.session_state['df_analistas'] = df_analistas
                    st.session_state['gdf_kml'] = gdf_kml
                    st.success(msg)
        else:
            st.error("Faça upload dos arquivos KML e Excel.")

# Aba 2: Mapa de Analistas
with tab2:
    st.header("🗺️ Mapa de Analistas")
    if 'df_analistas' in st.session_state and 'gdf_kml' in st.session_state:
        df_analistas = st.session_state['df_analistas']
        gdf_kml = st.session_state['gdf_kml']
        col1, col2, col3 = st.columns(3)
        with col1:
            gestores = ["Todos"] + sorted(df_analistas["GESTOR"].apply(normalize_str).unique())
            gestor = st.selectbox("Gestor", gestores, format_func=lambda x: x.title())
        with col2:
            especialistas = ["Todos"] + sorted(df_analistas["ESPECIALISTA"].apply(normalize_str).unique())
            especialista = st.selectbox("Especialista", especialistas, format_func=lambda x: x.title())
        with col3:
            mostrar_rotas = st.checkbox("Mostrar Rotas")
        mapa = criar_mapa_analistas(df_analistas, gdf_kml, gestor, especialista, mostrar_rotas)
        if mapa:
            st_folium(mapa, height=600, use_container_width=True)
    else:
        st.info("Faça upload e migração na Aba 1 para visualizar o mapa.")

# Aba 3: Cidades Próximas
with tab3:
    st.header("🏙️ Cidades Próximas")
    debug_mode = st.checkbox("Modo Depuração", value=False)
    geojson_file = st.file_uploader("🌎 GeoJSON de Cidades", type=["geojson"])
    if 'df_analistas' in st.session_state and 'gdf_kml' in st.session_state and geojson_file:
        df_analistas = st.session_state['df_analistas']
        gdf_kml = st.session_state['gdf_kml']
        cidades_gdf = gpd.read_file(geojson_file)

        if debug_mode:
            st.write("Colunas em cidades_gdf:", cidades_gdf.columns.tolist())
            st.write("Colunas em gdf_kml:", gdf_kml.columns.tolist())
            st.write("Colunas em df_analistas:", df_analistas.columns.tolist())
            st.write("UNIDADE_normalized em gdf_kml:", gdf_kml["UNIDADE_normalized"].unique().tolist())
            st.write("UNIDADE_normalized em df_analistas:", df_analistas["UNIDADE_normalized"].unique().tolist())

        fazenda = st.selectbox("🌾 Fazenda", sorted(df_analistas["UNIDADE"].unique()), format_func=lambda x: x.title())
        fazenda_norm = normalize_str(fazenda)
        selected_fazenda = gdf_kml[gdf_kml["UNIDADE_normalized"] == fazenda_norm]
        if selected_fazenda.empty:
            st.error(f"Fazenda '{fazenda}' não encontrada.")
            if debug_mode:
                st.write("UNIDADE_normalized em gdf_kml:", gdf_kml["UNIDADE_normalized"].unique().tolist())
            st.stop()

        fazenda_geom = selected_fazenda.geometry.iloc[0]
        centroid_4326 = selected_fazenda.to_crs("EPSG:4326").geometry.centroid.iloc[0]
        fazenda_lat, fazenda_lon = centroid_4326.y, centroid_4326.x

        buffer_km = st.slider("📏 Raio de Busca (km)", 10, 100, 50, step=5)
        buffer_projected = fazenda_geom.buffer(buffer_km * 1000)
        buffer_4326 = gpd.GeoSeries([buffer_projected], crs=gdf_kml.crs).to_crs("EPSG:4326").iloc[0]

        cidades_proximas = cidades_gdf.to_crs("EPSG:4326")[cidades_gdf.geometry.centroid.within(buffer_4326)]
        especialistas_gdf = gpd.GeoDataFrame(df_analistas, geometry=gpd.points_from_xy(df_analistas["LON_BASE"], df_analistas["LAT_BASE"]), crs="EPSG:4326")
        especialistas_proximos = especialistas_gdf[
            (especialistas_gdf["UNIDADE_normalized"] == fazenda_norm) & (especialistas_gdf.geometry.within(buffer_4326))
        ]

        if debug_mode:
            st.write(f"Cidades próximas: {len(cidades_proximas)}")
            st.write(f"Especialistas próximos: {len(especialistas_proximos)}")

        mapa = folium.Map(location=[fazenda_lat, fazenda_lon], zoom_start=9, tiles="cartodbpositron")
        folium.GeoJson(selected_fazenda.to_crs("EPSG:4326").geometry, style_function=lambda x: {"color": "green", "fillOpacity": 0.15}, name="Fazenda").add_to(mapa)
        folium.GeoJson(buffer_4326, style_function=lambda x: {"color": "blue", "fillOpacity": 0.1}, name="Raio").add_to(mapa)

        tabela_dados = []
        for idx, cidade in cidades_proximas.iterrows():
            cidade_nome = cidade.get("nome", "Desconhecida")
            geocodigo = str(cidade.get("geocodigo", ""))
            cidade_uf = UF_MAP.get(geocodigo[:2], "Desconhecida")
            distancia_km = haversine_m(fazenda_lon, fazenda_lat, cidade.geometry.centroid.x, cidade.geometry.centroid.y) / 1000
            folium.Marker(
                [cidade.geometry.centroid.y, cidade.geometry.centroid.x],
                popup=f"<b>Cidade:</b> {cidade_nome} ({cidade_uf})<br><b>Distância:</b> {distancia_km:.1f} km",
                icon=folium.Icon(color="blue", icon="star" if idx == cidades_proximas.index[0] else "circle", prefix="fa")
            ).add_to(mapa)
            tabela_dados.append({
                "Fazenda": fazenda.title(),
                "Cidade": f"{cidade_nome} ({cidade_uf})",
                "Distância (km)": f"{distancia_km:.1f}",
                "Especialistas": "Nenhum",
                "Tipo": "Cidade Próxima"
            })

        for _, esp in especialistas_proximos.iterrows():
            distancia_km = haversine_m(fazenda_lon, fazenda_lat, esp.geometry.x, esp.geometry.y) / 1000
            folium.Marker(
                [esp.geometry.y, esp.geometry.x],
                popup=f"<b>Especialista:</b> {esp['ESPECIALISTA'].title()}<br><b>Gestor:</b> {esp['GESTOR'].title()}<br><b>Cidade:</b> {esp['CIDADE_BASE'].title()}<br><b>Distância:</b> {distancia_km:.1f} km",
                icon=folium.Icon(color="red" if distancia_km > 200 else "purple", icon="user", prefix="fa")
            ).add_to(mapa)
            tabela_dados.append({
                "Fazenda": fazenda.title(),
                "Cidade": esp["CIDADE_BASE"].title(),
                "Distância (km)": f"{distancia_km:.1f}",
                "Especialistas": f"{esp['ESPECIALISTA'].title()} (Gestor: {esp['GESTOR'].title()})",
                "Tipo": "Cidade Base"
            })

        folium.LayerControl().add_to(mapa)
        st_folium(mapa, height=500, use_container_width=True)

        if tabela_dados:
            df_tabela = pd.DataFrame(tabela_dados)
            st.dataframe(df_tabela, use_container_width=True)
            st.download_button(
                label="📥 Baixar Tabela (CSV)",
                data=df_tabela.to_csv(index=False),
                file_name=f"tabela_{fazenda_norm.lower()}.csv",
                mime="text/csv"
            )
        else:
            st.info("Nenhuma cidade ou especialista encontrado no raio informado.")
    else:
        st.info("Faça upload dos arquivos e migração na Aba 1.")
```

<xaiArtifact artifact_id="bb39cf02-4626-48ab-ad81-c3359f41a7fb" artifact_version_id="d43598fd-ebe1-431e-85b7-bb6140ad10e0" title="styles.css" contentType="text/css">
```css
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
}
.stExpander {
    background-color: #f7f7fc !important;
    border: 1.5px solid #dbeafe !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 12px rgba(93, 188, 252, 0.08);
}
.metric-card {
    background: linear-gradient(135deg, #f8fafc 60%, #dbeafe 100%);
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 12px;
    box-shadow: 0 2px 8px rgba(93, 188, 252, 0.08);
    border: 1.2px solid #b6e0fe;
    text-align: center;
}
.metric-title {
    font-size: 14px;
    color: #82a1b7;
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
}
.stButton>button:hover {
    background: linear-gradient(90deg, #dbeafe 0, #ffd6e0 100%);
}
.stDataFrame {
    border-radius: 10px !important;
    border: 1.5px solid #dbeafe !important;
}
@media screen and (max-width: 768px) {
    .stApp { padding: 10px !important; }
    .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput {
        font-size: 12px !important;
        padding: 6px !important;
    }
    .metric-card { padding: 8px !important; }
    .metric-title { font-size: 12px; }
    .metric-value { font-size: 16px; }
}
