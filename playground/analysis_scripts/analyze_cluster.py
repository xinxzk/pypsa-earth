import pandas as pd
import pypsa

n = pypsa.Network("networks/CN_power_only_1month/elec_s.nc")

print("--- Links 载体类型分析 ---")
print(n.links.carrier.value_counts())

print("\n--- 寻找星型拓扑的中心节点 ---")
all_connected_links = pd.concat([n.links["bus0"], n.links["bus1"]])
center_nodes = all_connected_links.value_counts().head(3)
print(center_nodes)

print("🔍 正在分析 Links (直流/等效连接) 的连接度...")
# 统计 bus0 和 bus1
all_connected_links = pd.concat([n.links["bus0"], n.links["bus1"]])
link_degree = all_connected_links.value_counts()

print("\n[连接 Links 最多的 Top 5 节点]")
print(link_degree.head(5).to_string())

if "length" in n.links.columns:
    print("\n" + "-" * 40)
    print("📏 正在分析 Links 长度...")
    longest_links = n.links.sort_values(by="length", ascending=False).head(5)
    print("\n[最长的 Top 5 Links]")
    for idx, row in longest_links.iterrows():
        print(f"Link {idx}: {row['bus0']} <--> {row['bus1']}, 长度: {row['length']:.2f} km")
else:
    print("\n⚠️ 未在 links DataFrame 中找到 'length' 列，可能这些是无实际物理距离的虚拟连接。")

