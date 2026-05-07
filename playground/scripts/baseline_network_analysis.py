import os

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import pandas as pd
import pypsa

# ==========================================
# 0. 环境与目录初始化
# ==========================================
plt.rcParams["font.sans-serif"] = ["Source Han Sans SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.style.use("seaborn-v0_8-paper")

OUT_DIR = "./playground/analysis_baseline_grid"
os.makedirs(OUT_DIR, exist_ok=True)

file_path = "networks/CN_power_2035_ssp226/elec_s.nc"
print(f"🚀 正在加载现网基础设施基准模型: {file_path}")
n = pypsa.Network(file_path)

# ==========================================
# 1. 现有电源与储能装机结构分析
# ==========================================
print("\n🔋 [1/3] 正在分析当前系统本底发电与储能装机...")

# 1.1 发电机 (包含常规电源, 新能源, 及径流式水电 ror)
gen_p_nom = n.generators.groupby("carrier").p_nom.sum() / 1e3  # GW

# 1.2 存储单元 (包含水库水电 hydro, 抽水蓄能 PHS, 以及可能的某些老版本电池组件)
if not n.storage_units.empty:
    su_p_nom = n.storage_units.groupby("carrier").p_nom.sum() / 1e3  # GW
else:
    su_p_nom = pd.Series(dtype=float)

# 1.3 储能逆变器功率 (主要针对电池、氢能等被建模为 links + stores 的新版本)
# 寻找与电池放电(battery discharger)或氢燃料电池(H2 Fuel Cell)相关的 link 功率
link_p_nom = pd.Series(dtype=float)
if not n.links.empty:
    for c in n.links.carrier.unique():
        if any(kw in c.lower() for kw in ["discharge", "fuel cell", "battery"]):
            p_val = n.links[n.links.carrier == c].p_nom.sum() / 1e3
            if p_val > 0:
                link_p_nom[c] = p_val

# 合并所有功率装机
total_p_nom = pd.concat([gen_p_nom, su_p_nom, link_p_nom]).groupby(level=0).sum()

# 生成 DataFrame 并保存功率装机 (GW)
df_capacity = pd.DataFrame({"Existing_Power_Capacity_GW": total_p_nom}).sort_values(
    by="Existing_Power_Capacity_GW", ascending=False
)
df_capacity.to_csv(f"{OUT_DIR}/1_Baseline_Power_Capacity_GW.csv")
print(f"  => 现有总计功率 (包含电源与储能放电): {total_p_nom.sum():.2f} GW")
print(df_capacity.head(10))

# 1.4 提取储能能量容量 (GWh)
store_e_nom = pd.Series(dtype=float)
if not n.stores.empty:
    store_e_nom = n.stores.groupby("carrier").e_nom.sum() / 1e3  # GWh

# 合并 storage_units 自带的储能容量 (p_nom * max_hours)
if not n.storage_units.empty:
    su_e_nom = (n.storage_units.p_nom * n.storage_units.max_hours).groupby(n.storage_units.carrier).sum() / 1e3
    store_e_nom = pd.concat([store_e_nom, su_e_nom]).groupby(level=0).sum()

if not store_e_nom.empty:
    df_energy = pd.DataFrame({"Existing_Energy_Capacity_GWh": store_e_nom}).sort_values(
        by="Existing_Energy_Capacity_GWh", ascending=False
    )
    df_energy.to_csv(f"{OUT_DIR}/1_Baseline_Energy_Storage_GWh.csv")
    print("\n  => 系统固有储能总容量 (GWh):")
    print(df_energy)

# ==========================================
# 自定义能源载体颜色映射表
# ==========================================
color_dict = {
    "coal": "#4a4a4a",  # 煤电：深灰
    "lignite": "#8b5a2b",  # 褐煤：棕色
    "CCGT": "#c0392b",  # 联合循环燃气：深红
    "OCGT": "#e74c3c",  # 燃气轮机：红色
    "oil": "#8e44ad",  # 燃油：紫色
    "nuclear": "#e67e22",  # 核电：橙色
    "hydro": "#2980b9",  # 常规水电：经典蓝
    "ror": "#3498db",  # 径流式水电：亮蓝
    "PHS": "#1abc9c",  # 抽水蓄能：青绿
    "onwind": "#27ae60",  # 陆上风电：绿色
    "offwind-ac": "#2ecc71",  # 海上风电(AC)：浅绿
    "offwind-dc": "#58d68d",  # 海上风电(DC)：更浅的绿
    "solar": "#f1c40f",  # 光伏：黄色
    "biomass": "#16a085",  # 生物质能：墨绿
    "battery discharger": "#9b59b6",  # 电池放电：紫黑
    "H2 fuel cell": "#ff9ff3",  # 氢燃料电池：粉色
    "Other": "#bdc3c7",  # 其他：浅灰
}

# 绘制饼图
fig, ax = plt.subplots(figsize=(8, 8))

# 过滤并计算阈值（将总装机量占比小于 5% 的归为 "Other"）
threshold = 0.05 * total_p_nom.sum()
large_caps = total_p_nom[total_p_nom >= threshold].copy()
small_caps_sum = total_p_nom[(total_p_nom < threshold) & (total_p_nom > 0)].sum()

# 如果有小于阈值的部分，则合并为 Other
if small_caps_sum > 0:
    large_caps.loc["Other"] = small_caps_sum

# 排序并提取颜色
cap_gw_plot = large_caps.sort_values(ascending=False)
pie_colors = [color_dict.get(c, "#cccccc") for c in cap_gw_plot.index]  # 匹配字典里的颜色，找不到则用默认浅灰 #cccccc

# 画图 (用 colors=pie_colors 取代 cmap)
cap_gw_plot.plot.pie(ax=ax, autopct="%1.1f%%", colors=pie_colors, startangle=90, ylabel="")

# 字体调整
for text in ax.texts:
    text.set_fontsize(14)

ax.set_title("Base Year Power Capacity Mix (GW) \n(Includes Hydro & Storage)")
plt.savefig(f"{OUT_DIR}/1_Baseline_Capacity_Pie.png", dpi=300)
plt.close()

# ==========================================
# 2. 负荷需求与时序特征
# ==========================================
print("\n📊 [2/3] 正在分析系统设定的系统负荷...")
total_demand_twh = n.loads_t.p_set.sum().sum() / 1e6  # TWh
peak_load_gw = n.loads_t.p_set.sum(axis=1).max() / 1e3  # GW

print(f"  => 设定情景全年总负荷: {total_demand_twh:.2f} TWh")
print(f"  => 设定情景最大峰值负荷: {peak_load_gw:.2f} GW")

fig, ax = plt.subplots(figsize=(12, 5))
sys_demand = n.loads_t.p_set.sum(axis=1) / 1e3
sys_demand.plot(ax=ax, color="#2c3e50", lw=1)
ax.set_title("System Demand Profile Over the Year (GW)")
ax.set_ylabel("Demand (GW)")
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/2_Baseline_Demand_Profile.png", dpi=300)
plt.close()

# ==========================================
# 3. 现有电网线路拓扑与分布
# ==========================================
print("\n🌐 [3/3] 正在绘制中国区现有输电骨架地图...")

# 提取各节点总装机 (发电机 + 存储单元放电统算入该节点容量)
bus_total_gen = n.generators.groupby("bus").p_nom.sum()
if not n.storage_units.empty:
    bus_total_su = n.storage_units.groupby("bus").p_nom.sum()
    bus_total_gen = bus_total_gen.add(bus_total_su, fill_value=0)

n.buses["total_gen_hw"] = n.buses.index.map(bus_total_gen).fillna(0) / 1e3  # GW

fig, ax = plt.subplots(figsize=(12, 10), subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent([73, 135, 18, 54], crs=ccrs.PlateCarree())
ax.coastlines(resolution="50m", linewidth=0.5, color="black")

plot_collection = n.plot(
    ax=ax,
    bus_sizes=n.buses["total_gen_hw"] * 0.05,  # 适度缩放
    bus_colors="#3498db",
    line_widths=n.lines.s_nom / 1e3 * 0.6,
    line_colors="#95a5a6",
    title="Present China Power Grid Topology (OSM baseline with Hydro/Storage)",
)

plt.savefig(f"{OUT_DIR}/3_Baseline_Grid_Topology.png", dpi=300, bbox_inches="tight")
plt.close()

# ==========================================
# 4. 电网基础设施深度分析 (非地理展示)
# ==========================================
print("\n📏 [4/4] 正在分析线路的物理特性与跨省传输能力...")

# 4.1 提取并统计全网线路基础数据
n.lines["capacity_GW"] = n.lines.s_nom / 1e3  # 输送容量（GW）
line_lengths_km = n.lines.length

# 按电压等级(如果数据里有 v_nom)或容量级别(GW)划分统计线路长度
if "v_nom" in n.lines.columns:
    lines_by_voltage = n.lines.groupby("v_nom")[["length", "capacity_GW"]].sum()
    lines_by_voltage.to_csv(f"{OUT_DIR}/4_Lines_Summary_by_Voltage.csv")
    print("\n  => 按电压等级划分的线路总长度和总容量已保存至 CSV。")
else:
    # 如果没有 v_nom，则以容量大小按层级进行简单分级（例如 >3GW 通常为特高压大通道）
    bins = [0, 1, 3, 10, 50]
    labels = ["<1 GW (Local/Sub-transmission)", "1-3 GW (Regional)", "3-10 GW (UHV/Major Corridor)", ">10 GW"]
    n.lines["capacity_class"] = pd.cut(n.lines["capacity_GW"], bins=bins, labels=labels)
    lines_by_class = n.lines.groupby("capacity_class")[["length", "capacity_GW"]].sum()
    lines_by_class.to_csv(f"{OUT_DIR}/4_Lines_Summary_by_Capacity_Class.csv")
    print("\n  => 按容量等级划分的线路汇总:\n", lines_by_class)

# 4.2 跨区/跨省输电通道容量分析
# 将线两端的节点省份信息匹配过来
bus_regions = n.buses.country  # PyPSA-Earth中通常用country列来存储省份简称(如CN-GD)或国家名
n.lines["bus0_region"] = n.lines.bus0.map(bus_regions)
n.lines["bus1_region"] = n.lines.bus1.map(bus_regions)

# 筛选出起点和终点不在同一个省份的联络线
inter_regional_lines = n.lines[n.lines["bus0_region"] != n.lines["bus1_region"]].copy()

if not inter_regional_lines.empty:
    # 统一方向，避免 (A->B) 和 (B->A) 被算作两条独立的通道
    # 把名称排序，确保 A在前、B在后
    inter_regional_lines["route"] = inter_regional_lines.apply(
        lambda x: " <-> ".join(sorted([str(x["bus0_region"]), str(x["bus1_region"])])), axis=1
    )

    # 聚合汇总：省际联络通道总数量、总联络容量、通道总长度
    corridor_summary = (
        inter_regional_lines.groupby("route")
        .agg(
            line_count=("capacity_GW", "count"),
            total_capacity_GW=("capacity_GW", "sum"),
            total_length_km=("length", "sum"),
        )
        .sort_values("total_capacity_GW", ascending=False)
    )

    corridor_summary.to_csv(f"{OUT_DIR}/4_Inter_Regional_Corridors.csv")
    print("\n  => 前 10 大跨区/跨省输电走廊容量 (GW):\n", corridor_summary.head(10))
else:
    print("\n  => 未检测到明显的跨区/跨省联络线 (或者是单节点/单省电网模型)。")

# ==========================================
# 4. 电网主干形态与核心通道画像
# ==========================================
print("\n📏 [4/4] 正在分析网络物理形态、巨型通道与核心枢纽...")

# 提取线路容量 (GW)
n.lines["capacity_GW"] = n.lines.s_nom / 1e3

# ----------------------------------------------------
# 4.1 线路长度 vs 容量的二维分布特征
# ----------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# 图1: 通道容量分布直方图 (截断长尾)
cutoff_gw = 20  # 设置截断阈值，例如 20 GW
main_lines = n.lines[n.lines["capacity_GW"] <= cutoff_gw]["capacity_GW"]
giant_lines_count = len(n.lines[n.lines["capacity_GW"] > cutoff_gw])

main_lines.hist(bins=40, ax=ax1, color="#3498db", edgecolor="white", alpha=0.8)
ax1.set_title(f"Corridor Capacity Distribution (≤{cutoff_gw} GW)")
ax1.set_xlabel("Line Capacity (GW)")
ax1.set_ylabel("Number of Lines")
ax1.grid(axis="y", alpha=0.3)

# 在图上特殊标注超出范围的超大线路数量
if giant_lines_count > 0:
    ax1.text(
        0.5,
        0.85,
        f"Note: {giant_lines_count} giant lines\n(> {cutoff_gw} GW) not shown",
        transform=ax1.transAxes,
        fontsize=10,
        color="#e74c3c",
        bbox=dict(facecolor="white", alpha=0.8, edgecolor="none"),
    )

# 图2: 长度 vs 容量散点图 (寻找长距离大通道)
ax2.scatter(n.lines["length"], n.lines["capacity_GW"], alpha=0.6, color="#e74c3c", edgecolors="white")
ax2.set_title("Grid Topology: Length vs. Capacity")
ax2.set_xlabel("Line Length (km)")
ax2.set_ylabel("Line Capacity (GW)")
ax2.grid(True, alpha=0.3)
# 修改字号
for ax in [ax1, ax2]:
    ax.title.set_fontsize(14)
    ax.xaxis.label.set_fontsize(14)
    ax.yaxis.label.set_fontsize(14)

plt.tight_layout()
plt.savefig(f"{OUT_DIR}/4_Line_Properties_Distribution.png", dpi=300)
plt.close()
print("  => 已生成线路[长度 vs 容量]的形态画像分布图。")

# ----------------------------------------------------
# 4.2 提取全网 TOP 15 超级跨区/跨节点走廊
# ----------------------------------------------------
# 在聚类模型中，每根线基本上就是跨簇联络线，直接进行排行
corridor_summary = n.lines[["bus0", "bus1", "length", "capacity_GW"]].copy()
corridor_summary["route"] = corridor_summary.apply(lambda x: f"{x['bus0']} <-> {x['bus1']}", axis=1)
top_corridors = corridor_summary.sort_values("capacity_GW", ascending=False).head(15)

# 绘制 TOP 通道条形图
fig, ax = plt.subplots(figsize=(10, 7))
# 为了画图好看，把数据反转一下（最大的放最上面）
top_corridors.set_index("route")["capacity_GW"].sort_values().plot.barh(ax=ax, color="#2ecc71", alpha=0.85)

ax.set_title("Current Top 15 Transmission Corridors by Capacity (GW)")
ax.set_xlabel("Capacity (GW)")
ax.set_ylabel("Corridor Route (Bus0 <-> Bus1)")
for bar in ax.patches:
    ax.text(
        bar.get_width() + 0.5,
        bar.get_y() + bar.get_height() / 2,
        f"{bar.get_width():.1f} GW",
        va="center",
        ha="left",
        fontsize=10,
        color="black",
    )

# 增加图表右侧边距以免文字被遮挡
plt.subplots_adjust(right=0.85)
plt.savefig(f"{OUT_DIR}/4_Top15_Corridors.png", dpi=300, bbox_inches="tight")
plt.close()
print("  => 已生成现存 TOP 15 电网超级通道榜单。")

# ----------------------------------------------------
# 4.3 核心枢纽节点识别 (Node Degree & Centrality)
# ----------------------------------------------------
# 计算以每个 Bus 为汇聚点，共连接了多少根线，汇聚了多少容量
line_out = n.lines.groupby("bus0")["capacity_GW"].agg(Count=("count"), Sum_GW=("sum"))
line_in = n.lines.groupby("bus1")["capacity_GW"].agg(Count=("count"), Sum_GW=("sum"))
bus_hub = line_out.add(line_in, fill_value=0).sort_values("Sum_GW", ascending=False)

bus_hub.to_csv(f"{OUT_DIR}/4_Bus_Hub_Centrality.csv")
print("\n  => ⭐ 全网核心交流枢纽 TOP 5 (按汇聚输电容量排序):")
print(bus_hub.head(5).to_string())
import warnings

warnings.filterwarnings("ignore", message="facecolor will have no effect")
