from pathlib import Path

# 待检查的文件列表（根据你的错误日志整理）
files_to_check = [
    "data/global_buildings/NG_global_buildings_raw.parquet",
    "data/ssp2-2.6/2030/era5_2013/SouthAmerica.nc",
    "data/gebco/GEBCO_2025_sub_ice.nc",
    "data/copernicus/PROBAV_LC100_global_v3.0.1_2019-nrt_Discrete-Classification-map_EPSG-4326.tif",
    "data/eez/eez_v11.gpkg",
    "data/ssp2-2.6/2030/era5_2013/Asia.nc",
    "data/gadm/gadm36_NGA/gadm36_NGA.gpkg",
    "cutouts/cutout-2013-era5-tutorial.nc",
    "data/ssp2-2.6/2030/era5_2013/Africa.nc",
]


def check_files():
    print(f"{'File Path':<60} | {'Status':<10} | {'Size (MB)':<10}")
    print("-" * 85)

    issues_found = False
    for f in files_to_check:
        path = Path(f)
        if not path.exists():
            status = "❌ MISSING"
            size = 0
            issues_found = True
        elif path.stat().st_size == 0:
            status = "⚠️ EMPTY"
            size = 0
            issues_found = True
        else:
            status = "✅ OK"
            size = path.stat().st_size / (1024 * 1024)  # 转换为 MB

        print(f"{str(path):<60} | {status:<10} | {size:>8.2f}")

    print("-" * 85)
    if issues_found:
        print("\n💡 建议：删除状态为 MISSING 或 EMPTY 的文件，然后运行：")
        print("snakemake solve_sector_networks --rerun-incomplete")
    else:
        print("\n✨ 文件基础检查通过！如果 Snakemake 仍然报错，请尝试清理元数据：")
        print("snakemake --cleanup-metadata " + " ".join(files_to_check[:2]) + " ...")


if __name__ == "__main__":
    check_files()
