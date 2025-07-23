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

# Configuração da página (apenas uma vez, no início)
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

# CSS para responsividade
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

def extrair_dados_kml(kml_bytes):
    try:
        if not kml_bytes:
            st.error("Arquivo KML vazio ou inválido.")
            return gpd.GeoDataFrame(columns=['Name', 'geometry', 'UNIDADE_normalized'], crs="EPSG:4326")
        kml_string = kml_bytes.decode("utf-8")
        tree = ET.fromstring(kml_string)
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        dados = {}
        placemarks = tree.findall(".//kml:Placemark", ns)
        for placemark in placemarks:
            props = {sd.get("name"): sd.text for sd in placemark.findall(".//kml:SimpleData", ns)}
            name_elem = placemark.find("kml:name", ns)
            props["Name"] = name_elem.text if name_elem is not None else "Sem Nome"
            nome_faz = props.get("NOME_FAZ", props.get("Name", "Unidade Desconhecida"))
            props["UNIDADE_normalized"] = normalize_str(nome_faz)  # Garantir criação da coluna
            # ... resto do código ...
            geometry = None
            coord_tags = {
                "Polygon": ".//kml:Polygon/kml:outerBoundaryIs/kml:LinearRing/kml:coordinates",
                "LineString": ".//kml:LineString/kml:coordinates",
                "Point": ".//kml:Point/kml:coordinates"
            }
            for geom_type, tag in coord_tags.items():
                elem = placemark.find(tag, ns)
                if elem is not None:
                    coords_text = elem.text.strip()
                    coords = [tuple(map(float, c.split(","))) for c in coords_text.split()]
                    try:
                        if geom_type == "Polygon":
                            geometry = Polygon([(c[0], c[1]) for c in coords])
                        elif geom_type == "LineString":
                            geometry = LineString([(c[0], c[1]) for c in coords])
                        elif geom_type == "Point":
                            geometry = Point(coords[0])
                        break
                    except Exception as geom_e:
                        st.markdown(
                            f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
                            f'⚠️ Erro ao criar geometria para placemark {props.get("Name", "Sem Nome")}: {geom_e}'
                            f'</div>',
                            unsafe_allow_html=True
                        )
                        continue
            if geometry:
                nome_faz = props.get("NOME_FAZ", props.get("Name", "Unidade Desconhecida"))
                props["NOME_FAZ"] = nome_faz
                unidade = nome_faz
                if unidade not in dados:
                    dados[unidade] = {"geometries": [], "props": {}}
                dados[unidade]["geometries"].append(geometry)
                dados[unidade]["props"].update(props)

        if not dados:
            st.markdown(
                '<div style="background-color:#fff3cd;padding:12px;border-radius:8px;border-left:6px solid #ffca28;">'
                '⚠️ Nenhuma geometria válida encontrada no KML.'
                '</div>',
                unsafe_allow_html=True
            )
            return gpd.GeoDataFrame(columns=['Name', 'geometry', 'UNIDADE_normalized'], crs="EPSG:4326")

        gdf_data = [{
            "Name": unidade,
            "geometry": unary_union(info["geometries"]),
            "NOME_FAZ": info["props"].get("NOME_FAZ", info["props"].get("Name", "Unidade Desconhecida")),
            "UNIDADE_normalized": normalize_str(info["props"].get("NOME_FAZ", info["props"].get("Name", "Unidade Desconhecida"))),
            **info["props"]
        } for unidade, info in dados.items()]
        gdf = gpd.GeoDataFrame(gdf_data, crs="EPSG:4326")
        
        # Reprojetar para UTM dinamicamente com base na longitude média
        if not gdf.empty:
            lon_mean = gdf.geometry.centroid.x.mean()
            utm_zone = int((lon_mean + 180) / 6) + 1
            hemisphere = 'south' if gdf.geometry.centroid.y.mean() < 0 else 'north'
            utm_crs = f"EPSG:327{utm_zone}" if hemisphere == 'south' else f"EPSG:326{utm_zone}"
            gdf = gdf.to_crs(utm_crs)
            st.write(f"Geometrias reprojetadas para CRS: {utm_crs}")
        
        # Depuração: exibir os valores de UNIDADE_normalized
        st.write("Valores de UNIDADE_normalized no KML:", gdf["UNIDADE_normalized"].unique().tolist())
        return gdf
    except Exception as e:
        st.markdown(
            f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
            f'❌ Erro ao processar KML: {e}'
            f'</div>',
            unsafe_allow_html=True
        )
        return gpd.GeoDataFrame(columns=['Name', 'geometry', 'UNIDADE_normalized'], crs="EPSG:4326")

def normalize_str(s):
    try:
        return unidecode(str(s).strip().upper()) if pd.notna(s) else ""
    except Exception:
        return ""

def haversine(lon1, lat1, lon2, lat2):
    try:
        R = 6371
        lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c
    except Exception:
        return None

def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    c = 2*math.asin(math.sqrt(a))
    return R * c

def get_route(start_lon, start_lat, end_lon, end_lat):
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        r = requests.get(url)
        if r.status_code != 200:
            return None
        res = r.json()
        routes = res.get("routes", [])
        if not routes:
            return None
        route_coords = routes[0]["geometry"]["coordinates"]
        points = [(point[1], point[0]) for point in route_coords]
        return points
    except Exception:
        return None

def criar_banco():
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
    return "Banco de dados 'mapa_dados.db' e tabelas criadas com sucesso!"

def migrar(kml_file, xlsx_file):
    conn = sqlite3.connect('mapa_dados.db')
    cursor = conn.cursor()

    # Processar Excel
    df_analistas = pd.read_excel(xlsx_file)
    df_analistas.columns = [normalize_str(col) for col in df_analistas.columns]
    coords = df_analistas["COORDENADAS_CIDADE"].astype(str).str.replace("'", "").str.split(",", expand=True)
    df_analistas["LAT_BASE"] = pd.to_numeric(coords[0], errors="coerce")
    df_analistas["LON_BASE"] = pd.to_numeric(coords[1], errors="coerce")
    df_analistas["UNIDADE_normalized"] = df_analistas["UNIDADE"].apply(normalize_str)
    # Depuração: exibir valores de UNIDADE_normalized no Excel
    st.write("Valores de UNIDADE_normalized no Excel:", df_analistas["UNIDADE_normalized"].unique().tolist())

    especialistas_unicos = df_analistas.drop_duplicates(subset=['ESPECIALISTA'])
    for _, row in especialistas_unicos.iterrows():
        cursor.execute(
            "INSERT OR IGNORE INTO especialistas (nome, gestor, cidade_base, latitude_base, longitude_base) VALUES (?, ?, ?, ?, ?)",
            (normalize_str(row['ESPECIALISTA']), normalize_str(row['GESTOR']), normalize_str(row['CIDADE_BASE']), row['LAT_BASE'], row['LON_BASE'])
        )
    conn.commit()

    # Processar KML
    kml_content = kml_file.read()
    gdf_kml = extrair_dados_kml(kml_content)
    if 'UNIDADE_normalized' not in gdf_kml.columns:
        st.error("Coluna 'UNIDADE_normalized' não encontrada no KML após processamento. Verifique o arquivo KML.")
        conn.close()
        return df_analistas, gdf_kml, "Erro na migração: UNIDADE_normalized ausente."
    # Depuração: exibir valores de UNIDADE_normalized no KML
    st.write("Valores de UNIDADE_normalized no KML:", gdf_kml["UNIDADE_normalized"].unique().tolist())
    st.write(f"CRS do gdf_kml após extrair_dados_kml: {gdf_kml.crs}")

    # Juntar e inserir fazendas
    df_merged = pd.merge(
        df_analistas, gdf_kml,
        on="UNIDADE_normalized", how="inner"
    )
    if df_merged.empty:
        st.warning("Nenhuma correspondência encontrada entre Excel e KML. Verifique se os nomes em 'UNIDADE' (Excel) correspondem a 'NOME_FAZ' (KML).")
        st.write("UNIDADE_normalized no Excel:", df_analistas["UNIDADE_normalized"].unique().tolist())
    st.write("UNIDADE_normalized no KML:", gdf_kml["UNIDADE_normalized"].unique().tolist())
    df_merged = pd.merge(df_analistas, gdf_kml, on="UNIDADE_normalized", how="inner")
    if df_merged.empty:
        st.error("Merge vazio! Verifique correspondência entre UNIDADE (Excel) e NOME_FAZ (KML).")
        st.write("Exemplo Excel:", df_analistas[["UNIDADE", "UNIDADE_normalized"]].head().to_dict())
        st.write("Exemplo KML:", gdf_kml[["NOME_FAZ", "UNIDADE_normalized"]].head().to_dict())
        conn.close()
        return df_analistas, gdf_kml, "Erro na migração: Nenhuma correspondência encontrada."

    for _, row in df_merged.iterrows():
        cursor.execute("SELECT id FROM especialistas WHERE nome = ?", (normalize_str(row['ESPECIALISTA']),))
        result = cursor.fetchone()
        if result:
            especialista_id = result[0]
            geometry = row['geometry']
            # Converter geometria para EPSG:4326 para armazenamento
            geometry_4326 = gpd.GeoSeries([geometry], crs=gdf_kml.crs).to_crs("EPSG:4326").iloc[0]
            geometria_geojson = gpd.GeoSeries([geometry_4326], crs="EPSG:4326").to_json()
            cursor.execute(
                "INSERT INTO fazendas (nome_fazenda, especialista_id, geometria_json, latitude_centroide, longitude_centroide) VALUES (?, ?, ?, ?, ?)",
                (row['NOME_FAZ'], especialista_id, geometria_geojson, geometry_4326.centroid.y, geometry_4326.centroid.x)
            )
    conn.commit()
    conn.close()
    return df_analistas, gdf_kml, f"{len(especialistas_unicos)} especialistas e {len(df_merged)} fazendas inseridos!"
def criar_mapa_analistas(df_analistas, gdf_kml, gestor, especialista, mostrar_rotas):
    if gdf_kml.empty:
        st.markdown(
            '<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
            '❌ Nenhuma geometria válida encontrada no KML.'
            '</div>',
            unsafe_allow_html=True
        )
        return None

    gdf_kml["Longitude_Unidade"] = gdf_kml.geometry.centroid.x
    gdf_kml["Latitude_Unidade"] = gdf_kml.geometry.centroid.y
    gdf_kml["UNIDADE_normalized"] = gdf_kml["NOME_FAZ"].apply(normalize_str)

    df_analistas.columns = [normalize_str(col) for col in df_analistas.columns]
    expected_cols = ["GESTOR", "ESPECIALISTA", "CIDADE_BASE", "UNIDADE", "COORDENADAS_CIDADE"]
    missing_cols = [col for col in expected_cols if col not in df_analistas.columns]
    if missing_cols:
        st.markdown(
            f'<div style="background-color:#f8d7da;padding:12px;border-radius:8px;border-left:6px solid #dc3545;">'
            f'❌ Colunas faltando no Excel: {missing_cols}'
            f'</div>',
            unsafe_allow_html=True
        )
        return None

    for col in ["GESTOR", "ESPECIALISTA", "CIDADE_BASE", "UNIDADE"]:
        df_analistas[col] = df_analistas[col].apply(normalize_str)

    df_analistas["COORDENADAS_CIDADE"] = df_analistas["COORDENADAS_CIDADE"].astype(str).str.replace("'", "")
    coords = df_analistas["COORDENADAS_CIDADE"].str.split(",", expand=True)
    df_analistas["LAT_BASE"] = pd.to_numeric(coords[0], errors="coerce")
    df_analistas["LON_BASE"] = pd.to_numeric(coords[1], errors="coerce")
    df_analistas = df_analistas.dropna(subset=["LAT_BASE", "LON_BASE"])
    df_analistas["UNIDADE_normalized"] = df_analistas["UNIDADE"].apply(normalize_str)

    df_merged = pd.merge(
        df_analistas,
        gdf_kml[["UNIDADE_normalized", "Latitude_Unidade", "Longitude_Unidade", "geometry", "Name", "NOME_FAZ"]],
        on="UNIDADE_normalized",
        how="left"
    )
    df_merged = df_merged.dropna(subset=["Latitude_Unidade", "Longitude_Unidade"])
    df_merged["DISTANCIA_KM"] = df_merged.apply(
        lambda row: haversine(row["LON_BASE"], row["LAT_BASE"], row["Longitude_Unidade"], row["Latitude_Unidade"]),
        axis=1
    )

    cores_base = ["#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231",
                  "#911EB4", "#46F0F0", "#F032E6", "#BCF60C", "#FABEBE",
                  "#008080", "#E6BEFF", "#9A6324", "#FFFAC8", "#800000",
                  "#AAFFC3", "#808000", "#FFD8B1", "#000075", "#808080"]
    especialistas_unicos = df_merged["ESPECIALISTA"].unique()
    cor_especialista = {especialista: cores_base[i % len(cores_base)] for i, especialista in enumerate(especialistas_unicos)}
    df_merged["COR"] = df_merged["ESPECIALISTA"].map(cor_especialista)

    df_filtrado = df_merged.copy()
    if gestor != "Todos":
        df_filtrado = df_filtrado[df_filtrado["GESTOR"] == gestor]
    if especialista != "Todos":
        df_filtrado = df_filtrado[df_filtrado["ESPECIALISTA"] == especialista]

    if df_filtrado.empty:
        st.markdown(
            '<div style="background-color:#fff3cd;padding:12px;border-radius:8px;border-left:6px solid #ffca28;">'
            '⚠️ Nenhum resultado para a seleção. Verifique os filtros de gestor e especialista.'
            '</div>',
            unsafe_allow_html=True
        )
        return None

    map_center = [df_filtrado["Latitude_Unidade"].mean(), df_filtrado["Longitude_Unidade"].mean()]
    mapa = folium.Map(location=map_center, zoom_start=7, tiles="openstreetmap", control=True)

    colaboradores_cluster = MarkerCluster(name="Colaboradores").add_to(mapa)
    fazendas_group = folium.FeatureGroup(name="Fazendas").add_to(mapa)
    rotas_group = folium.FeatureGroup(name="Rotas").add_to(mapa)

    popup_css = """
    <style>
        .leaflet-popup-content {
            font-family: Arial, sans-serif;
            font-size: 16px;
            line-height: 1.6;
            padding: 15px;
            background-color: #ffffff;
            border-radius: 10px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.2);
            min-width: 400px;
            max-height: 350px;
            overflow-y: auto;
        }
        .leaflet-popup-content b {
            color: #00497a;
            font-weight: bold;
        }
        .leaflet-popup-content ul {
            margin: 8px 0;
            padding-left: 25px;
        }
        .leaflet-popup-content li {
            margin-bottom: 6px;
        }
        .leaflet-popup-content-wrapper {
            width: 450px !important;
        }
    </style>
    """
    mapa.get_root().html.add_child(folium.Element(popup_css))

    info_especialistas = df_filtrado.groupby(["ESPECIALISTA", "CIDADE_BASE", "LAT_BASE", "LON_BASE", "COR"]).agg(
        RAIO_MAXIMO_KM=("DISTANCIA_KM", "max"),
        DIST_MEDIA_KM=("DISTANCIA_KM", "mean"),
        UNIDADES_ATENDIDAS=("UNIDADE", lambda x: list(x.unique()))
    ).reset_index()

    for _, row in info_especialistas.iterrows():
        especialista_nome = row["ESPECIALISTA"].title()
        cidade_base = row["CIDADE_BASE"].title()
        raio_maximo = row["RAIO_MAXIMO_KM"]
        dist_media = row["DIST_MEDIA_KM"]
        unidades_lista = row["UNIDADES_ATENDIDAS"]
        cor = row["COR"]
        lat_base = row["LAT_BASE"]
        lon_base = row["LON_BASE"]

        max_unidades = 5
        unidades_mostradas = unidades_lista[:max_unidades]
        if len(unidades_lista) > max_unidades:
            unidades_mostradas.append(f"... e mais {len(unidades_lista) - max_unidades} unidades")
        unidades_html_list = [f"<li>{u.title()}</li>" for u in unidades_mostradas]
        unidades_html = "<ul>" + "".join(unidades_html_list) + "</ul>"

        popup_colaborador_html = (
            f"<b>Especialista:</b> {especialista_nome}<br>"
            f"<b>Cidade Base:</b> {cidade_base}<br>"
            f"<b>Raio de Atuação:</b> {raio_maximo:.1f} km<br>"
            f"<b>Distância Média:</b> {dist_media:.1f} km<br>"
            f"<b>Unidades Atendidas:</b> {unidades_html}"
        )

        folium.Circle(
            location=[lat_base, lon_base],
            radius=raio_maximo * 1000,
            color=cor,
            fill=True,
            fill_color=cor,
            fill_opacity=0.15,
            weight=2
        ).add_to(mapa)

        folium.Marker(
            location=[lat_base, lon_base],
            icon=folium.Icon(color="white", icon_color=cor, icon="user", prefix="fa"),
            popup=folium.Popup(popup_colaborador_html, max_width=450, max_height=350),
            tooltip=especialista_nome
        ).add_to(colaboradores_cluster)

    route_count = 0
    max_routes = 10
    for _, row in df_filtrado.dropna(subset=["Latitude_Unidade", "Longitude_Unidade", "geometry"]).iterrows():
        fazenda_nome = row["NOME_FAZ"].title()
        cidade_origem = row["CIDADE_BASE"].title()
        especialista_responsavel = row["ESPECIALISTA"].title()
        cor_fazenda = row["COR"]
        lat_unidade = row["Latitude_Unidade"]
        lon_unidade = row["Longitude_Unidade"]
        lat_base_colab = row["LAT_BASE"]
        lon_base_colab = row["LON_BASE"]
        geometry = row["geometry"]

        if isinstance(geometry, (Polygon, MultiPolygon)):
            if isinstance(geometry, Polygon):
                coords = [list(geometry.exterior.coords)]
            else:
                coords = [list(poly.exterior.coords) for poly in geometry.geoms]
            for coord in coords:
                folium.Polygon(
                    locations=[(lat, lon) for lon, lat in coord],
                    color=cor_fazenda,
                    fill=True,
                    fill_color=cor_fazenda,
                    fill_opacity=0.3,
                    weight=2,
                    popup=f"<b>Fazenda:</b> {fazenda_nome}<br><b>Atendida por:</b> {especialista_responsavel}"
                ).add_to(fazendas_group)

        distancia_km = row['DISTANCIA_KM']
        popup_fazenda_html = (
            f"<b>Fazenda:</b> {fazenda_nome}<br>"
            f"<b>Cidade de Origem:</b> {cidade_origem}<br>"
            f"<b>Atendida por:</b> {especialista_responsavel}<br>"
            f"<b>Distância da Base:</b> {distancia_km:.1f} km"
        )
        folium.Marker(
            location=[lat_unidade, lon_unidade],
            icon=folium.Icon(color="white", icon_color=cor_fazenda, icon="home", prefix="fa"),
            popup=folium.Popup(popup_fazenda_html, max_width=450, max_height=350),
            tooltip=fazenda_nome
        ).add_to(fazendas_group)

        if mostrar_rotas and route_count < max_routes:
            route_points = get_route(lon_base_colab, lat_base_colab, lon_unidade, lat_unidade)
            if route_points:
                line = LineString([(lon, lat) for lat, lon in route_points])
                simplified_line = line.simplify(tolerance=0.001)
                simplified_points = [(y, x) for x, y in simplified_line.coords]
                folium.PolyLine(simplified_points, color=cor_fazenda, weight=2.5, opacity=0.8).add_to(rotas_group)
                route_count += 1
            time.sleep(0.3)

    legenda_html = '''
    <div style="position: fixed;
    bottom: 10px; left: 10px; width: 250px; max-height: 300px;
    border: 2px solid grey; z-index: 9999; font-size: 14px;
    background-color: white; padding: 10px; border-radius: 8px;
    overflow-y: auto;">
    <b>Legenda de Especialistas</b><br>
    '''
    for esp, cor in cor_especialista.items():
        if esp in df_filtrado["ESPECIALISTA"].unique():
            legenda_html += f'<i class="fa fa-circle" style="color:{cor}"></i> {esp.title()}<br>'
    legenda_html += "</div>"
    mapa.get_root().html.add_child(folium.Element(legenda_html))

    folium.LayerControl(collapsed=False).add_to(mapa)
    return mapa

# Título principal
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor, especialista ou visualize as cidades mais próximas das unidades. Use 'Todos' para ver a visão consolidada.")

# Abas
tab1, tab2, tab3 = st.tabs(["📤 Upload e Migração", "🗺️ Mapa de Analistas", "🏙️ Análise de Cidades"])

# Aba 1: Upload e Migração
with tab1:
    st.header("📤 Upload de Arquivos e Migração de Dados")
    kml_file = st.file_uploader("📍 Carregar arquivo KML", type=["kml"], key="kml_upload")
    xlsx_file = st.file_uploader("📊 Carregar arquivo Excel", type=["xlsx"], key="xlsx_upload")
    
    if st.button("🚀 Criar Banco e Migrar Dados"):
        if kml_file and xlsx_file:
            with st.spinner("Criando banco e migrando dados..."):
                try:
                    st.success(criar_banco())
                    df_analistas, gdf_kml, msg = migrar(kml_file, xlsx_file)
                    st.session_state['df_analistas'] = df_analistas
                    st.session_state['gdf_kml'] = gdf_kml
                    st.success(msg)
                except Exception as e:
                    st.error(f"Erro ao migrar dados: {str(e)}")
        else:
            st.error("Por favor, faça upload dos arquivos KML e Excel.")

# Aba 2: Mapa de Analistas
with tab2:
    st.header("🗺️ Mapa Interativo de Analistas")
    
    # Verificar se os dados estão disponíveis no session_state
    if 'df_analistas' in st.session_state and 'gdf_kml' in st.session_state:
        df_analistas = st.session_state['df_analistas'].copy()  # Criar cópia para evitar alterações no original
        gdf_kml = st.session_state['gdf_kml'].copy()

        # Garantir que UNIDADE_normalized existe em ambos os DataFrames
        if 'UNIDADE_normalized' not in df_analistas.columns:
            st.error("Coluna 'UNIDADE_normalized' não encontrada em df_analistas. Verifique o upload e migração na aba 1.")
            st.write("Colunas disponíveis em df_analistas:", df_analistas.columns.tolist())
            st.stop()

        if 'UNIDADE_normalized' not in gdf_kml.columns:
            st.error("Coluna 'UNIDADE_normalized' não encontrada em gdf_kml. Verifique o upload do arquivo KML na aba 1.")
            st.write("Colunas disponíveis em gdf_kml:", gdf_kml.columns.tolist())
            st.stop()

        # Normalizar novamente as colunas necessárias para garantir consistência
        df_analistas['GESTOR'] = df_analistas['GESTOR'].apply(normalize_str)
        df_analistas['ESPECIALISTA'] = df_analistas['ESPECIALISTA'].apply(normalize_str)
        df_analistas['CIDADE_BASE'] = df_analistas['CIDADE_BASE'].apply(normalize_str)
        df_analistas['UNIDADE'] = df_analistas['UNIDADE'].apply(normalize_str)
        df_analistas['UNIDADE_normalized'] = df_analistas['UNIDADE'].apply(normalize_str)

        # Garantir que gdf_kml tenha UNIDADE_normalized e geometrias válidas
        gdf_kml['UNIDADE_normalized'] = gdf_kml['NOME_FAZ'].apply(normalize_str)
        gdf_kml = gdf_kml[gdf_kml.geometry.notnull()]  # Remover geometrias nulas

        # Reprojetar gdf_kml para UTM dinamicamente
        try:
            lon_mean = gdf_kml.geometry.centroid.x.mean()
            utm_zone = int((lon_mean + 180) / 6) + 1
            hemisphere = 'south' if gdf_kml.geometry.centroid.y.mean() < 0 else 'north'
            utm_crs = f"EPSG:327{utm_zone}" if hemisphere == 'south' else f"EPSG:326{utm_zone}"
            gdf_kml = gdf_kml.to_crs(utm_crs)
            gdf_kml["centroid"] = gdf_kml.geometry.centroid
            st.write(f"Geometrias reprojetadas para CRS: {utm_crs}")
        except Exception as e:
            st.error(f"Erro ao reprojetar geometrias: {e}")
            st.stop()

        # Calcular centroides em EPSG:4326 para o mapa
        gdf_kml_4326 = gdf_kml.to_crs("EPSG:4326")
        gdf_kml["Longitude_Unidade_4326"] = gdf_kml_4326.geometry.centroid.x
        gdf_kml["Latitude_Unidade_4326"] = gdf_kml_4326.geometry.centroid.y

        # Merge entre df_analistas e gdf_kml
        try:
            df_merged = pd.merge(
                df_analistas,
                gdf_kml[["UNIDADE_normalized", "Latitude_Unidade_4326", "Longitude_Unidade_4326", "geometry", "Name", "NOME_FAZ"]],
                on="UNIDADE_normalized",
                how="left"
            )
            if df_merged.empty:
                st.error("Nenhuma correspondência encontrada entre df_analistas e gdf_kml. Verifique os dados de entrada.")
                st.write("Valores de UNIDADE_normalized em df_analistas:", df_analistas["UNIDADE_normalized"].unique().tolist())
                st.write("Valores de UNIDADE_normalized em gdf_kml:", gdf_kml["UNIDADE_normalized"].unique().tolist())
                st.stop()
        except Exception as e:
            st.error(f"Erro ao mesclar dados: {e}")
            st.stop()

        # Calcular distâncias
        df_merged["DISTANCIA_KM"] = df_merged.apply(
            lambda row: haversine(row["LON_BASE"], row["LAT_BASE"], 
                                 row["Longitude_Unidade_4326"], row["Latitude_Unidade_4326"]) 
            if pd.notnull(row["Longitude_Unidade_4326"]) and pd.notnull(row["Latitude_Unidade_4326"]) 
            else None,
            axis=1
        )
        df_merged = df_merged.dropna(subset=["Latitude_Unidade_4326", "Longitude_Unidade_4326", "DISTANCIA_KM"])

        if df_merged.empty:
            st.error("Nenhum dado válido após o merge. Verifique os arquivos KML e Excel.")
            st.stop()

        # Definir cores para especialistas
        cores_base = ["#E6194B", "#3CB44B", "#FFE119", "#4363D8", "#F58231",
                      "#911EB4", "#46F0F0", "#F032E6", "#BCF60C", "#FABEBE",
                      "#008080", "#E6BEFF", "#9A6324", "#FFFAC8", "#800000",
                      "#AAFFC3", "#808000", "#FFD8B1", "#000075", "#808080"]
        especialistas_unicos = df_merged["ESPECIALISTA"].unique()
        cor_especialista = {especialista: cores_base[i % len(cores_base)] for i, especialista in enumerate(especialistas_unicos)}
        df_merged["COR"] = df_merged["ESPECIALISTA"].map(cor_especialista)

        # Filtros
        st.markdown("### Filtros")
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1], gap="medium")
        with col1:
            gestores = ["Todos os Gestores"] + sorted(df_analistas["GESTOR"].unique().tolist())
            gestor_selecionado = st.selectbox("Gestor:", options=gestores, format_func=lambda x: x.title(), key="gestor_mapa")
        with col2:
            especialistas = ["Todos os Especialistas"] + sorted(df_analistas["ESPECIALISTA"].unique().tolist())
            especialista_selecionado = st.selectbox("Especialista:", options=especialistas, format_func=lambda x: x.title(), key="especialista_mapa")
        with col3:
            mostrar_rotas = st.checkbox("Mostrar Rotas", value=False, key="mostrar_rotas")
        with col4:
            mostrar_raio = st.checkbox("Mostrar Raio de Atuação", value=True, key="mostrar_raio")

        # Aplicar filtros
        df_filtrado = df_merged.copy()
        if gestor_selecionado != "Todos os Gestores":
            df_filtrado = df_filtrado[df_filtrado["GESTOR"] == gestor_selecionado]
        if especialista_selecionado != "Todos os Especialistas":
            df_filtrado = df_filtrado[df_filtrado["ESPECIALISTA"] == especialista_selecionado]

        if df_filtrado.empty:
            st.warning("Nenhum resultado para a seleção. Verifique os filtros de gestor e especialista.")
            st.stop()

        # Criar o mapa
        map_center = [df_filtrado["Latitude_Unidade_4326"].mean(), df_filtrado["Longitude_Unidade_4326"].mean()]
        mapa = folium.Map(location=map_center, zoom_start=7, tiles="openstreetmap", control=True)

        colaboradores_cluster = MarkerCluster(name="Colaboradores").add_to(mapa)
        fazendas_group = folium.FeatureGroup(name="Fazendas").add_to(mapa)
        rotas_group = folium.FeatureGroup(name="Rotas").add_to(mapa)

        # Estilizar popups
        popup_css = """
        <style>
            .leaflet-popup-content {
                font-family: Arial, sans-serif;
                font-size: 16px;
                line-height: 1.6;
                padding: 15px;
                background-color: #ffffff;
                border-radius: 10px;
                box-shadow: 0 3px 10px rgba(0,0,0,0.2);
                min-width: 400px;
                max-height: 350px;
                overflow-y: auto;
            }
            .leaflet-popup-content b {
                color: #00497a;
                font-weight: bold;
            }
            .leaflet-popup-content ul {
                margin: 8px 0;
                padding-left: 25px;
            }
            .leaflet-popup-content li {
                margin-bottom: 6px;
            }
            .leaflet-popup-content-wrapper {
                width: 450px !important;
            }
        </style>
        """
        mapa.get_root().html.add_child(folium.Element(popup_css))

        # Adicionar marcadores de especialistas
        info_especialistas = df_filtrado.groupby(["ESPECIALISTA", "CIDADE_BASE", "LAT_BASE", "LON_BASE", "COR"]).agg(
            RAIO_MAXIMO_KM=("DISTANCIA_KM", "max"),
            DIST_MEDIA_KM=("DISTANCIA_KM", "mean"),
            UNIDADES_ATENDIDAS=("UNIDADE", lambda x: list(x.unique()))
        ).reset_index()

        for _, row in info_especialistas.iterrows():
            especialista_nome = row["ESPECIALISTA"].title()
            cidade_base = row["CIDADE_BASE"].title()
            raio_maximo = row["RAIO_MAXIMO_KM"]
            dist_media = row["DIST_MEDIA_KM"]
            unidades_lista = row["UNIDADES_ATENDIDAS"]
            cor = row["COR"]
            lat_base = row["LAT_BASE"]
            lon_base = row["LON_BASE"]

            max_unidades = 5
            unidades_mostradas = unidades_lista[:max_unidades]
            if len(unidades_lista) > max_unidades:
                unidades_mostradas.append(f"... e mais {len(unidades_lista) - max_unidades} unidades")
            unidades_html_list = [f"<li>{u.title()}</li>" for u in unidades_mostradas]
            unidades_html = "<ul>" + "".join(unidades_html_list) + "</ul>"

            popup_colaborador_html = (
                f"<b>Especialista:</b> {especialista_nome}<br>"
                f"<b>Cidade Base:</b> {cidade_base}<br>"
                f"<b>Raio de Atuação:</b> {raio_maximo:.1f} km<br>"
                f"<b>Distância Média:</b> {dist_media:.1f} km<br>"
                f"<b>Unidades Atendidas:</b> {unidades_html}"
            )

            if mostrar_raio:
                folium.Circle(
                    location=[lat_base, lon_base],
                    radius=raio_maximo * 1000,
                    color=cor,
                    fill=True,
                    fill_color=cor,
                    fill_opacity=0.15,
                    weight=2
                ).add_to(mapa)

            folium.Marker(
                location=[lat_base, lon_base],
                icon=folium.Icon(color="white", icon_color=cor, icon="user", prefix="fa"),
                popup=folium.Popup(popup_colaborador_html, max_width=450, max_height=350),
                tooltip=especialista_nome
            ).add_to(colaboradores_cluster)

        # Adicionar marcadores de fazendas e rotas
        route_count = 0
        max_routes = 10
        for _, row in df_filtrado.dropna(subset=["Latitude_Unidade_4326", "Longitude_Unidade_4326", "geometry"]).iterrows():
            fazenda_nome = row["NOME_FAZ"].title()
            cidade_origem = row["CIDADE_BASE"].title()
            especialista_responsavel = row["ESPECIALISTA"].title()
            cor_fazenda = row["COR"]
            lat_unidade = row["Latitude_Unidade_4326"]
            lon_unidade = row["Longitude_Unidade_4326"]
            lat_base_colab = row["LAT_BASE"]
            lon_base_colab = row["LON_BASE"]
            geometry = row["geometry"]

            if isinstance(geometry, (Polygon, MultiPolygon)):
                if isinstance(geometry, Polygon):
                    coords = [list(geometry.exterior.coords)]
                else:
                    coords = [list(poly.exterior.coords) for poly in geometry.geoms]
                for coord in coords:
                    folium.Polygon(
                        locations=[(lat, lon) for lon, lat in coord],
                        color=cor_fazenda,
                        fill=True,
                        fill_color=cor_fazenda,
                        fill_opacity=0.3,
                        weight=2,
                        popup=f"<b>Fazenda:</b> {fazenda_nome}<br><b>Atendida por:</b> {especialista_responsavel}"
                    ).add_to(fazendas_group)

            distancia_km = row['DISTANCIA_KM']
            popup_fazenda_html = (
                f"<b>Fazenda:</b> {fazenda_nome}<br>"
                f"<b>Cidade de Origem:</b> {cidade_origem}<br>"
                f"<b>Atendida por:</b> {especialista_responsavel}<br>"
                f"<b>Distância da Base:</b> {distancia_km:.1f} km"
            )
            folium.Marker(
                location=[lat_unidade, lon_unidade],
                icon=folium.Icon(color="white", icon_color=cor_fazenda, icon="home", prefix="fa"),
                popup=folium.Popup(popup_fazenda_html, max_width=450, max_height=350),
                tooltip=fazenda_nome
            ).add_to(fazendas_group)

            if mostrar_rotas and route_count < max_routes:
                route_points = get_route(lon_base_colab, lat_base_colab, lon_unidade, lat_unidade)
                if route_points:
                    line = LineString([(lon, lat) for lat, lon in route_points])
                    simplified_line = line.simplify(tolerance=0.001)
                    simplified_points = [(y, x) for x, y in simplified_line.coords]
                    folium.PolyLine(simplified_points, color=cor_fazenda, weight=2.5, opacity=0.8).add_to(rotas_group)
                    route_count += 1
                else:
                    st.warning(f"Falha ao obter rota para {fazenda_nome}.")
                time.sleep(0.3)

        # Adicionar legenda
        legenda_html = '''
        <div style="position: fixed;
        bottom: 10px; left: 10px; width: 250px; max-height: 300px;
        border: 2px solid grey; z-index: 9999; font-size: 14px;
        background-color: white; padding: 10px; border-radius: 8px;
        overflow-y: auto;">
        <b>Legenda de Especialistas</b><br>
        '''
        for esp, cor in cor_especialista.items():
            if esp in df_filtrado["ESPECIALISTA"].unique():
                legenda_html += f'<i class="fa fa-circle" style="color:{cor}"></i> {esp.title()}<br>'
        legenda_html += "</div>"
        mapa.get_root().html.add_child(folium.Element(legenda_html))

        folium.LayerControl(collapsed=False).add_to(mapa)

        # Exibir estatísticas
        st.markdown("### Estatísticas")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(
                f'<div class="metric-card"><div class="metric-title">Total de Especialistas</div><div class="metric-value">{len(df_analistas["ESPECIALISTA"].unique())}</div></div>',
                unsafe_allow_html=True
            )
        with col2:
            st.markdown(
                f'<div class="metric-card"><div class="metric-title">Total de Unidades</div><div class="metric-value">{len(df_analistas["UNIDADE"].unique())}</div></div>',
                unsafe_allow_html=True
            )
        with col3:
            st.markdown(
                f'<div class="metric-card"><div class="metric-title">Total de Fazendas</div><div class="metric-value">{len(gdf_kml)}</div></div>',
                unsafe_allow_html=True
            )
        with col4:
            st.markdown(
                f'<div class="metric-card"><div class="metric-title">Gestores Ativos</div><div class="metric-value">{len(df_analistas["GESTOR"].unique())}</div></div>',
                unsafe_allow_html=True
            )

        # Exibir o mapa
        st.subheader("Mapa Interativo")
        st_folium(mapa, height=600, use_container_width=True)
    else:
        st.info("ℹ️ Para visualizar o mapa, faça upload dos arquivos KML e Excel e realize a migração na primeira aba.")
