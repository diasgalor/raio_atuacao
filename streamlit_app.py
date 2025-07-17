import pandas as pd
import math

# Função haversine para distância entre pontos geográficos
def haversine(lon1, lat1, lon2, lat2):
    R = 6371  # Raio da Terra em km
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# Exemplo df_analistas (substitua pelo seu dataframe real carregado)
# Deve conter pelo menos essas colunas: ['GESTOR','ESPECIALISTA','CIDADE_BASE','Latitude','Longitude','UNIDADE_normalized']

# Agrupar linhas do mesmo especialista juntando unidades
df_agrupado = (
    df_analistas.groupby(['GESTOR','ESPECIALISTA','CIDADE_BASE','Latitude','Longitude'])['UNIDADE_normalized']
    .apply(lambda x: ','.join(sorted(set([u.strip() for sublist in x.str.split(',') for u in sublist]))))
    .reset_index()
)

# Simule um dicionário com centroides das unidades para calcular distâncias
# Exemplo: {'PARNAGUA': (lon, lat), 'PLANALTO': (lon, lat), ...}
centroides_unidades = {
    # Preencha com dados reais das unidades
    'PARNAGUA': (-54.0, -20.5),
    'PLANALTO': (-53.8, -20.7),
    # ...
}

# Agora percorra especialistas agrupados e calcule métricas
for _, row in df_agrupado.iterrows():
    especialista = row['ESPECIALISTA']
    lat_esp = row['Latitude']
    lon_esp = row['Longitude']
    unidades = [u.strip() for u in row['UNIDADE_normalized'].split(',')]

    distancias = []
    for unidade in unidades:
        if unidade in centroides_unidades:
            lon_uni, lat_uni = centroides_unidades[unidade]
            dist = haversine(lon_esp, lat_esp, lon_uni, lat_uni)
            distancias.append((unidade, dist))
        else:
            distancias.append((unidade, None))

    # Filtra distâncias válidas
    dist_validas = [d for u,d in distancias if d is not None]
    media = sum(dist_validas)/len(dist_validas) if dist_validas else None
    max_dist = max(dist_validas) if dist_validas else None

    print(f"Especialista: {especialista}")
    print(f"Unidades Atendidas: {len(unidades)}")
    print(f"Distância Média (km): {media:.2f}" if media is not None else "Distância Média (km): N/A")
    print(f"Distância Máxima (km): {max_dist:.2f}" if max_dist is not None else "Distância Máxima (km): N/A")
    print("Detalhes por Unidade:")
    for u,d in distancias:
        if d is not None:
            print(f" - {u}: {d:.2f} km")
        else:
            print(f" - {u}: distância não disponível")
    print("-"*40)
