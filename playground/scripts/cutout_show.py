import os

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

# ==========================================
# 0. 环境与样式初始化
# ==========================================
plt.rcParams["font.sans-serif"] = ["Source Han Sans SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
OUT_DIR = "./playground/analysis_cutout"
os.makedirs(OUT_DIR, exist_ok=True)

# 加载 Cutout 的 NetCDF 文件
file_path = "cutouts/cutout-2013-era5.nc"
print(f"🚀 正在加载 ERA5 气象数据: {file_path}")
ds = xr.open_dataset(file_path)

# ==========================================
# 1. 区域系坐标标准化与截取 (聚焦中国区)
# ==========================================
# 检查坐标轴名称，atlite 通常用 x, y，标准 ERA5 常使用 longitude, latitude
lon_name = "longitude" if "longitude" in ds.coords else "x"
lat_name = "latitude" if "latitude" in ds.coords else "y"

# 如果你的 Cutout 范围非常大（比如全球），我们需要截取中国的大致范围
# （中国经度约 73°~135°E，纬度约 18°~54°N）
# 判断当前数据是否需要切割
min_lon, max_lon = float(ds[lon_name].min()), float(ds[lon_name].max())
if max_lon > 140 or min_lon < 70:
    print("✂️ 数据范围较大，正在截取中国区域...")
    # 注意切片时 y 轴方向如果是降序（北->南），需要考虑 slice 的顺序
    if float(ds[lat_name][0]) > float(ds[lat_name][-1]):  # 降序
        ds = ds.sel({lon_name: slice(73, 125), lat_name: slice(54, 18)})
    else:  # 升序
        ds = ds.sel({lon_name: slice(73, 125), lat_name: slice(18, 54)})

# 选取一个特定的时间步（比如第一个时刻，或者春季某一天）
# 这里我们选择时间维度上的第 100 个小时做展示，如果有时间维的话
if "time" in ds.dims:
    time_idx = min(100, len(ds.time) - 1)
    ds_plot = ds.isel(time=time_idx)
    time_str = str(ds_plot.time.values)[:16].replace("T", " ")
else:
    ds_plot = ds
    time_str = "Static (No Time Dimension)"

print(f"📅 正在绘制时间节点: {time_str}")

# ==========================================
# 2. 准备四大变量数据
# ==========================================
# 1. 地表高度 Height
var_height = ds_plot["height"] if "height" in ds_plot else None

# 2. 地表粗糙度 Roughness
var_rough = ds_plot["roughness"] if "roughness" in ds_plot else None

# 3. 第三个变量（尝试找 表面气压 sp，如果没有找 温度 temperature 或 辐射 influx）
if "sp" in ds_plot:
    var_third = ds_plot["sp"]
    var_third_title = "Surface pressure [Pa]"
elif "temperature" in ds_plot:
    var_third = ds_plot["temperature"] - 273.15  # 转摄氏度
    var_third.name = "Temperature"
    var_third_title = "Surface Temperature [°C]"
elif "influx" in ds_plot:
    var_third = ds_plot["influx"]
    var_third_title = "Solar Influx [W/m²]"
else:
    var_third = None
    var_third_title = "N/A"

# 4. 100米风速 Wind Speed
if "wnd100m" in ds_plot:
    var_wind = ds_plot["wnd100m"]
elif "u100" in ds_plot and "v100" in ds_plot:
    # 矢量合成风速
    var_wind = np.sqrt(ds_plot["u100"] ** 2 + ds_plot["v100"] ** 2)
    var_wind.name = "Wind speed"
else:
    var_wind = None

# ==========================================
# 3. 绘制 2x2 组图
# ==========================================
fig, axes = plt.subplots(2, 2, figsize=(16, 12))


# 通用绘图函数封装
def plot_panel(ax, data, title, cmap):
    if data is not None:
        # 🌟 关键修改：将 data.plot 替换为 data.plot.imshow
        data.plot.imshow(ax=ax, cmap=cmap, cbar_kwargs={"shrink": 0.8})
        ax.set_title(title, fontsize=14)
        ax.set_xlabel(f"Longitude [{lon_name}]", fontsize=12)
        ax.set_ylabel(f"Latitude [{lat_name}]", fontsize=12)
    else:
        ax.text(0.5, 0.5, "Variable not found", ha="center", va="center")
        ax.set_title(title)


# 左上：高度
plot_panel(axes[0, 0], var_height, "Height [m]", cmap="viridis")

# 右上：地表粗糙度
plot_panel(axes[0, 1], var_rough, "Forecast surface roughness [m]", cmap="viridis")

# 左下：气压/温度/辐射（基于前面的探测）
msg_time = f"time = {time_str}"
plot_panel(axes[1, 0], var_third, f"{msg_time}\n{var_third_title}", cmap="viridis_r")

# 右下：100米风速
plot_panel(axes[1, 1], var_wind, f"{msg_time}\n100 metre wind speed [m s**-1]", cmap="viridis")

plt.tight_layout()
out_file = f"{OUT_DIR}/cutout_4panels_china.png"
plt.savefig(out_file, dpi=300, bbox_inches="tight")
plt.close()

print(f"🎉 Cutout 可视化完成！图片已保存至: {out_file}")
