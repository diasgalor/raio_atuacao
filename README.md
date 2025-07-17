# Análise de Raio de Atuação dos Analistas

Esta é uma aplicação Streamlit que exibe um mapa interativo com:
- Limites de unidades a partir de um arquivo KML.
- Marcadores para analistas com base em uma tabela CSV.
- Círculos representando o raio de atuação de cada analista.
- Informações sobre a distância entre o analista e o centro da unidade.

## Como usar
1. Faça upload de um arquivo KML contendo os limites das unidades (com uma coluna `Name`).
2. Faça upload de um arquivo CSV com as colunas: `GESTOR`, `ESPECIALISTA`, `CIDADE_BASE`, `UNIDADE`, `COORDENADAS_CIDADE`.
3. Defina o raio de atuação (em km).
4. Visualize o mapa interativo e clique nos marcadores para ver detalhes.

## Estrutura do CSV
```csv
GESTOR,ESPECIALISTA,CIDADE_BASE,UNIDADE,COORDENADAS_CIDADE
ANTONIO NETO,IGOR.DIAS,CHAPADAO DO SUL,PANTANAL,-18.785815277673734, -52.60783105764658
