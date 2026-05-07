import pypsa
import numpy as np

print("正在加载 elec.nc (文件较大，可能需要几十秒)...")
n = pypsa.Network("networks/CN_power_only_1month/elec.nc")

print("开始实施降维打击：将所有的无穷大 (inf) 替换为 999999 MW...")

# 1. 处理发电机 (Generators, 例如 OCGT 或未设上限的新能源)
if 'p_nom_max' in n.generators.columns:
    inf_count = np.isinf(n.generators['p_nom_max']).sum()
    n.generators['p_nom_max'] = n.generators['p_nom_max'].replace(np.inf, 999999)
    print(f" -> 修复了 {inf_count} 个 Generators 的无穷大容量。")

# 2. 处理储能单元 (Storage Units)
if not n.storage_units.empty and 'p_nom_max' in n.storage_units.columns:
    inf_count = np.isinf(n.storage_units['p_nom_max']).sum()
    n.storage_units['p_nom_max'] = n.storage_units['p_nom_max'].replace(np.inf, 999999)
    print(f" -> 修复了 {inf_count} 个 Storage Units 的无穷大容量。")

# 3. 处理独立储能 (Stores, 电池和氢能通常在这里)
if not n.stores.empty and 'e_nom_max' in n.stores.columns:
    inf_count = np.isinf(n.stores['e_nom_max']).sum()
    n.stores['e_nom_max'] = n.stores['e_nom_max'].replace(np.inf, 999999)
    print(f" -> 修复了 {inf_count} 个 Stores (电池/氢能) 的无穷大容量。")

# 4. 处理直流线路 (Links)
if not n.links.empty and 'p_nom_max' in n.links.columns:
    inf_count = np.isinf(n.links['p_nom_max']).sum()
    n.links['p_nom_max'] = n.links['p_nom_max'].replace(np.inf, 999999)
    print(f" -> 修复了 {inf_count} 条 Links 的无穷大容量。")

print("\n正在保存修改后的 elec.nc...")
n.export_to_netcdf("networks/CN_power_only_1month/elec.nc")
print("保存成功！inf 免死金牌已被彻底销毁。")