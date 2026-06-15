import os

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import pandas as pd
import pypsa
import seaborn as sns

# 1. 加载网络模型
network_path = "networks/CN_power_2035_ssp226/elec_s.nc"
n = pypsa.Network(network_path)
OUT_DIR = "./playground/analysis_load"
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)
# ---------------------------------------------------------
# 数据提取
# n.loads_t.p_set 是一个 DataFrame，行是时间，列是不同的 Load ID
# n.loads 是静态信息，包含 Load 所属的 bus (节点) 等
# n.buses 包含节点的经纬度 (x, y)
# ---------------------------------------------------------

# 计算每个 Load 的年均/年总负荷和峰值负荷
load_sum = n.loads_t.p_set.sum()  # 各节点年总用电量 (MWh)
load_max = n.loads_t.p_set.max()  # 各节点峰值负荷 (MW)

# 计算每个时间步的系统总负荷
system_total_load = n.loads_t.p_set.sum(axis=1)

# 获取 network 中 snapshot 的年份，以解决切片越界问题
year_str = str(system_total_load.index[0].year)

# =========================================================
# 可视化 1: 空间分布 - 节点总用电量地图 (气泡图)
# =========================================================
fig, ax = plt.subplots(figsize=(12, 10), subplot_kw={"projection": ccrs.PlateCarree()})

# 获取与节点 (buses) 对应的总负荷
bus_loads = load_sum.groupby(n.loads.bus).sum()

# 归一化并放大气泡大小：将 0.05 调大到 1.5（你可以根据具体视觉效果在此微调，如1.0~2.0）
bus_sizes = bus_loads / bus_loads.max() * 1.5

n.plot(
    ax=ax,
    bus_sizes=bus_sizes,
    bus_colors="blue",
    bus_alpha=0.6,  # 增加透明度，重叠区域会颜色加深，且不会完全掩盖底层线路
    line_colors="grey",
    line_widths=0.3,  # 稍微将线路调细，突出气泡
    title="Spatial Distribution of Total Annual Electricity Demand",
)

# 确保图片保存
plt.savefig(f"{OUT_DIR}/load_spatial_distribution.png", dpi=300, bbox_inches="tight")
plt.show()

# =========================================================
# 可视化 2: 时间序列 - 系统总负荷曲线与典型的单周波动
# =========================================================
fig, axes = plt.subplots(2, 1, figsize=(12, 10))

# a. 全年系统总负荷曲线
system_total_load.plot(ax=axes[0], color="blue", linewidth=0.5)
axes[0].set_title("Total System Load over the Year (8760h)")
axes[0].set_ylabel("Load (MW)")

# b. 截取夏季某一周的波动 (例如 7月份的某一周)
system_total_load.loc[f"{year_str}-07-01" : f"{year_str}-07-07"].plot(ax=axes[1], color="orange")
axes[1].set_title("Typical Week Summer Load Profile (July 1 - July 7)")
axes[1].set_ylabel("Load (MW)")

plt.tight_layout()
plt.savefig(f"{OUT_DIR}/load_timeseries.png", dpi=300)
plt.show()

# =========================================================
# 可视化 3: 热力图 - 一天中各小时 vs 全年各天的系统负荷形态
# =========================================================
# 将时间序列重塑为 365天 x 24小时 的矩阵
# 注意：假设模型时间步长为 1 小时，且涵盖整年
df_load_time = pd.DataFrame(
    {
        "Load": system_total_load.values,
        "DayOfYear": system_total_load.index.dayofyear,
        "Hour": system_total_load.index.hour,
    }
)
pivot_load = df_load_time.pivot_table(index="Hour", columns="DayOfYear", values="Load")

plt.figure(figsize=(15, 6))
sns.heatmap(pivot_load, cmap="viridis", cbar_kws={"label": "System Load (MW)"})
plt.title("System Load Heatmap: Hour of Day vs. Day of Year")
plt.xlabel("Day of Year")
plt.ylabel("Hour of Day")
plt.gca().invert_yaxis()  # 让0点在最下方或者按习惯调整
plt.savefig(f"{OUT_DIR}/load_heatmap.png", dpi=300)
plt.show()

# =========================================================
# 可视化 4: 负荷持续曲线 (Load Duration Curve)
# =========================================================
plt.figure(figsize=(8, 5))
sorted_load = system_total_load.sort_values(ascending=False).values
plt.plot(range(len(sorted_load)), sorted_load, color="purple")
plt.title("Load Duration Curve (LDC)")
plt.xlabel("Hours of the Year")
plt.ylabel("Load (MW)")
plt.fill_between(range(len(sorted_load)), sorted_load, color="purple", alpha=0.2)
plt.grid(True, linestyle="--", alpha=0.6)
plt.savefig(f"{OUT_DIR}/load_duration_curve.png", dpi=300)
plt.show()
