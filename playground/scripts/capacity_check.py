import pandas as pd
import pypsa

print("正在加载 elec_s.nc ...")
n = pypsa.Network("networks/CN_power_only_1month/elec_s.nc")
n.determine_network_topology()

# 1. 提取负荷 (Load)
loads = n.loads.copy()
loads["sub_network"] = loads.bus.map(n.buses.sub_network)
if not n.loads_t.p_set.empty:
    loads["avg_load"] = n.loads_t.p_set.mean().values
else:
    loads["avg_load"] = loads.p_set if "p_set" in loads.columns else 0
island_loads = loads.groupby("sub_network").avg_load.sum()

# 2. 提取发电机装机 (Generators)
# 在 PyPSA-Earth 中，未建成的风光水电通常有巨大的 p_nom_max (最大开发潜力)
gens = n.generators.copy()
gens["sub_network"] = gens.bus.map(n.buses.sub_network)
# 取已有装机和最大潜力中的最大值作为该节点的“发电体量”
if "p_nom_max" in gens.columns:
    gens["capacity"] = gens[["p_nom", "p_nom_max"]].max(axis=1)
else:
    gens["capacity"] = gens["p_nom"]
island_gens = gens.groupby("sub_network").capacity.sum()

# 3. 提取储能装机 (Storage Units)
if not n.storage_units.empty:
    stores = n.storage_units.copy()
    stores["sub_network"] = stores.bus.map(n.buses.sub_network)
    if "p_nom_max" in stores.columns:
        stores["capacity"] = stores[["p_nom", "p_nom_max"]].max(axis=1)
    else:
        stores["capacity"] = stores["p_nom"]
    island_stores = stores.groupby("sub_network").capacity.sum()
else:
    island_stores = pd.Series(dtype=float)

# 4. 汇总所有数据
summary = pd.DataFrame(
    {
        "节点数": n.buses.sub_network.value_counts(),
        "负荷 (MW)": island_loads,
        "发电容量潜力 (MW)": island_gens,
        "储能容量 (MW)": island_stores,
    }
).fillna(0)

# 计算综合体量：这是 simplify_network 决定是否删除它的核心依据
summary["综合总规模 (MW)"] = summary["负荷 (MW)"] + summary["发电容量潜力 (MW)"] + summary["储能容量 (MW)"]

# 按照编号
summary = summary.sort_values(by="sub_network")

print(f"\n=== 网络拓扑扫描完成，共发现 {len(summary)} 个独立电网区域 ===")
print("\n[规模最大的前 15 个电网区域 (包含主网)]")
# 格式化输出，方便阅读
formatters = {
    "负荷 (MW)": "{:,.0f}".format,
    "发电容量潜力 (MW)": "{:,.0f}".format,
    "储能容量 (MW)": "{:,.0f}".format,
    "综合总规模 (MW)": "{:,.0f}".format,
}
print(summary.head(113).to_string(formatters=formatters))

# 保存结果到 CSV，按编号排序
summary.to_csv("playground/results/island_capacity_summary.csv", index_label="sub_network")
print("\n结果已保存到 playground/results/island_capacity_summary.csv")
