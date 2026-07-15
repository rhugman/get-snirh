from enum import Enum

class SnirhUrls:
    """Base URLs for SNIRH services."""
    BASE_URL = "https://snirh.apambiente.pt/snirh/_dadosbase/site"
    STATION_LIST_CSV = f"{BASE_URL}/paraCSV/lista_csv.php"
    DATA_CSV = f"{BASE_URL}/paraCSV/dados_csv.php"

class SnirhHeaders:
    """Default headers for requests."""
    DEFAULT = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://snirh.apambiente.pt/'
    }

class Parameters(Enum):
    """SNIRH Parameter IDs."""
    # Meteorological
    WIND_DIRECTION_HOURLY = '1857'
    EVAPORATION_PICHE_DAILY = '4131'
    EVAPORATION_PICHE_MONTHLY = '1847'
    EVAPORATION_PAN_DAILY = '100733600'
    EVAPORATION_PAN_MONTHLY = '100733750'
    HUMIDITY_RELATIVE_HOURLY = '100750599'
    HUMIDITY_RELATIVE_AVG_DAILY = '439882260'
    CLOUD_COVER_DAILY = '1860'
    PAN_LEVEL_HOURLY = '100744027'
    PRECIPITATION_ANNUAL = '4237'
    PRECIPITATION_DAILY = '413026594'
    PRECIPITATION_DAILY_MAX_ANNUAL = '1578135698'
    PRECIPITATION_HOURLY = '100744007'
    PRECIPITATION_MONTHLY = '1436794570'
    RADIATION_DAILY = '490269378'
    RADIATION_HOURLY = '100749780'
    AIR_TEMP_HOURLY = '100745177'
    AIR_TEMP_MAX_DAILY = '1852'
    AIR_TEMP_AVG_DAILY = '490270830'
    AIR_TEMP_AVG_MONTHLY = '1520200094'
    AIR_TEMP_MIN_DAILY = '1853'
    WIND_SPEED_DAILY = '641792832'
    WIND_SPEED_HOURLY = '100750606'
    WIND_SPEED_INSTANT = '1041803938'
    WIND_SPEED_MAX_HOURLY = '100750612'
    WIND_SPEED_AVG_DAILY = '490270858'
    
    # Groundwater
    GWL_DEPTH = '2277'
    PIEZOMETRIC_LEVEL = '100290981'
