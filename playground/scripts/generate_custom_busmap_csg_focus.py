#!/usr/bin/env python3
"""Generate a custom PyPSA-Earth busmap focused on China Southern Grid.

Default output:
    data/custom_busmap_elec_s_51.csv

The cluster allocation is:
    CSG provinces: 40
    Northeast: 1
    North China: 2
    East China: 2
    Central China excluding CSG: 2
    Northwest: 2
    Tibet/Xinjiang: 2

AC and DC buses are never assigned to the same cluster. PyPSA requires the
aggregated Bus.carrier attribute to be consistent inside each cluster.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pypsa
from shapely.geometry import Point
from sklearn.cluster import KMeans


DEFAULT_NETWORK = "networks/CN_power_2035_ssp226/elec_s.nc"
DEFAULT_PROVINCES = "playground/res/china_map/\u7701\u7ea7\u884c\u653f\u533a.shp"
DEFAULT_OUTPUT = "data/custom_busmap_elec_s_51.csv"

PROVINCE_COL = "NAME"

REGIONS = {
    "CSG": {
        "clusters": 40,
        "provinces": [
            "\u5e7f\u4e1c",
            "\u5e7f\u897f",
            "\u4e91\u5357",
            "\u8d35\u5dde",
            "\u6d77\u5357",
            "\u9999\u6e2f",
            "\u6fb3\u95e8",
        ],
    },
    "NE": {
        "clusters": 1,
        "provinces": ["\u8fbd\u5b81", "\u5409\u6797", "\u9ed1\u9f99\u6c5f"],
    },
    "NC": {
        "clusters": 2,
        "provinces": [
            "\u5317\u4eac",
            "\u5929\u6d25",
            "\u6cb3\u5317",
            "\u5c71\u897f",
            "\u5185\u8499\u53e4",
            "\u5c71\u4e1c",
        ],
    },
    "EC": {
        "clusters": 2,
        "provinces": [
            "\u4e0a\u6d77",
            "\u6c5f\u82cf",
            "\u6d59\u6c5f",
            "\u5b89\u5fbd",
            "\u798f\u5efa",
        ],
    },
    "CC_NON_CSG": {
        "clusters": 2,
        "provinces": [
            "\u6cb3\u5357",
            "\u6e56\u5317",
            "\u6e56\u5357",
            "\u6c5f\u897f",
            "\u56db\u5ddd",
            "\u91cd\u5e86",
        ],
    },
    "NW": {
        "clusters": 2,
        "provinces": ["\u9655\u897f", "\u7518\u8083", "\u9752\u6d77", "\u5b81\u590f"],
    },
    "XJ_XZ": {
        "clusters": 2,
        "provinces": ["\u65b0\u7586", "\u897f\u85cf"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create data/custom_busmap_elec_s_51.csv for a CSG-focused China clustering."
    )
    parser.add_argument("--network", default=DEFAULT_NETWORK, help="Input elec_s.nc")
    parser.add_argument(
        "--provinces",
        default=DEFAULT_PROVINCES,
        help="Province shapefile with a NAME column",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output busmap CSV")
    parser.add_argument(
        "--random-state",
        type=int,
        default=0,
        help="KMeans random_state for reproducible clusters",
    )
    parser.add_argument(
        "--n-init",
        type=int,
        default=100,
        help="KMeans n_init",
    )
    return parser.parse_args()


def normalize_province_name(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def province_to_region() -> dict[str, str]:
    mapping: dict[str, str] = {}
    duplicates: list[str] = []
    for region, spec in REGIONS.items():
        for province in spec["provinces"]:
            if province in mapping:
                duplicates.append(province)
            mapping[province] = region

    if duplicates:
        raise ValueError(f"Province(s) assigned to multiple regions: {duplicates}")
    return mapping


def assign_provinces_to_buses(n: pypsa.Network, province_path: Path) -> gpd.GeoDataFrame:
    if not province_path.exists():
        raise FileNotFoundError(province_path)

    provinces = gpd.read_file(province_path)
    if PROVINCE_COL not in provinces.columns:
        raise ValueError(
            f"Province file must contain column {PROVINCE_COL!r}; "
            f"available columns: {list(provinces.columns)}"
        )

    provinces = provinces[[PROVINCE_COL, "geometry"]].copy()
    provinces[PROVINCE_COL] = provinces[PROVINCE_COL].map(normalize_province_name)
    provinces = provinces.to_crs("EPSG:4326")

    buses = n.buses.copy()
    buses["geometry"] = [Point(x, y) for x, y in zip(buses["x"], buses["y"])]
    buses_gdf = gpd.GeoDataFrame(buses, geometry="geometry", crs="EPSG:4326")

    joined = gpd.sjoin(
        buses_gdf,
        provinces,
        how="left",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")

    missing = joined[PROVINCE_COL].isna()
    if missing.any():
        joined_3857 = joined.to_crs("EPSG:3857")
        provinces_3857 = provinces.to_crs("EPSG:3857")
        nearest = gpd.sjoin_nearest(
            joined_3857.loc[missing, joined_3857.columns.difference([PROVINCE_COL])],
            provinces_3857,
            how="left",
            distance_col="distance_to_province_m",
        )
        joined.loc[missing, PROVINCE_COL] = nearest[PROVINCE_COL].to_numpy()

    joined[PROVINCE_COL] = joined[PROVINCE_COL].map(normalize_province_name)
    return joined


def bus_weights(n: pypsa.Network) -> pd.Series:
    load = (
        n.loads_t.p_set.mean()
        .groupby(n.loads.bus)
        .sum()
        .reindex(n.buses.index, fill_value=0.0)
    )
    generation = n.generators.groupby("bus").p_nom.sum().reindex(
        n.buses.index, fill_value=0.0
    )
    storage = n.storage_units.groupby("bus").p_nom.sum().reindex(
        n.buses.index, fill_value=0.0
    )

    weights = load + generation + storage
    positive = weights[weights > 0]
    floor = positive.quantile(0.10) if not positive.empty else 1.0
    floor = max(float(floor), 1.0)
    return weights.clip(lower=floor)


def kmeans_labels(
    buses: pd.DataFrame,
    weights: pd.Series,
    n_clusters: int,
    random_state: int,
    n_init: int,
) -> np.ndarray:
    if len(buses) <= n_clusters:
        return np.arange(len(buses))

    xy = buses[["x", "y"]].to_numpy(dtype=float)
    sample_weight = weights.reindex(buses.index).to_numpy(dtype=float)

    model = KMeans(
        n_clusters=n_clusters,
        random_state=random_state,
        n_init=n_init,
    )
    return model.fit_predict(xy, sample_weight=sample_weight)


def clusters_by_carrier(region_buses: pd.DataFrame, n_clusters: int) -> dict[str, int]:
    carriers = sorted(region_buses["carrier"].astype(str).unique())
    if len(carriers) == 1:
        return {carriers[0]: n_clusters}

    if n_clusters < len(carriers):
        raise ValueError(
            f"Region {region_buses['cluster_region'].iat[0]} has carriers {carriers} "
            f"but only {n_clusters} cluster(s). Increase its cluster quota."
        )

    allocation = {carrier: 1 for carrier in carriers}
    primary_carrier = "AC" if "AC" in allocation else carriers[0]
    allocation[primary_carrier] += n_clusters - len(carriers)
    return allocation


def build_busmap(
    n: pypsa.Network,
    buses: gpd.GeoDataFrame,
    random_state: int,
    n_init: int,
) -> pd.Series:
    p_to_r = province_to_region()
    buses = buses.copy()
    buses["cluster_region"] = buses[PROVINCE_COL].map(p_to_r)

    missing_region = buses["cluster_region"].isna()
    if missing_region.any():
        missing_provinces = sorted(set(buses.loc[missing_region, PROVINCE_COL]))
        raise ValueError(
            "Some bus provinces are not covered by REGIONS: "
            f"{missing_provinces}. Update REGIONS before generating the busmap."
        )

    weights = bus_weights(n)
    busmap = pd.Series(index=n.buses.index, dtype=object, name="busmap")

    for region, spec in REGIONS.items():
        region_buses = buses[buses["cluster_region"] == region]
        if region_buses.empty:
            raise ValueError(f"No buses found for region {region}")

        carrier_allocation = clusters_by_carrier(region_buses, spec["clusters"])
        for carrier, n_carrier_clusters in carrier_allocation.items():
            carrier_buses = region_buses[
                region_buses["carrier"].astype(str) == carrier
            ]
            labels = kmeans_labels(
                carrier_buses,
                weights,
                n_carrier_clusters,
                random_state=random_state,
                n_init=n_init,
            )
            busmap.loc[carrier_buses.index] = [
                f"{region}_{carrier}_{int(label):02d}" for label in labels
            ]

    if busmap.isna().any():
        raise RuntimeError("Internal error: generated busmap has missing values")

    return busmap


def main() -> None:
    args = parse_args()
    network_path = Path(args.network)
    province_path = Path(args.provinces)
    output_path = Path(args.output)

    n = pypsa.Network(network_path)
    buses = assign_provinces_to_buses(n, province_path)
    busmap = build_busmap(n, buses, args.random_state, args.n_init)

    expected_clusters = sum(spec["clusters"] for spec in REGIONS.values())
    actual_clusters = int(busmap.nunique())
    if actual_clusters != expected_clusters:
        raise RuntimeError(
            f"Expected {expected_clusters} clusters, got {actual_clusters}. "
            "This usually means one region has fewer buses than requested clusters."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    busmap.to_frame().to_csv(output_path)

    summary = busmap.groupby(busmap.str.rsplit("_", n=1).str[0]).nunique()
    print(f"Wrote {output_path}")
    print(f"Buses: {len(busmap)}")
    print(f"Clusters: {actual_clusters}")
    print(summary.sort_index().to_string())


if __name__ == "__main__":
    main()
