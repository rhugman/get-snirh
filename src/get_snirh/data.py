import logging
import pandas as pd
from typing import List, Union, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .client import SnirhClient
from .constants import SnirhUrls, Parameters
from .exceptions import SnirhNetworkError

logger = logging.getLogger(__name__)

class DataFetcher:
    """
    Fetches time-series data for stations.
    """

    def __init__(self, client: SnirhClient):
        self.client = client

    def get_timeseries(
        self, 
        station_codes: Union[List[str], Dict[str, str], pd.DataFrame], 
        parameter: Union[str, Parameters], 
        start_date: str, 
        end_date: str,
        max_workers: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetches time-series data for a list of station codes (marker sites).
        
        Args:
            station_codes: Can be:
                - List of 'marker_site' codes (URL codes).
                - Dict mapping 'marker_site' -> 'station_name'.
                - DataFrame with 'marker_site' and 'estacao' columns.
            parameter: The parameter ID (string or Enum).
            start_date: Start date in 'dd/mm/yyyy' format.
            end_date: End date in 'dd/mm/yyyy' format.
            max_workers: Maximum number of concurrent requests. 
                         If None, defaults to min(10, len(stations)).
            
        Returns:
            pd.DataFrame: Concatenated data for all stations.
        """
        if isinstance(parameter, Parameters):
            par_id = parameter.value
            par_name = parameter.name
        else:
            par_id = str(parameter)
            par_name = str(parameter)

        # Station mapping: {marker_site: station_name}
        station_map = {}
        if isinstance(station_codes, list):
            station_map = {code: code for code in station_codes}
        elif isinstance(station_codes, dict):
            station_map = station_codes
        elif isinstance(station_codes, pd.DataFrame):
            if 'marker_site' in station_codes.columns and 'estacao' in station_codes.columns:
                station_map = dict(zip(station_codes['marker_site'], station_codes['estacao']))
            else:
                raise ValueError("DataFrame must contain 'marker_site' and 'estacao' columns.")
        
        logger.info("Fetching time-series for %d stations. Parameter: %s (%s)", len(station_map), par_name, par_id)

        all_dfs = []

        def fetch_single(code, name):
            try:
                logger.debug("Fetching data for station: %s (code: %s)", name, code)
                url = (
                    f"{SnirhUrls.DATA_CSV}?"
                    f"sites={code}&pars={par_id}&tmin={start_date}&tmax={end_date}&formato=csv"
                )
                
                csv_buffer = self.client.fetch_csv(url)

                df_temp = pd.read_csv(
                    csv_buffer,
                    sep=',',
                    skiprows=3,
                    parse_dates=[0],
                    date_format='%d/%m/%Y %H:%M',
                    dayfirst=True,
                    index_col=[0],
                    usecols=[0, 1],
                    header=0,
                    skipfooter=1,
                    names=['date', 'value'],
                    engine='python'
                )
                
                df_temp = df_temp.reset_index()
                df_temp['site_name'] = name
                df_temp['parameter'] = par_name
                df_temp = df_temp[['date', 'site_name', 'parameter', 'value']]
                return df_temp
            except Exception as e:
                logger.error("Error fetching data for station %s (code %s): %s", name, code, str(e))
                return None

        if max_workers is None:
            # Cap at 10 to be polite to the SNIRH server.
            max_workers = max(1, min(10, len(station_map)))

        logger.debug("Using %d workers for concurrent fetching", max_workers)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_station = {executor.submit(fetch_single, code, name): name for code, name in station_map.items()}
            for future in as_completed(future_to_station):
                try:
                    result = future.result()
                    if result is not None and not result.empty:
                        all_dfs.append(result)
                except Exception as e:
                    logger.error("Unexpected error in thread: %s", str(e))

        all_dfs = [df for df in all_dfs if not df.empty]

        if not all_dfs:
            logger.warning("No data fetched for any station.")
            return pd.DataFrame(columns=['date', 'site_name', 'parameter', 'value'])

        final_df = pd.concat(all_dfs, ignore_index=True)
        final_df = final_df.sort_values(by=['site_name', 'date']).reset_index(drop=True)
        
        logger.info("Fetched total %d rows of data.", len(final_df))
        return final_df
