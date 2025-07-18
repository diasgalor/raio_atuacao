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

# CSS atualizado para maior responsividade
st.markdown("""
   <style>
   html, body, .stApp {
       background-color: #f7f8fa;
       font-family: 'Inter', 'Arial', sans-serif !important;
   }
   .stApp {
       max-width: 1400px;
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
       margin-bottom: 12px;
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
   .stData  {
       border-radius: 10px !important;
       border: 1.5px solid #dbeafe !important;
   }
   @media screen and (max-width: 768px) {
       .stApp { padding: 10px !important; max-width: 100% !important; }
       .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput { 
           font-size: 12px !important; 
           padding: 6px !important; 
       }
       .stExpander { padding: 10px !important; }
       .metric-card { padding: 10px !important; }
       .metric-title { font-size: 12px; }
       .metric-value { font-size: 16px; }
       .stButton>button { font-size: 12px; padding: 6px 12px; }
       .stColumn { width: 100% !important; margin-bottom: 8px; }
       .stMap { height: 350px !important; }
   }
   @media screen and (max-width: 480px) {
       .stApp { padding: 8px !important; }
       .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput { 
           font-size: 11px !important; 
           padding: 5px !important; 
       }
       .metric-card { padding: 8px !important; }
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
                    st.warning(f"Erro ao criar geometria para placemark {props.get('Name', 'Sem Nome')}: {geom_e}")
                    geometry = None

            line_elem = placemark.find('.//kml:LineString/kml:coordinates', ns)
            if line_elem is not None:
                coords_text = line_elem.text.strip()
                coords = [tuple(map(float, c.split(','))) for c in coords_text.split()]
                try:
                    from shapely.geometry import LineString
                    geometry = LineString([(c[0], c[1]) for c in coords]).centroid
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

def normalize_str(s):
    return unidecode(str(s).strip().upper())

# ========================= BLOCO DE ANÁLISE DE CIDADE MAIS PRÓXIMA =========================

st.markdown("---")
st.header("🏙️ Análise de Cidade Mais Próxima da Unidade (Fazenda)")

st.sidebar.markdown("### (Opcional) Cidade mais próxima")
geojson_file = st.sidebar.file_uploader("🌎 Upload Cidades GeoJSON", type=['geojson'])

if kml_file and xlsx_file and geojson_file:
    try:
        cidades_data = json.load(geojson_file)
        cidades_lista = []
        for feat in cidades_data["features"]:
            prop = feat["properties"]
            cidade_nome = prop.get("nome") or prop.get("NOME") or prop.get("cidade") or prop.get("City") or list(prop.values())[0]
            geom = shape(feat["geometry"])
            lon, lat = geom.centroid.x, geom.centroid.y
            cidades_lista.append({
                "CIDADE": normalize_str(cidade_nome),
                "LAT": lat,
                "LON": lon,
                "raw_nome": cidade_nome
            })
        df_cidades = pd.DataFrame(cidades_lista)
        unidades_opcoes = sorted(set(df_analistas["UNIDADE"].unique()))
        unidade_sel = st.selectbox("Selecione a unidade (fazenda) para análise:", options=unidades_opcoes, key="unidade_cidade_mais_proxima")
        unidade_norm = normalize_str(unidade_sel)

        unidade_row = gdf_kml[gdf_kml['UNIDADE_normalized'] == unidade_norm]
        if not unidade_row.empty:
            uni_lat = unidade_row['Latitude'].iloc[0]
            uni_lon = unidade_row['Longitude'].iloc[0]

            def haversine_m(lon1, lat1, lon2, lat2):
                R = 6371000
                lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
                dlon = lon2 - lon1
                dlat = lat2 - lat1
                a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
                c = 2*math.asin(math.sqrt(a))
                return R * c

            df_cidades["DIST_METROS"] = df_cidades.apply(lambda row: haversine_m(uni_lon, uni_lat, row["LON"], row["LAT"]), axis=1)
            cidade_mais_proxima = df_cidades.loc[df_cidades["DIST_METROS"].idxmin()]
            cidade_nome = cidade_mais_proxima["raw_nome"]
            cidade_norm = cidade_mais_proxima["CIDADE"]
            cidade_dist_km = cidade_mais_proxima["DIST_METROS"] / 1000

            st.success(f"Cidade mais próxima: **{cidade_nome}** ({cidade_dist_km:.1f} km da unidade)")

            analistas_cidade = df_analistas[df_analistas["CIDADE_BASE"] == cidade_norm]
            analistas_atendem = df_analistas[df_analistas["UNIDADE_normalized"] == unidade_norm]

            analistas_moram_atendem = analistas_cidade[analistas_cidade["UNIDADE_normalized"] == unidade_norm]
            analistas_moram_atendem = analistas_moram_atendem.drop_duplicates(subset=["ESPECIALISTA", "GESTOR", "CIDADE_BASE"])

            analistas_moram_nao_atendem = analistas_cidade[analistas_cidade["UNIDADE_normalized"] != unidade_norm]
            analistas_moram_nao_atendem = analistas_moram_nao_atendem.drop_duplicates(subset=["ESPECIALISTA", "GESTOR", "CIDADE_BASE"])

            st.markdown("#### Analistas que moram na cidade mais próxima e atendem esta fazenda:")
            if not analistas_moram_atendem.empty:
                st.dataframe(analistas_moram_atendem[["GESTOR", "ESPECIALISTA", "CIDADE_BASE", "UNIDADE"]], hide_index=True)
            else:
                st.info("Nenhum analista mora nessa cidade e atende esta fazenda.")

            st.markdown("#### Analistas que moram na cidade mais próxima e **NÃO** atendem esta fazenda:")
            if not analistas_moram_nao_atendem.empty:
                st.dataframe(analistas_moram_nao_atendem[["GESTOR", "ESPECIALISTA", "CIDADE_BASE", "UNIDADE"]], hide_index=True)
            else:
                st.info("Nenhum analista mora nessa cidade e não atende esta fazenda.")

            if analistas_moram_atendem.empty:
                st.warning("Nenhum analista mora na cidade mais próxima e atende esta fazenda. Veja abaixo as cidades base dos especialistas que atendem esta fazenda:")
                if not analistas_atendem.empty:
                    st.dataframe(analistas_atendem[["GESTOR", "ESPECIALISTA", "CIDADE_BASE", "UNIDADE"]].drop_duplicates(), hide_index=True)
                else:
                    st.info("Nenhum analista atende esta fazenda.")
        else:
            st.error("Não foi possível localizar a unidade selecionada no KML.")
    except Exception as e:
        st.error(f"Erro na análise de cidade mais próxima: {str(e)}")
else:
    st.info("Para a análise de cidade mais próxima, faça upload dos arquivos KML, Excel e GeoJSON de cidades.")
# ====================== FIM DO BLOCO DE ANÁLISE DE CIDADE MAIS PRÓXIMA ======================
