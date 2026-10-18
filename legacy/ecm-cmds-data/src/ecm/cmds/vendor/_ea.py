import base64
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor as Pool
from functools import cached_property
from io import StringIO
from multiprocessing import Pool as MP_Pool
from typing import List

import pandas as pd
import requests
import urllib3
from ecm.atom.clients import retry
from ecm.cmds.core.schema import EAMetadata
from ecm.cmds.core.sql import LO25DB
from loguru import logger as log
from tqdm import tqdm
from urllib3.exceptions import InsecureRequestWarning

urllib3.disable_warnings(category=InsecureRequestWarning)


if sys.platform.startswith("win"):
    os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = r"C:\local\certs\root.crt"
    os.environ["REQUESTS_CA_BUNDLE"] = r"C:\local\certs\root.crt"
    os.environ["SSL_CERT_FILE"] = r"C:\local\certs\root.crt"


class EAClient:
    """
    Client for accessing EA data.
    """

    _api_key = os.environ["EA_API_KEY"]

    def __init__(self):
        self.base_url = "https://api.energyaspects.com"
        self.dataset_mappings

    @retry(max_tries=3, exceptions=[requests.HTTPError], before_retry=lambda **_: time.sleep(10))
    def _get_data(self, endpoint: str, **kwargs) -> pd.DataFrame:
        """
        Fetch data from the EA API.
        """
        parameters = "&".join(f"{k}={v}" for k, v in kwargs.items())
        req_url = f"{self.base_url}/{endpoint}?api_key={self._api_key}&{parameters}"
        response = requests.get(req_url, verify=False)
        response.raise_for_status()
        return response.json() if "csv" not in endpoint else response.content.decode("utf-8")

    @cached_property
    def dataset_mappings(self) -> dict:
        base_url = "data/dataset_mappings"
        kwg = {"licensed": 1}  # only licensed datasets
        all_webfile_mappings = self._get_data(base_url, **kwg)
        return all_webfile_mappings

    @property
    def metadata(self) -> pd.DataFrame:
        db = LO25DB("prod")
        meta = EAMetadata(nullable=False).load_sql(db, form="db")
        return meta

    def get_timeseries_dataset_names(self) -> pd.DataFrame:
        """
        Get all dataset IDs from the EA API.
        """
        all_webfile_mappings_json = self.dataset_mappings
        dataset_names = self.get_datasets_names(all_webfile_mappings_json)
        return dataset_names

    def get_datasets_names(self, all_webfile_mappings: dict) -> List[str]:
        """
        Gets the datasets names from webfile mappings

        Args:
            all_webfile_mappings: Response from dataset_mappings endpoint

        Returns:
            A list of dataset names
        """
        dataset_names = []
        for category in all_webfile_mappings.values():
            for item in category:
                dataset_names.append(item["name"])

        return dataset_names

    def get_all_mappings(self) -> pd.DataFrame:
        all_webfile_mappings = self.dataset_mappings
        dataset_names = self.get_datasets_names(all_webfile_mappings)
        name_to_dataset_ids = {}
        for name in dataset_names:
            dataset_ids = self.get_dataset_ids_for_dataset(name)
            name_to_dataset_ids[name] = dataset_ids
        df = pd.concat(
            [
                pd.DataFrame({"dataset_ids": y}, index=[x] * len(y))
                for x, y in name_to_dataset_ids.items()
            ]
        ).reset_index()
        df.columns = ["dataset_name", "dataset_ids"]
        df = (
            df.groupby("dataset_name", as_index=False)
            .agg(lambda x: list(x))
            .set_index("dataset_name")
        )
        return df

    def find_dataset_by_keyword(self, keyword: str) -> pd.DataFrame:
        """
        Find datasets by a keyword in their names.

        Args:
            keyword: The keyword to search for in dataset names.

        Returns:
            A DataFrame containing dataset names and their IDs that match the keyword.
        """
        all_mappings = self.get_all_mappings()
        filtered_datasets = all_mappings[
            all_mappings.index.str.contains(keyword, case=False, regex=True)
        ]
        return filtered_datasets

    def get_dataset_ids_for_dataset(self, dataset_name: str):
        """
        Retrieve the dataset IDs associated with a given dataset

        Args:
            all_webfile_mappings: Response from dataset_mapping endpoint
            dataset_name: The name of the file to search for.

        Returns:
            A list of dataset IDs corresponding to the given file name.
        """
        all_webfile_mappings_json = self.dataset_mappings

        dataset_ids = next(
            (
                dataset_mapping["dataset_ids"]
                for category in all_webfile_mappings_json.values()
                for dataset_mapping in category
                if dataset_mapping["name"] == dataset_name
            ),
            None,
        )
        return dataset_ids

    def get_data(
        self,
        dataset_ids: str | List[str] | List[int] | None = None,
        dataset_name: str = None,
        start_date: str = None,
        release_date: str = None,
    ) -> pd.DataFrame:
        """Get data dataset by its name or ID(s).

        dataset_ids can be a single ID, a list of IDs, or a comma-separated string of IDs.
        dataset_name can be used to find dataset IDs if not provided. Does a regex search
        on dataset names to find matching datasets.
        start_date and release_date can be used to filter the data from the EA API.

        """
        if not dataset_name and not dataset_ids:
            raise ValueError("Either dataset_name or dataset_ids must be provided.")
        if dataset_ids and isinstance(dataset_ids, str):
            dataset_ids = dataset_ids.split(",")
        if not dataset_ids and dataset_name:
            dataset_id_df = self.find_dataset_by_keyword(dataset_name)
        else:
            dataset_id_df = pd.DataFrame(
                {"dataset_ids": [dataset_ids]}, index=[dataset_name or "unknown"]
            )

        if dataset_id_df.empty:
            raise ValueError(f"No dataset IDs found for dataset name: {dataset_name}")
        if len(dataset_id_df) > 1:
            log.warning(
                f"Warning: Multiple dataset ID lists found for dataset name '{dataset_name}'"
            )
        out_df = pd.DataFrame()
        for name, row in dataset_id_df.iterrows():
            try:
                endpoint = "data/timeseries/csv"
                params = {}
                if start_date:
                    params["date_from"] = start_date
                if release_date:
                    params["release_date"] = release_date
                dataset_ids_str = ",".join(list(map(str, row.dataset_ids)))
                params["dataset_id"] = dataset_ids_str
                response = self._get_data(endpoint, **params)
                resp_df = pd.read_csv(StringIO(response))
                out_df = pd.concat([out_df, resp_df])
            except Exception as e:
                log.error(f"Error fetching data for dataset name {name}: {e}")
                continue

        return out_df

    def _get_metadata(self, dataset_ids: str | List[str] | List[int]) -> dict:
        """
        Get metadata for a specific dataset ID.

        Args:
            dataset_id: A single ID, a list of IDs, or a comma-separated string of IDs.

        Returns:
            A dictionary containing the metadata for the specified dataset ID.
        """
        if not dataset_ids:
            raise ValueError("dataset_ids must be provided.")
        if dataset_ids and isinstance(dataset_ids, str):
            dataset_ids = dataset_ids.split(",")
        if not isinstance(dataset_ids, list):
            dataset_ids = [dataset_ids]
        kwg = {"dataset_id": ",".join(map(str, dataset_ids))}

        endpoint = "data/datasets/timeseries"
        response = self._get_data(endpoint, **kwg)
        if isinstance(response, list):
            if len(response) == 0:
                resp = pd.DataFrame()
            else:
                resp = pd.concat(
                    [
                        pd.DataFrame(dict(dataset_id=x["dataset_id"], **x["metadata"]))
                        for x in response
                    ]
                )
        else:
            resp = pd.DataFrame(dict(dataset_id=response["dataset_id"], **response["metadata"]))

        if "release_dates" in resp.columns:
            resp = resp.drop(columns=["release_dates"])
            resp = resp.drop_duplicates()

        return resp

    def _process_metadata(self, name, ids, comp) -> pd.DataFrame:
        try:
            if isinstance(ids, list):
                group_size = 20  # Adjust this based on your system's capabilities
                groups = [ids[i : i + group_size] for i in range(0, len(ids), group_size)]
                metadata = pd.DataFrame()
                with Pool() as pool:
                    meta = list(tqdm(pool.map(self._get_metadata, groups), total=len(groups)))
                    if len(meta) > 0:
                        metadata = pd.concat(meta)
                        metadata["dataset_name"] = name
            else:
                metadata = self._get_metadata(ids)
                metadata["dataset_name"] = name
        except Exception as e:
            log.error(f"Error fetching metadata for dataset name {name}: {e}")
            metadata = pd.DataFrame()
        log.info(f"Done: {comp}")
        return metadata

    def get_metadata(
        self, dataset_ids: str | List[str] | List[int] | None = None, dataset_name: str = None
    ) -> pd.DataFrame:
        """
        Get metadata for a specific dataset ID or IDs.

        Args:
            dataset_ids: A single ID, a list of IDs, or a comma-separated string of IDs.

        Returns:
            A DataFrame containing the metadata for the specified dataset ID(s).
        """
        all_meta = self.all_metadata(licensed=False)
        all_meta = all_meta.reset_index()
        all_meta = all_meta.drop(columns=["id"])
        if dataset_ids:
            if isinstance(dataset_ids, str):
                dataset_ids = list(map(int, dataset_ids.split(",")))
            else:
                dataset_ids = list(map(int, dataset_ids))
            filtered_meta = all_meta[all_meta.dataset_id.isin(dataset_ids)]
            if not filtered_meta.empty:
                metadata = filtered_meta
            else:
                log.warning(f"No metadata found for dataset IDs: {dataset_ids}")
                metadata = pd.DataFrame()  # return empty DataFrame if no metadata found
        elif dataset_name:
            filtered_meta = all_meta[all_meta.dataset_name.str.contains(dataset_name)]
            if not filtered_meta.empty:
                metadata = filtered_meta
            else:
                log.warning(f"No metadata found for dataset name: {dataset_name}")
                metadata = pd.DataFrame()
        else:
            log.warning("No dataset_ids or dataset_name provided. Returning all metadata.")
            metadata = all_meta
        return metadata

    def all_metadata(self, update=False, licensed=True) -> pd.DataFrame:
        existing_metadata = self.metadata
        datasets = self.get_all_mappings()
        missing_meta = datasets[~datasets.index.isin(list(existing_metadata.dataset_name.unique()))]
        if missing_meta.empty:
            meta_df = existing_metadata
        elif update or not missing_meta.empty:
            datasets = missing_meta
            meta_df = pd.DataFrame()
            args = [
                (row.name, row.dataset_ids, f"{i+1}/{len(datasets)}")
                for i, (_, row) in enumerate(datasets.iterrows())
            ]
            with MP_Pool(10) as pool:
                meta = pool.starmap(self._process_metadata, args)
            meta_df = pd.concat(meta)
            if meta_df.empty:
                log.warning("No new metadata found.")
                return existing_metadata
            else:
                meta_df.licensed = meta_df.licensed.replace({"no": False, "yes": True})
                meta_df = EAMetadata(meta_df)
                to_insert = meta_df[~meta_df.index.isin(existing_metadata.index)]
                EAMetadata(to_insert).dump_sql(
                    LO25DB("prod"), form="db", mode="update_first", chunk_size=5000
                )
                meta_df = EAMetadata().load_sql(LO25DB("prod"), form="db")
        else:
            meta_df = existing_metadata
        if licensed:
            meta_df = meta_df[meta_df.licensed == True]  # noqa: E712
        return meta_df

    def get_release_dates(self, dataset_id: str, monthly=True) -> List[str]:
        """
        Get release dates for the given dataset ID.

        Args:
            dataset_id: A single ID, a list of IDs, or a comma-separated string of IDs.

        Returns:
            A DataFrame containing the release dates for the specified dataset IDs.
        """
        if not dataset_id:
            raise ValueError("dataset_id must be provided.")
        if not isinstance(dataset_id, str):
            dataset_id = str(dataset_id)

        endpoint = f"data/datasets/timeseries/{dataset_id}"
        response = self._get_data(endpoint)
        release_dates = response.get("metadata", {}).get("release_dates", [])
        if len(release_dates) == 0:
            log.warning(f"No release dates found for dataset ID: {dataset_id}")
            return []
        release_dates = release_dates[-80:]
        release_dates = pd.DatetimeIndex(release_dates)

        if monthly:
            monthly_release_dts = release_dates[~release_dates.to_period("m").duplicated()]
            monthly_release_dts = [x.strftime("%Y-%m-%dT23:55:00") for x in monthly_release_dts]
            return monthly_release_dts
        else:
            weekly_release_dts = release_dates[
                ~release_dates.to_period("d").duplicated(keep="last")
            ]
            weekly_release_dts = [x.strftime("%Y-%m-%dT23:55:00") for x in weekly_release_dts]
            return weekly_release_dts


if __name__ == "__main__":
    client = EAClient()
    x = client.get_metadata(dataset_ids="3325,3326")
    print(x.head())
    y = client.get_metadata(dataset_name="runs")
    print(y)
