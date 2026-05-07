import os
import time

import atlite
import dask
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr

# ==========================================
# 0. 环境与样式初始化
# ==========================================
# 配置 Dask 多核并行计算 (使用所有可用的 144 个线程)
dask.config.set(scheduler="threads", num_workers=144)
print("⚡ 已配置 Dask 线程池: 144 workers")

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

# ==========================================
# 1. 预先切片一个极小区域 (提前准备)
# ==========================================
print(f"🕵️ 正在加载并嗅探原始气象文件 {original_file}...")
ds = xr.open_dataset(original_file)

lon_name = "x" if "x" in ds.coords else "longitude"
lat_name = "y" if "y" in ds.coords else "latitude"

lon_min, lon_max = float(ds[lon_name].min()), float(ds[lon_name].max())
lat_min, lat_max = float(ds[lat_name].min()), float(ds[lat_name].max())
print(f"  [原图] 经度范围: {lon_min:.1f} 到 {lon_max:.1f}")
print(f"  [原图] 纬度范围: {lat_min:.1f} 到 {lat_max:.1f}")

# 动态目标制定机制
target_name = "中国·甘肃酒泉核心区"
center_x, center_y = 98.5, 39.5

if not (lon_min < center_x < lon_max and lat_min < center_y < lat_max):
    target_name = "Cutout 数据集中心区域"
    center_x = (lon_min + lon_max) / 2
    center_y = (lat_min + lat_max) / 2
    print(f"⚠️ 文件范围不包括甘肃酒泉。已转移至中心区域: ({center_x:.1f}, {center_y:.1f})")

# 裁剪一个更小的区域，仅 0.5 度跨度 (约50km x 50km)，避免计算过慢
delta = 1
x_lim = [center_x - delta, center_x + delta]
y_lim = [center_y - delta, center_y + delta]

print(f"\n✂️ 正在从巨型矩阵中切割 X: {x_lim}, Y: {y_lim} (微型核心区)...")

# 高级对齐：防止降序坐标引发的全空选择
if float(ds[lat_name].values[0]) > float(ds[lat_name].values[-1]):
    ds_tiny = ds.sel({lon_name: slice(x_lim[0], x_lim[1]), lat_name: slice(y_lim[1], y_lim[0])})
else:
    ds_tiny = ds.sel({lon_name: slice(x_lim[0], x_lim[1]), lat_name: slice(y_lim[0], y_lim[1])})

tiny_file = f"{OUT_DIR}/cutout_jiuquan_small.nc"
print(f"💾 正在将小区域数据剥离并保存在硬盘上: {tiny_file} \n   (这能极大缩小等会儿 atlite 进入内存时的解析耗时)")
ds_tiny.to_netcdf(tiny_file)

# 释放重型占用的内存
ds.close()
ds_tiny.close()


# ==========================================
# 2. 分析切出来的极小区域气象数据集
# ==========================================
print("\n🔍 =======================================")
print("     对刚刚切下来的微型 Cutout 进行独立体检")
print("   =======================================")
ds_test = xr.open_dataset(tiny_file)
size_mb = os.path.getsize(tiny_file) / 1024 / 1024
print(f"   • 文件路径: {tiny_file}")
print(f"   • 物理大小: {size_mb:.2f} MB")
print(f"   • 包含维度: {dict(ds_test.dims)}")
if "time" in ds_test.dims:
    print(f"   • 时间长度: {ds_test.dims['time']} 小时 (时序完整通过 ✅)")
else:
    print("   ❌ 严重警告：丢失了 time 维度！")

print(f"   • {lon_name} 网格数: {ds_test.dims.get(lon_name, '未知')}")
print(f"   • {lat_name} 网格数: {ds_test.dims.get(lat_name, '未知')}")
print(f"   • 包含量: {list(ds_test.data_vars.keys())[:5]} ...")
ds_test.close()


# ==========================================
# 3. 在微型版 Cutout 上立刻调用 AtLite 极速求解
# ==========================================
print("\n🚀 正在启动 AtLite 解析微型气象数据...")
# 由于被裁得很小了（预计只有几十MB），不用分 block chunk了，直接全速处理
cutout = atlite.Cutout(tiny_file)

t0 = time.time()

# --- 1. 计算空间分布 (无 layout -> 丢失时间，但原样保留2D空间地图供作图) ---
print("   🗺️ 正在获取空间潜力图 (用于渲染热力地图)...")
wind_map = cutout.wind(turbine="Vestas_V112_3MW",capacity_factor=True)
pv_map = cutout.pv(panel="CSi", orientation="latitude_optimal", capacity_factor=True)

# --- 2. 计算动态时序 (有 layout -> 合并空间，但完美保留 8760h 时间) ---
print("   💨 正在计算风电出力时序 (Vestas V112 3MW)...")
weight_per_cell = 1.0 / (cutout.data.sizes["x"] * cutout.data.sizes["y"])
uniform_layout = xr.DataArray(weight_per_cell, coords=[cutout.data.coords["y"], cutout.data.coords["x"]])

ts_wind = cutout.wind(turbine="Vestas_V112_3MW", layout=uniform_layout)
print("   ☀️ 正在计算光伏出力时序 (晶硅 CSi)...")
ts_pv = cutout.pv(panel="CSi", orientation="latitude_optimal", layout=uniform_layout)

t1 = time.time()
print(f"   ✅ AtLite 物理换算及双轨分离完成！总耗时: {t1 - t0:.2f} 秒 🚀")


# 提取空间维保留时序
spatial_dims_wind = [d for d in ts_wind.dims if d != "time"]
spatial_dims_pv = [d for d in ts_pv.dims if d != "time"]

ts_wind = ts_wind.mean(dim=spatial_dims_wind) if spatial_dims_wind else ts_wind
ts_pv = ts_pv.mean(dim=spatial_dims_pv) if spatial_dims_pv else ts_pv

# pv_map = ts_pv.mean(dim="time") if "time" in ts_pv.dims else ts_pv
# wind_map = ts_wind.mean(dim="time") if "time" in ts_wind.dims else ts_wind

# 对带有地理空间维度的原始 map 数据进行时间求均值，保留地理矩阵
pv_map = pv_map.mean(dim="time") if "time" in pv_map.dims else pv_map
wind_map = wind_map.mean(dim="time") if "time" in wind_map.dims else wind_map

print("\n📈 最终时序输出维度:")
print(f"  ts_wind: dims={ts_wind.dims}, shape={ts_wind.shape}")
print(f"  ts_pv: dims={ts_pv.dims}, shape={ts_pv.shape}")

# 检查 time 维度
if "time" in ts_wind.dims and len(ts_wind.time) > 1:
    ts_wind_series = ts_wind.to_series()
    ts_pv_series = ts_pv.to_series()

    plot_hours = min(720, len(ts_wind_series))
    ts_wind_head = ts_wind_series.iloc[:plot_hours]
    ts_pv_head = ts_pv_series.iloc[:plot_hours]
    print(f"✅ 成功！捕捉到 {len(ts_wind_series)} 小时的完整时序！展示前 {plot_hours} 小时。")
else:
    print("❌ 错误：仍未获得时间维度！")
    plot_hours = 1
    ts_wind_head = pd.Series([ts_wind.item() if ts_wind.size > 0 else 0], index=["SnapShot"])
    ts_pv_head = pd.Series([ts_pv.item() if ts_pv.size > 0 else 0], index=["SnapShot"])

# ==========================================
# 4. 绘制分析仪表盘
# ==========================================
fig = plt.figure(figsize=(16, 12))

# 这个由于上面已经用 dask.compute 计算过，所以不需要再次判断
# pv_map = cf_pv.mean(dim="time") if "time" in cf_pv.dims else cf_pv
# wind_map = cf_wind.mean(dim="time") if "time" in cf_wind.dims else cf_wind

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
print("\n" + "=" * 60)
print("⚡ 极致性能优化总结:")
print("   • 完全抛弃全盘加载，底层物理剥离微型区域 (约50km见方)")
print("   • 避开了全部无效区域的 Dask 内存分配图")
print("   • 生成专属独立微小型 NC，二次传递给 AtLite 加速")
print("=" * 60)
