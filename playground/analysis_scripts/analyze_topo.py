import pandas as pd
import pypsa

# 请根据你的实际情况修改网络文件路径
# 如果你测试的是聚类前的数据，可以改为 "networks/CN_power_only_1month/elec_s.nc"
NETWORK_PATH = "networks/CN_power_only_1month/elec.nc"

def diagnose_topology(n_path):
    print(f"正在加载网络: {n_path} ...\n")
    try:
        n = pypsa.Network(n_path)
    except Exception as e:
        print(f"❌ 加载网络失败: {e}")
        return

    print("-" * 40)
    print("📊 网络基础信息")
    print(f"节点 (Buses) 总数: {len(n.buses)}")
    print(f"交流线路 (Lines) 总数: {len(n.lines)}")
    if not n.links.empty:
        print(f"直流/其他连接 (Links) 总数: {len(n.links)}")
    print("-" * 40)

    # 1. 节点连接度分析 (寻找“超级节点”)
    print("\n🔍 正在分析节点连接度...")
    # 将 bus0 和 bus1 合并统计，计算每个节点引出的线路总数
    all_connected_buses = pd.concat([n.lines["bus0"], n.lines["bus1"]])
    bus_degree = all_connected_buses.value_counts()

    print("\n[连接线路最多的 Top 5 节点]")
    print(bus_degree.head(5).to_string())

    if not bus_degree.empty:
        max_degree = bus_degree.iloc[0]
        super_node = bus_degree.index[0]
        # 如果一个节点连接了超过 15% 的总节点，这在真实的输电网中是非常离谱的
        if max_degree > len(n.buses) * 0.15:
            print(f"\n⚠️ 警告: 发现异常“超级节点”！节点 '{super_node}' 竟然连接了 {max_degree} 条线路。")
            print("这极有可能就是导致星型拓扑的罪魁祸首。")

    # 2. 线路长度分析 (寻找跨越大半个中国的异常连线)
    print("\n" + "-" * 40)
    print("📏 正在分析线路长度...")
    if "length" in n.lines.columns:
        longest_lines = n.lines.sort_values(by="length", ascending=False).head(5)
        print("\n[最长的 Top 5 线路]")
        for idx, row in longest_lines.iterrows():
            print(f"线路 {idx}: {row['bus0']} <--> {row['bus1']}, 长度: {row['length']:.2f} km")

        # 统计超长线路数量 (聚类为150个节点后，超过1500km的直连交流线通常是不合理的)
        abnormal_length_threshold = 1500
        long_lines = n.lines[n.lines["length"] > abnormal_length_threshold]

        if not long_lines.empty:
            print(f"\n⚠️ 警告: 发现了 {len(long_lines)} 条长度超过 {abnormal_length_threshold} km 的交流线路。")
    else:
        print("未在 lines DataFrame 中找到 'length' 列，跳过长度分析。")

    print("-" * 40)
    print("诊断完成。")


if __name__ == "__main__":
    diagnose_topology(NETWORK_PATH)
