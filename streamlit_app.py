""import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import plotly.express as px
import math
import xml.etree.ElementTree as ET
from unidecode import unidecode

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")
st.markdown("""
<style>
    .element-container:has(.stPlotlyChart) {
        margin-bottom: 0px !important;
    }
</style>
""", unsafe_allow_html=True)

# Função para converter coordenadas de string para objeto Point
def converter_para_ponto(coordenada):
    lat, lon = map(float, coordenada.split(", "))
