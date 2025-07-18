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

# CSS e funções auxiliares permanecem iguais...

# Título e descrição
st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Selecione um gestor e especialista (ou 'Todos') para visualizar as unidades atendidas, distâncias e o raio de atuação no mapa.")

# Verificação se os arquivos foram carregados
if kml_file and xlsx_file:
    try:
        # Processamento dos arquivos (igual ao anterior)
        # ... [código de processamento do KML e Excel]
        
        # APÓS processar os arquivos e criar a variável 'resultados', então criamos a interface
        if 'resultados' in locals():  # Verifica se a variável foi definida
            # Interface: seleção por gestor e especialista
            col1, col2 = st.columns([1, 1], gap="medium")
            with col1:
                st.markdown("### Seleção")
                gestores = sorted(resultados['GESTOR'].unique())
                gestor_selecionado = st.selectbox("Gestor", options=gestores, format_func=lambda x: x.title())
                especialistas_filtrados = resultados[resultados['GESTOR'] == gestor_selecionado]
                nomes_especialistas = ['Todos'] + sorted(especialistas_filtrados['ESPECIALISTA'].unique())
                especialista_selecionado = st.selectbox("Especialista", options=nomes_especialistas, format_func=lambda x: x.title())
            
            # Restante do código que usa 'resultados'...
            
        else:
            st.error("Erro ao processar os dados. Verifique os arquivos e tente novamente.")
            
    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {str(e)}")
else:
    st.info("Por favor, faça upload dos arquivos KML e Excel na barra lateral para continuar.")
