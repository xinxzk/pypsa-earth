from pathlib import Path  # [修改] 新增 pathlib 用于路径解析

import cartopy.crs as ccrs
import matplotlib.cm as cm
import matplotlib.colors as colors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pypsa

# ==========================================
# 1. 加载结果网络 —— 只需修改这一行来切换不同结果
# ==========================================
path = "results/CN_power_2035_ssp226/networks/elec_s_34_ec_lcopt_Co2L-1h.nc"

# [修改] 自动从 path 解析场景名和网络文件名
#   path 结构: results/{scenario}/networks/{network_name}.nc
_p = Path(path)
scenario = _p.parts[1]  # e.g. "CN_power_2035_ssp226"
net_name = _p.stem  # e.g. "elec_s_34_ec_lcopt_Co2L-3h"
output_dir = Path("./playground/results") / scenario
output_dir.mkdir(parents=True, exist_ok=True)  # 自动创建目录

print(f"正在加载网络: {path} ...")
print(f"输出目录: {output_dir}\n")
n = pypsa.Network(path)

# ==========================================
# 2. 分析：各能源类型最优装机容量 (GW)
# ==========================================
print("--- 2035年各能源类型最优装机容量 (GW) ---")
capacity = n.generators.groupby("carrier").p_nom_opt.sum() / 1e3
capacity = capacity[capacity > 0.001].sort_values(ascending=False)
print(capacity.round(2))

# ==========================================
# 3. 特高压线路扩容情况
# ==========================================
print("\n--- 2035年跨省线路扩容 TOP 5 (GW) ---")
line_expansion = (n.lines.s_nom_opt - n.lines.s_nom) / 1e3
top_lines = line_expansion.sort_values(ascending=False).head(5)
for line_id, exp_gw in top_lines.items():
    bus0 = n.lines.loc[line_id, "bus0"]
    bus1 = n.lines.loc[line_id, "bus1"]
    print(f"{bus0} <--> {bus1} : 新增 {exp_gw:.2f} GW")

# ==========================================
# 4. 全年弃风弃光率
# ==========================================
print("\n--- 2035年全年新能源消纳情况 ---")
for carrier in ["solar", "onwind", "offwind-ac", "offwind-dc"]:
    gens = n.generators[n.generators.carrier == carrier].index
    if len(gens) > 0:
        available_energy = (n.generators_t.p_max_pu[gens] * n.generators.loc[gens, "p_nom_opt"]).sum().sum()
        used_energy = n.generators_t.p[gens].sum().sum()
        curtailment_rate = (available_energy - used_energy) / available_energy * 100
        print(f"{carrier.upper()} 弃电率: {curtailment_rate:.2f}%")

# ==========================================
# 5. 平均节点边际电价 (LMP) 极值
# ==========================================
print("\n--- 2035年平均节点边际电价 (LMP) 极值 ---")
lmp_cny_kwh = n.buses_t.marginal_price.mean() * 7.8 / 1000
print("最贵的 3 个节点 (￥/kWh):")
print(lmp_cny_kwh.sort_values(ascending=False).head(3).round(3))
print("最便宜的 3 个节点 (￥/kWh):")
print(lmp_cny_kwh.sort_values(ascending=True).head(3).round(3))

# ==========================================
# 6. 可视化：全年出力曲线
# ==========================================
p_by_carrier = n.generators_t.p.groupby(n.generators.carrier, axis=1).sum() / 1e3
p_by_carrier = p_by_carrier.loc[:, (p_by_carrier != 0).any(axis=0)]
demand = n.loads_t.p_set.sum(axis=1) / 1e3
p_resampled = p_by_carrier.resample("W").mean()
demand_resampled = demand.resample("W").mean()

fig, ax = plt.subplots(figsize=(14, 7))
p_resampled.plot.area(ax=ax, alpha=0.8, cmap="tab20", linewidth=0)
demand_resampled.plot(ax=ax, color="black", lw=2, linestyle="--", label="Total Demand")
plt.title(f"Weekly Average Power Generation Mix - {scenario} ({net_name})")  # [修改] 标题动态化
plt.ylabel("Average Power (GW)")
plt.xlabel("Time (Weeks)")
plt.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
plt.tight_layout()

# [修改] 文件名包含 net_name，保存到对应子目录
out_mix = output_dir / f"generation_mix_{net_name}.png"
plt.savefig(out_mix, dpi=300)
plt.show()
print(f"\n=> 全年出力趋势图已保存至 {out_mix}")

# ==========================================
# 7. 地理拓扑可视化：LMP分布与线路扩容图
# ==========================================
print("\n--- 正在生成高品质地理拓扑图 ---")
lmp_cny = n.buses_t.marginal_price.mean() * 7.8 / 1000
line_capacities_gw = n.lines.s_nom_opt / 1e3
is_expanded = (n.lines.s_nom_opt - n.lines.s_nom) > 100
line_colors = is_expanded.map({True: "#e74c3c", False: "#95a5a6"})

projection = ccrs.PlateCarree()
fig, ax = plt.subplots(figsize=(12, 10), subplot_kw={"projection": projection})
ax.set_extent([73, 135, 18, 54], crs=projection)
ax.coastlines(resolution="50m", linewidth=0.5, color="black")

n.plot(
    ax=ax,
    bus_sizes=0.015,
    bus_colors=lmp_cny,
    bus_cmap="viridis",
    line_widths=line_capacities_gw * 0.5,
    line_colors=line_colors,
    title=f"{scenario}: Nodal Prices and Transmission Expansion ({net_name})",  # [修改]
)

norm = colors.Normalize(vmin=lmp_cny.min(), vmax=lmp_cny.max())
sm = cm.ScalarMappable(cmap="viridis", norm=norm)
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax, shrink=0.6, pad=0.02)
cbar.set_label("Average LMP (CNY / kWh)", fontsize=12)

red_patch = mpatches.Patch(color="#e74c3c", label="Expanded / New Lines")
grey_patch = mpatches.Patch(color="#95a5a6", label="Existing Lines")
ax.legend(handles=[red_patch, grey_patch], loc="lower right", framealpha=0.9)
plt.tight_layout()

# [修改] 文件名包含 net_name，保存到对应子目录
out_map = output_dir / f"map_lmp_expansion_{net_name}.png"
plt.savefig(out_map, dpi=300, bbox_inches="tight")
print(f"=> LMP热力与扩容地图已保存至 {out_map}")

# ==========================================
# 6. 可视化：夏季典型周逐小时源荷平衡图 (含储能)
# ==========================================
print("\n--- 正在生成夏季典型周逐小时源荷平衡图 ---")

# 提取所有发电机的出力
p_gens = n.generators_t.p.groupby(n.generators.carrier, axis=1).sum()

# 提取储能放电 (假设 PyPSA-Earth 中储能通过 Link 模型化，放电为负向 input 或正向 output)
# 通常 battery discharger 和 H2 Fuel Cell 属于 links
# 为了通用性，寻找 carrier 包含 battery 或 H2，且输出电能的环节
storage_discharge = pd.DataFrame(index=n.snapshots)
storage_charge = pd.DataFrame(index=n.snapshots)

if not n.links.empty:
    for carrier in ["battery discharger", "H2 Fuel Cell"]:
        links_c = n.links[n.links.carrier == carrier].index
        if len(links_c) > 0:
            # 放电是向母线注入功率 (通常是 p1 的绝对值，根据方向)
            storage_discharge[carrier] = -n.links_t.p1[links_c].sum(axis=1)

    for carrier in ["battery charger", "H2 Electrolysis"]:
        links_c = n.links[n.links.carrier == carrier].index
        if len(links_c) > 0:
            # 充电是消耗功率 (p0)
            storage_charge[carrier] = n.links_t.p0[links_c].sum(axis=1)

# [新增] 提取 StorageUnit 组件 (例如抽水蓄能、带有调水水库的水电等) 的出力
if not n.storage_units.empty:
    su_p = n.storage_units_t.p.groupby(n.storage_units.carrier, axis=1).sum()
    # P > 0 为放电（相当于发电），P < 0 为充电（相当于负荷）
    su_discharge = su_p.clip(lower=0)
    su_charge = -su_p.clip(upper=0)

    # 将 StorageUnit 的放电加入放电 DataFrame，充电加入充电 DataFrame
    storage_discharge = pd.concat([storage_discharge, su_discharge], axis=1)
    storage_charge = pd.concat([storage_charge, su_charge], axis=1)

# 合并所有正向发电来源 (发电机 + 储能放电)
p_positive = pd.concat([p_gens, storage_discharge], axis=1).fillna(0) / 1e3
# 移除全为0的列
p_positive = p_positive.loc[:, (p_positive != 0).any(axis=0)]

# 计算总负荷 (基础负荷 + 储能充电负荷)
base_demand = n.loads_t.p_set.sum(axis=1) / 1e3
total_demand = base_demand + storage_charge.sum(axis=1).fillna(0) / 1e3

# 选择夏季典型周，例如 7月中旬 的 168 小时
# 获取网络时间戳的年份
year = str(n.snapshots[0].year)
start_time = f"{year}-07-15 00:00:00"
end_time = f"{year}-07-21 23:00:00"

try:
    p_week = p_positive.loc[start_time:end_time]
    d_week = total_demand.loc[start_time:end_time]
except KeyError:
    # 如果时间戳匹配不上，直接取中间的 168 小时
    mid_idx = len(n.snapshots) // 2
    p_week = p_positive.iloc[mid_idx : mid_idx + 168]
    d_week = total_demand.iloc[mid_idx : mid_idx + 168]

# ==========================================
# 自动寻找缺电最严重的一周进行可视化
# ==========================================
if "load shedding" in p_positive.columns and p_positive["load shedding"].max() > 0.001:
    # 找到全年 load shedding 发电量最大（缺电最严重）的那一个小时
    worst_hour = p_positive["load shedding"].idxmax()
    print(f"\n[诊断] 发现最严重拉闸限电发生在: {worst_hour}，功率高达 {p_positive['load shedding'].max():.2f} GW")

    # 提取这个小时前后各 3.5 天（凑齐 168 小时）
    start_time = worst_hour - pd.Timedelta(hours=84)
    end_time = worst_hour + pd.Timedelta(hours=83)

    p_week = p_positive.loc[start_time:end_time]
    d_week = total_demand.loc[start_time:end_time]
    title_time = f"Worst Week around {worst_hour.strftime('%Y-%m-%d')}"
else:
    print("\n[诊断] 全年没有发生任何负荷削减 (Load shedding)！")
    # 如果没缺电，就默认画前 168 个小时
    p_week = p_positive.iloc[:168]
    d_week = total_demand.iloc[:168]
    title_time = "First Week"

fig, ax = plt.subplots(figsize=(14, 7))
# 使用堆叠面积图展示发电结构，包括 Load shedding
p_week.plot.area(ax=ax, alpha=0.9, cmap="tab20", linewidth=0)
# 画出负荷曲线
d_week.plot(ax=ax, color="black", lw=2, linestyle="--", label="Total Demand (incl. Charge)")

plt.title(f"{title_time} Hourly Power Balance - {scenario} ({net_name})")
plt.ylabel("Power (GW)")
plt.xlabel("Time (Hourly)")
plt.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
plt.tight_layout()

out_mix = output_dir / f"generation_mix_hourly_{net_name}.png"
plt.savefig(out_mix, dpi=300)
plt.show()
print(f"=> 夏季典型周源荷平衡图已保存至 {out_mix}")
