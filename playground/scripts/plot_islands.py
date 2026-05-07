import matplotlib.pyplot as plt
import pypsa

# ==========================================
# 1. 设置路径和参数
# ==========================================
# 请将此路径替换为你通过 simplify_network 阶段生成的 NC 文件路径
network_path = "networks/CN_power_only_1month/elec_s.nc"

# 为了防止孤岛数量太多导致绘图耗时过长，设置只画出节点数最多的 N 个孤岛
# （不包括那个最大的主电网）
num_islands_to_plot = 10

print(f"正在加载网络: {network_path} ...")
n = pypsa.Network(network_path)

# ==========================================
# 2. 拓扑分析：识别连通分量
# ==========================================
print("正在进行拓扑分析，识别连通子网（Islands）...")
n.determine_network_topology()

# ---- 修复：手动计算每个子网的节点数 ----
# n.buses.sub_network 列存储了每个节点所属的子网 ID
bus_counts = n.buses.groupby("sub_network").size().rename("n_buses")

# 将节点数合并到 sub_networks DataFrame
subnets = n.sub_networks.copy()
subnets = subnets.join(bus_counts, how="left")
subnets["n_buses"] = subnets["n_buses"].fillna(0).astype(int)

# 按节点数量排序（降序）
subnets = subnets.sort_values(by="n_buses", ascending=False)

# 获取主网的 ID
main_grid_id = subnets.index[0]
n_buses_main = subnets.iloc[0]["n_buses"]

print("分析完成。")
print(f" -> 共有 {len(subnets)} 个独立的子网（Synchronous Zones）。")
print(f" -> 最大的主网 (ID: {main_grid_id}) 包含 {n_buses_main} 个节点。")

# 提取所有的孤岛 (排除主网)
islands = subnets.iloc[1:].head(num_islands_to_plot)

if islands.empty:
    print("太棒了！你的网络中没有发现孤岛（除了一个主网）。")
    exit()

print(f"准备单独绘制前 {len(islands)} 个最大的孤岛...")

# ==========================================
# 3. 循环绘图
# ==========================================
# 设置投影坐标系，以便添加 contextily 底图 (Web Mercator)
plot_crs = "EPSG:3857"

for i, (sn_id, sn_info) in enumerate(islands.iterrows()):
    n_buses = sn_info["n_buses"]

    print(f"[{i + 1}/{len(islands)}] 正在绘制孤岛 ID: {sn_id}, 包含节点数: {n_buses} ...")

    # a. 提取属于该孤岛的组件
    # 提取节点
    island_buses = n.buses[n.buses.sub_network == sn_id]

    # 提取交流线路 (两端节点都在该岛上的线路)
    island_lines = n.lines[(n.lines.bus0.isin(island_buses.index)) & (n.lines.bus1.isin(island_buses.index))]

    # 提取直流跨接/特高压 (这通常是点对点直流悬空的原因)
    island_links = n.links[(n.links.bus0.isin(island_buses.index)) & (n.links.bus1.isin(island_buses.index))]

    # b. 准备绘图
    if island_lines.empty and island_links.empty and n_buses < 2:
        print(f"   (ID: {sn_id} 是单一孤立节点，跳过绘图)")
        continue

    # ---- 修复：移除无效的 projection 参数 ----
    fig, ax = plt.subplots(figsize=(10, 10))

    # c. 使用 PyPSA 内置绘图功能绘制该孤岛的子集
    # 这里我们必须把坐标转为 geopandas 的地理点，以便 plot() 能处理范围
    # PyPSA 绘图默认使用 Lat/Lon (EPSG:4326)

    try:
        # 如果 contextily 版本较新，可以直接在 n.plot 中设置转换，
        # 否则我们需要手动调整 ax 的范围。这里采用兼容性最好的方法：先画，后调。
        collection = n.plot(
            ax=ax,
            bus_subset=island_buses.index,
            line_subset=island_lines.index,
            link_subset=island_links.index,
            bus_colors="red",  # 孤岛节点用红色突出
            bus_sizes=10,
            line_colors="blue",  # 交流线路用蓝色
            link_colors="purple",  # 直流 Links 用紫色
            line_widths=2,
            geomap=True,  # 启用地理坐标支持
        )

        # d. 自动调整视角放大到该孤岛
        # 计算该岛所有节点的地理边界
        min_x, max_x = island_buses.x.min(), island_buses.x.max()
        min_y, max_y = island_buses.y.min(), island_buses.y.max()

        # 添加一点边界填充（Buffer），防止组件贴边
        use_buffer = 0.5  # 度
        if n_buses < 2 or (min_x == max_x and min_y == max_y):
            # 只有一个点的特殊情况，强制放大视角
            use_buffer = 0.2

        ax.set_xlim(min_x - use_buffer, max_x + use_buffer)
        ax.set_ylim(min_y - use_buffer, max_y + use_buffer)

        # e. 添加 Contextily 卫星/路网底图
        # PyPSA 绘图默认是 4326 投影，底图通常需要 3857，contextily 自动处理转换

        # f. 装饰
        title = (
            f"Island Subnet: {sn_id}\nBuses: {n_buses} | Lines: {len(island_lines)} | Links(HVDC): {len(island_links)}"
        )
        ax.set_title(title, fontsize=12)
        ax.set_axis_off()  # 隐藏坐标轴刻度

        # 可选：保存图片
        # plt.savefig(f"island_{sn_id}_map.png", dpi=150, bbox_inches='tight')
        plt.show()  # 在 Jupyter 或 IDE 中弹出显示
        plt.savefig(f"./playground/islandpic/island_{sn_id}_map.png", dpi=300, bbox_inches="tight")
        plt.close(fig)  # 释放内存

    except Exception as e:
        print(f"   绘制 ID: {sn_id} 时发生错误 (通常是地理范围计算问题): {e}")
        plt.close(fig)

print("孤岛分析绘图完成。请检查弹出的图片。")
