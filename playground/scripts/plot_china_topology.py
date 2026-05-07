import geopandas as gpd
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import pypsa

# ================= 数据加载 =================
path = "networks/CN_power_2035_ssp226/elec_s.nc"
n = pypsa.Network(path)

# 使用 GeoPandas 读取本地官方 shapefile！这是最稳健的做法，不怕读取错误。
province_shp = "playground/res/china_map/省级行政区.shp"
national_shp = "playground/res/china_map/国界线.shp"

print("正在使用 geopandas 加载地图...")
# 转换为 4326 (WGS84) 的常规经纬度坐标系，保证与 PyPSA 输出对齐
gdf_prov = gpd.read_file(province_shp).to_crs(epsg=4326)
gdf_nat = gpd.read_file(national_shp).to_crs(epsg=4326)

# ================= 初始化绘图 =================
# 注意：这回不去使用 cartopy 的 ccrs 投影复杂套件了，直接用普通 matplotlib 坐标轴
# 因为 geopandas 可以在普通 plot 上画经纬度。
fig, ax = plt.subplots(figsize=(12, 10))

# 设定图的经纬度显示范围 (相当于 set_extent)
extent = [73, 137, 3, 55]
ax.set_xlim(extent[0], extent[1])
ax.set_ylim(extent[2], extent[3])

# ================= 1. 绘制 GeoPandas 中国地图基底 =================
print("正在绘制官方地图图层...")
# 画省界 (颜色灰色、线条偏细、底色全白)
gdf_prov.plot(
    ax=ax,
    facecolor="white",  # 同样提供白底隔离
    edgecolor="gray",
    linewidth=0.5,
    zorder=1,
)

# 画国界 (也就是加粗最外圈及其九段线)
gdf_nat.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.2, zorder=2)

# ================= 2. 绘制 PyPSA 拓扑 =================
print("正在叠加 PyPSA 拓扑网络...")
# 这次 geomap=False，并且坐标轴不再是带有特殊 geo 属性的。
# PyPSA 将单纯只是把 buses 和 lines 的坐标以常规的 x=经度, y=纬度 的形式投射到 ax 上。
n.plot(
    ax=ax,
    geomap=False,  # 完全禁用自带地图！
    bus_sizes=0.005,
    line_widths=0.5,
    link_widths=0.5,
    bus_colors="red",
    line_colors="blue",
    link_colors="teal",
    zorder=10,  # 确保是在最高层显示
    title=f"China Power Network Topology ({path.split('/')[-1].replace('.nc', '')})",
)

# ================= 3. 绘制自定义图例与收尾 =================
legend_handles = [
    mlines.Line2D(
        [], [], color="white", marker="o", markerfacecolor="red", markeredgecolor="red", markersize=8, label="Buses"
    ),
    mlines.Line2D([], [], color="blue", linewidth=2, label="AC Lines"),
    mlines.Line2D([], [], color="teal", linewidth=2, label="DC Links"),
]
ax.legend(handles=legend_handles, loc="lower left", fontsize=12, framealpha=0.9)

# 因为没有使用 geo 投影，我们手动固定 ax 比例系，免得被拉伸变形
ax.set_aspect("equal")

plt.tight_layout()
out_png = f"./playground/china_topology_{path.split('/')[-1].replace('.nc', '')}.png"
plt.savefig(out_png, dpi=300)
print(f"出图完毕，已保存至 {out_png}")
plt.show()
