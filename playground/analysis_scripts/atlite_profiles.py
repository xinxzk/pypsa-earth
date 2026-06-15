import os

import atlite
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

# ==========================================
# 0. 环境与样式初始化
# ==========================================
plt.rcParams["font.sans-serif"] = ["Source Han Sans SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
OUT_DIR = "./playground/analysis_cutout"
os.makedirs(OUT_DIR, exist_ok=True)

# 自动判断哪个教程文件可用
fallback_files = ["cutouts/cutout-2013-era5.nc", "cutouts/cutout-2013-era5-tutorial.nc"]
original_file = None
for f in fallback_files:
    if os.path.exists(f):
        original_file = f
        break

if not original_file:
    raise FileNotFoundError("在这个目录下没有找到预期的 cutout (.nc) 气象文件，请检查！")

tiny_file = f"{OUT_DIR}/cutout_dynamic_small.nc"

# ==========================================
# 1. 智能嗅探与裁剪：适配任何范围的 Cutout 数据
# ==========================================
print(f"🕵️ 正在嗅探气象文件 {original_file} 的内部环境...")

with xr.open_dataset(original_file) as ds:
    # 确定坐标名
    lon_name = "x" if "x" in ds.coords else "longitude"
    lat_name = "y" if "y" in ds.coords else "latitude"

    lon_min, lon_max = float(ds[lon_name].min()), float(ds[lon_name].max())
    lat_min, lat_max = float(ds[lat_name].min()), float(ds[lat_name].max())
    time_len = len(ds.time) if "time" in ds.dims else 0

    print(f"  [发现] 经度范围: {lon_min:.1f} 到 {lon_max:.1f}")
    print(f"  [发现] 纬度范围: {lat_min:.1f} 到 {lat_max:.1f}")
    print(f"  [发现] 时间切片数: {time_len} 个时刻")

    # 动态目标制定机制
    # 1. 优先尝试提取中国甘肃·酒泉大基地
    target_name = "中国·甘肃酒泉大基地"
    center_x, center_y = 98.5, 39.5

    # 2. 如果包含酒泉的坐标在文件的包围框之外，退而求其次：
    if not (lon_min < center_x < lon_max and lat_min < center_y < lat_max):
        target_name = "Cutout 数据集自带区域地空中心位置"
        center_x = (lon_min + lon_max) / 2
        center_y = (lat_min + lat_max) / 2
        print(f"⚠️ 文件范围不包括甘肃酒泉。已转移降落坐标点至本文件中心区域: ({center_x:.1f}, {center_y:.1f})")

    # 以中心点为核心，切出 1.5° × 1.5° 的范围 (边长约 150km 的正方形)
    x_lim = [center_x - 0.75, center_x + 0.75]
    y_lim = [center_y - 0.75, center_y + 0.75]

    # 执行最终安全切片
    if float(ds[lat_name][0]) > float(ds[lat_name][-1]):
        ds_tiny = ds.sel({lon_name: slice(x_lim[0], x_lim[1]), lat_name: slice(y_lim[1], y_lim[0])})
    else:
        ds_tiny = ds.sel({lon_name: slice(x_lim[0], x_lim[1]), lat_name: slice(y_lim[0], y_lim[1])})

    ds_tiny.to_netcdf(tiny_file)

print(f"✅ 裁剪完成！区域数据已浓缩至: {os.path.getsize(tiny_file) / 1024:.1f} KB")

# ==========================================
# 2. 物理模型换算 (高速运算)
# ==========================================
print("\n🚀 正在通过 AtLite 核心接口提取可再生能源潜力...")
cutout = atlite.Cutout(tiny_file)

print("💨 正在计算该微区域的风电出力 (Vestas V112 3MW)...")
cf_wind = cutout.wind(turbine="Vestas_V112_3MW")

print("☀️ 正在计算该微区域的光伏出力 (晶硅 CSi)...")
cf_pv = cutout.pv(panel="CSi", orientation="latitude_optimal")

# ==========================================
# 3. 数据聚合 (修复 8760h 时序降级 Bug)
# ==========================================
print("📈 正在聚合时空数据以便作图...")

# 打印诊断信息：看看 atlite 返回了什么结构
print("\n🔍 [诊断] cf_wind 数组结构：")
print(f"  dimensions: {cf_wind.dims}")
print(f"  shape: {cf_wind.shape}")
print(f"  coords: {list(cf_wind.coords.keys())}")
print(f"  size: {cf_wind.size}")

print("\n🔍 [诊断] cf_pv 数组结构：")
print(f"  dimensions: {cf_pv.dims}")
print(f"  shape: {cf_pv.shape}")
print(f"  coords: {list(cf_pv.coords.keys())}")

# 关键：用 xr.DataArray.dims 获得维度元组，排除不含 'time' 的所有维度进行均值
# 这比之前的做法更保险
all_dims_wind = set(cf_wind.dims)
all_dims_pv = set(cf_pv.dims)

# 如果存在 'time' 维，则只对其他维求均值；否则全部维度求均值
if "time" in all_dims_wind:
    dims_to_mean_wind = list(all_dims_wind - {"time"})
    print(f"\n✅ cf_wind 中找到 time 维！将对这些维度求均值: {dims_to_mean_wind}")
else:
    dims_to_mean_wind = list(all_dims_wind)
    print(f"\n⚠️ cf_wind 中未找到 time 维!所有维度: {dims_to_mean_wind}")

if "time" in all_dims_pv:
    dims_to_mean_pv = list(all_dims_pv - {"time"})
    print(f"✅ cf_pv 中找到 time 维！将对这些维度求均值: {dims_to_mean_pv}")
else:
    dims_to_mean_pv = list(all_dims_pv)
    print(f"⚠️ cf_pv 中未找到 time 维!所有维度: {dims_to_mean_pv}")

# 执行均值操作
ts_wind = cf_wind.mean(dim=dims_to_mean_wind) if dims_to_mean_wind else cf_wind
ts_pv = cf_pv.mean(dim=dims_to_mean_pv) if dims_to_mean_pv else cf_pv

print("\n🔍 [诊断] 均值之后的 ts_wind 结构：")
print(f"  dimensions: {ts_wind.dims}")
print(f"  shape: {ts_wind.shape if hasattr(ts_wind, 'shape') else 'N/A'}")
print(f"  size: {ts_wind.size}")

# 最后的保险检查：看看 time 维度有多长
time_length = 0
if "time" in ts_wind.dims:
    time_length = len(ts_wind.time)
    ts_wind_series = ts_wind.to_series()
    ts_pv_series = ts_pv.to_series()

    plot_hours = min(720, len(ts_wind_series))
    ts_wind_head = ts_wind_series.iloc[:plot_hours]
    ts_pv_head = ts_pv_series.iloc[:plot_hours]
    print(f"\n✅ 成功！检测到 {time_length} 个完整的时间步。将展示前 {plot_hours} 小时。")
else:
    print("\n❌ 失败：均值操作后仍然没有 'time' 维度！")
    plot_hours = 1
    ts_wind_head = pd.Series([ts_wind.item() if ts_wind.size > 0 else 0], index=["SnapShot"])
    ts_pv_head = pd.Series([ts_pv.item() if ts_pv.size > 0 else 0], index=["SnapShot"])

# ==========================================
# 4. 绘制分析仪表盘
# ==========================================
fig = plt.figure(figsize=(16, 12))

# 为了防止没有 time 维度而报错，均值空间图作防呆处理
pv_map = cf_pv.mean(dim="time") if "time" in cf_pv.dims else cf_pv
wind_map = cf_wind.mean(dim="time") if "time" in cf_wind.dims else cf_wind

# --- 图 1：光伏潜力空间分布图 ---
ax1 = plt.subplot(2, 2, 1)
pv_map.plot.imshow(ax=ax1, cmap="Oranges", cbar_kwargs={"label": "PV CF"})
ax1.set_title(f"{target_name} - 局部光伏年均潜力分布", fontsize=14)
ax1.set_xlabel("Longitude")
ax1.set_ylabel("Latitude")

# --- 图 2：风电潜力空间分布图 ---
ax2 = plt.subplot(2, 2, 2)
wind_map.plot.imshow(ax=ax2, cmap="Blues", cbar_kwargs={"label": "Wind CF"})
ax2.set_title(f"{target_name} - 局部风电年均潜力分布", fontsize=14)
ax2.set_xlabel("Longitude")
ax2.set_ylabel("Latitude")

# --- 图 3：风光综合出力动态曲线 ---
ax3 = plt.subplot(2, 1, 2)
ts_pv_head.plot(
    ax=ax3, color="#f39c12", lw=1.5, marker="o" if plot_hours < 24 else None, label="PV (光伏均值)", alpha=0.85
)
ts_wind_head.plot(
    ax=ax3, color="#2980b9", lw=1.5, marker="o" if plot_hours < 24 else None, label="Wind (风电均值)", alpha=0.85
)

ax3.set_title(
    f"区域综合发电容量因子曲线 (0~1) - {'前 ' + str(plot_hours) + ' 小时连续监测' if plot_hours > 1 else '静态基准点'}",
    fontsize=14,
)
ax3.set_ylabel("Capacity Factor")
ax3.set_xlabel("Time (时间)")
ax3.grid(True, alpha=0.3, linestyle="--")

# 防止图表拥挤造成遮挡，把图例放右上角并调整文字
ax3.legend(loc="upper right", framealpha=0.9, fontsize=12)

# 为了防止X轴时间文字覆盖
plt.setp(ax3.xaxis.get_majorticklabels(), rotation=0)

plt.tight_layout()
out_file = f"{OUT_DIR}/atlite_wind_pv_dynamic.png"
plt.savefig(out_file, dpi=300, bbox_inches="tight")
plt.close()

import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
print(f"🎉 动态分析全部通过并绘制完成！请查看: {out_file}")
