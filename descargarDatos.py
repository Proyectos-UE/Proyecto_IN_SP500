from dotenv import load_dotenv
load_dotenv() #Para algunas versiones de KaggleAPi es necesario cargar las variables antes de importar
from kaggle.api.kaggle_api_extended import KaggleApi

api = KaggleApi()
api.authenticate()
api.dataset_download_files("andrewmvd/sp-500-stocks", path="data/SP500Data", unzip=True)

