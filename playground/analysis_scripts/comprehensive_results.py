import os

import cartopy.crs as ccrs
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa

# ==========================================
# 0. 环境与目录初始化
# ==========================================
plt.rcParams["font.sans-serif"] = [
    "Source Han Sans SC",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "DejaVu Sans",
]  # 解决中文显示问题
plt.rcParams["axes.unicode_minus"] = False
plt.style.use("seaborn-v0_8-paper")

# 创建高品质输出目录

# 加载 1h 全时序网络模型
file_path = "results/CN_power_2035_ssp226_Limited/networks/elec_s_34_ec_lcopt_Co2L-1h_EXTREME_assessed.nc"

OUT_DIR = "./playground/comprehensive_results"
os.makedirs(OUT_DIR, exist_ok=True)
print(f"🚀 正在加载 1h 全时序大型网络模型: {file_path}")
n = pypsa.Network(file_path)
print("✅ 加载完成！开始执行 5 大维度综合分析...\n")

# ==========================================
# 维度一：宏观系统账本与经济性 (Macro-Economics)
# ==========================================
print("📊 [1/5] 正在计算宏观经济指标...")
total_cost_bn = n.objective / 1e9  # 十亿
total_demand_twh = n.loads_t.p_set.sum().sum() / 1e6  # 太瓦时 (TWh)
# LCOE 计算 (转换为 ￥/kWh，假设汇率 7.8)
lcoe_cny_kwh = (n.objective * 7.8) / (total_demand_twh * 1e9)

print(f"  => 2035年系统总年度成本: {total_cost_bn:.2f} 十亿")
print(f"  => 2035年系统总用电需求: {total_demand_twh:.2f} TWh")
print(f"  => 预测平准化度电成本 (LCOE): {lcoe_cny_kwh:.4f} ￥/kWh\n")

# ==========================================
# 维度二：电源与储能结构 (Generation & Storage Mix)
# ==========================================
print("🔋 [2/5] 正在分析装机、发电与储能结构...")

# 2.1 发电装机与发电量统计
gen_p_nom = n.generators.groupby("carrier").p_nom.sum() / 1e3  # 初始装机 (GW)
gen_p_nom_opt = n.generators.groupby("carrier").p_nom_opt.sum() / 1e3  # 优化后装机 (GW)
gen_expansion = gen_p_nom_opt - gen_p_nom  # 扩容装机 (GW)
gen_twh = n.generators_t.p.sum().groupby(n.generators.carrier).sum() / 1e6  # 年发电量 (TWh)

# 弃电率计算
curtailment_dict = {}
for carrier in n.generators.carrier.unique():
    gens = n.generators[n.generators.carrier == carrier].index
    # 仅针对具有时间序列约束（p_max_pu）的新能源或特定电源计算弃电
    if len(gens) > 0 and len(set(gens).intersection(n.generators_t.p_max_pu.columns)) > 0:
        valid_gens = list(set(gens).intersection(n.generators_t.p_max_pu.columns))
        available = (n.generators_t.p_max_pu[valid_gens] * n.generators.loc[valid_gens, "p_nom_opt"]).sum().sum()
        used = n.generators_t.p[valid_gens].sum().sum()
        curtailment_dict[carrier] = (available - used) / available * 100 if available > 0 else 0
    else:
        curtailment_dict[carrier] = 0

# 汇总发电机 DataFrame 并保存 CSV
df_gens = pd.DataFrame(
    {
        "Original_Capacity_GW": gen_p_nom,
        "Optimal_Capacity_GW": gen_p_nom_opt,
        "Expansion_GW": gen_expansion,
        "Generation_TWh": gen_twh,
    }
).fillna(0)
df_gens["Curtailment_%"] = pd.Series(curtailment_dict)
df_gens = df_gens.sort_values(by="Optimal_Capacity_GW", ascending=False)
df_gens.to_csv(f"{OUT_DIR}/2_Generators_Summary.csv")
print(f"  => 发电结构数据已保存至 {OUT_DIR}/2_Generators_Summary.csv")

# 2.2 储能容量统计
if not n.stores.empty:
    store_e_nom = n.stores.groupby("carrier").e_nom.sum() / 1e3  # 初始能量容量 (GWh)
    store_e_nom_opt = n.stores.groupby("carrier").e_nom_opt.sum() / 1e3  # 优化后能量容量 (GWh)

    df_stores = (
        pd.DataFrame(
            {
                "Original_Energy_Capacity_GWh": store_e_nom,
                "Optimal_Energy_Capacity_GWh": store_e_nom_opt,
                "Expansion_GWh": store_e_nom_opt - store_e_nom,
            }
        )
        .fillna(0)
        .sort_values(by="Optimal_Energy_Capacity_GWh", ascending=False)
    )

    df_stores.to_csv(f"{OUT_DIR}/2_Storage_Energy_Summary.csv")
    print(f"  => 储能容量数据已保存至 {OUT_DIR}/2_Storage_Energy_Summary.csv")

    print("\n  => 储能能量容量配置概览 (GWh):")
    print(df_stores[["Optimal_Energy_Capacity_GWh"]].round(2))

# 可视化：发电装机结构饼图 (仅绘制占比大于 1% 的)
fig, ax = plt.subplots(figsize=(8, 8))
cap_gw_plot = gen_p_nom_opt[gen_p_nom_opt > 0.01].sort_values(ascending=False)
cap_gw_plot.plot.pie(ax=ax, autopct="%1.1f%%", cmap="tab20", startangle=90, ylabel="")
ax.set_title("2035年装机容量结构 (GW)")
plt.savefig(f"{OUT_DIR}/1_Capacity_Mix_Pie.png", dpi=300)
plt.close()

# ==========================================
# 维度三：极端时序调度与韧性 (Temporal Dispatch) / 1 Month Dispatch
# 统一且安全的时间序列数据聚合方案
# ==========================================
print("\n📈 [3/5] 正在构建一致性的供需时序对齐视图...")

# 统一按照网络自身的snapshots作为基础索引构建绝对的对齐DF
snapshots = n.snapshots

# 1. 聚类正向电源 (发电能力)
# 获取各类发电机组每小时合计出力 (GW)
p_gen = pd.DataFrame(index=snapshots)
for carrier in n.generators.carrier.unique():
    gens = n.generators[n.generators.carrier == carrier].index
    if not gens.empty:
        p_gen[carrier] = n.generators_t.p[gens].sum(axis=1) / 1e3

# 2. 聚类储能系统放电与充电 (基于 Links & Storage Units)
p_store_discharge = pd.DataFrame(index=snapshots)
p_store_charge = pd.DataFrame(index=snapshots)

# Links (例如 Battery discharge, H2 Fuel Cell, Electrolysis等)
if not n.links.empty:
    for carrier in n.links.carrier.unique():
        links = n.links[n.links.carrier == carrier].index
        # 一般惯例: discharger/fuel cell的正向出力进入电网
        if any(kw in carrier.lower() for kw in ["discharge", "fuel cell"]):
            p_store_discharge[carrier] = n.links_t.p0[links].sum(axis=1) / 1e3
        # charger/electrolysis作为负荷抽调电量
        elif any(kw in carrier.lower() for kw in ["charge", "electrolysis"]):
            p_store_charge[carrier] = -n.links_t.p0[links].sum(axis=1) / 1e3

# Storage Units (例如抽水蓄能 PHS, 负数代表抽水, 正数代表发电)
if not n.storage_units.empty:
    for carrier in n.storage_units.carrier.unique():
        sus = n.storage_units[n.storage_units.carrier == carrier].index
        su_p = n.storage_units_t.p[sus].sum(axis=1) / 1e3
        # 大于0为放电
        p_store_discharge[f"{carrier} discharge"] = su_p.clip(lower=0)
        # 小于0为充电
        p_store_charge[f"{carrier} charge"] = su_p.clip(upper=0)

# 3. 聚合所有的电力供给(Positive)并计算真正的总耗电(Total Demand)
# 这一步极其关键：直接用 index 去 concat 保障绝对不出 NaN
p_positive = pd.concat([p_gen, p_store_discharge], axis=1).fillna(0)
# 剔除全为0的无用列
p_positive = p_positive.loc[:, (p_positive != 0).any(axis=0)]

# 计算基础负荷 (GW)
base_demand = n.loads_t.p_set.sum(axis=1) / 1e3

# 若存在由于充能/电解导致的其他耗电大户，系统的"真实表现需求"需要包含这部分
# 注意：在一些可视化标准里，我们会把电池充电画在0轴以下，Demand线仅画原始系统负荷

# 构建严格规范的堆叠排序顺序
stack_order_all = [
    "nuclear",
    "lignite",
    "coal",
    "biomass",
    "CCGT",
    "OCGT",
    "oil",
    "ror",
    "hydro",
    "offwind-ac",
    "offwind-dc",
    "onwind",
    "solar",
    "battery discharger",
    "H2 fuel cell",
    "hydro discharge",
    "PHS discharge",
]
p_positive = p_positive[
    [c for c in stack_order_all if c in p_positive.columns]
    + [c for c in p_positive.columns if c not in stack_order_all]
]

try:
    c_map = n.carriers.color.to_dict()
except AttributeError:
    c_map = {}

default_colors = {
    "nuclear": "#b3628e",
    "lignite": "#545454",
    "coal": "#232322",
    "CCGT": "#a85522",
    "OCGT": "#e0722f",
    "oil": "#826b67",
    "ror": "#4169e1",
    "hydro": "#084996",
    "onwind": "#40b5c4",
    "offwind-ac": "#6895dd",
    "offwind-dc": "#74a6f2",
    "solar": "#f3c623",
    "biomass": "#5e9668",
    "battery discharger": "#9e7ba8",
    "H2 fuel cell": "#e89cc4",
    "hydro discharge": "#7f9dbf",
    "load shedding": "#cc2929",
}
colors_positive = [c_map.get(c, default_colors.get(c, "#cccccc")) for c in p_positive.columns]


# -------- 开始绘制 [极端周 168h] --------
print("  => 正在绘制: 夏季极端周 168h 调度图...")
peak_idx = base_demand.argmax()
start_idx = max(0, peak_idx - 72)
end_idx = min(len(base_demand), peak_idx + 96)

# 通过数字行号 iloc 切片，安全又稳定
pw_positive = p_positive.iloc[start_idx:end_idx]
pw_charge = p_store_charge.iloc[start_idx:end_idx]
pw_demand = base_demand.iloc[start_idx:end_idx]
pw_time = snapshots[start_idx:end_idx]

fig, ax = plt.subplots(figsize=(14, 6))
pw_positive.plot.area(ax=ax, color=colors_positive, linewidth=0, alpha=0.85)

pw_charge_clean = pw_charge.loc[:, (pw_charge != 0).any(axis=0)]
if not pw_charge_clean.empty:
    pw_charge_clean.plot.area(ax=ax, linewidth=0, cmap="viridis", alpha=0.6)

pw_demand.plot(ax=ax, color="black", lw=2.5, linestyle="--", label="System Base Demand")

ax.set_title(f"2035 Peak Week Dispatch (Centered at: {snapshots[peak_idx]})", fontsize=14)
ax.set_ylabel("Power (GW)", fontsize=12)
ax.set_xlabel("Time", fontsize=12)
ax.set_xlim(pw_time[0], pw_time[-1])

handles, labels = ax.get_legend_handles_labels()
ax.legend(reversed(handles), reversed(labels), loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/2_Peak_Week_Dispatch_1h.png", dpi=300, bbox_inches="tight")
plt.close()


# -------- 开始绘制 [1个月时序全景] --------
print("  => 正在绘制: 首月电源组合全景图...")
# 改成1月10号到25号
pm_positive = p_positive.iloc[240:600]  # 1月10日0点到25日23点，共16天*24小时=384小时
pm_demand = base_demand.iloc[240:600]
pm_time = snapshots[240:600]

fig, ax = plt.subplots(figsize=(16, 6))
pm_positive.plot.area(ax=ax, color=colors_positive, linewidth=0, alpha=0.85)
pm_demand.plot(ax=ax, color="black", lw=2.5, linestyle="-", label="System Base Demand")

ax.set_title("Power Generation Mix - China (Month 1)", fontsize=14, pad=10)
ax.set_ylabel("Power (GW)", fontsize=12)
ax.set_xlabel("Time", fontsize=12)
ax.set_xlim(pm_time[0], pm_time[-1])

handles, labels = ax.get_legend_handles_labels()
ax.legend(reversed(handles), reversed(labels), loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/3_One_Month_Dispatch.png", dpi=300, bbox_inches="tight")
plt.close()

print("✅ 时序图重绘完成！数据不对齐和 NaN 的问题已被全面清洗。")

# ==========================================
# 维度四：空间拓扑与特高压扩容 (Transmission & Congestion)
# ==========================================
print("🌐 [4/5] 正在分析跨省线路拥塞与扩容...")

# 计算线路扩容与拥塞率
lines_expansion = (n.lines.s_nom_opt - n.lines.s_nom) / 1e3  # GW
# 拥塞率：实际潮流 > 99% 容量的小时数占比
congestion_rate = (n.lines_t.p0.abs() >= n.lines.s_nom_opt * 0.99).mean() * 100

df_lines = pd.DataFrame(
    {
        "Bus0": n.lines.bus0,
        "Bus1": n.lines.bus1,
        "Original_GW": n.lines.s_nom / 1e3,
        "Optimal_GW": n.lines.s_nom_opt / 1e3,
        "Expansion_GW": lines_expansion,
        "Congestion_%": congestion_rate,
    }
).sort_values(by="Expansion_GW", ascending=False)

print("  => 特高压线路扩容 TOP 5 (GW):")
print(df_lines[["Bus0", "Bus1", "Expansion_GW", "Congestion_%"]].head(5).to_string(index=False))
df_lines.to_csv(f"{OUT_DIR}/3_Transmission_Expansion.csv")

# ==========================================
# 维度五：节点经济学 (Nodal Economics)
# ==========================================
print("\n💸 [5/5] 正在生成全网节点边际电价 (LMP) 地理分布与持续曲线...")

# 提取 LMP (转为 CNY/kWh)
lmp_cny = n.buses_t.marginal_price * 7.8 / 1000
mean_lmp = lmp_cny.mean()

# 5.1 绘制电价持续曲线 (Price Duration Curve)
sorted_lmp = np.sort(lmp_cny.values.flatten())[::-1]  # 全年所有节点所有时刻电价降序
x_axis = np.arange(len(sorted_lmp)) / len(sorted_lmp) * 100  # 百分比化

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(x_axis, sorted_lmp, color="purple", lw=2)
ax.axhline(y=0, color="black", linestyle="--", lw=1)
ax.set_title("2035 全系统节点电价持续曲线 (Price Duration Curve)")
ax.set_xlabel("全年时间占比 (%)")
ax.set_ylabel("LMP (￥/kWh)")
ax.set_ylim([-0.1, max(sorted_lmp) * 1.05 if max(sorted_lmp) < 2 else 2])  # 截断极端惩罚电价以看清主体
plt.grid(True, alpha=0.3)
plt.savefig(f"{OUT_DIR}/4_Price_Duration_Curve.png", dpi=300)
plt.close()

# 5.2 绘制高品质地理拓扑地图
fig, ax = plt.subplots(figsize=(12, 10), subplot_kw={"projection": ccrs.PlateCarree()})
ax.set_extent([73, 135, 18, 54], crs=ccrs.PlateCarree())
ax.coastlines(resolution="50m", linewidth=0.5, color="black")

# 设定扩容线路为红色，其他为灰色
is_expanded = lines_expansion > 0.5  # 扩容超过 500MW 标红
line_colors = is_expanded.map({True: "#e74c3c", False: "#bdc3c7"})

plot_collection = n.plot(
    ax=ax,
    bus_sizes=0.015,
    bus_colors=mean_lmp,
    bus_cmap="viridis",
    line_widths=n.lines.s_nom_opt / 1e3 * 0.4,  # 缩放系数调整视觉
    line_colors=line_colors,
    title="2035 China Power Grid: Nodal Prices & Transmission Expansion (1h Resolution)",
)

# 独立生成颜色条
norm = mcolors.Normalize(vmin=mean_lmp.min(), vmax=mean_lmp.max())
sm = cm.ScalarMappable(cmap="viridis", norm=norm)
sm.set_array([])
cbar = plt.colorbar(sm, ax=ax, shrink=0.6, pad=0.02)
cbar.set_label("Average LMP (CNY / kWh)", fontsize=12)

# 自定义图例
red_patch = mpatches.Patch(color="#e74c3c", label="Expanded Transmission")
grey_patch = mpatches.Patch(color="#bdc3c7", label="Existing Transmission")
ax.legend(handles=[red_patch, grey_patch], loc="lower right", framealpha=0.9)

plt.savefig(f"{OUT_DIR}/5_Map_LMP_Expansion_1h.png", dpi=300, bbox_inches="tight")
plt.close()

print("\n🎉 全部分析执行完毕！")
print(f"所有数据报表和高清图片已保存至: {os.path.abspath(OUT_DIR)}")

# 1. 强制手动计算所有设备的年化建设成本 (CAPEX)
capex_gen = (n.generators.capital_cost * n.generators.p_nom_opt).sum()
capex_line = (n.lines.capital_cost * n.lines.s_nom_opt).sum()
capex_link = (n.links.capital_cost * n.links.p_nom_opt).sum()
capex_store = (n.stores.capital_cost * n.stores.e_nom_opt).sum() if not n.stores.empty else 0
total_capex = capex_gen + capex_line + capex_link + capex_store

# 2. 强制手动计算所有设备的运行成本与停电罚款 (OPEX)
total_opex = (n.generators.marginal_cost * n.generators_t.p).sum().sum()

# 3. 真实的总系统成本
real_total_cost = total_capex + total_opex

# 4. 真实的总需求和 LCOE
total_demand = n.loads_t.p_set.sum().sum()
real_lcoe = (real_total_cost / total_demand) * 7.8 # 假设汇率 7.8 换算为人民币

print(f"  => 真实系统总年度成本: {real_total_cost / 1e9:.2f} 十亿")
print(f"     - 其中 建设成本(CAPEX): {total_capex / 1e9:.2f} 十亿")
print(f"     - 其中 运行及罚款(OPEX): {total_opex / 1e9:.2f} 十亿")
print(f"  => 预测平准化度电成本 (LCOE): {real_lcoe:.4f} ￥/kWh")