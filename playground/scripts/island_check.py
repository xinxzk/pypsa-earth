import os

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pypsa

print("Loading elec_s.nc ...")
n = pypsa.Network("networks/CN_power_8760h/elec_s.nc")

n.determine_network_topology()

island_counts = n.buses.sub_network.value_counts()
print(f"\nFound {len(island_counts)} independent grid zones.")
print("\n--- Top 5 zones by bus count ---")
print(island_counts.head(5))

if not n.loads.empty:
    loads_with_subnet = n.loads.copy()
    loads_with_subnet["sub_network"] = loads_with_subnet.bus.map(n.buses.sub_network)
    if "p_set" in n.loads.columns and n.loads.p_set.sum() > 0:
        island_loads = loads_with_subnet.groupby("sub_network").p_set.sum()
    elif not n.loads_t.p_set.empty:
        loads_with_subnet["avg_load"] = n.loads_t.p_set.mean().values
        island_loads = loads_with_subnet.groupby("sub_network").avg_load.sum()
    else:
        island_loads = pd.Series(dtype=float)

    if not island_loads.empty:
        print("\n--- Top 5 zones by load (MW) ---")
        print(island_loads.sort_values(ascending=False).head(5))
        print("\n--- Bottom 5 zones by load (MW) ---")
        print(island_loads.sort_values(ascending=True).head(5))

# ==========================================
# 1. 确定主网和孤岛
# ==========================================
print("\nGenerating island distribution map...")

bus_counts = n.buses.groupby("sub_network").size().rename("n_buses")
subnets = n.sub_networks.copy()
subnets = subnets.join(bus_counts, how="left")
subnets["n_buses"] = subnets["n_buses"].fillna(0).astype(int)
subnets = subnets.sort_values(by="n_buses", ascending=False)

main_grid_id = subnets.index[0]
island_ids = subnets.index[1:]

print(f"Main grid ID: {main_grid_id}, buses: {subnets.iloc[0]['n_buses']}")
print(f"Number of islands: {len(island_ids)}")

# ==========================================
# 2. 导出 CSV 结果，按编号排序
# ==========================================
os.makedirs("playground/results", exist_ok=True)


# 统计每个孤岛的线路数
def count_branches(subnet_id):
    buses = n.buses[n.buses.sub_network == subnet_id].index
    n_lines = ((n.lines.bus0.isin(buses)) & (n.lines.bus1.isin(buses))).sum()
    n_links = ((n.links.bus0.isin(buses)) & (n.links.bus1.isin(buses))).sum()
    return n_lines, n_links


records = []
for sn_id, sn_info in subnets.iterrows():
    n_lines, n_links = count_branches(sn_id)
    is_main = sn_id == main_grid_id

    # 计算地理中心
    buses_in_sn = n.buses[n.buses.sub_network == sn_id]
    center_x = buses_in_sn.x.mean() if not buses_in_sn.empty else float("nan")
    center_y = buses_in_sn.y.mean() if not buses_in_sn.empty else float("nan")

    # 负荷
    load_mw = island_loads.get(sn_id, 0.0) if not island_loads.empty else 0.0

    records.append(
        {
            "subnet_id": sn_id,
            "is_main_grid": is_main,
            "n_buses": sn_info["n_buses"],
            "n_ac_lines": int(n_lines),
            "n_dc_links": int(n_links),
            "avg_load_mw": round(float(load_mw), 2),
            "center_lon": round(float(center_x), 4),
            "center_lat": round(float(center_y), 4),
        }
    )

results_df = pd.DataFrame(records)
csv_path = "playground/results/island_analysis.csv"
# 按编号排序
results_df = results_df.sort_values(by="subnet_id")
results_df.to_csv(csv_path, index=False)
print(f"\nResults saved to: {csv_path}")
print(results_df.head(10).to_string(index=False))

# ==========================================
# 3. 颜色映射
# ==========================================
cmap = matplotlib.colormaps["YlOrRd"]
island_bus_counts = bus_counts.reindex(island_ids).fillna(0)
max_count = island_bus_counts.max() if island_bus_counts.max() > 0 else 1

# bus_colors & bus_sizes
bus_color_map, bus_size_map = {}, {}
for bus_id, row in n.buses.iterrows():
    sn = row["sub_network"]
    if sn == main_grid_id:
        bus_color_map[bus_id] = "#aaaaaa"
        bus_size_map[bus_id] = 0.001
    else:
        cnt = island_bus_counts.get(sn, 0)
        bus_color_map[bus_id] = mcolors.to_hex(cmap(cnt / max_count))
        bus_size_map[bus_id] = max(0.01, min(0.08, cnt * 0.003))

bus_colors_series = pd.Series(bus_color_map)
bus_sizes_series = pd.Series(bus_size_map)


# AC lines（n.lines）：主网浅灰，孤岛按颜色
def build_branch_series(branch_df, main_color, main_width, island_width=1.5):
    colors, widths = {}, {}
    for br_id, row in branch_df.iterrows():
        sn = n.buses.loc[row["bus0"], "sub_network"] if row["bus0"] in n.buses.index else main_grid_id
        if sn == main_grid_id:
            colors[br_id] = main_color
            widths[br_id] = main_width
        else:
            cnt = island_bus_counts.get(sn, 0)
            colors[br_id] = mcolors.to_hex(cmap(cnt / max_count))
            widths[br_id] = island_width
    return pd.Series(colors), pd.Series(widths)


# AC lines → 实线（由 n.plot 默认处理）
line_colors_s, line_widths_s = build_branch_series(n.lines, "#cccccc", 0.3, island_width=1.8)
# DC links → 用蓝色系区分，主网仍灰，孤岛 DC 用蓝色
link_color_map, link_width_map = {}, {}
for br_id, row in n.links.iterrows():
    sn = n.buses.loc[row["bus0"], "sub_network"] if row["bus0"] in n.buses.index else main_grid_id
    if sn == main_grid_id:
        link_color_map[br_id] = "#f61e06"
        link_width_map[br_id] = 0.3
    else:
        link_color_map[br_id] = "#1a6faf"  # 蓝色 = DC
        link_width_map[br_id] = 2.0
link_colors_s = pd.Series(link_color_map)
link_widths_s = pd.Series(link_width_map)

# ==========================================
# 4. 构建地图
# ==========================================
proj = ccrs.PlateCarree()
fig, ax = plt.subplots(figsize=(14, 11), subplot_kw={"projection": proj})

ax.set_extent([73, 135, 18, 55], crs=proj)
ax.add_feature(cfeature.LAND, facecolor="#f5f5f0", zorder=0)
ax.add_feature(cfeature.OCEAN, facecolor="#d0e8f5", zorder=0)
ax.add_feature(cfeature.BORDERS, linewidth=1.0, edgecolor="black", zorder=4)
ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor="black", zorder=4)

provinces = cfeature.NaturalEarthFeature(
    category="cultural",
    name="admin_1_states_provinces_lines",
    scale="50m",
    facecolor="none",
)
ax.add_feature(provinces, linewidth=0.4, edgecolor="gray", linestyle="--", zorder=4)

# 绘制网络
n.plot(
    ax=ax,
    bus_sizes=bus_sizes_series,
    bus_colors=bus_colors_series,
    bus_alpha=0.9,
    line_colors=line_colors_s,
    line_widths=line_widths_s,
    link_colors=link_colors_s,
    link_widths=link_widths_s,
    geomap=False,
)

# ==========================================
# 5. Colorbar
# ==========================================
sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(vmin=0, vmax=int(max_count)))
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax, orientation="vertical", fraction=0.025, pad=0.02)
cbar.set_label("Buses per Island", fontsize=11)

# ==========================================
# 6. 图例：区分主网/孤岛/AC/DC
# ==========================================
main_patch = mpatches.Patch(color="#aaaaaa", label=f"Main Grid (ID:{main_grid_id}, {subnets.iloc[0]['n_buses']} buses)")
island_patch = mpatches.Patch(color=mcolors.to_hex(cmap(0.7)), label=f"Islands ({len(island_ids)} total)")
ac_line = mpatches.Patch(color=mcolors.to_hex(cmap(0.5)), label="AC Line (island)")
dc_line = mpatches.Patch(color="#1a6faf", label="DC Link (island)")
ac_main = mpatches.Patch(color="#cccccc", label="AC/DC (main grid)")

ax.legend(
    handles=[main_patch, island_patch, ac_line, dc_line, ac_main],
    loc="lower left",
    fontsize=9,
    framealpha=0.9,
)

# ==========================================
# 7. 统计注释
# ==========================================
n_island_ac = int((line_colors_s != "#cccccc").sum())
n_island_dc = int((link_colors_s == "#1a6faf").sum())

stats_text = (
    f"Total buses   : {len(n.buses)}\n"
    f"Total subnets : {len(subnets)}\n"
    f"Islands       : {len(island_ids)}\n"
    f"Max island buses: {int(island_bus_counts.max()) if len(island_ids) > 0 else 0}\n"
    f"Island AC lines : {n_island_ac}\n"
    f"Island DC links : {n_island_dc}"
)
ax.text(
    0.02,
    0.97,
    stats_text,
    transform=ax.transAxes,
    fontsize=8.5,
    verticalalignment="top",
    family="monospace",
    bbox=dict(boxstyle="round", facecolor="white", alpha=0.85),
    zorder=10,
)

ax.set_title(
    "China Power Grid – Island Distribution (elec_s.nc)\n"
    "Grey = Main Grid | Warm colors = Islands (darker = more buses) | Blue lines = DC Links",
    fontsize=12,
)

plt.tight_layout()
output_path = "playground/islandpic/china_island_distribution.png"
os.makedirs("playground/islandpic", exist_ok=True)
plt.savefig(output_path, dpi=300, bbox_inches="tight")
print(f"\nMap saved to: {output_path}")
plt.show()
plt.close(fig)
print("Done.")
