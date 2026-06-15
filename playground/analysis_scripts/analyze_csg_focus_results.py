#!/usr/bin/env python3
"""Analyze the CSG-focused PyPSA-Earth result network.

The script produces CSV summaries and figures for the 51-node CSG-focused
workflow. It is intentionally standalone so old 34-node analysis scripts remain
unchanged.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D


DEFAULT_NETWORK = (
    "results/CN_power_2035_ssp226_CSG50/networks/"
    "elec_s_51_ec_lcopt_Co2L-1h.nc"
)
DEFAULT_OUTPUT = "playground/analysis_csg_focus"
DEFAULT_PROVINCES = "playground/res/china_map/\u7701\u7ea7\u884c\u653f\u533a.shp"
DEFAULT_NATIONAL = "playground/res/china_map/\u56fd\u754c\u7ebf.shp"
DEFAULT_EXCHANGE_RATE = 7.8

REGION_ORDER = ["CSG", "CC_NON_CSG", "EC", "NC", "NE", "NW", "XJ_XZ"]
REGION_COLORS = {
    "CSG": "#d62728",
    "CC_NON_CSG": "#9467bd",
    "EC": "#1f77b4",
    "NC": "#ff7f0e",
    "NE": "#8c564b",
    "NW": "#2ca02c",
    "XJ_XZ": "#17becf",
    "UNKNOWN": "#7f7f7f",
}
TECH_COLORS = {
    "solar": "#f2c94c",
    "onwind": "#27ae60",
    "offwind-ac": "#6aa5ff",
    "offwind-dc": "#4c78a8",
    "hydro": "#1f4e79",
    "ror": "#4fa3ff",
    "PHS": "#00a6a6",
    "nuclear": "#b279a2",
    "coal": "#4d4d4d",
    "lignite": "#6b4f3a",
    "CCGT": "#c44e52",
    "OCGT": "#e17c05",
    "oil": "#8c6d62",
    "biomass": "#59a14f",
    "load shedding": "#e15759",
    "battery discharger": "#9c755f",
    "H2 fuel cell": "#f28e2b",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create analysis tables and figures for the CSG-focused result."
    )
    parser.add_argument("--network", default=DEFAULT_NETWORK, help="Solved network path")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--province-shp", default=DEFAULT_PROVINCES, help="Province shapefile")
    parser.add_argument("--national-shp", default=DEFAULT_NATIONAL, help="National boundary shapefile")
    parser.add_argument(
        "--exchange-rate",
        type=float,
        default=DEFAULT_EXCHANGE_RATE,
        help="EUR to CNY exchange rate used for CNY/kWh views",
    )
    return parser.parse_args()


def set_plot_style() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Source Han Sans SC",
        "Noto Sans CJK SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    plt.style.use("seaborn-v0_8-paper")


def bus_region(bus: object) -> str:
    text = str(bus)
    match = re.match(r"(.+?)_(?:AC|DC)_\d+(?:\b|$)", text)
    if match:
        return match.group(1)
    match = re.match(r"(.+?)_\d+$", text)
    if match:
        return match.group(1)
    return "UNKNOWN"


def add_region_columns(n: pypsa.Network) -> None:
    n.buses["analysis_region"] = n.buses.index.map(bus_region)
    n.buses["is_csg"] = n.buses["analysis_region"].eq("CSG")
    if not n.generators.empty:
        n.generators["analysis_region"] = n.generators.bus.map(n.buses.analysis_region)
    if not n.loads.empty:
        n.loads["analysis_region"] = n.loads.bus.map(n.buses.analysis_region)
    if not n.storage_units.empty:
        n.storage_units["analysis_region"] = n.storage_units.bus.map(n.buses.analysis_region)
    if not n.stores.empty and "bus" in n.stores:
        n.stores["analysis_region"] = n.stores.bus.map(n.buses.analysis_region)
    if not n.links.empty:
        n.links["bus0_region"] = n.links.bus0.map(n.buses.analysis_region)
        n.links["bus1_region"] = n.links.bus1.map(n.buses.analysis_region)
    if not n.lines.empty:
        n.lines["bus0_region"] = n.lines.bus0.map(n.buses.analysis_region)
        n.lines["bus1_region"] = n.lines.bus1.map(n.buses.analysis_region)


def component_opt(df: pd.DataFrame, nominal: str) -> pd.Series:
    opt = f"{nominal}_opt"
    if opt in df.columns:
        return df[opt].fillna(df[nominal])
    return df[nominal]


def annual_system_summary(n: pypsa.Network, out: Path, exchange_rate: float) -> pd.DataFrame:
    objective = float(getattr(n, "objective", np.nan))
    demand_mwh = n.loads_t.p_set.sum().sum()
    served_load_mwh = demand_mwh
    lcoe_cny_kwh = objective * exchange_rate / (served_load_mwh * 1000) if served_load_mwh else np.nan
    peak_load_gw = n.loads_t.p_set.sum(axis=1).max() / 1e3

    summary = pd.DataFrame(
        [
            ("objective_EUR_bn", objective / 1e9),
            ("annual_demand_TWh", demand_mwh / 1e6),
            ("peak_load_GW", peak_load_gw),
            ("average_lcoe_CNY_per_kWh", lcoe_cny_kwh),
            ("bus_count", len(n.buses)),
            ("line_count", len(n.lines)),
            ("link_count", len(n.links)),
        ],
        columns=["metric", "value"],
    )
    summary.to_csv(out / "00_system_summary.csv", index=False)
    return summary


def generation_and_storage_summary(n: pypsa.Network, out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    gen_nom = n.generators.groupby("carrier").p_nom.sum() / 1e3
    gen_opt = component_opt(n.generators, "p_nom").groupby(n.generators.carrier).sum() / 1e3
    gen_twh = n.generators_t.p.sum().groupby(n.generators.carrier).sum() / 1e6

    curtailment = {}
    for carrier, gens in n.generators.groupby("carrier"):
        cols = gens.index.intersection(n.generators_t.p_max_pu.columns)
        if len(cols) == 0:
            curtailment[carrier] = np.nan
            continue
        available = (n.generators_t.p_max_pu[cols] * component_opt(n.generators.loc[cols], "p_nom")).sum().sum()
        used = n.generators_t.p[cols].sum().sum()
        curtailment[carrier] = max(0.0, (available - used) / available * 100) if available else np.nan

    df = pd.DataFrame(
        {
            "original_capacity_GW": gen_nom,
            "optimal_capacity_GW": gen_opt,
            "expansion_GW": gen_opt - gen_nom,
            "generation_TWh": gen_twh,
            "curtailment_percent": pd.Series(curtailment),
        }
    ).fillna({"generation_TWh": 0})
    df = df.sort_values("optimal_capacity_GW", ascending=False)
    df.to_csv(out / "01_generation_summary.csv")

    storage_rows = []
    if not n.storage_units.empty:
        su_power = component_opt(n.storage_units, "p_nom").groupby(n.storage_units.carrier).sum() / 1e3
        su_energy = (
            component_opt(n.storage_units, "p_nom") * n.storage_units.max_hours
        ).groupby(n.storage_units.carrier).sum() / 1e3
        for carrier in su_power.index:
            storage_rows.append(
                {
                    "carrier": carrier,
                    "power_capacity_GW": su_power.loc[carrier],
                    "energy_capacity_GWh": su_energy.loc[carrier],
                    "component": "StorageUnit",
                }
            )
    if not n.stores.empty:
        store_energy = component_opt(n.stores, "e_nom").groupby(n.stores.carrier).sum() / 1e3
        for carrier, value in store_energy.items():
            storage_rows.append(
                {
                    "carrier": carrier,
                    "power_capacity_GW": np.nan,
                    "energy_capacity_GWh": value,
                    "component": "Store",
                }
            )
    if not n.links.empty:
        link_power = component_opt(n.links, "p_nom").groupby(n.links.carrier).sum() / 1e3
        for carrier, value in link_power.items():
            if any(token in carrier.lower() for token in ["battery", "h2", "electrolysis", "fuel cell"]):
                storage_rows.append(
                    {
                        "carrier": carrier,
                        "power_capacity_GW": value,
                        "energy_capacity_GWh": np.nan,
                        "component": "Link",
                    }
                )

    storage = pd.DataFrame(storage_rows)
    if not storage.empty:
        storage = storage.sort_values(["component", "carrier"])
    storage.to_csv(out / "02_storage_summary.csv", index=False)
    return df, storage


def regional_summary(n: pypsa.Network, out: Path, exchange_rate: float) -> pd.DataFrame:
    gen_capacity = (
        component_opt(n.generators, "p_nom")
        .groupby(n.generators.analysis_region)
        .sum()
        / 1e3
    )
    generation = n.generators_t.p.sum().groupby(n.generators.analysis_region).sum() / 1e6
    load_by_bus = n.loads_t.p_set.sum().groupby(n.loads.bus).sum()
    demand = load_by_bus.groupby(n.buses.analysis_region).sum() / 1e6
    mean_lmp = (n.buses_t.marginal_price.mean() * exchange_rate / 1000).groupby(n.buses.analysis_region).mean()

    df = pd.DataFrame(
        {
            "optimal_generation_capacity_GW": gen_capacity,
            "annual_generation_TWh": generation,
            "annual_demand_TWh": demand,
            "mean_lmp_CNY_per_kWh": mean_lmp,
        }
    ).reindex(REGION_ORDER).fillna(0)
    df["generation_minus_demand_TWh"] = df["annual_generation_TWh"] - df["annual_demand_TWh"]
    df.to_csv(out / "03_regional_summary.csv")
    return df


def transmission_summary(n: pypsa.Network, out: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    line_expansion = (component_opt(n.lines, "s_nom") - n.lines.s_nom).clip(lower=0) / 1e3
    congestion = (n.lines_t.p0.abs() >= component_opt(n.lines, "s_nom") * 0.99).mean() * 100
    lines = pd.DataFrame(
        {
            "bus0": n.lines.bus0,
            "bus1": n.lines.bus1,
            "bus0_region": n.lines.bus0_region,
            "bus1_region": n.lines.bus1_region,
            "length_km": n.lines.length,
            "original_GW": n.lines.s_nom / 1e3,
            "optimal_GW": component_opt(n.lines, "s_nom") / 1e3,
            "expansion_GW": line_expansion,
            "congestion_percent": congestion,
        }
    ).sort_values("expansion_GW", ascending=False)
    lines.to_csv(out / "04_line_expansion_and_congestion.csv")

    inter = lines[lines.bus0_region != lines.bus1_region].copy()
    if not inter.empty:
        inter["corridor"] = inter.apply(
            lambda row: " <-> ".join(sorted([str(row.bus0_region), str(row.bus1_region)])),
            axis=1,
        )
        corridors = (
            inter.groupby("corridor")
            .agg(
                line_count=("optimal_GW", "count"),
                original_GW=("original_GW", "sum"),
                optimal_GW=("optimal_GW", "sum"),
                expansion_GW=("expansion_GW", "sum"),
                mean_congestion_percent=("congestion_percent", "mean"),
            )
            .sort_values("expansion_GW", ascending=False)
        )
    else:
        corridors = pd.DataFrame()
    corridors.to_csv(out / "05_interregional_corridors.csv")
    return lines, corridors


def lmp_summary(n: pypsa.Network, out: Path, exchange_rate: float) -> pd.DataFrame:
    lmp = n.buses_t.marginal_price * exchange_rate / 1000
    df = pd.DataFrame(
        {
            "region": n.buses.analysis_region,
            "mean_CNY_per_kWh": lmp.mean(),
            "p05_CNY_per_kWh": lmp.quantile(0.05),
            "p50_CNY_per_kWh": lmp.quantile(0.50),
            "p95_CNY_per_kWh": lmp.quantile(0.95),
            "max_CNY_per_kWh": lmp.max(),
        }
    ).sort_values("mean_CNY_per_kWh", ascending=False)
    df.to_csv(out / "06_bus_lmp_summary.csv")
    return df


def dispatch_tables(n: pypsa.Network) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    p_gen = n.generators_t.p.groupby(n.generators.carrier, axis=1).sum() / 1e3
    p_discharge = pd.DataFrame(index=n.snapshots)
    p_charge = pd.DataFrame(index=n.snapshots)

    if not n.storage_units.empty:
        su = n.storage_units_t.p.groupby(n.storage_units.carrier, axis=1).sum() / 1e3
        p_discharge = pd.concat([p_discharge, su.clip(lower=0).add_suffix(" discharge")], axis=1)
        p_charge = pd.concat([p_charge, -su.clip(upper=0).add_suffix(" charge")], axis=1)

    if not n.links.empty:
        for carrier in n.links.carrier.unique():
            idx = n.links.index[n.links.carrier == carrier]
            lower = carrier.lower()
            if "discharger" in lower or "fuel cell" in lower:
                p_discharge[carrier] = (-n.links_t.p1[idx].sum(axis=1)).clip(lower=0) / 1e3
            elif "charger" in lower or "electrolysis" in lower:
                p_charge[carrier] = n.links_t.p0[idx].sum(axis=1).clip(lower=0) / 1e3

    supply = pd.concat([p_gen, p_discharge], axis=1).fillna(0)
    supply = supply.loc[:, (supply.abs() > 1e-8).any(axis=0)]
    demand = n.loads_t.p_set.sum(axis=1) / 1e3
    return supply, demand, p_charge.fillna(0)


def plot_capacity_and_generation(gen: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    plot = gen[gen["optimal_capacity_GW"] > 0.01]["optimal_capacity_GW"].sort_values()
    plot.plot.barh(ax=ax, color=[TECH_COLORS.get(c, "#999999") for c in plot.index])
    ax.set_xlabel("GW")
    ax.set_title("Optimal Generation Capacity by Carrier")
    plt.tight_layout()
    plt.savefig(out / "fig01_capacity_by_carrier.png", dpi=300)
    plt.close()

    fig, ax = plt.subplots(figsize=(10, 5))
    plot = gen[gen["generation_TWh"].abs() > 0.01]["generation_TWh"].sort_values()
    plot.plot.barh(ax=ax, color=[TECH_COLORS.get(c, "#999999") for c in plot.index])
    ax.set_xlabel("TWh")
    ax.set_title("Annual Generation by Carrier")
    plt.tight_layout()
    plt.savefig(out / "fig02_generation_by_carrier.png", dpi=300)
    plt.close()


def plot_regional_summary(regional: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    regional[["annual_generation_TWh", "annual_demand_TWh"]].plot.bar(ax=ax)
    ax.set_ylabel("TWh")
    ax.set_title("Regional Annual Generation and Demand")
    ax.tick_params(axis="x", rotation=30)
    plt.tight_layout()
    plt.savefig(out / "fig03_regional_generation_demand.png", dpi=300)
    plt.close()

    fig, ax = plt.subplots(figsize=(8, 4))
    regional["mean_lmp_CNY_per_kWh"].plot.bar(
        ax=ax,
        color=[REGION_COLORS.get(r, "#999999") for r in regional.index],
    )
    ax.set_ylabel("CNY/kWh")
    ax.set_title("Regional Mean LMP")
    ax.tick_params(axis="x", rotation=30)
    plt.tight_layout()
    plt.savefig(out / "fig04_regional_lmp.png", dpi=300)
    plt.close()


def plot_price_duration(n: pypsa.Network, out: Path, exchange_rate: float) -> None:
    lmp = (n.buses_t.marginal_price * exchange_rate / 1000).to_numpy().ravel()
    lmp = lmp[np.isfinite(lmp)]
    values = np.sort(lmp)[::-1]
    x = np.linspace(0, 100, len(values))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x, values, color="#5b2a86", lw=1.6)
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.set_xlabel("Duration share (%)")
    ax.set_ylabel("CNY/kWh")
    ax.set_title("Nodal Price Duration Curve")
    upper = np.nanpercentile(values, 99.5)
    if np.isfinite(upper) and upper > 0:
        ax.set_ylim(min(np.nanpercentile(values, 0.5), -0.05), upper * 1.1)
    ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(out / "fig05_price_duration_curve.png", dpi=300)
    plt.close()


def plot_dispatch(n: pypsa.Network, out: Path) -> None:
    supply, demand, charge = dispatch_tables(n)
    colors = [TECH_COLORS.get(c.replace(" discharge", ""), "#999999") for c in supply.columns]

    weekly = supply.resample("W").mean()
    weekly_demand = demand.resample("W").mean()
    fig, ax = plt.subplots(figsize=(13, 6))
    weekly.plot.area(ax=ax, color=colors, linewidth=0, alpha=0.85)
    weekly_demand.plot(ax=ax, color="black", lw=2, ls="--", label="Demand")
    ax.set_ylabel("GW")
    ax.set_title("Weekly Average Dispatch")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    plt.tight_layout()
    plt.savefig(out / "fig06_weekly_dispatch.png", dpi=300, bbox_inches="tight")
    plt.close()

    peak_hour = demand.idxmax()
    start = max(0, n.snapshots.get_loc(peak_hour) - 84)
    end = min(len(n.snapshots), start + 168)
    supply_week = supply.iloc[start:end]
    demand_week = demand.iloc[start:end]
    charge_week = charge.iloc[start:end]

    fig, ax = plt.subplots(figsize=(14, 6))
    supply_week.plot.area(ax=ax, color=colors, linewidth=0, alpha=0.85)
    charge_week = charge_week.loc[:, (charge_week > 1e-8).any(axis=0)]
    if not charge_week.empty:
        (-charge_week).plot.area(ax=ax, linewidth=0, alpha=0.5, cmap="Greys")
    demand_week.plot(ax=ax, color="black", lw=2, label="Demand")
    ax.set_ylabel("GW")
    ax.set_title(f"Peak-Load Week Dispatch around {peak_hour}")
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    plt.tight_layout()
    plt.savefig(out / "fig07_peak_week_dispatch.png", dpi=300, bbox_inches="tight")
    plt.close()


def load_map_layers(province_path: str, national_path: str) -> tuple[gpd.GeoDataFrame | None, gpd.GeoDataFrame | None]:
    provinces = None
    national = None
    if Path(province_path).exists():
        provinces = gpd.read_file(province_path).to_crs(epsg=4326)
    if Path(national_path).exists():
        national = gpd.read_file(national_path).to_crs(epsg=4326)
    return provinces, national


def line_segments(n: pypsa.Network, branches: pd.DataFrame, bus0_col: str, bus1_col: str) -> list[list[tuple[float, float]]]:
    segments = []
    for _, row in branches.iterrows():
        if row[bus0_col] not in n.buses.index or row[bus1_col] not in n.buses.index:
            continue
        b0 = n.buses.loc[row[bus0_col]]
        b1 = n.buses.loc[row[bus1_col]]
        segments.append([(b0.x, b0.y), (b1.x, b1.y)])
    return segments


def draw_base_map(ax: plt.Axes, provinces: gpd.GeoDataFrame | None, national: gpd.GeoDataFrame | None, extent: list[float]) -> None:
    if provinces is not None:
        provinces.plot(ax=ax, facecolor="#f8f8f8", edgecolor="#bbbbbb", linewidth=0.4, zorder=0)
    if national is not None:
        national.plot(ax=ax, facecolor="none", edgecolor="#222222", linewidth=0.8, zorder=1)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.grid(alpha=0.15, lw=0.4)


def plot_maps(
    n: pypsa.Network,
    lines: pd.DataFrame,
    out: Path,
    province_path: str,
    national_path: str,
    exchange_rate: float,
) -> None:
    provinces, national = load_map_layers(province_path, national_path)
    lmp = n.buses_t.marginal_price.mean() * exchange_rate / 1000
    gen_by_bus = component_opt(n.generators, "p_nom").groupby(n.generators.bus).sum() / 1e3
    load_by_bus = n.loads_t.p_set.mean().groupby(n.loads.bus).sum() / 1e3
    bus_size = (gen_by_bus.add(load_by_bus, fill_value=0).reindex(n.buses.index).fillna(0) + 1).pow(0.65) * 10

    for name, extent in {
        "china": [73, 137, 3, 55],
        "csg": [96, 123, 16, 30],
    }.items():
        fig, ax = plt.subplots(figsize=(12, 9))
        draw_base_map(ax, provinces, national, extent)

        expanded = lines["expansion_GW"] > 0.1
        base_segments = line_segments(n, lines[~expanded], "bus0", "bus1")
        exp_segments = line_segments(n, lines[expanded], "bus0", "bus1")
        if base_segments:
            ax.add_collection(LineCollection(base_segments, colors="#9aa0a6", linewidths=0.6, alpha=0.65, zorder=2))
        if exp_segments:
            widths = (lines.loc[expanded, "expansion_GW"].clip(lower=0.1).pow(0.5) * 0.8).to_numpy()
            ax.add_collection(LineCollection(exp_segments, colors="#d62728", linewidths=widths, alpha=0.9, zorder=3))

        if not n.links.empty:
            link_segments = line_segments(n, n.links, "bus0", "bus1")
            if link_segments:
                ax.add_collection(LineCollection(link_segments, colors="#008b8b", linewidths=1.0, alpha=0.75, zorder=4))

        scatter = ax.scatter(
            n.buses.x,
            n.buses.y,
            s=bus_size,
            c=lmp.reindex(n.buses.index),
            cmap="viridis",
            edgecolor="white",
            linewidth=0.4,
            zorder=5,
        )
        cbar = plt.colorbar(scatter, ax=ax, shrink=0.7, pad=0.01)
        cbar.set_label("Mean LMP (CNY/kWh)")
        ax.set_title(f"CSG-Focused Network Map: {name.upper()}")
        legend = [
            Line2D([0], [0], color="#9aa0a6", lw=1.5, label="Existing AC line"),
            Line2D([0], [0], color="#d62728", lw=2.0, label="Expanded AC line"),
            Line2D([0], [0], color="#008b8b", lw=2.0, label="DC link"),
        ]
        ax.legend(handles=legend, loc="lower left", framealpha=0.9)
        plt.tight_layout()
        plt.savefig(out / f"fig08_map_lmp_expansion_{name}.png", dpi=300, bbox_inches="tight")
        plt.close()

    fig, ax = plt.subplots(figsize=(12, 9))
    draw_base_map(ax, provinces, national, [73, 137, 3, 55])
    region_colors = n.buses.analysis_region.map(REGION_COLORS).fillna(REGION_COLORS["UNKNOWN"])
    segments = line_segments(n, n.lines, "bus0", "bus1")
    if segments:
        ax.add_collection(LineCollection(segments, colors="#b0b0b0", linewidths=0.5, alpha=0.55, zorder=2))
    ax.scatter(n.buses.x, n.buses.y, s=bus_size, c=region_colors, edgecolor="white", linewidth=0.4, zorder=3)
    handles = [
        Line2D([0], [0], marker="o", color="white", markerfacecolor=REGION_COLORS[r], markersize=8, label=r)
        for r in REGION_ORDER
        if (n.buses.analysis_region == r).any()
    ]
    ax.legend(handles=handles, loc="lower left", framealpha=0.9)
    ax.set_title("CSG-Focused Cluster Regions")
    plt.tight_layout()
    plt.savefig(out / "fig09_map_cluster_regions.png", dpi=300, bbox_inches="tight")
    plt.close()


def write_key_findings(
    out: Path,
    summary: pd.DataFrame,
    gen: pd.DataFrame,
    regional: pd.DataFrame,
    lines: pd.DataFrame,
    lmp: pd.DataFrame,
) -> None:
    metric = summary.set_index("metric")["value"]
    top_expansion = lines.head(5)
    top_lmp = lmp.head(5)
    renewable_carriers = [c for c in ["solar", "onwind", "offwind-ac", "offwind-dc", "ror", "hydro"] if c in gen.index]
    renewable_capacity = gen.loc[renewable_carriers, "optimal_capacity_GW"].sum()
    total_capacity = gen["optimal_capacity_GW"].sum()

    with (out / "README_key_findings.md").open("w", encoding="utf-8") as f:
        f.write("# CSG-Focused Result Key Findings\n\n")
        f.write("## System Scale\n\n")
        f.write(f"- Annual demand: {metric.get('annual_demand_TWh', np.nan):.2f} TWh\n")
        f.write(f"- Peak load: {metric.get('peak_load_GW', np.nan):.2f} GW\n")
        f.write(f"- Average system LCOE proxy: {metric.get('average_lcoe_CNY_per_kWh', np.nan):.4f} CNY/kWh\n")
        f.write(f"- Renewable/hydro capacity share: {renewable_capacity / total_capacity * 100:.1f}%\n\n")
        f.write("## Regional Balance\n\n")
        f.write(regional.round(3).to_markdown())
        f.write("\n\n## Top Line Expansions\n\n")
        f.write(top_expansion[["bus0", "bus1", "bus0_region", "bus1_region", "expansion_GW", "congestion_percent"]].round(3).to_markdown(index=False))
        f.write("\n\n## Highest Mean LMP Buses\n\n")
        f.write(top_lmp.round(4).to_markdown())
        f.write("\n")


def main() -> None:
    args = parse_args()
    set_plot_style()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    network_path = Path(args.network)
    if not network_path.exists():
        raise FileNotFoundError(network_path)

    print(f"Loading network: {network_path}")
    print(f"Writing outputs to: {out}")
    n = pypsa.Network(network_path)
    add_region_columns(n)

    summary = annual_system_summary(n, out, args.exchange_rate)
    gen, storage = generation_and_storage_summary(n, out)
    regional = regional_summary(n, out, args.exchange_rate)
    lines, corridors = transmission_summary(n, out)
    lmp = lmp_summary(n, out, args.exchange_rate)

    plot_capacity_and_generation(gen, out)
    plot_regional_summary(regional, out)
    plot_price_duration(n, out, args.exchange_rate)
    plot_dispatch(n, out)
    plot_maps(n, lines, out, args.province_shp, args.national_shp, args.exchange_rate)
    write_key_findings(out, summary, gen, regional, lines, lmp)

    print("Analysis complete.")
    print(f"Tables and figures are in: {out.resolve()}")


if __name__ == "__main__":
    main()
