import pypsa

# ==========================================
# 1. 加载已经“锁死物理天花板”的基准规划答卷
# ==========================================
input_path = "results/CN_power_2035_ssp226_Limited/networks/elec_s_34_ec_lcopt_Co2L-1h_solved.nc"
print(f"📥 正在加载 2035 年基准电网: {input_path}")
n = pypsa.Network(input_path)

# ==========================================
# 2. 身份转换：从“规划(Planning)”切换为“调度(Dispatch)”
# ==========================================
print("🔒 正在剥夺求解器的基建投资权，锁定所有物理资产...")

# 将优化得到的容量(_opt)固化为既有容量(p_nom / s_nom)
n.generators["p_nom"] = n.generators["p_nom_opt"]
n.lines["s_nom"] = n.lines["s_nom_opt"]
n.links["p_nom"] = n.links["p_nom_opt"]
if not n.stores.empty:
    n.stores["e_nom"] = n.stores["e_nom_opt"]

# 彻底关闭所有扩容开关！模型只能基于现有设备进行调度
n.generators["p_nom_extendable"] = False
n.lines["s_nom_extendable"] = False
n.links["p_nom_extendable"] = False
if not n.stores.empty:
    n.stores["e_nom_extendable"] = False

# ==========================================
# 3. 引入“天价”虚拟发电机：定量测算停电量的关键
# ==========================================
print("💡 正在各省部署 '拉闸限电 (Load Shedding)' 虚拟监控机组...")
# 如果模型中已经有 load shedding，先清除，确保我们的统计是最干净的
if "load shedding" in n.generators.carrier.unique():
    ls_gens = n.generators[n.generators.carrier == "load shedding"].index
    n.mremove("Generator", ls_gens)

# 在 34 个节点分别添加虚拟限电机组 (VoLL = 10000 EUR/MWh)
n.madd(
    "Generator",
    n.buses.index + " load shedding",
    bus=n.buses.index,
    carrier="load shedding",
    p_nom=1e5,  # 单省 100 GW 的虚拟备用，确保一定能填平缺口
    marginal_cost=10000,
)  # 天价惩罚成本，逼迫模型非到绝境不限电

# ==========================================
# 4. 数据-机理融合：精准复刻“华中-华东”极端冰冻灾害
# ==========================================
start_time = "2013-01-15 00:00:00"
end_time = "2013-01-19 23:00:00"
print(f"\n🌪️ 开始注入极端气象：{start_time} 至 {end_time}")

# 设定 2D 气象灾害包围盒 (Bounding Box)
# 锁定：华东、华中及部分华北地区 (约占全国 1/3 的核心负荷节点)
affected_buses = n.buses[(n.buses.y >= 26.0) & (n.buses.y <= 38.0) & (n.buses.x >= 110.0)].index

safe_buses = n.buses.index.difference(affected_buses)

print(f"   ❄️ 寒潮重灾区 (中东部核心地带): 共 {len(affected_buses)} 个节点")
print(f"   ☀️ 正常幸存区 (西北、西南、华南): 共 {len(safe_buses)} 个节点")

# 提取受灾区的发电机和负荷索引
wind_gens_affected = n.generators[
    n.generators.carrier.str.contains("wind") & n.generators.bus.isin(affected_buses)
].index
solar_gens_affected = n.generators[
    n.generators.carrier.str.contains("solar") & n.generators.bus.isin(affected_buses)
].index
loads_affected = n.loads[n.loads.bus.isin(affected_buses)].index

# 【机理 1 & 2：仅重灾区风光骤降】
n.generators_t.p_max_pu.loc[start_time:end_time, wind_gens_affected] *= 0.10
n.generators_t.p_max_pu.loc[start_time:end_time, solar_gens_affected] *= 0.05

# 【机理 3：仅重灾区取暖负荷激增 20%】
n.loads_t.p_set.loc[start_time:end_time, loads_affected] *= 1.20

print("✅ 2D 空间异质性气象冲击注入完成！西北大基地和南方电网将全面驰援中东部。")

# ==========================================
# 5. 进行风险压力测试 (运行纯调度优化)
# ==========================================
print("\n🚀 开始进行极端气候下的电网压力测试 (纯调度模式)...")
solver_options = {"Method": 2, "Crossover": 0, "BarConvTol": 1e-3, "Threads": 32}
n.optimize(solver_name="gurobi", **solver_options)

# ==========================================
# 6. 计算终极风险评估指标 (LOLE & EENS)
# ==========================================
print("\n📊 压力测试完成！正在评估全国电力损失指标：")

# 提取虚拟发电机(拉闸限电)的出力时间序列 (MW)
ls_gens = n.generators[n.generators.carrier == "load shedding"].index
shedding_t = n.generators_t.p[ls_gens]

# 计算全国总计的每小时缺电量 (GW)
total_shedding_hourly_gw = shedding_t.sum(axis=1) / 1000

# 指标 1：电量不足期望 (EENS - Expected Energy Not Supplied)
eens_twh = total_shedding_hourly_gw.sum() / 1000  # 转为 TWh
print(f"🔴 [核心指标] 全年电量不足期望 (EENS): {eens_twh:.2f} TWh")

# 指标 2：失负荷期望 (LOLE - Loss of Load Expectation)
# 判定标准：只要全国一小时内缺电超过 1 GW (1000MW)，就算作停电小时
lole_hours = (total_shedding_hourly_gw > 1).sum()
print(f"🔴 [核心指标] 失负荷期望 (LOLE): {lole_hours} 小时")

# 寻找受灾最严重的 TOP 3 省份
provincial_eens = shedding_t.sum() / 1e6  # TWh
worst_provinces = provincial_eens[provincial_eens > 0].sort_values(ascending=False).head(3)
if not worst_provinces.empty:
    print("\n⚠️ 停电灾情最严重的 3 个省份节点 (TWh):")
    for idx, val in worst_provinces.items():
        print(f"   - {idx.replace(' load shedding', '')}: {val:.2f} TWh")

# 保存极端测试后的网络，方便后续画图
n.export_to_netcdf("results/CN_power_2035_ssp226_Limited/networks/elec_s_34_ec_lcopt_Co2L-1h_EXTREME_assessed.nc")
print("\n✅ 分析结束！受压网络已保存。")
