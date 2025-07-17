import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster
from shapely.geometry import Point
from streamlit_folium import st_folium

# Configuração da página
st.set_page_config(page_title="Raio de Atuação dos Analistas", layout="wide")

st.title("📍 Raio de Atuação dos Analistas")
st.markdown("Faça upload do **arquivo KML** da localização das unidades e da **planilha Excel** com analistas e gestores.")

# Upload de arquivos
kml_file = st.file_uploader("📂 Faça upload do arquivo KML", type=['kml'])
xlsx_file = st.file_uploader("📊 Faça upload da tabela de analistas (Excel)", type=['xlsx', 'xls'])

if kml_file and xlsx_file:
    try:
        # Leitura do KML
        gdf_kml = gpd.read_file(kml_file, driver='KML')
        gdf_kml['geometry'] = gdf_kml['geometry'].to_crs(epsg=4326)  # Garante CRS
        gdf_kml[['Longitude', 'Latitude']] = gdf_kml.geometry.apply(lambda p: pd.Series([p.centroid.x, p.centroid.y]))
        gdf_kml['UNIDADE_normalized'] = gdf_kml['Name'].str.upper().str.strip()

        # Leitura da planilha de analistas
        df_analistas = pd.read_excel(xlsx_file)
        df_analistas.columns = df_analistas.columns.str.upper()
        df_analistas['UNIDADE'] = df_analistas['UNIDADE'].str.upper().str.strip()
        df_analistas['ESPECIALISTA'] = df_analistas['ESPECIALISTA'].str.strip().str.upper()
        df_analistas['GESTOR'] = df_analistas['GESTOR'].str.strip().str.upper()
        df_analistas['CIDADE_BASE'] = df_analistas['CIDADE_BASE'].str.upper()

        # Junta coordenadas da unidade
        df_merge = df_analistas.merge(gdf_kml[['UNIDADE_normalized', 'Latitude', 'Longitude']], left_on='UNIDADE', right_on='UNIDADE_normalized', how='left')
        df_merge = df_merge.dropna(subset=['Latitude', 'Longitude'])

        # Agrupa e calcula distâncias por especialista
        gdf_base = df_merge.drop_duplicates(subset=['ESPECIALISTA', 'Latitude', 'Longitude'])
        gdf_base['base_point'] = gdf_base.apply(lambda row: Point(row['Longitude'], row['Latitude']), axis=1)

        resultados = []
        for (gestor, esp), df_sub in df_merge.groupby(['GESTOR', 'ESPECIALISTA']):
            cidade_base = df_sub['CIDADE_BASE'].iloc[0]
            base_coords = df_sub[['Latitude', 'Longitude']].iloc[0]

            distancias = []
            for _, row in df_sub.iterrows():
                dist = ((row['Latitude'] - base_coords[0])**2 + (row['Longitude'] - base_coords[1])**2)**0.5 * 111  # Aproximação
                distancias.append((row['UNIDADE'], dist))

            unidades = list(set([d[0] for d in distancias]))
            medias = sum([d[1] for d in distancias]) / len(distancias)
            max_dist = max([d[1] for d in distancias])

            resultados.append({
                'GESTOR': gestor,
                'ESPECIALISTA': esp,
                'CIDADE_BASE': cidade_base,
                'UNIDADES_ATENDIDAS': unidades,
                'DIST_MEDIA': round(medias, 1),
                'DIST_MAX': round(max_dist, 1),
                'DETALHES': distancias
            })

        # Interface: seleção por gestor → especialista
        gestores = sorted(set([r['GESTOR'] for r in resultados]))
        gestor_selecionado = st.selectbox("👨‍💼 Selecione o Gestor", options=gestores)

        especialistas_filtrados = [r for r in resultados if r['GESTOR'] == gestor_selecionado]
        nomes_especialistas = [r['ESPECIALISTA'] for r in especialistas_filtrados]

        especialistas_selecionados = st.multiselect("👨‍🔬 Selecione os Especialistas", options=nomes_especialistas, default=nomes_especialistas)

        # Exibição
        for r in especialistas_filtrados:
            if r['ESPECIALISTA'] in especialistas_selecionados:
                with st.container():
                    st.markdown(f"### 👤 Especialista: `{r['ESPECIALISTA']}`")
                    st.markdown(f"📍 Cidade Base: **{r['CIDADE_BASE']}**")
                    st.markdown(f"🏢 Unidades Atendidas: **{len(r['UNIDADES_ATENDIDAS'])}**")
                    st.markdown(f"📏 Distância Média: **{r['DIST_MEDIA']} km**")
                    st.markdown(f"📏 Distância Máxima: **{r['DIST_MAX']} km**")
                    st.dataframe(pd.DataFrame(r['DETALHES'], columns=['Unidade', 'Distância (km)']).sort_values('Distância (km)'))

    except Exception as e:
        st.error(f"Erro ao processar os arquivos: {e}")
else:
    st.info("🔄 Aguarde o upload dos arquivos KML e Excel para continuar.")
