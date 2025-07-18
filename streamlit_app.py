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
        padding: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    }
    .stExpander {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        margin-bottom: 15px;
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
    @media screen and (max-width: 600px) {
        .stApp {
            padding: 10px !important;
        }
        .stExpander {
            padding: 12px !important;
        }
        .metric-card {
            padding: 12px !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

# Título e descrição
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor e especialista (ou 'Todos') para visualizar as unidades atendidas, distâncias e o raio de atuação no mapa.")

# [As funções extrair_dados_kml, normalize_str e haversine permanecem EXATAMENTE as mesmas que no código anterior]

if kml_file and xlsx_file:
    try:
        # [Todo o processamento dos arquivos KML e Excel permanece EXATAMENTE igual]
        
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
                    ).sort_values('Distância (km)')
                    
                    # Formatação condicional para a tabela
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

                # Criação do mapa (permanece igual)
                m = folium.Map(location=[row['LAT'], row['LON']], zoom_start=8, tiles="cartodbpositron")
                # [...] (restante do código do mapa permanece igual)
                
            else:
                st.warning("Nenhum dado encontrado para o especialista selecionado.")
    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload dos arquivos KML e Excel na barra lateral para continuar.")
