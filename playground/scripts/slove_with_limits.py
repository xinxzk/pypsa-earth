import os

import pypsa

# 1. 加载 Snakemake 已经生成好的、未求解的 1h 网络
input_path = "networks/CN_power_2035_ssp226/elec_s_34_ec_lcopt_Co2L-1h.nc"
print(f"📥 正在加载网络: {input_path}")
n = pypsa.Network(input_path)

# ==========================================
# 2. 注入动态物理天花板 (核心绝招)
# ==========================================
print("🚧 正在施加特高压物理扩容天花板...")
# 限制交流线路：最大允许容量 = 既有容量 + 25000 MW (即最多只允许新增 25 GW)
n.lines.s_nom_max = n.lines.s_nom + 25000

# 限制直流线路/储能 (在 PyPSA 中通常用 Link 建模，其容量属性叫 p_nom)
# 只限制特高压直流 (HVDC)，不限制电池储能
hvdc_links = n.links[n.links.carrier == "DC"].index
if len(hvdc_links) > 0:
    n.links.loc[hvdc_links, "p_nom_max"] = n.links.loc[hvdc_links, "p_nom"] + 25000

print("✅ 天花板施加成功！每条跨省通道最多新增 25 GW。")

# ==========================================
# 3. 召唤求解器并保存终极结果
# ==========================================
print("🚀 开始进行受物理约束的最终求解 (这可能需要一些时间)...")
solver_options = {
    "Method": 2,         # 强制使用 Barrier 内点法
    "Crossover": 0,      # 强制跳过耗时的 Crossover 阶段
    "BarConvTol": 1e-3,  # 稍微放宽收敛容忍度，极大提速
    "Threads": 32        # 调用你的 32 个线程
}

print("🚀 开始进行受物理约束的最终求解...")
n.optimize(
    solver_name='gurobi',
    **solver_options  # <--- 把参数字典解包传进去
)

# 保存求解后的结果
output_dir = "results/CN_power_2035_ssp226_Limited/networks"
os.makedirs(output_dir, exist_ok=True)
output_path = f"{output_dir}/elec_s_34_ec_lcopt_Co2L-1h_solved.nc"
n.export_to_netcdf(output_path)
print(f"🎉 求解完成！结果已保存至: {output_path}")
