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
