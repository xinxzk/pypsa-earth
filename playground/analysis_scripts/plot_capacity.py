import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import pandas as pd
import pypsa


def get_node_capacities(n, is_solved=False):
    """
    聚合每个节点上不同技术的装机容量。
    求解前使用 p_nom，求解后使用 p_nom_opt。
    """
    col = "p_nom_opt" if is_solved else "p_nom"

    # 提取发电机的容量
    gen_caps = n.generators.groupby(["bus", "carrier"])[col].sum()

    # 提取储能（Storage Units）的容量
    if not n.storage_units.empty:
        su_caps = n.storage_units.groupby(["bus", "carrier"])[col].sum()
        caps = pd.concat([gen_caps, su_caps])
    else:
        caps = gen_caps

    # 重组为 DataFrame：行是节点(bus)，列是技术(carrier)
    df = caps.groupby(["bus", "carrier"]).sum().unstack(fill_value=0)

    # 将容量单位转换为 GW 以便绘图时数值和饼图大小适中
    return df / 1e3


def plot_capacity(network_path, is_solved=False, output_name="plot.png"):
    print(f"Loading network: {network_path} ...")
    n = pypsa.Network(network_path)

    # 获取节点容量数据 (此时为 DataFrame)
    bus_sizes = get_node_capacities(n, is_solved=is_solved)

    # 【修复关键点】：将 bus_sizes 补齐至与 n.buses 的索引完全一致，缺失的设为0
    bus_sizes = bus_sizes.reindex(n.buses.index).fillna(0)

    # 提取载体（技术）的颜色字典
    # PyPSA 通常会在 n.carriers.color 中预定义好颜色
    if "color" in n.carriers.columns:
        colors = n.carriers["color"].to_dict()
    else:
        # 如果没有颜色，可以利用 matplotlib 的缺省色系生成
        cmap = plt.get_cmap("tab20")
        colors = {carrier: cmap(i % 20) for i, carrier in enumerate(bus_sizes.columns)}

    # 处理一些没有预定义颜色的 carrier
    for c in bus_sizes.columns:
        if c not in colors or pd.isna(colors[c]) or colors[c] == "":
            colors[c] = "gray"

    # 设置地图投影与绘图参数
    proj = ccrs.PlateCarree()
    fig, ax = plt.subplots(figsize=(12, 12), subplot_kw={"projection": proj})

    ax.add_feature(cfeature.BORDERS, linewidth=0.8, edgecolor="black", zorder=1)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.8, edgecolor="black", zorder=1)

    # 绘制省级边界（可选）
    provinces = cfeature.NaturalEarthFeature(
        category="cultural", name="admin_1_states_provinces_lines", scale="50m", facecolor="none"
    )
    ax.add_feature(provinces, linewidth=0.4, edgecolor="gray", zorder=1)

    # 绘制 PyPSA 网络
    title_suffix = "Solved (Optimized)" if is_solved else "Unsolved (Initial)"

    # ====== 【修复核心】======
    # 当不能直接通过 bus_sizes 画饼状图时，我们可以利用 PyPSA 图层的 "pie" 相关的特定参数或自定义画图。
    # 我们先仅仅画出线（此时 bus_sizes=0，不画节点本身），然后再用 pandas/matplotlib 自己用 ax.pie() 砸在这！
    n.plot(
        ax=ax,
        bus_sizes=0,  # 让它不画 PyPSA 默认的点
        line_widths=0.8,
        link_widths=0.8,
        line_colors="darkgray",
        link_colors="cadetblue",
        title=f"34-Node Capacity ({title_suffix})",
        margin=0.05,
        color_geomap=False,
    )

    # 我们根据 bus_sizes (DataFrame) 自己画饼图
    # 获取节点的经纬度坐标
    xs = n.buses["x"]
    ys = n.buses["y"]

    # 尺寸控制
    scale = 0.3  # 你可以调节这个数字让其更大或更小
    pie_colors_list = [colors[c] for c in bus_sizes.columns]

    for bus in bus_sizes.index:
        total = bus_sizes.loc[bus].sum()
        if total < 1e-3:
            continue  # 忽略过小的容量

        # 使用 matplotlib 定义插入坐标系以绘制饼状图
        # 大小依据总装机量的开方
        r = (total**0.5) * scale

        x = xs[bus]
        y = ys[bus]

        # 将经纬度转化为目标轴系的图表上比例
        ax_ins = ax.inset_axes([x - r / 2, y - r / 2, r, r], transform=ax.transData)
        ax_ins.set_aspect("equal")

        # 提取值，过滤全0
        vals = bus_sizes.loc[bus]
        masks = vals > 0

        ax_ins.pie(vals[masks], colors=[pie_colors_list[i] for i, m in enumerate(masks) if m], startangle=90)

    # --- 添加图例 (Legend) ---
    import matplotlib.patches as mpatches

    legend_handles = [mpatches.Patch(color=colors[c], label=c) for c in bus_sizes.columns if bus_sizes[c].sum() > 0]
    ax.legend(
        handles=legend_handles, loc="center left", bbox_to_anchor=(1.05, 0.5), title="Technologies", frameon=False
    )

    plt.tight_layout()
    plt.savefig(output_name, dpi=300, bbox_inches="tight")
    print(f"Saved plot to {output_name}")
    plt.close()


if __name__ == "__main__":
    # 文件路径
    network_presolve = "networks/CN_power_2035_ssp226/elec_s_34_ec_lcopt_Co2L-1h.nc"
    network_postsolve = "results/CN_power_2035_ssp226_Limited/networks/elec_s_34_ec_lcopt_Co2L-1h_solved.nc"

    # 1. 绘制求解前 (p_nom)
    plot_capacity(network_path=network_presolve, is_solved=False, output_name="playground/capacity_presolve_34.png")

    # 2. 绘制求解后 (p_nom_opt)
    plot_capacity(network_path=network_postsolve, is_solved=True, output_name="playground/capacity_postsolve_34.png")
