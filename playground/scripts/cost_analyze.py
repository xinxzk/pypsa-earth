import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

OUT_DIR = "./playground/analysis_cost"
if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)

# 设置字体以防中文乱码
plt.rcParams["font.sans-serif"] = ["Source Han Sans SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ================= 核心分析技术池 =================
KEY_POWER_TECHS = [
    "solar",
    "solar-utility",
    "solar-rooftop",
    "onwind",
    "offwind",
    "battery storage",
    "battery inverter",
    "CCGT",
    "OCGT",
]

KEY_GRID_TECHS = [
    "HVAC overhead",
    "HVDC overhead",
    "HVDC submarine",
    "HVDC inverter cable",
    "H2 pipeline",
    "H2 pipeline retrofitted",
]


def load_and_preprocess():
    costs_2025_path = "playground/res/costs_2025.csv"
    costs_2035_path = "playground/res/costs_2035.csv"

    df_2025 = pd.read_csv(costs_2025_path)
    df_2035 = pd.read_csv(costs_2035_path)

    df_2025["dataset_year"] = "2025"
    df_2035["dataset_year"] = "2035"

    common_cols = ["technology", "parameter", "value", "unit", "dataset_year"]

    df_combined = pd.concat(
        [
            df_2025[[c for c in common_cols if c in df_2025.columns]],
            df_2035[[c for c in common_cols if c in df_2035.columns]],
        ],
        ignore_index=True,
    )

    df_combined["value"] = pd.to_numeric(df_combined["value"], errors="coerce")
    return df_combined


def export_comprehensive_csvs(df):
    """
    分多维度将对比结果导出为多个 CSV 文件
    """
    pivot_df = df.pivot_table(
        index=["technology", "parameter", "unit"], columns="dataset_year", values="value"
    ).reset_index()

    if "2025" in pivot_df.columns and "2035" in pivot_df.columns:
        pivot_df = pivot_df.dropna(subset=["2025", "2035"])
        pivot_df["absolute_change"] = pivot_df["2035"] - pivot_df["2025"]
        pivot_df["change_percent(%)"] = (pivot_df["absolute_change"] / pivot_df["2025"]) * 100
        pivot_df["change_percent(%)"] = pivot_df["change_percent(%)"].round(2)

        # 1. 导出主表
        main_csv = f"{OUT_DIR}/01_all_technologies_cost_change_25_vs_35.csv"
        pivot_df.sort_values(by=["parameter", "change_percent(%)"]).to_csv(main_csv, index=False)

        # 2. 投资降幅排行表
        inv_df = pivot_df[pivot_df["parameter"] == "investment"]
        top_drops = inv_df.sort_values(by="change_percent(%)").head(25)
        top_drops_csv = f"{OUT_DIR}/02_top_investment_cost_drops.csv"
        top_drops.to_csv(top_drops_csv, index=False)

        # 3. 运维与效率变化表
        om_eff_df = pivot_df[pivot_df["parameter"].isin(["FOM", "efficiency", "lifetime"])]
        om_eff_csv = f"{OUT_DIR}/03_fom_lifetime_efficiency_changes.csv"
        om_eff_df.to_csv(om_eff_csv, index=False)


# ================= 绘图函数 =================


def plot_key_power_technologies(df):
    """专项图1: 核心发电与储能技术 (风、光、气、储、逆变器)"""
    df_pw = df[(df["parameter"] == "investment") & (df["technology"].isin(KEY_POWER_TECHS))]
    if df_pw.empty:
        return

    plt.figure(figsize=(12, 6))
    sns.barplot(data=df_pw, x="technology", y="value", hue="dataset_year", palette="Set1")
    plt.title("Core Power Gen & Storage: Investment Cost Comparison (2025 vs 2035)")
    plt.ylabel(f"Investment ({df_pw['unit'].iloc[0]})")
    plt.xlabel("Technology")
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/fig1_core_power_investment.png", dpi=300)
    plt.close()


def plot_network_infrastructure(df):
    """专项图2: 线路与管网基础设施 (HVAC, HVDC, 氢气管道)"""
    # 模糊匹配抓取线路和管道数据
    grid_techs = [t for t in df["technology"].unique() if "HVAC" in t or "HVDC" in t or "pipeline" in t]
    df_net = df[(df["parameter"] == "investment") & (df["technology"].isin(grid_techs))]
    if df_net.empty:
        return

    plt.figure(figsize=(12, 6))
    sns.barplot(data=df_net, x="technology", y="value", hue="dataset_year", palette="Oranges_d")
    plt.title("Network Infrastructure: Cables & Pipelines Investment")
    plt.ylabel("Investment (per MW/km or per unit)")
    plt.xlabel("Infrastructure Technology")
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/fig2_network_cables_pipelines.png", dpi=300)
    plt.close()


def plot_hydrogen_focus(df):
    """专项图3: 聚焦制氢技术 (电解槽和氨气分解)"""
    h2_techs = [t for t in df["technology"].unique() if "electrolyz" in t.lower() or "ammonia" in t.lower()]
    df_h2 = df[(df["parameter"] == "investment") & (df["technology"].isin(h2_techs))]

    if df_h2.empty:
        return

    plt.figure(figsize=(10, 6))
    sns.barplot(data=df_h2, x="technology", y="value", hue="dataset_year", palette="Blues_d")
    plt.title("Hydrogen Economy: Investment Cost of Converters")
    plt.ylabel("Investment")
    plt.xticks(rotation=25, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/fig3_hydrogen_technologies.png", dpi=300)
    plt.close()


def plot_heavy_transport_focus(df):
    """专项图4: 重型电动交通"""
    bev_techs = [t for t in df["technology"].unique() if "BEV" in t and ("Truck" in t or "Bus" in t or "Coach" in t)]
    df_bev = df[(df["parameter"] == "investment") & (df["technology"].isin(bev_techs))]

    if df_bev.empty:
        return

    plt.figure(figsize=(12, 6))
    sns.barplot(data=df_bev, x="technology", y="value", hue="dataset_year", palette="Greens_d")
    plt.title("Heavy Transport: Commercial BEVs Investment")
    plt.ylabel(f"Investment ({df_bev['unit'].iloc[0]})")
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/fig4_heavy_transport.png", dpi=300)
    plt.close()


def plot_efficiency_improvements(df):
    """专项图5: 全局关键效率指标 (Efficiency) 对比"""
    # 挑选一些效率参数很重要的技术
    eff_techs = [
        "CCGT",
        "OCGT",
        "solar",
        "battery inverter",
        "H2 pipeline",
        "Alkaline electrolyzer small size",
        "Ammonia cracker",
    ]
    df_eff = df[(df["parameter"].isin(["efficiency"])) & (df["technology"].isin(eff_techs))]

    if df_eff.empty:
        return

    plt.figure(figsize=(10, 6))
    sns.pointplot(
        data=df_eff, x="technology", y="value", hue="dataset_year", dodge=True, join=False, markers=["o", "s"]
    )
    plt.title("Efficiency Improvements (2025 vs 2035)")
    plt.ylabel("Efficiency Rate / Index")
    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/fig5_efficiency_improvements.png", dpi=300)
    plt.close()


if __name__ == "__main__":
    df = load_and_preprocess()

    print("开始生产多维分析文件与图表...")

    # 1. 导出 CSV 报表
    export_comprehensive_csvs(df)

    # 2. 绘制业务切片图表
    plt.rcParams.update({"font.size": 12})
    plot_key_power_technologies(df)  # 发电储能篇 (恢复最重要参数)
    plot_network_infrastructure(df)  # 电网管网篇 (新增：交/直流与管道)
    plot_hydrogen_focus(df)  # 氢能转化篇
    plot_heavy_transport_focus(df)  # 脱碳交通篇
    plot_efficiency_improvements(df)  # 技术效率进步篇

    print(f"✅ 生成完毕！请查看 {OUT_DIR} 文件夹。")
