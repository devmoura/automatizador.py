import pandas as pd
import geopandas as gpd
import rasterio
from pygbif import occurrences as occ
import matplotlib.pyplot as plt

# 1. EXTRAÇÃO (GBIF)
def get_gbif_data(species_name):
    print(f"Buscando dados para {species_name}...")
    # Buscando 1000 registros
    search_res = occ.search(
        scientificName=species_name,
        hasCoordinate=True,
        occurrenceStatus='PRESENT',
        stablishmentMeans='NATIVE',
        limit=1000
    )
    
    if not search_res['results']:
        return pd.DataFrame()
        
    df = pd.DataFrame(search_res['results'])
    # Selecionamos colunas seguras que sempre existem
    cols = ['scientificName', 'decimalLatitude', 'decimalLongitude', 'country']
    # print(df.columns)
    return df[cols]

# 2. LIMPEZA MANUAL
def clean_data_manual(df):
    print("Limpando dados (Removendo ruídos geográficos)...")
    
    # a) Remover Nulos
    df = df.dropna(subset=['decimalLatitude', 'decimalLongitude'])
    
    # b) Remover pontos (0,0) - Erro comum de GPS
    df = df[(df['decimalLatitude'] != 0) & (df['decimalLongitude'] != 0)]
    
    # c) Remover duplicatas espaciais (mesma espécie no mesmo lugar)
    df = df.drop_duplicates(subset=['decimalLatitude', 'decimalLongitude'])
    
    # d) Filtro de sanidade: Lat (-90 a 90) e Lon (-180 a 180)
    df = df[(df['decimalLatitude'].between(-90, 90)) & 
            (df['decimalLongitude'].between(-180, 180))]
    
    return df

# 3. CRUZAMENTO COM KOPPEN
def cross_with_koppen(df, raster_path):
    print("Realizando cruzamento espacial com o Raster...")
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df.decimalLongitude, df.decimalLatitude),
        crs="EPSG:4326"
    )
    
    try:
        with rasterio.open(raster_path) as src:
            gdf = gdf.to_crs(src.crs)
            coords = [(x, y) for x, y in zip(gdf.geometry.x, gdf.geometry.y)]
            # Extrai o valor do pixel
            gdf['koppen_value'] = [val[0] for val in src.sample(coords)]
        return gdf
    except Exception as e:
        print(f"Erro ao abrir o arquivo .tif: {e}")
        return None

# EXECUÇÃO
SPECIES = "saccharum officinarum" 
RASTER_FILE = "koppen_geiger_0p00833333.tif"

raw_data = get_gbif_data(SPECIES)
if not raw_data.empty:
    cleaned = clean_data_manual(raw_data)
    final_result = cross_with_koppen(cleaned, RASTER_FILE)
    
    if final_result is not None:
        # 1. Contagem absoluta de cada código de clima
        contagem = final_result['koppen_value'].value_counts()
        
        # 2. Cálculo da porcentagem
        porcentagem = final_result['koppen_value'].value_counts(normalize=True) * 100
        
        # 3. Criar um DataFrame de resumo para facilitar a visualização
        resumo_clima = pd.DataFrame({
            'Frequencia_Absoluta': contagem,
            'Porcentagem (%)': porcentagem
        })
        
        # Ordenar do mais frequente para o menos frequente
        resumo_clima = resumo_clima.sort_values(by='Porcentagem (%)', ascending=False)
        
        print("\n--- Resumo da Distribuição Climática ---")
        print(resumo_clima)
        
        # Identificar o predominante
        predominante = resumo_clima.index[0]
        print(f"\nO clima predominante para esta espécie é o ID: {predominante}")
        
        # Dicionário de tradução (Beck et al.)
        koppen_legend_dict = {
            1: "Af   Tropical, rainforest ", 2: "Am   Tropical, monsoon", 3: "Aw   Tropical, savannah", 4: "BWh  Arid, desert, hot",
            5: "BWk  Arid, desert, cold", 6: "BSh  Arid, steppe, hot", 7: "BSk  Arid, steppe, cold", 8: "Csa  Temperate, dry summer, hot summer" ,
            9: "Csb  Temperate, dry summer, warm summer", 10: "Csc  Temperate, dry summer, cold summer", 11: "Cwa  Temperate, dry winter, hot summer", 
            12: "Cwb  Temperate, dry winter, warm summer", 13:"Cwc  Temperate, dry winter, cold summer"
            # Adicione outros conforme a legenda do seu arquivo .tif
        }

        # Aplicando a tradução no seu resumo
        resumo_clima['Nome_Clima'] = resumo_clima.index.map(koppen_legend_dict)
        print(resumo_clima[['Nome_Clima', 'Porcentagem (%)']])
        
        # Salvar o resumo em um CSV separado
        resumo_clima.to_csv(F"{SPECIES}_resumo_distribuicao_climatica.csv")
        
        final_result[['scientificName', 'decimalLatitude', 'decimalLongitude', 'country', 'koppen_value']].to_csv(f'{SPECIES}_resultado_coords_clima.csv', index=False)
        print("Finalizado! O arquivo 'resultado_coords_clima.csv' foi gerado.")
        
        # --- 2. Criar a Coluna de Nome do Clima ---
        # Usamos .map() para traduzir o ID numérico para o nome
        final_result['Nome_Clima'] = final_result['koppen_value'].map(koppen_legend_dict)

        # Filtrar pontos 'Nodata' para não poluírem o gráfico
        final_result = final_result[final_result['Nome_Clima'] != 'Nodata (Fora do mapa)']

        # --- 3. Plotar o Gráfico Categórico ---
        # Agora plotamos usando a coluna 'Nome_Clima'
        ax = final_result.plot(
            column='Nome_Clima', # Use a coluna categórica
            categorical=True,    # Force o gráfico a tratar como categorias
            legend=True,         # Ative a legenda automática
            markersize=10,        # Ajuste o tamanho do ponto
            cmap='viridis',      # Escolha uma paleta de cores (ex: tab10, jet, set1, accent)
            figsize=(12, 8),     # Aumente o tamanho da figura
            legend_kwds={'title': 'Classificação de Köppen-Geiger (Beck et al., 2023)', 'loc': 'upper right', 'bbox_to_anchor': (1.5, 1)} # Posicione a legenda
        )

        # --- 4. Adicionar Detalhes ao Mapa ---
        plt.title(f"Distribuição de '{SPECIES}' por Clima de Köppen (Com Legenda)")

        # Focar no Nordeste do Brasil (ajuste conforme necessário)
        ax.set_xlim(-46, -34) # Longitude
        ax.set_ylim(-15, -2)  # Latitude
        
        plt.show()

else:
    print("Nenhum dado encontrado para esta espécie.")
    
