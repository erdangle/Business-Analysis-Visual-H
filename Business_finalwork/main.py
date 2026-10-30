from __future__ import annotations

import json
import math
import urllib.request
import warnings
from itertools import count, product
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle, Wedge
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent
DATA_RAW = ROOT / "data" / "raw"
DATA_CLEAN = ROOT / "data" / "clean"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
TABLES = OUTPUTS / "tables"
DASHBOARD = OUTPUTS / "dashboard.html"

for directory in (DATA_RAW, DATA_CLEAN, FIGURES, TABLES):
    directory.mkdir(parents=True, exist_ok=True)

if FIGURES.exists():
    for old_img in FIGURES.glob("*.png"):
        old_img.unlink()  

SOURCE_URL = "https://public.tableau.com/app/sample-data/sample_-_superstore.xls"
SOURCE_FILE = DATA_RAW / "sample_-_superstore.xls"
CUTOFF = pd.Timestamp("2026-09-30")
RANDOM_SEED = 20261027

plt.rcParams.update(
    {
        "font.family": ["Times New Roman", "SimHei", "Microsoft YaHei", "Arial"],
        "axes.unicode_minus": False,
        "figure.dpi": 140,
        "savefig.dpi": 300,
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlepad": 10,
        "axes.labelsize": 10.5,
        "axes.labelcolor": "#263238",
        "axes.edgecolor": "#455A64",
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.axisbelow": True,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.color": "#455A64",
        "ytick.color": "#455A64",
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "axes.grid": True,
        "grid.color": "#CFD8DC",
        "grid.alpha": 0.35,
        "grid.linestyle": "-",
        "grid.linewidth": 0.5,
        "legend.frameon": False,
        "mathtext.fontset": "stix",
    }
)

COLORS = {
    "navy": "#174A7E",
    "blue": "#3C7DBF",
    "teal": "#2A9D8F",
    "coral": "#D95F59",
    "gold": "#E9C46A",
    "gray": "#6C757D",
}

CHART_INDEX: list[dict[str, str]] = []

FIGURE_COUNTER = count(1)


def stamp_figure_number(fig: plt.Figure) -> None:
    """按生成顺序为论文图编号（图 1、图 2 …），写入面板标题或总标题。"""
    no = next(FIGURE_COUNTER)
    suptitle = getattr(fig, "_suptitle", None)
    if suptitle is not None and suptitle.get_text():
        fig.suptitle(f"{suptitle.get_text()}", fontweight="bold")
        return
    titled_axes = [ax for ax in fig.axes if ax.get_title()]
    if len(titled_axes) == 1:
        titled_axes[0].set_title(f"{titled_axes[0].get_title()}")

def ensure_dependencies() -> None:
    required = {
        "pandas": "pandas",
        "numpy": "numpy",
        "matplotlib": "matplotlib",
        "sklearn": "scikit-learn",
        "statsmodels": "statsmodels",
            "xlrd": "xlrd",
    }
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        packages = " ".join(missing)
        raise SystemExit(
            "缺少依赖。请先在 PyCharm 终端执行：\n"
            f"python -m pip install {packages}"
        )

def ensure_source_file() -> Path:
    if SOURCE_FILE.exists() and SOURCE_FILE.stat().st_size > 1_000_000:
        return SOURCE_FILE
    print(f"下载数据：{SOURCE_URL}")
    urllib.request.urlretrieve(SOURCE_URL, SOURCE_FILE)
    if SOURCE_FILE.stat().st_size < 1_000_000:
        raise RuntimeError("数据文件下载不完整，请检查网络后重试。")
    return SOURCE_FILE

def read_source() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source = ensure_source_file()
    orders = pd.read_excel(
        source,
        sheet_name="Orders",
        parse_dates=["Order Date", "Ship Date"],
    )
    returns = pd.read_excel(source, sheet_name="Returns")
    people = pd.read_excel(source, sheet_name="People")
    return orders, returns, people

def clean_data(
    orders_raw: pd.DataFrame,
    returns_raw: pd.DataFrame,
    people: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    orders = orders_raw.copy()
    returns = returns_raw.copy()
    people = people.copy()

    raw_rows = len(orders)
    raw_duplicates = int(orders.duplicated().sum())
    orders = orders.drop_duplicates().copy()
    orders["Order Date"] = pd.to_datetime(orders["Order Date"], errors="coerce")
    orders["Ship Date"] = pd.to_datetime(orders["Ship Date"], errors="coerce")
    future_rows = int((orders["Order Date"] > CUTOFF).sum())
    orders = orders[
        (orders["Order Date"] >= pd.Timestamp("2023-01-01"))
        & (orders["Order Date"] <= CUTOFF)
    ].copy()
    invalid_ship = int((orders["Ship Date"] < orders["Order Date"]).sum())
    orders = orders[orders["Ship Date"] >= orders["Order Date"]].copy()
    orders["Sales"] = pd.to_numeric(orders["Sales"], errors="coerce")
    orders["Profit"] = pd.to_numeric(orders["Profit"], errors="coerce")
    orders["Quantity"] = pd.to_numeric(orders["Quantity"], errors="coerce")
    orders["Discount"] = pd.to_numeric(orders["Discount"], errors="coerce")
    orders = orders[
        orders["Sales"].notna()
        & orders["Profit"].notna()
        & (orders["Sales"] > 0)
        & (orders["Quantity"] > 0)
        & orders["Discount"].between(0, 1)
    ].copy()

    returns["Returned"] = returns["Returned"].eq("Yes").astype(int)
    returns = (
        returns.groupby("Order ID", as_index=False)
        .agg(Returned=("Returned", "max"))
        .copy()
    )
    orders = orders.merge(returns, on="Order ID", how="left")
    orders["Returned"] = orders["Returned"].fillna(0).astype(int)
    orders = orders.merge(people, on="Region", how="left")

    orders["Ship Days"] = (orders["Ship Date"] - orders["Order Date"]).dt.days
    orders["Profit Margin"] = orders["Profit"] / orders["Sales"]
    orders["Loss"] = (orders["Profit"] < 0).astype(int)
    orders["Year"] = orders["Order Date"].dt.year
    orders["Month"] = orders["Order Date"].dt.to_period("M")
    orders["Quarter"] = orders["Order Date"].dt.to_period("Q")
    orders["YearMonth"] = orders["Order Date"].dt.strftime("%Y-%m")

    sales_q1, sales_q3 = orders["Sales"].quantile([0.25, 0.75])
    sales_upper = float(sales_q3 + 1.5 * (sales_q3 - sales_q1))
    profit_q1, profit_q3 = orders["Profit"].quantile([0.25, 0.75])
    profit_lower = float(profit_q1 - 1.5 * (profit_q3 - profit_q1))
    profit_upper = float(profit_q3 + 1.5 * (profit_q3 - profit_q1))

    audit = {
        "raw_rows": raw_rows,
        "raw_duplicates": raw_duplicates,
        "future_rows_removed": future_rows,
        "invalid_ship_rows_removed": invalid_ship,
        "clean_rows": int(len(orders)),
        "orders": int(orders["Order ID"].nunique()),
        "customers": int(orders["Customer ID"].nunique()),
        "products": int(orders["Product ID"].nunique()),
        "date_min": str(orders["Order Date"].min().date()),
        "date_max": str(orders["Order Date"].max().date()),
        "sales_outlier_upper": sales_upper,
        "sales_outlier_rows": int((orders["Sales"] > sales_upper).sum()),
        "profit_outlier_lower": profit_lower,
        "profit_outlier_upper": profit_upper,
        "negative_profit_rows": int((orders["Profit"] < 0).sum()),
        "negative_profit_share": float((orders["Profit"] < 0).mean()),
        "missing_values": int(orders.isna().sum().sum()),
    }
    return orders, audit

def calculate_analytics(orders: pd.DataFrame) -> dict[str, object]:
    total_sales = float(orders["Sales"].sum())
    total_profit = float(orders["Profit"].sum())
    order_count = int(orders["Order ID"].nunique())
    customer_count = int(orders["Customer ID"].nunique())
    returned_orders = int(orders.loc[orders["Returned"] == 1, "Order ID"].nunique())

    kpi = {
        "sales": total_sales,
        "profit": total_profit,
        "margin": total_profit / total_sales,
        "orders": order_count,
        "customers": customer_count,
        "avg_order_value": total_sales / order_count,
        "return_rate": returned_orders / order_count,
        "loss_row_rate": float((orders["Profit"] < 0).mean()),
        "avg_discount": float(orders["Discount"].mean()),
        "avg_ship_days": float(orders["Ship Days"].mean()),
    }

    monthly = (
        orders.set_index("Order Date")
        .resample("MS")
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Orders=("Order ID", "nunique"),
            Returns=("Returned", "sum"),
        )
    )
    monthly["Margin"] = monthly["Profit"] / monthly["Sales"]
    monthly["ReturnRate"] = monthly["Returns"] / monthly["Orders"]
    monthly = monthly.reset_index().rename(columns={"Order Date": "MonthDate"})

    category_summary = (
        orders.groupby("Category", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Quantity=("Quantity", "sum"),
            Orders=("Order ID", "nunique"),
            ReturnRate=("Returned", "mean"),
        )
        .copy()
    )
    category_summary["Margin"] = category_summary["Profit"] / category_summary["Sales"]
    category_summary = category_summary.sort_values("Sales", ascending=False)

    subcategory_summary = (
        orders.groupby("Sub-Category", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Quantity=("Quantity", "sum"),
            Orders=("Order ID", "nunique"),
            ReturnRate=("Returned", "mean"),
        )
        .copy()
    )
    subcategory_summary["Margin"] = (
        subcategory_summary["Profit"] / subcategory_summary["Sales"]
    )
    subcategory_summary = subcategory_summary.sort_values("Sales", ascending=False)
    subcategory_summary["Share"] = (
        subcategory_summary["Sales"] / subcategory_summary["Sales"].sum()
    )
    subcategory_summary["Cumulative"] = subcategory_summary["Share"].cumsum()
    subcategory_summary["ABC"] = np.select(
        [subcategory_summary["Cumulative"] <= 0.80, subcategory_summary["Cumulative"] <= 0.95],
        ["A", "B"],
        default="C",
    )

    state_summary = (
        orders.groupby("State/Province", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Orders=("Order ID", "nunique"),
            ReturnRate=("Returned", "mean"),
        )
        .copy()
    )
    state_summary["Margin"] = state_summary["Profit"] / state_summary["Sales"]
    state_summary = state_summary.sort_values("Sales", ascending=False)

    region_summary = (
        orders.groupby("Region", as_index=False)
        .agg(
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Orders=("Order ID", "nunique"),
            ReturnRate=("Returned", "mean"),
        )
        .copy()
    )
    region_summary["Margin"] = region_summary["Profit"] / region_summary["Sales"]

    discount_bins = pd.cut(
        orders["Discount"],
        bins=[-0.001, 0.001, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8],
        labels=["0%", "1-10%", "11-20%", "21-30%", "31-40%", "41-50%", ">50%"],
    )
    discount_summary = (
        orders.assign(DiscountBand=discount_bins)
        .groupby("DiscountBand", observed=True, as_index=False)
        .agg(
            Rows=("Row ID", "count"),
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
            AvgProfit=("Profit", "mean"),
            LossRate=("Loss", "mean"),
        )
    )
    discount_summary["Margin"] = discount_summary["Profit"] / discount_summary["Sales"]

    snapshot = orders["Order Date"].max() + pd.Timedelta(days=1)
    rfm = (
        orders.groupby("Customer ID", as_index=False)
        .agg(
            LastPurchase=("Order Date", "max"),
            Frequency=("Order ID", "nunique"),
            Monetary=("Sales", "sum"),
            Profit=("Profit", "sum"),
            Segment=("Segment", "last"),
            Region=("Region", "last"),
        )
        .copy()
    )
    rfm["Recency"] = (snapshot - rfm["LastPurchase"]).dt.days
    monetary_median = float(rfm["Monetary"].median())
    rfm["RHigh"] = rfm["Recency"] <= 180
    rfm["FHigh"] = rfm["Frequency"] >= 3
    rfm["MHigh"] = rfm["Monetary"] > monetary_median
    rfm["RFM"] = rfm.apply(classify_rfm, axis=1)

    segment_order = [
        "重要价值客户",
        "重要保持客户",
        "重要发展客户",
        "重要挽留客户",
        "一般价值客户",
        "一般保持客户",
        "一般发展客户",
        "一般挽留客户",
    ]
    rfm_summary = (
        rfm.groupby("RFM", as_index=False)
        .agg(
            Customers=("Customer ID", "nunique"),
            Sales=("Monetary", "sum"),
            Profit=("Profit", "sum"),
            AvgFrequency=("Frequency", "mean"),
            AvgRecency=("Recency", "mean"),
        )
    )
    rfm_summary["CustomerShare"] = rfm_summary["Customers"] / len(rfm)
    rfm_summary["SalesShare"] = rfm_summary["Sales"] / rfm_summary["Sales"].sum()
    rfm_summary["ProfitShare"] = rfm_summary["Profit"] / rfm_summary["Profit"].sum()
    rfm_summary["RFM"] = pd.Categorical(
        rfm_summary["RFM"], categories=segment_order, ordered=True
    )
    rfm_summary = rfm_summary.sort_values("RFM").reset_index(drop=True)

    first_month = (
        orders.groupby("Customer ID")["Month"].min().rename("Cohort").reset_index()
    )
    customer_months = (
        orders[["Customer ID", "Month"]]
        .drop_duplicates()
        .merge(first_month, on="Customer ID", how="left")
    )
    customer_months["CohortIndex"] = (
        (customer_months["Month"].dt.year - customer_months["Cohort"].dt.year) * 12
        + customer_months["Month"].dt.month
        - customer_months["Cohort"].dt.month
    )
    cohort_sizes = first_month.groupby("Cohort")["Customer ID"].nunique()
    cohort_activity = (
        customer_months.groupby(["Cohort", "CohortIndex"])["Customer ID"]
        .nunique()
        .rename("Active")
        .reset_index()
    )
    cohort_activity["Size"] = cohort_activity["Cohort"].map(cohort_sizes)
    cohort_activity["Retention"] = cohort_activity["Active"] / cohort_activity["Size"]
    cohort_activity = cohort_activity[
        cohort_activity["Cohort"].between(
            pd.Period("2023-01", "M"), pd.Period("2025-06", "M")
        )
    ]
    cohort_matrix = cohort_activity.pivot(
        index="Cohort", columns="CohortIndex", values="Retention"
    )
    cohort_matrix = cohort_matrix.loc[:, 0:12]

    current_ytd = (
        orders[
            (orders["Year"] == 2026)
            & (orders["Order Date"].dt.month <= 9)
        ]
        .groupby("Sub-Category")["Sales"]
        .sum()
    )
    previous_ytd = (
        orders[
            (orders["Year"] == 2025)
            & (orders["Order Date"].dt.month <= 9)
        ]
        .groupby("Sub-Category")["Sales"]
        .sum()
    )
    boston = subcategory_summary.set_index("Sub-Category")[
        ["Sales", "Profit", "Margin", "Share"]
    ].copy()
    boston["Growth"] = (current_ytd / previous_ytd - 1).replace([np.inf, -np.inf], np.nan)
    boston = boston.dropna(subset=["Growth"]).copy()
    boston["GrowthMedian"] = boston["Growth"].median()
    boston["ShareMedian"] = boston["Share"].median()
    boston["Quadrant"] = np.select(
        [
            (boston["Share"] >= boston["ShareMedian"])
            & (boston["Growth"] >= boston["GrowthMedian"]),
            (boston["Share"] >= boston["ShareMedian"])
            & (boston["Growth"] < boston["GrowthMedian"]),
            (boston["Share"] < boston["ShareMedian"])
            & (boston["Growth"] >= boston["GrowthMedian"]),
        ],
        ["明星品类", "现金牛品类", "问题品类"],
        default="瘦狗品类",
    )

    regression_features = [
        "Discount",
        "Discount2",
        "Quantity",
        "Ship Days",
        "Category",
        "Sub-Category",
        "Segment",
        "Ship Mode",
        "Region",
    ]
    model_data = orders.copy()
    model_data["Discount2"] = model_data["Discount"] ** 2
    X = model_data[regression_features]
    y = model_data["Loss"]
    numeric = ["Discount", "Discount2", "Quantity", "Ship Days"]
    categorical = [column for column in regression_features if column not in numeric]
    preprocessor = ColumnTransformer(
        [
            ("num", StandardScaler(), numeric),
            ("cat", OneHotEncoder(handle_unknown="ignore", drop="first"), categorical),
        ]
    )
    classifier = Pipeline(
        [
            ("preprocess", preprocessor),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced", max_iter=3000, random_state=RANDOM_SEED
                ),
            ),
        ]
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=RANDOM_SEED, stratify=y
    )
    classifier.fit(X_train, y_train)
    probabilities = classifier.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    fpr, tpr, _ = roc_curve(y_test, probabilities)
    classification_metrics = {
        "auc": float(roc_auc_score(y_test, probabilities)),
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(precision_score(y_test, predictions)),
        "recall": float(recall_score(y_test, predictions)),
        "f1": float(f1_score(y_test, predictions)),
        "confusion_matrix": confusion_matrix(y_test, predictions).tolist(),
    }
    transformed_names = classifier.named_steps["preprocess"].get_feature_names_out()
    coefficients = pd.DataFrame(
        {
            "Feature": transformed_names,
            "Coefficient": classifier.named_steps["model"].coef_[0],
        }
    ).sort_values("Coefficient", key=np.abs, ascending=False)

    sales_series = monthly.set_index("MonthDate")["Sales"].astype(float)
    backtest_rows = []
    backtest_predictions = []
    for train_end in (27, 33, 39):
        train = sales_series.iloc[:train_end]
        test = sales_series.iloc[train_end:train_end + 6]
        model = ExponentialSmoothing(
            train,
            trend="add",
            damped_trend=True,
            seasonal="add",
            seasonal_periods=12,
            initialization_method="estimated",
        )
        result = model.fit(optimized=True)
        predicted = result.forecast(6)
        rmse = float(np.sqrt(mean_squared_error(test, predicted)))
        mae = float(mean_absolute_error(test, predicted))
        mape = float(np.mean(np.abs((test - predicted) / test)) * 100)
        backtest_rows.append(
            {
                "train_end": str(train.index.max().date()),
                "test_start": str(test.index.min().date()),
                "test_end": str(test.index.max().date()),
                "rmse": rmse,
                "mae": mae,
                "mape": mape,
            }
        )
        backtest_predictions.append(
            pd.DataFrame(
                {
                    "Date": test.index,
                    "Actual": test.values,
                    "Forecast": predicted.values,
                }
            )
        )
    backtest_frame = pd.concat(backtest_predictions, ignore_index=True)
    forecast_rmse = float(
        np.sqrt(
            mean_squared_error(backtest_frame["Actual"], backtest_frame["Forecast"])
        )
    )
    forecast_mae = float(
        mean_absolute_error(backtest_frame["Actual"], backtest_frame["Forecast"])
    )
    forecast_mape = float(
        np.mean(
            np.abs(
                (backtest_frame["Actual"] - backtest_frame["Forecast"])
                / backtest_frame["Actual"]
            )
        )
        * 100
    )

    full_model = ExponentialSmoothing(
        sales_series,
        trend="add",
        damped_trend=True,
        seasonal="add",
        seasonal_periods=12,
        initialization_method="estimated",
    )
    full_result = full_model.fit(optimized=True)
    future_mean = full_result.forecast(6).clip(lower=0)
    np.random.seed(RANDOM_SEED)
    simulations = full_result.simulate(
        nsimulations=6, repetitions=1200, error="add"
    ).clip(lower=0)
    future_lower = simulations.quantile(0.025, axis=1).to_numpy()
    future_upper = simulations.quantile(0.975, axis=1).to_numpy()
    future_dates = pd.date_range(
        sales_series.index.max() + pd.offsets.MonthBegin(1), periods=6, freq="MS"
    )
    future_frame = pd.DataFrame(
        {
            "Date": future_dates,
            "Forecast": future_mean.values,
            "Lower95": future_lower,
            "Upper95": future_upper,
        }
    )

    return {
        "kpi": kpi,
        "monthly": monthly,
        "category": category_summary,
        "subcategory": subcategory_summary,
        "state": state_summary,
        "region": region_summary,
        "discount": discount_summary,
        "rfm": rfm,
        "rfm_summary": rfm_summary,
        "rfm_thresholds": {
            "recency": 180,
            "frequency": 3,
            "monetary": monetary_median,
        },
        "cohort_matrix": cohort_matrix,
        "boston": boston,
        "classification": classification_metrics,
        "coefficients": coefficients,
        "roc": pd.DataFrame({"fpr": fpr, "tpr": tpr}),
        "forecast": {
            "backtest": backtest_rows,
            "backtest_frame": backtest_frame,
            "future": future_frame,
            "rmse": forecast_rmse,
            "mae": forecast_mae,
            "mape": forecast_mape,
        },
    }


def classify_rfm(row: pd.Series) -> str:
    if row["RHigh"] and row["FHigh"] and row["MHigh"]:
        return "重要价值客户"
    if not row["RHigh"] and row["FHigh"] and row["MHigh"]:
        return "重要保持客户"
    if row["RHigh"] and not row["FHigh"] and row["MHigh"]:
        return "重要发展客户"
    if not row["RHigh"] and not row["FHigh"] and row["MHigh"]:
        return "重要挽留客户"
    if row["RHigh"] and row["FHigh"] and not row["MHigh"]:
        return "一般价值客户"
    if not row["RHigh"] and row["FHigh"] and not row["MHigh"]:
        return "一般保持客户"
    if row["RHigh"] and not row["FHigh"] and not row["MHigh"]:
        return "一般发展客户"
    return "一般挽留客户"


def save_figure(
    fig: plt.Figure,
    filename: str,
    title: str,
    chart_type: str,
    template_no: str = "",
) -> None:
    stamp_figure_number(fig)
    fig.savefig(FIGURES / filename, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    CHART_INDEX.append(
        {
            "filename": filename,
            "title": title,
            "chart_type": chart_type,
            "template_no": template_no,
        }
    )


def base_figure(width: float = 8.8, height: float = 5.0) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(width, height))
    return fig, ax


def clean_axes(ax: plt.Axes) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.18, linestyle="--")
    ax.grid(axis="x", visible=False)


def axis_percent(ax: plt.Axes, axis: str = "y") -> None:
    from matplotlib.ticker import PercentFormatter

    if axis == "y":
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    else:
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))



def build_selected_template_charts(
    orders: pd.DataFrame, analytics: dict[str, object]
) -> None:
    """Build 18 business-focused template charts in a restrained journal style."""
    monthly: pd.DataFrame = analytics["monthly"]
    category: pd.DataFrame = analytics["category"]
    subcategory: pd.DataFrame = analytics["subcategory"]
    states: pd.DataFrame = analytics["state"]
    regions: pd.DataFrame = analytics["region"]
    kpi: dict[str, float] = analytics["kpi"]

    palette = ["#0B3C5D", "#2A9D8F", "#E76F51", "#E9C46A", "#6C757D", "#8AB17D"]
    nature_rc = {
        "font.size": 8.5,
        "axes.titlesize": 11,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 7.5,
        "axes.linewidth": 0.7,
        "grid.linewidth": 0.5,
        "grid.alpha": 0.8,
        "savefig.dpi": 300,
    }

    def setup_axis(ax: plt.Axes, ylabel: str = "", xlabel: str = "") -> None:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#455A64")
        ax.spines["bottom"].set_color("#455A64")
        ax.tick_params(colors="#455A64", labelcolor="#37474F", length=3, width=0.7)
        ax.grid(axis="y", color="#E3EAEE", linestyle="-", linewidth=0.55)
        ax.grid(axis="x", visible=False)
        ax.set_axisbelow(True)
        if ylabel:
            ax.set_ylabel(ylabel)
        if xlabel:
            ax.set_xlabel(xlabel)

    def panel_header(ax: plt.Axes, title: str) -> None:
        ax.set_title(title, loc="center", fontweight="bold", pad=8)

    def source_note(fig: plt.Figure) -> None:
        fig.text(
            0.01,
            0.01,
            "数据来源：Tableau Superstore 示例数据（2023-01至2026-09）",
            fontsize=5.8,
            color="#6C757D",
            ha="left",
            va="bottom",
        )

    def save_nature(
        fig: plt.Figure,
        filename: str,
        title: str,
        chart_type: str,
    ) -> None:
        stamp_figure_number(fig)
        source_note(fig)
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        fig.savefig(FIGURES / filename, bbox_inches="tight", facecolor="white", dpi=300)
        plt.close(fig)
        CHART_INDEX.append(
            {
                "filename": filename,
                "title": title,
                "chart_type": chart_type,
                "template_no": filename.split("_")[0].replace("n", ""),
            }
        )

    with plt.rc_context(nature_rc):
        # n01 Horizontal gradient bars.
        fig, ax = plt.subplots(figsize=(7.2, 4.0))
        plot = regions.sort_values("Sales", ascending=True)
        cmap = LinearSegmentedColormap.from_list(
            "journal_blue", ["#B6D5E3", "#0B3C5D"]
        )
        colors = cmap(np.linspace(0.25, 1, len(plot)))
        bars = ax.barh(plot["Region"], plot["Sales"] / 1000, color=colors, height=0.56)
        for bar, value in zip(bars, plot["Sales"] / 1000):
            ax.text(
                value + 5,
                bar.get_y() + bar.get_height() / 2,
                f"{value:,.0f}",
                va="center",
                fontsize=7.2,
            )
        setup_axis(ax, xlabel="销售额（千美元）")
        panel_header(ax, "区域销售规模")
        save_nature(fig, "n01_regional_sales.png", "区域销售规模", "渐变柱形图")

        # n02 Bar with mean reference.
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        plot = states.head(8).sort_values("Sales")
        mean_value = plot["Sales"].mean() / 1000
        bars = ax.barh(plot["State/Province"], plot["Sales"] / 1000, color="#2A9D8F", height=0.56)
        ax.axvline(mean_value, color="#E76F51", linestyle="--", linewidth=1.0)
        ax.text(mean_value, len(plot) - 0.25, f"均值 {mean_value:,.0f}", color="#E76F51", fontsize=7, ha="center")
        for bar, value in zip(bars, plot["Sales"] / 1000):
            ax.text(value + 4, bar.get_y() + bar.get_height() / 2, f"{value:,.0f}", va="center", fontsize=6.8)
        setup_axis(ax, xlabel="销售额（千美元）")
        panel_header(ax, "重点州销售额与均值")
        save_nature(fig, "n02_state_mean.png", "重点州销售额与均值", "带均值柱形图")

        # n03 Annotated subcategory bars.
        fig, ax = plt.subplots(figsize=(6.9, 4.5))
        plot = subcategory.head(10).sort_values("Sales")
        bars = ax.barh(plot["Sub-Category"], plot["Sales"] / 1000, color="#0B3C5D", height=0.58)
        for bar, value, share in zip(bars, plot["Sales"] / 1000, plot["Share"]):
            # 同时标注绝对值与占比
            ax.text(
                bar.get_width() + 3,
                bar.get_y() + bar.get_height() / 2,
                f"{value:,.0f}  |  {share:.1%}",
                va="center",
                fontsize=6.8,
                color="#37474F",
                fontweight="bold" if share > 0.1 else "normal"
            )
        setup_axis(ax, xlabel="销售额（千美元）")
        panel_header(ax, "前十品类销售贡献")
        save_nature(fig, "n03_top_subcategories.png", "前十品类销售贡献", "标注柱形图")

        # n04 Stacked category-region bars.
        pivot = (
            orders.pivot_table(
                index="Region", columns="Category", values="Sales", aggfunc="sum", fill_value=0,
            ) / 1000
        )
        fig, ax = plt.subplots(figsize=(7.0, 4.1))
        bottom = np.zeros(len(pivot))
        category_colors = {"Technology": "#0B3C5D", "Furniture": "#E76F51", "Office Supplies": "#2A9D8F"}
        for name in ["Technology", "Furniture", "Office Supplies"]:
            values = pivot[name].to_numpy()
            bars = ax.bar(pivot.index, values, bottom=bottom, color=category_colors[name], label=name, width=0.58)
            # 内部标注百分比（仅当色块足够大时）
            for i, v in enumerate(values):
                total = pivot.iloc[i].sum()
                if total > 0 and (v / total) > 0.12:
                    ax.text(pivot.index[i], bottom[i] + v / 2, f"{v/total:.0%}",
                            ha="center", va="center", fontsize=6.5, color="white", fontweight="bold")
            bottom += values
        # 顶部标注总销售额
        for i, total in enumerate(bottom):
            ax.text(pivot.index[i], total + 2, f"{total:,.0f}", ha="center", va="bottom", fontsize=7, fontweight="bold")
            
        setup_axis(ax, ylabel="销售额（千美元）")
        ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, 1.02))
        panel_header(ax, "区域与品类结构")
        save_nature(fig, "n04_stacked_structure.png", "区域与品类结构", "层叠柱形图")

        # n05 Butterfly chart (center labels + aligned percent columns).
        pivot = (
            orders.pivot_table(
                index="Category", columns="Segment", values="Sales", aggfunc="sum", fill_value=0
            ) / 1000
        )
        for col in ["Consumer", "Corporate"]:
            if col not in pivot.columns:
                pivot[col] = 0.0
        pivot = pivot[["Consumer", "Corporate"]]
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

        # 各客户类型内部的花费占比（每侧合计100%）
        left_share = pivot["Consumer"] / pivot["Consumer"].sum()
        right_share = pivot["Corporate"] / pivot["Corporate"].sum()

        fig, ax = plt.subplots(figsize=(7.6, 3.8))
        n = len(pivot)
        ys = (n - 1) - np.arange(n)          # 第一行在最上方
        gap = 0.22                           # 中间类别标签留白
        scale = max(left_share.max(), right_share.max())   # 两侧共用比例尺
        lw = (left_share / scale).to_numpy()
        rw = (right_share / scale).to_numpy()

        # 左：Consumer 向左延伸；右：Corporate 向右延伸（保持原配色）
        ax.barh(ys, lw, left=-(gap + lw), height=0.55, color="#0B3C5D")
        ax.barh(ys, rw, left=gap, height=0.55, color="#E76F51")

        # 中间类别标签
        for y, name in zip(ys, pivot.index):
            ax.text(0, y, name, ha="center", va="center",
                    fontsize=8.5, color="#37474F", fontweight="bold")

        # 两侧百分比：固定列对齐（左列右对齐、右列左对齐）
        for y, lv, rv in zip(ys, left_share, right_share):
            ax.text(-1.26, y, f"{lv:.0%}", ha="right", va="center", fontsize=8.5, color="#0B3C5D")
            ax.text(1.26, y, f"{rv:.0%}", ha="left", va="center", fontsize=8.5, color="#E76F51")

        # 彩色列标题替代图例
        ax.text(-1.26, n - 0.32, "Consumer", ha="right", va="center",
                fontsize=8.5, color="#0B3C5D", fontweight="bold")
        ax.text(1.26, n - 0.32, "Corporate", ha="left", va="center",
                fontsize=8.5, color="#E76F51", fontweight="bold")

        ax.set_xlim(-1.6, 1.6)
        ax.set_ylim(-0.8, n - 0.05)
        ax.axis("off")
        panel_header(ax, "客户类型的品类偏好")
        save_nature(fig, "n05_customer_butterfly.png", "客户类型的品类偏好", "蝴蝶图")

        # n06 Quarterly comparison (true YoY: same quarter paired).
        tmp = orders[orders["Year"].isin([2025, 2026])].copy()
        tmp["Q"] = tmp["Order Date"].dt.quarter
        compare = (
            tmp.groupby(["Q", "Year"])["Sales"].sum().unstack("Year") / 1000
        )
        compare = compare.reindex(columns=[2025, 2026]).fillna(0)

        fig, ax = plt.subplots(figsize=(7.0, 3.9))
        x = np.arange(len(compare))
        ax.bar(x - 0.18, compare[2025], width=0.34, color="#B6D5E3", label="2025")
        ax.bar(x + 0.18, compare[2026], width=0.34, color="#0B3C5D", label="2026")

        # 数值标注：仅 >0 时绘制；同比增速：仅两年均有数据时绘制
        for i, q in enumerate(compare.index):
            v25, v26 = compare.loc[q, 2025], compare.loc[q, 2026]
            if v25 > 0:
                ax.text(i - 0.18, v25 + 2, f"{v25:.0f}", ha="center", va="bottom",
                        fontsize=6.5, color="#455A64")
            if v26 > 0:
                ax.text(i + 0.18, v26 + 2, f"{v26:.0f}", ha="center", va="bottom",
                        fontsize=6.5, color="#0B3C5D", fontweight="bold")
            if v25 > 0 and v26 > 0:
                growth = (v26 / v25 - 1) * 100
                color = "#2A9D8F" if growth >= 0 else "#E76F51"
                ax.text(i, max(v25, v26) + 10, f"{growth:+.1f}%", ha="center", va="bottom",
                        fontsize=7, color=color, fontweight="bold")

        ax.set_xticks(x, [f"Q{q}" for q in compare.index])
        setup_axis(ax, ylabel="销售额（千美元）")
        ax.legend(frameon=False, ncol=2, loc="upper left")
        panel_header(ax, "季度销售同比")
        save_nature(fig, "n06_quarter_comparison.png", "季度销售同比", "对比柱形图")
    
        # n07 Gantt chart.
        sample = orders.sort_values("Order Date").iloc[10:22].copy()
        fig, ax = plt.subplots(figsize=(7.2, 4.0))
        for index, row in enumerate(sample.itertuples()):
            start = mdates.date2num(row._3)
            end = mdates.date2num(row._4)
            days = (row._4 - row._3).days
            ax.plot([start, end], [index, index], color="#2A9D8F", linewidth=5.5, solid_capstyle="round")
            ax.scatter([start, end], [index, index], s=14, color=["#0B3C5D", "#E76F51"], zorder=3)
            # 增加履约天数标注
            ax.text((start + end) / 2, index + 0.18, f"{days}天", ha="center", va="bottom", fontsize=6.5, color="#37474F", fontweight="bold")
            
        ax.set_yticks(range(len(sample)), [f"O{index + 1:02d}" for index in range(len(sample))])
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.tick_params(axis="x", rotation=35)
        setup_axis(ax, xlabel="2023年订单日期")
        panel_header(ax, "订单履约周期")
        save_nature(fig, "n07_order_timeline.png", "订单履约周期", "甘特图")

        # n08 Smoothed sales line.
        fig, ax = plt.subplots(figsize=(7.4, 3.9))
        smooth = monthly["Sales"].rolling(3, center=True, min_periods=1).mean()
        ax.plot(monthly["MonthDate"], monthly["Sales"] / 1000, color="#B6D5E3", linewidth=1.0)
        ax.plot(monthly["MonthDate"], smooth / 1000, color="#0B3C5D", linewidth=1.8, label="3个月平滑")
        
        # 极值与终点标注
        for idx in [monthly["Sales"].idxmax(), monthly["Sales"].idxmin(), monthly.index[-1]]:
            val = monthly.loc[idx, "Sales"] / 1000
            date = monthly.loc[idx, "MonthDate"]
            ax.annotate(f"{val:,.0f}", (date, val), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=6.8, color="#0B3C5D", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))
                        
        ax.tick_params(axis="x", rotation=35)
        setup_axis(ax, ylabel="销售额（千美元）")
        ax.legend(frameon=False, loc="upper left")
        panel_header(ax, "月度销售趋势")
        save_nature(fig, "n08_smoothed_sales.png", "月度销售趋势", "平滑折线图")

        # n09 Profit-margin diamonds.
        fig, ax = plt.subplots(figsize=(7.4, 3.9))
        ax.plot(monthly["MonthDate"], monthly["Margin"] * 100, color="#0B3C5D", linewidth=1.0,
                marker="D", markersize=3.2, markerfacecolor="#E76F51", markeredgewidth=0)
        ax.axhline(kpi["margin"] * 100, color="#6C757D", linestyle="--", linewidth=0.9)
        ax.text(monthly["MonthDate"].iloc[1], kpi["margin"] * 100 + 0.7, "整体利润率", color="#6C757D", fontsize=6.8)
        
        # 极值与终点标注
        for idx in [monthly["Margin"].idxmax(), monthly["Margin"].idxmin(), monthly.index[-1]]:
            val = monthly.loc[idx, "Margin"] * 100
            date = monthly.loc[idx, "MonthDate"]
            ax.annotate(f"{val:.1f}%", (date, val), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=6.8, color="#E76F51", fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))
                        
        ax.tick_params(axis="x", rotation=35)
        setup_axis(ax, ylabel="利润率（%）")
        panel_header(ax, "月度利润率")
        save_nature(fig, "n09_margin_trend.png", "月度利润率", "菱形走势图")

        # n10 Sales and profit comparison.
        fig, ax = plt.subplots(figsize=(7.4, 3.9))
        ax.plot(monthly["MonthDate"], monthly["Sales"] / 1000, color="#0B3C5D", linewidth=1.6, label="销售额")
        ax.set_ylabel("销售额（千美元）")
        ax2 = ax.twinx()
        ax2.plot(monthly["MonthDate"], monthly["Profit"] / 1000, color="#E76F51", linewidth=1.4, label="利润")
        ax2.set_ylabel("利润（千美元）")
        ax2.grid(False)
        
        # 终点数值高亮标注
        last_date = monthly["MonthDate"].iloc[-1]
        ax.annotate(f"{monthly['Sales'].iloc[-1]/1000:,.0f}", (last_date, monthly["Sales"].iloc[-1]/1000),
                    textcoords="offset points", xytext=(8, 0), ha="left", va="center", fontsize=7, color="#0B3C5D", fontweight="bold")
        ax2.annotate(f"{monthly['Profit'].iloc[-1]/1000:,.0f}", (last_date, monthly["Profit"].iloc[-1]/1000),
                     textcoords="offset points", xytext=(8, 0), ha="left", va="center", fontsize=7, color="#E76F51", fontweight="bold")
                     
        ax.tick_params(axis="x", rotation=35)
        setup_axis(ax)
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, frameon=False, loc="upper left", ncol=2)
        panel_header(ax, "销售额与利润走势")
        save_nature(fig, "n10_sales_profit.png", "销售额与利润走势", "对比折线图")

        # n11 Runway chart.
        fig, ax = plt.subplots(figsize=(7.2, 3.8))
        plot = regions.sort_values("Sales", ascending=True).reset_index(drop=True)
        normalized = plot["Sales"] / plot["Sales"].max()
        y = np.arange(len(plot))
        bar_height = 0.42                      # 所有跑道统一粗细

        # 背景跑道（满格 100%）
        ax.barh(y, 1.0, height=bar_height, color="#ECF0F2", edgecolor="none")
        # 前景实际值
        ax.barh(y, normalized, height=bar_height, color="#0B3C5D", edgecolor="none")

        # 百分比标注
        for index, value in enumerate(normalized):
            ax.text(min(value + 0.02, 1.02), index, f"{value:.0%}",
                    va="center", fontsize=7)

        ax.set_yticks(y, plot["Region"])
        ax.set_ylim(-0.6, len(plot) - 0.4)     # 关键：显式留边，防止首末条被裁切
        ax.set_xlim(0, 1.1)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0%", "25%", "50%", "75%", "100%"])
        setup_axis(ax, xlabel="相对最大区域销售额")
        ax.grid(False)
        panel_header(ax, "区域销售规模指数")
        save_nature(fig, "n11_region_runway.png", "区域销售规模指数", "跑道图")

        # n12 Nightingale rose (centered, symmetric margins).
        plot = subcategory.head(8).sort_values("Sales", ascending=False)
        fig = plt.figure(figsize=(6.0, 5.6))
        ax = fig.add_axes([0.12, 0.10, 0.76, 0.76], projection="polar")
        angles = np.linspace(0, 2 * np.pi, len(plot), endpoint=False)
        radii = plot["Sales"] / plot["Sales"].max()
        ax.bar(angles, radii, width=0.72, bottom=0.08,
               color=plt.cm.Blues(np.linspace(0.35, 0.9, len(plot))),
               edgecolor="white", linewidth=0.5)

        for angle, radius, val in zip(angles, radii, plot["Sales"] / 1000):
            ax.text(angle, radius + 0.17, f"${val:,.0f}K", ha="center", va="center",
                    fontsize=6.8, color="#0B3C5D", fontweight="bold")

        ax.set_xticks(angles)
        ax.set_xticklabels(plot["Sub-Category"], fontsize=6.5)
        ax.set_yticklabels([])
        ax.set_ylim(0, 1.32)   # 预留标注环带，品类名在最外圈
        ax.set_title("品类销售规模 (Top 8)", fontsize=10.5, fontweight="bold", pad=20)
  
        fig.text(0.01, 0.015, "数据来源：Tableau Superstore 示例数据（2023-01至2026-09）",
                 fontsize=7.5, color="#6C757D", ha="left", va="bottom")
        stamp_figure_number(fig)
        fig.savefig(FIGURES / "n12_category_rose.png", facecolor="white")
        plt.close(fig)
        CHART_INDEX.append(
            {
                "filename": "n12_category_rose.png", "title": "品类销售规模", "chart_type": "南丁格尔玫瑰图", "template_no": "12",
            }
        )

        # n13 Bar-line combination.
        fig, ax = plt.subplots(figsize=(7.4, 3.9))
        ax.bar(monthly["MonthDate"], monthly["Sales"] / 1000, width=18, color="#B6D5E3", label="销售额")
        ax.set_ylabel("销售额（千美元）")
        ax2 = ax.twinx()
        ax2.plot(monthly["MonthDate"], monthly["Margin"] * 100, color="#E76F51", linewidth=1.3, label="利润率")
        ax2.set_ylabel("利润率（%）")
        ax2.grid(False)
        
        # 柱顶全标销售额，折线标极值
        for i, date in enumerate(monthly["MonthDate"]):
            ax.text(date, monthly.iloc[i]["Sales"]/1000 + 1, f"{monthly.iloc[i]['Sales']/1000:.0f}",
                    ha="center", va="bottom", fontsize=6, color="#0B3C5D")
        for idx in [monthly["Margin"].idxmax(), monthly["Margin"].idxmin(), monthly.index[-1]]:
            val = monthly.loc[idx, "Margin"] * 100
            date = monthly.loc[idx, "MonthDate"]
            ax2.annotate(f"{val:.1f}%", (date, val), textcoords="offset points", xytext=(0, 6),
                         ha="center", fontsize=6.5, color="#E76F51", fontweight="bold")
                         
        ax.tick_params(axis="x", rotation=35)
        setup_axis(ax)
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, frameon=False, loc="upper left", ncol=2)
        panel_header(ax, "销售规模与利润率")
        save_nature(fig, "n13_sales_margin.png", "销售规模与利润率", "柱形折线图")

        # n14 Bullet chart.
        fig, ax = plt.subplots(figsize=(7.0, 3.8))
        plot = category.sort_values("Margin")
        for index, row in enumerate(plot.itertuples()):
            ax.add_patch(Rectangle((0, index - 0.18), 0.20, 0.36, facecolor="#ECF0F2", edgecolor="none"))
            ax.add_patch(Rectangle((0, index - 0.09), max(row.Margin, 0), 0.18, facecolor="#0B3C5D", edgecolor="none"))
            ax.vlines(0.15, index - 0.24, index + 0.24, color="#E76F51", linewidth=1.6)
            ax.text(max(row.Margin, 0) + 0.006, index, f"{row.Margin:.1%}", va="center", fontsize=7)
        ax.set_yticks(range(len(plot)), plot["Category"])
        ax.set_xlim(0, 0.23)
        ax.set_xticks([0, 0.05, 0.10, 0.15, 0.20], ["0%", "5%", "10%", "15%", "20%"])
        setup_axis(ax)
        ax.grid(False)
        panel_header(ax, "品类利润率与参考线")
        save_nature(fig, "n14_category_bullet.png", "品类利润率与参考线", "子弹图")

        # n15 Dumbbell comparison.
        current = orders[(orders["Year"] == 2026) & (orders["Order Date"].dt.month <= 9)].groupby("Sub-Category")["Sales"].sum()
        previous = orders[(orders["Year"] == 2025) & (orders["Order Date"].dt.month <= 9)].groupby("Sub-Category")["Sales"].sum()
        compare = pd.DataFrame({"2025": previous, "2026": current}).dropna().sort_values("2026").tail(9)
        compare_norm = compare / compare.max()
        
        fig, ax = plt.subplots(figsize=(7.2, 4.1))
        for index, (name, row) in enumerate(compare_norm.iterrows()):
            v25, v26 = row["2025"], row["2026"]
            ax.plot([v25, v26], [index, index], color="#CFD8DC", linewidth=3.2, zorder=1)
            ax.scatter(v25, index, s=36, color="#8FB8CC", zorder=3)
            ax.scatter(v26, index, s=36, color="#0B3C5D", zorder=3)
            
            # 增加具体指数与变化率标注
            ax.text(v25, index - 0.18, f"{v25*100:.0f}", ha="center", va="top", fontsize=6.5, color="#8FB8CC")
            ax.text(v26, index - 0.18, f"{v26*100:.0f}", ha="center", va="top", fontsize=6.5, color="#0B3C5D", fontweight="bold")
            
            real_v25, real_v26 = compare.loc[name, "2025"], compare.loc[name, "2026"]
            if real_v25 > 0:
                growth = (real_v26 / real_v25 - 1) * 100
                color_g = "#2A9D8F" if growth >= 0 else "#E76F51"
                ax.text(max(v25, v26) + 0.03, index, f"{name} ({growth:+.1f}%)", va="center", fontsize=6.8, color=color_g, fontweight="bold")
            else:
                ax.text(max(v25, v26) + 0.03, index, name, va="center", fontsize=6.8)
                
        ax.set_yticks([])
        ax.set_xlim(0, 1.18) # 扩大X轴上限防止文字截断
        setup_axis(ax, xlabel="相对销售额指数")
        ax.grid(False)
        ax.scatter([], [], s=36, color="#8FB8CC", label="2025年1-9月")
        ax.scatter([], [], s=36, color="#0B3C5D", label="2026年1-9月")
        ax.legend(frameon=False, loc="lower right")
        panel_header(ax, "重点品类同期销售变化")
        save_nature(fig, "n15_category_dumbbell.png", "重点品类同期销售变化", "对比滑珠图")


def build_model_charts(
    orders: pd.DataFrame, analytics: dict[str, object]
) -> None:
    rfm: pd.DataFrame = analytics["rfm"]
    rfm_summary: pd.DataFrame = analytics["rfm_summary"]
    cohort_matrix: pd.DataFrame = analytics["cohort_matrix"]
    subcategory: pd.DataFrame = analytics["subcategory"]
    boston: pd.DataFrame = analytics["boston"]
    discount: pd.DataFrame = analytics["discount"]
    classification: dict[str, object] = analytics["classification"]
    roc: pd.DataFrame = analytics["roc"]
    forecast: dict[str, object] = analytics["forecast"]
    monthly: pd.DataFrame = analytics["monthly"]

    # RFM sizes and contributions.
    plot = rfm_summary.sort_values("SalesShare", ascending=True)
    fig, ax = base_figure(9.4, 5.8)
    y = np.arange(len(plot))
    ax.barh(y, plot["CustomerShare"] * 100, color=COLORS["blue"], alpha=0.8, label="客户占比")
    ax.set_yticks(y, plot["RFM"])
    ax.set_xlabel("占比（%）")
    ax2 = ax.twiny()
    ax2.plot(plot["SalesShare"] * 100, y, marker="o", color=COLORS["coral"], lw=2, label="销售占比")
    ax2.set_xlabel("销售占比（%）")
    ax2.grid(False)
    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, frameon=False, loc="lower right")
    ax.set_title("RFM客户分层与销售贡献")
    save_figure(fig, "m01_rfm_segments.png", "RFM客户分层与销售贡献", "RFM", "")

    # RFM scatter.
    sample = rfm.sample(min(500, len(rfm)), random_state=RANDOM_SEED)
    segment_order = rfm_summary["RFM"].astype(str).tolist()
    palette = ["#174A7E", "#2A9D8F", "#E9C46A", "#D95F59", "#457B9D", "#8AB17D", "#F4A261", "#8D99AE"]
    fig, ax = base_figure(9.2, 5.7)
    for color, segment in zip(palette, segment_order):
        subset = sample[sample["RFM"] == segment]
        if subset.empty:
            continue
        ax.scatter(
            subset["Recency"],
            subset["Monetary"].clip(upper=rfm["Monetary"].quantile(0.99)),
            s=np.clip(subset["Frequency"] * 14, 14, 180),
            alpha=0.58,
            color=color,
            label=segment,
        )
    ax.set_xlabel("最近购买间隔R（天）")
    ax.set_ylabel("累计销售额M（美元）")
    ax.set_title("RFM客户分布")
    ax.legend(ncol=2, fontsize=8, frameon=False)
    save_figure(fig, "m02_rfm_scatter.png", "RFM客户分布", "RFM", "")

    # Cohort heatmap.
    fig, ax = plt.subplots(figsize=(9.0, 7.4))
    cmap = LinearSegmentedColormap.from_list("cohort", ["#FFFFFF", "#B6D5E3", "#0B3C5D"])
    im = ax.imshow(cohort_matrix.values * 100, aspect="auto", cmap=cmap, vmin=0, vmax=40)
    labels = [period.strftime("%Y-%m") for period in cohort_matrix.index]
    ax.set_yticks(range(len(labels)), labels, fontsize=7.2)
    ax.set_xticks(range(cohort_matrix.shape[1]), [f"第{i}月" for i in cohort_matrix.columns], fontsize=8)
    ax.set_xlabel("首购后月份")
    ax.set_ylabel("客户首购同期群")
    ax.set_title("客户同期群留存率")
    ax.grid(False)
    # 白色细分隔线让格子边界清晰（学术热力图惯例）
    ax.set_xticks(np.arange(-0.5, cohort_matrix.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-0.5, cohort_matrix.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.8)
    ax.tick_params(which="minor", length=0)
    for row_index in range(cohort_matrix.shape[0]):
        for column_index in range(cohort_matrix.shape[1]):
            value = cohort_matrix.iloc[row_index, column_index]
            if pd.notna(value):
                tone = "white" if value * 100 >= 25 else "#263238"
                ax.text(column_index, row_index, f"{value * 100:.0f}", ha="center", va="center",
                        fontsize=6.6, color=tone)
    cbar = fig.colorbar(im, ax=ax, fraction=0.028, pad=0.02)
    cbar.set_label("留存率（%）")
    save_figure(fig, "m03_cohort_heatmap.png", "客户同期群留存率", "同期群", "")

    # ABC Pareto.
    pareto = subcategory.head(17).copy()
    fig, ax = base_figure(9.8, 5.2)
    colors = pareto["ABC"].map({"A": COLORS["navy"], "B": COLORS["teal"], "C": COLORS["gold"]})
    ax.bar(range(len(pareto)), pareto["Sales"] / 1000, color=colors)
    ax.set_xticks(range(len(pareto)), pareto["Sub-Category"], rotation=58, ha="right", fontsize=8)
    ax.set_ylabel("销售额（千美元）")
    ax2 = ax.twinx()
    ax2.plot(range(len(pareto)), pareto["Cumulative"] * 100, marker="o", color=COLORS["coral"], lw=2)
    ax2.axhline(80, color=COLORS["gray"], linestyle="--", linewidth=0.9)
    ax2.axhline(95, color=COLORS["gray"], linestyle=":", linewidth=0.9)
    ax2.text(len(pareto) - 0.4, 80.6, "80% 线", fontsize=7.5, color=COLORS["gray"], ha="right", va="bottom")
    ax2.text(len(pareto) - 0.4, 95.6, "95% 线", fontsize=7.5, color=COLORS["gray"], ha="right", va="bottom")
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("累计占比（%）")
    ax2.grid(False)
    ax.set_title("品类ABC帕累托图")
    clean_axes(ax)
    save_figure(fig, "m04_abc_pareto.png", "品类ABC帕累托图", "ABC分类", "")

    # Boston matrix.
    fig, ax = base_figure(9.2, 5.8)
    quadrant_colors = {
        "明星品类": COLORS["teal"],
        "现金牛品类": COLORS["navy"],
        "问题品类": COLORS["gold"],
        "瘦狗品类": COLORS["coral"],
    }
    for quadrant, subset in boston.groupby("Quadrant"):
        ax.scatter(
            subset["Share"] * 100,
            subset["Growth"] * 100,
            s=np.clip(subset["Sales"] / 1200, 40, 650),
            alpha=0.7,
            color=quadrant_colors[quadrant],
            edgecolor="white",
            label=quadrant,
        )
    for name, row in boston.iterrows():
        ax.annotate(name, (row["Share"] * 100, row["Growth"] * 100), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.axvline(boston["ShareMedian"].iloc[0] * 100, color=COLORS["gray"], linestyle="--")
    ax.axhline(boston["GrowthMedian"].iloc[0] * 100, color=COLORS["gray"], linestyle="--")
    ax.set_xlabel("销售份额（%）")
    ax.set_ylabel("2026年1-9月同比增长（%）")
    ax.set_title("品类波士顿矩阵")
    ax.legend(frameon=False, fontsize=8)
    save_figure(fig, "m05_boston_matrix.png", "品类波士顿矩阵", "波士顿矩阵", "")

    # Loss risk model.
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.8))
    axes[0].plot(roc["fpr"], roc["tpr"], color=COLORS["navy"], lw=2.5, label=f"AUC={classification['auc']:.3f}")
    axes[0].plot([0, 1], [0, 1], linestyle="--", color=COLORS["gray"])
    axes[0].set_xlabel("假阳性率")
    axes[0].set_ylabel("真阳性率")
    axes[0].set_title("亏损订单识别ROC")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.2)
    axes[1].plot(discount["DiscountBand"].astype(str), discount["LossRate"], marker="o", color=COLORS["coral"], lw=2.4)
    axes[1].set_ylim(0, 1.05)
    axis_percent(axes[1])
    axes[1].set_xlabel("折扣区间")
    axes[1].set_ylabel("亏损明细占比")
    axes[1].set_title("折扣与亏损风险")
    axes[1].tick_params(axis="x", rotation=28)
    fig.suptitle("亏损风险预警", fontsize=14)
    fig.tight_layout()
    save_figure(fig, "m06_loss_risk.png", "亏损风险预警", "逻辑回归", "")

    # Forecast.
    future = forecast["future"]
    fig, ax = base_figure(9.8, 5.2)
    ax.plot(monthly["MonthDate"], monthly["Sales"] / 1000, color=COLORS["navy"], marker="o", lw=2, label="历史销售")
    ax.plot(future["Date"], future["Forecast"] / 1000, color=COLORS["coral"], marker="o", lw=2.2,
            linestyle="--", label="未来6个月")
    ax.fill_between(
        future["Date"],
        future["Lower95"] / 1000,
        future["Upper95"] / 1000,
        color=COLORS["coral"],
        alpha=0.18,
        label="95%置信区间",
    )
    ax.axvline(monthly["MonthDate"].max(), color=COLORS["gray"], linestyle="--")
    ax.set_title(f"Holt-Winters销售预测（MAPE={forecast['mape']:.1f}%）")
    ax.set_ylabel("销售额（千美元）")
    ax.tick_params(axis="x", rotation=35)
    ax.legend(frameon=False)
    clean_axes(ax)
    save_figure(fig, "m07_forecast.png", "Holt-Winters销售预测", "Holt-Winters", "")

    # Profit and returns by subcategory.
    fig, ax = base_figure(9.2, 5.2)
    plot = subcategory.sort_values("Profit", ascending=True)
    colors = np.where(plot["Profit"] < 0, COLORS["coral"], COLORS["teal"])
    ax.barh(plot["Sub-Category"], plot["Profit"] / 1000, color=colors)
    ax.axvline(0, color=COLORS["gray"], lw=1)
    ax.set_xlabel("利润（千美元）")
    ax.set_title("品类利润质量诊断")
    clean_axes(ax)
    save_figure(fig, "m08_profit_quality.png", "品类利润质量诊断", "利润诊断", "")


def export_tables(orders: pd.DataFrame, analytics: dict[str, object], audit: dict[str, object]) -> None:
    orders.to_csv(DATA_CLEAN / "orders_clean.csv", index=False)
    (
        orders.groupby("Customer ID", as_index=False)
        .agg(
            CustomerName=("Customer Name", "last"),
            Segment=("Segment", "last"),
            Region=("Region", "last"),
            Orders=("Order ID", "nunique"),
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
        )
        .to_csv(DATA_CLEAN / "customer_dim.csv", index=False)
    )
    (
        orders.groupby("Product ID", as_index=False)
        .agg(
            ProductName=("Product Name", "last"),
            Category=("Category", "last"),
            SubCategory=("Sub-Category", "last"),
            Sales=("Sales", "sum"),
            Profit=("Profit", "sum"),
        )
        .to_csv(DATA_CLEAN / "product_dim.csv", index=False)
    )
    analytics["monthly"].to_csv(TABLES / "monthly_summary.csv", index=False)
    analytics["category"].to_csv(TABLES / "category_summary.csv", index=False)
    analytics["subcategory"].to_csv(TABLES / "subcategory_summary.csv", index=False)
    analytics["state"].to_csv(TABLES / "state_summary.csv", index=False)
    analytics["region"].to_csv(TABLES / "region_summary.csv", index=False)
    analytics["discount"].to_csv(TABLES / "discount_summary.csv", index=False)
    analytics["rfm"].to_csv(DATA_CLEAN / "customer_rfm.csv", index=False)
    analytics["rfm_summary"].to_csv(TABLES / "rfm_summary.csv", index=False)
    analytics["cohort_matrix"].to_csv(DATA_CLEAN / "cohort_retention.csv")
    analytics["boston"].to_csv(TABLES / "boston_matrix.csv")
    analytics["coefficients"].to_csv(TABLES / "loss_model_coefficients.csv", index=False)
    analytics["roc"].to_csv(TABLES / "loss_model_roc.csv", index=False)
    analytics["forecast"]["backtest_frame"].to_csv(TABLES / "forecast_backtest.csv", index=False)
    analytics["forecast"]["future"].to_csv(TABLES / "forecast_next_6m.csv", index=False)

    summary = {
        "source": {
            "name": "Tableau Superstore Sample Data",
            "url": SOURCE_URL,
            "license": "Tableau official sample data; no separate open-data license stated",
            "cutoff": str(CUTOFF.date()),
        },
        "audit": audit,
        "kpi": analytics["kpi"],
        "rfm_thresholds": analytics["rfm_thresholds"],
        "classification": analytics["classification"],
        "forecast": {
            "method": "Holt-Winters additive seasonal",
            "rolling_folds": analytics["forecast"]["backtest"],
            "rmse": analytics["forecast"]["rmse"],
            "mae": analytics["forecast"]["mae"],
            "mape": analytics["forecast"]["mape"],
            "next_6m_total": float(analytics["forecast"]["future"]["Forecast"].sum()),
            "next_6m_lower": float(analytics["forecast"]["future"]["Lower95"].sum()),
            "next_6m_upper": float(analytics["forecast"]["future"]["Upper95"].sum()),
        },
        "abc": {
            "a_count": int((analytics["subcategory"]["ABC"] == "A").sum()),
            "a_sales_share": float(
                analytics["subcategory"].loc[
                    analytics["subcategory"]["ABC"] == "A", "Sales"
                ].sum()
                / analytics["subcategory"]["Sales"].sum()
            ),
        },
        "charts": CHART_INDEX,
    }
    with (TABLES / "analysis_summary.json").open("w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)

import re

ECHARTS_URLS = [
    "https://registry.npmmirror.com/echarts/5.5.1/files/dist/echarts.min.js",
    "https://cdn.bootcdn.net/ajax/libs/echarts/5.5.1/echarts.min.js",
    "https://cdn.staticfile.net/echarts/5.5.1/echarts.min.js",
    "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
    "https://unpkg.com/echarts@5.5.1/dist/echarts.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.1/echarts.min.js",
]


def get_echarts_tag() -> str:
    """优先使用本地缓存的 ECharts（离线可用），缺失时按镜像列表下载并缓存，全部失败则回退 CDN。"""
    for cand in (ROOT / "echarts.min.js", OUTPUTS / "echarts.min.js"):
        if cand.exists() and cand.stat().st_size > 500_000:
            print(f"[ECharts] 使用本地缓存：{cand}")
            js = cand.read_text(encoding="utf-8").replace("</script", "<\\/script")
            return f"<script>\n{js}\n</script>"
    for url in ECHARTS_URLS:
        try:
            print(f"[ECharts] 尝试下载：{url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            if len(data) > 500_000:
                (ROOT / "echarts.min.js").write_bytes(data)
                print("[ECharts] 下载成功，已缓存到项目根目录（之后可完全离线运行）")
                js = data.decode("utf-8").replace("</script", "<\\/script")
                return f"<script>\n{js}\n</script>"
            print(f"  文件大小异常（{len(data)} 字节），换下一个源")
        except Exception as exc:
            print(f"  下载失败：{exc}")
    print("[ECharts] 所有下载源均失败，页面将改为联网加载 CDN（打开看板时需要网络）")
    return '<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>'


DASH_CSS = """
#bi-dashboard-root {
  --na-text: #e6efff;
  --na-muted: #8fa3c8;
  --na-faint: #64789e;
  --na-line: rgba(59, 130, 246, 0.16);
  --na-card-a: rgba(17, 30, 56, 0.72);
  --na-card-b: rgba(12, 21, 40, 0.5);
  --na-cyan: #22d3ee;
  color: var(--na-text);
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  padding: 18px 22px 14px;
  border-radius: 14px;
  min-width: 0;
  background:
    radial-gradient(1100px 480px at 50% -8%, rgba(56, 189, 248, 0.14), transparent 62%),
    radial-gradient(900px 420px at 8% 108%, rgba(124, 58, 237, 0.08), transparent 60%),
    linear-gradient(180deg, #0c1830 0%, #0a1426 55%, #091120 100%);
}
#bi-dashboard-root * { box-sizing: border-box; }

/* ---------- 头部（三区：左信息 / 中大标题 / 右状态） ---------- */
.na-header2 { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 14px; margin-bottom: 14px; }
.h2-left { display: flex; align-items: center; gap: 11px; min-width: 0; }
.na-logo { width: 44px; height: 44px; border-radius: 12px; flex: 0 0 auto;
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.25), rgba(59, 130, 246, 0.12));
  border: 1px solid rgba(34, 211, 238, 0.45);
  display: flex; align-items: center; justify-content: center; color: #67e8f9;
  box-shadow: 0 0 18px rgba(34, 211, 238, 0.25), inset 0 0 12px rgba(34, 211, 238, 0.12); }
.h2-meta { min-width: 0; }
.h2-meta .src { font-size: 12.5px; color: var(--na-muted); white-space: nowrap; }
.h2-meta .upt { font-size: 11.5px; color: var(--na-faint); white-space: nowrap; }
.h2-center { text-align: center; }
.h2-title-row { display: flex; align-items: center; justify-content: center; gap: 16px; }
.h2-deco { height: 2px; width: 110px; background: linear-gradient(90deg, transparent, #22d3ee); border-radius: 2px; }
.h2-deco.r { transform: scaleX(-1); }
.h2-center h1 { margin: 0; font-size: 25px; font-weight: 700; letter-spacing: 3px; white-space: nowrap;
  background: linear-gradient(180deg, #ffffff 30%, #7dd3fc 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  text-shadow: 0 0 26px rgba(56, 189, 248, 0.35); }
.h2-center p { margin: 3px 0 0; font-size: 12px; color: var(--na-faint); letter-spacing: 1px; white-space: nowrap; }
.h2-right { display: flex; justify-content: flex-end; }
.na-chip { font-size: 13px; font-weight: 700; color: #67e8f9; font-variant-numeric: tabular-nums;
  background: rgba(34, 211, 238, 0.08); border: 1px solid rgba(34, 211, 238, 0.4);
  border-radius: 9px; padding: 6px 14px; white-space: nowrap;
  text-shadow: 0 0 12px rgba(34, 211, 238, 0.5); }

/* ---------- 筛选栏 ---------- */
.na-filterbar { background: linear-gradient(180deg, var(--na-card-a), var(--na-card-b));
  border: 1px solid var(--na-line); border-radius: 12px; padding: 10px 18px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }
.na-filterbar .fl-label { font-size: 13px; font-weight: 700; color: #67e8f9; letter-spacing: 3px; }
.na-filterbar label { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: #9fb2d8; }
.na-filterbar select { background: rgba(10, 20, 38, 0.9); color: #dbe7ff;
  border: 1px solid rgba(94, 130, 190, 0.4); border-radius: 8px; padding: 5px 10px;
  font-family: inherit; font-size: 13px; outline: none; cursor: pointer; min-width: 120px; }
.na-filterbar select:focus { border-color: var(--na-cyan); box-shadow: 0 0 10px rgba(34, 211, 238, 0.35); }
.na-filterbar select option { background: #0d1b33; color: #dbe7ff; }
.na-hint { font-size: 12px; color: var(--na-faint); margin-left: auto; text-align: right; line-height: 1.45; max-width: 360px; }

/* ---------- KPI ---------- */
.na-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 12px; }
.na-kpi { background: linear-gradient(180deg, var(--na-card-a), var(--na-card-b));
  border: 1px solid var(--na-line); border-radius: 12px; padding: 12px 14px 12px 18px; position: relative;
  overflow: hidden; min-width: 0; }
.na-kpi::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--ac, #22d3ee); box-shadow: 0 0 12px var(--ac, #22d3ee); }
.na-kpi-top { display: flex; justify-content: space-between; gap: 6px; font-size: 12.5px; color: #aebfe0; font-weight: 600; }
.na-kpi-tag { color: var(--na-faint); font-weight: 400; white-space: nowrap; }
.na-kpi-val { font-size: 25px; font-weight: 700; margin: 3px 0 1px; letter-spacing: .3px; white-space: nowrap;
  color: #f4f9ff; font-variant-numeric: tabular-nums; text-shadow: 0 0 18px var(--ac, #22d3ee); }
.na-kpi-val small { font-size: 13px; font-weight: 600; color: var(--na-muted); margin-left: 3px; }

/* ---------- 详情钉住栏 ---------- */
.na-brief { background: linear-gradient(90deg, rgba(34, 211, 238, 0.10), rgba(17, 30, 56, 0.55) 45%);
  border: 1px solid rgba(34, 211, 238, 0.22); border-left: 3px solid #22d3ee;
  border-radius: 12px; padding: 10px 18px; font-size: 13.5px; line-height: 1.75; margin-bottom: 14px;
  color: #c9d8f5; min-height: 46px; box-shadow: 0 0 22px rgba(34, 211, 238, 0.07) inset; }
.na-brief b { font-weight: 700; }
.na-brief .bd-row { display: inline-flex; gap: 6px; margin-right: 18px; align-items: baseline; }
.na-brief .bd-k { color: var(--na-faint); }
.na-brief .bd-v { font-weight: 700; font-variant-numeric: tabular-nums; }

/* ---------- 图表网格：左 / 中 / 右三栏 ---------- */
.na-grid2 { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
.na-col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.na-col.left, .na-col.right { grid-column: span 3; }
.na-col.center { grid-column: span 6; }
.na-card { background: linear-gradient(180deg, var(--na-card-a), var(--na-card-b));
  border: 1px solid var(--na-line); border-radius: 10px; padding: 13px 15px 8px;
  display: flex; flex-direction: column; min-width: 0; position: relative; }
.na-card::before, .na-card::after { content: ''; position: absolute; width: 9px; height: 9px;
  border: 0 solid rgba(56, 189, 248, 0.65); pointer-events: none; }
.na-card::before { top: -1px; left: -1px; border-top-width: 2px; border-left-width: 2px; }
.na-card::after { bottom: -1px; right: -1px; border-bottom-width: 2px; border-right-width: 2px; }
.na-card-h { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.na-card-h h3 { font-size: 15px; font-weight: 700; margin: 0; white-space: nowrap; color: #dcebff; letter-spacing: .5px; }
.na-hint-r { font-size: 12px; color: var(--na-faint); white-space: nowrap; }
.na-sub { font-size: 12px; color: var(--na-faint); margin: 1px 0 2px; }
.na-chart { width: 100%; }
.na-col.left .na-chart, .na-col.right .na-chart { height: 298px; }
.na-col.center #ch-trend { height: 378px; }

/* ---------- 订单明细表（深色） ---------- */
#bi-table { height: 246px; overflow-y: auto; overflow-x: hidden; border-top: 1px solid rgba(148, 163, 184, 0.10); }
table.od { width: 100%; border-collapse: collapse; font-size: 12.5px; }
table.od th { position: sticky; top: 0; background: #0d1b33; color: #9fb2d8; font-weight: 600; text-align: left;
  padding: 8px 10px; border-bottom: 1px solid rgba(56, 189, 248, 0.25); white-space: nowrap; z-index: 1; }
table.od td { padding: 7px 10px; border-bottom: 1px solid rgba(148, 163, 184, 0.08); color: #c9d8f5;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-variant-numeric: tabular-nums; }
table.od tbody tr:nth-child(even) { background: rgba(255, 255, 255, 0.02); }
table.od tbody tr:hover { background: rgba(34, 211, 238, 0.07); }
.od-pos { color: #34d399; font-weight: 600; }
.od-neg { color: #fb7185; font-weight: 600; }

.na-foot { font-size: 11.5px; color: #55688c; margin-top: 10px; line-height: 1.7; }

@media (prefers-reduced-motion: reduce) {
  #bi-dashboard-root *, #bi-dashboard-root *::before, #bi-dashboard-root *::after {
    animation: none !important; transition: none !important;
  }
}
@media (max-width: 1360px) {
  .na-col.left, .na-col.center, .na-col.right { grid-column: span 12; }
  .na-col.center { order: -1; }
  .na-kpis { grid-template-columns: repeat(3, 1fr); }
  .na-hint { display: none; }
}
@media (max-width: 1080px) {
  .na-header2 { grid-template-columns: 1fr; text-align: center; }
  .h2-left { justify-content: center; }
  .h2-right { justify-content: center; }
}
@media (max-width: 720px) {
  .na-kpis { grid-template-columns: 1fr; }
  #bi-dashboard-root { padding: 12px; }
  .h2-deco { width: 40px; }
}
"""

DASH_TEMPLATE = """
<style>
/*__STYLE__*/
</style>

<div id="bi-dashboard-root">
  <div class="na-header2">
    <div class="h2-left">
      <div class="na-logo" aria-hidden="true">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
          <path d="M5 20V13" /><path d="M12 20V5" /><path d="M19 20v-9" />
        </svg>
      </div>
      <div class="h2-meta">
        <div class="src">Tableau Superstore · 零售明细数据</div>
        <div class="upt">经清洗校验 · 三维筛选全链路联动</div>
      </div>
    </div>
    <div class="h2-center">
      <div class="h2-title-row">
        <span class="h2-deco" aria-hidden="true"></span>
        <h1>零售经营分析数据大屏</h1>
        <span class="h2-deco r" aria-hidden="true"></span>
      </div>
      <p>销售额 · 利润 · 品类 · 区域 · 折扣风险 &nbsp;|&nbsp; 2023-01 — 2026-09 · 45 个月经营明细</p>
    </div>
    <div class="h2-right">
      <span class="na-chip">数据截至 2026-09</span>
    </div>
  </div>

  <div class="na-filterbar">
    <span class="fl-label">筛选</span>
    <label>区域 <select id="f-region"></select></label>
    <label>品类 <select id="f-category"></select></label>
    <label>客户细分 <select id="f-segment"></select></label>
    <span class="na-hint">切换筛选器即联动全部指标与图表；点击图表中的柱、点、扇区可钉住详情</span>
  </div>

  <div class="na-kpis" id="bi-kpis"></div>
  <div class="na-brief" id="bi-detail" aria-live="polite"></div>

  <div class="na-grid2">
    <div class="na-col left">
      <div class="na-card">
        <div class="na-card-h"><h3>州销售额 Top 12</h3><span class="na-hint-r">点击条目钉住详情</span></div>
        <div class="na-sub">当前筛选下的销售额（美元）</div>
        <div class="na-chart" id="ch-state"></div>
      </div>
      <div class="na-card">
        <div class="na-card-h"><h3>品类利润率</h3><span class="na-hint-r">净利率</span></div>
        <div class="na-sub">利润 ÷ 销售额（%）</div>
        <div class="na-chart" id="ch-cat"></div>
      </div>
    </div>

    <div class="na-col center">
      <div class="na-card">
        <div class="na-card-h"><h3>月度销售额与利润</h3><span class="na-hint-r">点击柱体或圆点钉住详情</span></div>
        <div class="na-sub">柱：月度销售额 · 线：月度利润（美元）</div>
        <div class="na-chart" id="ch-trend"></div>
      </div>
      <div class="na-card">
        <div class="na-card-h"><h3>近期订单明细</h3><span class="na-hint-r">按下单时间倒序 Top 20</span></div>
        <div id="bi-table"></div>
      </div>
    </div>

    <div class="na-col right">
      <div class="na-card">
        <div class="na-card-h"><h3>折扣区间平均利润</h3><span class="na-hint-r">谁在吞噬利润</span></div>
        <div class="na-sub">各折扣带的平均单行利润（美元）</div>
        <div class="na-chart" id="ch-disc"></div>
      </div>
      <div class="na-card">
        <div class="na-card-h"><h3>品类销售额占比</h3><span class="na-hint-r">点击扇区钉住详情</span></div>
        <div class="na-sub">当前筛选下的品类结构</div>
        <div class="na-chart" id="ch-donut"></div>
      </div>
    </div>
  </div>

  <div class="na-foot">
    数据来源：Tableau Superstore 示例数据（2023-01至2026-09，经清洗校验：去重、剔除未来与无效日期、金额校验）。
    筛选器（区域 / 品类 / 客户细分）联动上方全部指标与图表；点击图形元素可将该数据点钉住显示在详情栏。
    利润率 = 利润 ÷ 销售额；退货率为明细行口径。
  </div>
</div>

__ECHARTS__

<script>
window.BI_DATA = __DATA__;
</script>

<script>
__APP__
</script>
"""

DASH_APP = r"""
(function () {
  'use strict';
  var root = document.getElementById('bi-dashboard-root');
  if (!root) return;
  if (typeof echarts === 'undefined') {
    root.innerHTML = '<div style="padding:60px 20px;text-align:center;color:#8fa3c8;font-size:14px;">ECharts 加载失败：请联网后刷新页面（首次运行脚本会自动下载并内联图表库）。</div>';
    return;
  }
  var DATA = window.BI_DATA;
  var PAYLOAD = DATA.payload;
  var cur = null;

  var C = {
    cyan: '#22d3ee', gold: '#fbbf24', rose: '#fb7185', purple: '#c084fc',
    green: '#34d399', blue: '#38bdf8',
    axis: '#7e93bd', axisLine: 'rgba(126,147,189,0.35)', split: 'rgba(148,163,184,0.09)',
    label: '#dbe7ff', yLabel: '#9fb2d8', legend: '#8fa3c8',
    tipBg: 'rgba(8,15,31,0.95)', tipBorder: 'rgba(56,189,248,0.35)', tipText: '#e6efff'
  };
  var TIP = {
    backgroundColor: C.tipBg, borderColor: C.tipBorder, borderWidth: 1,
    padding: [10, 14], textStyle: { color: C.tipText, fontSize: 12.5 },
    extraCssText: 'box-shadow:0 12px 32px rgba(0,0,0,0.5);border-radius:10px;'
  };
  var DEFAULT_HINT = '<b>📌 使用提示</b>&nbsp;&nbsp;点击任意图表中的柱、点、扇区，可将该数据钉住显示在此栏；切换筛选器即联动全部指标与图表。';

  function el(id) { return document.getElementById(id); }
  function fmt$(v) { return '$' + Math.round(v).toLocaleString('en-US'); }
  function fmtK(v) { return '$' + (v >= 1000 ? (v / 1000) + 'K' : v); }
  function tipTitle(q) { return '<div style="font-weight:700;font-size:13px;margin-bottom:4px;">' + q + '</div>'; }
  function tipRow(k, v, color) {
    return '<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.9;">' +
      '<span style="opacity:.75;">' + k + '</span>' +
      '<span style="font-weight:600;' + (color ? 'color:' + color : '') + '">' + v + '</span></div>';
  }
  function mk(id) { return echarts.init(el(id)); }
  var chTrend = mk('ch-trend'), chState = mk('ch-state'), chCat = mk('ch-cat'),
      chDisc = mk('ch-disc'), chDonut = mk('ch-donut');
  var ALL = [chTrend, chState, chCat, chDisc, chDonut];

  function gradV(top, bottom) {
    return new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: top }, { offset: 1, color: bottom }]);
  }
  function gradH(left, right) {
    return new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: left }, { offset: 1, color: right }]);
  }
  function catAxis(data, rotate) {
    return { type: 'category', data: data, axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
      axisLabel: { color: C.axis, fontSize: 10.5, rotate: rotate || 0 } };
  }
  function valAxis(fmt) {
    return { type: 'value', axisLabel: { formatter: fmt, color: C.axis, fontSize: 10.5 }, splitLine: { lineStyle: { color: C.split } } };
  }

  /* ---------- 各图表配置 ---------- */
  function optTrend(d) {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      legend: { top: 0, right: 4, itemWidth: 14, itemHeight: 9, itemGap: 16, textStyle: { fontSize: 12, color: C.legend }, data: ['销售额', '利润'] },
      grid: { left: 66, right: 58, top: 30, bottom: 52 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          var i = ps[0].dataIndex, s = d.trend.sales[i], p = d.trend.profit[i];
          return tipTitle(d.trend.x[i]) +
            tipRow('销售额', fmt$(s), C.cyan) +
            tipRow('利润', fmt$(p), C.gold) +
            tipRow('利润率', (s ? (p / s * 100) : 0).toFixed(1) + '%');
        }
      }),
      xAxis: catAxis(d.trend.x, 38),
      yAxis: [valAxis(fmtK), { type: 'value', axisLabel: { formatter: fmtK, color: C.axis, fontSize: 10.5 }, splitLine: { show: false } }],
      series: [
        { name: '销售额', type: 'bar', data: d.trend.sales, barWidth: '55%',
          itemStyle: { borderRadius: [3, 3, 0, 0], color: gradV('rgba(56,189,248,0.95)', 'rgba(14,116,190,0.22)') } },
        { name: '利润', type: 'line', yAxisIndex: 1, data: d.trend.profit, symbol: 'circle', symbolSize: 6, z: 6,
          lineStyle: { width: 2.5, color: C.gold, shadowColor: C.gold, shadowBlur: 8 }, itemStyle: { color: C.gold } }
      ]
    };
  }

  function optState(d) {
    var pairs = [];
    for (var i = 0; i < d.state.x.length; i++) {
      if (d.state.y[i] > 0) pairs.push([d.state.x[i], d.state.y[i]]);
    }
    pairs.sort(function (a, b) { return b[1] - a[1]; });
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 92, right: 62, top: 10, bottom: 22 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) { return tipTitle(p.name) + tipRow('销售额', fmt$(p.value), C.cyan); }
      }),
      xAxis: valAxis(fmtK),
      yAxis: { type: 'category', inverse: true, data: pairs.map(function (p) { return p[0]; }),
        axisLine: { lineStyle: { color: C.axisLine } }, axisTick: { show: false },
        axisLabel: { color: C.yLabel, fontSize: 11 } },
      series: [{
        name: '销售额', type: 'bar', barWidth: '58%',
        data: pairs.map(function (p) { return p[1]; }),
        itemStyle: { borderRadius: [0, 3, 3, 0], color: gradH('rgba(14,165,233,0.3)', 'rgba(34,211,238,0.95)') },
        label: { show: true, position: 'right', fontSize: 10.5, color: C.label, fontWeight: 600, formatter: function (p) { return fmt$(p.value); } }
      }]
    };
  }

  function optCat(d) {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 40, right: 20, top: 30, bottom: 26 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) { return tipTitle(p.name) + tipRow('利润率', p.value.toFixed(1) + '%', C.purple); }
      }),
      xAxis: catAxis(d.category.x),
      yAxis: valAxis(function (v) { return v + '%'; }),
      series: [{
        name: '利润率', type: 'bar', barWidth: '46%', data: d.category.y,
        itemStyle: { borderRadius: [3, 3, 0, 0], color: gradV('rgba(192,132,252,0.95)', 'rgba(109,40,217,0.35)') },
        label: { show: true, position: 'top', fontSize: 11, color: C.label, fontWeight: 600, formatter: function (p) { return p.value.toFixed(1) + '%'; } }
      }]
    };
  }

  function optDisc(d) {
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      grid: { left: 62, right: 20, top: 30, bottom: 40 },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) { return tipTitle('折扣 ' + p.name) + tipRow('平均单行利润', fmt$(p.value), C.gold); }
      }),
      xAxis: catAxis(d.discount.x, 28),
      yAxis: valAxis(fmtK),
      series: [{
        name: '平均利润', type: 'line', data: d.discount.y, symbol: 'circle', symbolSize: 9,
        lineStyle: { width: 2.5, color: C.gold, shadowColor: C.gold, shadowBlur: 8 },
        itemStyle: { color: C.rose, borderColor: C.gold, borderWidth: 2 },
        label: { show: true, position: 'top', fontSize: 10.5, color: C.label, fontWeight: 600, formatter: function (p) { return fmt$(p.value); } },
        markLine: { silent: true, symbol: 'none', animation: false, label: { show: false },
          lineStyle: { type: 'dashed', color: 'rgba(148,163,184,0.45)' }, data: [{ yAxis: 0 }] }
      }]
    };
  }

  function optDonut(d) {
    var arr = [];
    for (var i = 0; i < d.donut.x.length; i++) {
      if (d.donut.y[i] > 0) arr.push({ name: d.donut.x[i], value: d.donut.y[i] });
    }
    return {
      animation: true, animationDuration: 0, animationDurationUpdate: 320,
      color: [C.cyan, C.purple, C.gold],
      legend: { bottom: 0, icon: 'circle', itemWidth: 9, itemHeight: 9, textStyle: { color: C.legend, fontSize: 11.5 } },
      tooltip: Object.assign({}, TIP, {
        trigger: 'item',
        formatter: function (p) { return tipTitle(p.name) + tipRow('销售额', fmt$(p.value), C.cyan) + tipRow('销售额占比', p.percent.toFixed(1) + '%', C.gold); }
      }),
      series: [{
        name: '品类销售额', type: 'pie', radius: ['42%', '64%'], center: ['50%', '46%'],
        data: arr, avoidLabelOverlap: true,
        itemStyle: { borderColor: 'rgba(8,15,31,0.9)', borderWidth: 2 },
        label: { color: C.yLabel, fontSize: 11, formatter: '{b}\n{d}%' },
        labelLine: { lineStyle: { color: 'rgba(148,163,184,0.4)' } }
      }]
    };
  }

  /* ---------- 详情钉住 ---------- */
  function pinDetail(html) { el('bi-detail').innerHTML = html; }
  function resetDetail() { el('bi-detail').innerHTML = DEFAULT_HINT; }

  chTrend.on('click', function (p) {
    if (!cur) return;
    var i = cur.trend.x.indexOf(p.name);
    if (i < 0) return;
    var s = cur.trend.sales[i], pr = cur.trend.profit[i];
    pinDetail(tipTitle('📌 ' + cur.trend.x[i]) +
      '<span class="bd-row"><span class="bd-k">销售额</span><span class="bd-v" style="color:' + C.cyan + '">' + fmt$(s) + '</span></span>' +
      '<span class="bd-row"><span class="bd-k">利润</span><span class="bd-v" style="color:' + C.gold + '">' + fmt$(pr) + '</span></span>' +
      '<span class="bd-row"><span class="bd-k">利润率</span><span class="bd-v" style="color:' + C.purple + '">' + (s ? (pr / s * 100) : 0).toFixed(1) + '%</span></span>');
  });
  chState.on('click', function (p) {
    if (!cur) return;
    var total = 0;
    for (var i = 0; i < cur.state.y.length; i++) { if (cur.state.y[i] > 0) total += cur.state.y[i]; }
    var share = total ? (p.value / total * 100) : 0;
    pinDetail(tipTitle('📌 ' + p.name) +
      '<span class="bd-row"><span class="bd-k">销售额</span><span class="bd-v" style="color:' + C.cyan + '">' + fmt$(p.value) + '</span></span>' +
      '<span class="bd-row"><span class="bd-k">占展示州合计</span><span class="bd-v" style="color:' + C.green + '">' + share.toFixed(1) + '%</span></span>');
  });
  chCat.on('click', function (p) {
    pinDetail(tipTitle('📌 ' + p.name) +
      '<span class="bd-row"><span class="bd-k">利润率</span><span class="bd-v" style="color:' + C.purple + '">' + p.value.toFixed(1) + '%</span></span>');
  });
  chDisc.on('click', function (p) {
    pinDetail(tipTitle('📌 折扣 ' + p.name) +
      '<span class="bd-row"><span class="bd-k">平均单行利润</span><span class="bd-v" style="color:' + (p.value < 0 ? C.rose : C.gold) + '">' + fmt$(p.value) + '</span></span>');
  });
  chDonut.on('click', function (p) {
    pinDetail(tipTitle('📌 ' + p.name) +
      '<span class="bd-row"><span class="bd-k">销售额</span><span class="bd-v" style="color:' + C.cyan + '">' + fmt$(p.value) + '</span></span>' +
      '<span class="bd-row"><span class="bd-k">销售额占比</span><span class="bd-v" style="color:' + C.gold + '">' + p.percent.toFixed(1) + '%</span></span>');
  });

  /* ---------- 筛选联动 ---------- */
  function apply(key) {
    var d = PAYLOAD[key];
    if (!d) return;
    cur = d;
    el('bi-kpis').innerHTML = d.kpi;
    el('bi-table').innerHTML = d.table_html;
    chTrend.setOption(optTrend(d), true);
    chState.setOption(optState(d), true);
    chCat.setOption(optCat(d), true);
    chDisc.setOption(optDisc(d), true);
    chDonut.setOption(optDonut(d), true);
    resetDetail();
  }

  function fillSelect(sel, options) {
    for (var i = 0; i < options.length; i++) {
      var o = document.createElement('option');
      o.value = options[i];
      o.textContent = options[i];
      sel.appendChild(o);
    }
  }
  var selR = el('f-region'), selC = el('f-category'), selS = el('f-segment');
  fillSelect(selR, DATA.filters.region);
  fillSelect(selC, DATA.filters.category);
  fillSelect(selS, DATA.filters.segment);
  function onChange() { apply(selR.value + '|' + selC.value + '|' + selS.value); }
  selR.addEventListener('change', onChange);
  selC.addEventListener('change', onChange);
  selS.addEventListener('change', onChange);

  window.addEventListener('resize', function () {
    for (var i = 0; i < ALL.length; i++) ALL[i].resize();
  });
  window.addEventListener('load', function () {
    for (var i = 0; i < ALL.length; i++) ALL[i].resize();
  });

  apply('全部|全部|全部');
})();
"""

def build_html_table(data: dict) -> str:
    """生成深色风格的近期订单明细表（吸顶表头 + 斑马纹 + 悬停高亮）。"""
    html = '<table class="od"><thead><tr>'
    for col in ["订单号", "日期", "州", "品类", "销售额", "利润"]:
        html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"
    for i in range(len(data["order"])):
        profit_val = data["profit"][i]
        profit_cls = "od-neg" if profit_val < 0 else "od-pos"
        html += "<tr>"
        html += f"<td>{data['order'][i]}</td>"
        html += f"<td>{data['date'][i]}</td>"
        html += f"<td>{data['state'][i]}</td>"
        html += f"<td>{data['category'][i]}</td>"
        html += f"<td>${data['sales'][i]:,.2f}</td>"
        html += f"<td class='{profit_cls}'>${profit_val:,.2f}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html

def sanitize_for_js(obj):
    """递归清洗字典/列表，确保所有数值都是合法的 JS 数字，消灭 NaN、Infinity 和非法控制字符。"""
    if isinstance(obj, dict):
        return {k: sanitize_for_js(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_js(v) for v in obj]
    elif isinstance(obj, (int, np.integer)):
        return int(obj)
    elif isinstance(obj, (float, np.floating)):
        val = float(obj)
        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    elif isinstance(obj, str):
        return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', obj)
    elif obj is None:
        return 0.0
    return obj

def build_dashboard(orders: pd.DataFrame) -> None:
    """生成深色科技风 ECharts 交互大屏：三维筛选联动 + 点击钉住详情，输出单文件离线 HTML。"""
    regions = ["全部", *sorted(orders["Region"].dropna().unique())]
    categories = ["全部", *sorted(orders["Category"].dropna().unique())]
    segments = ["全部", *sorted(orders["Segment"].dropna().unique())]

    # 预先计算全局静态 X 轴，各筛选组合的数据对齐到同一坐标轴，缺失补 0
    all_months = sorted({str(p) for p in orders["Order Date"].dt.to_period("M").unique()})
    all_states = (
        orders.groupby("State/Province")["Sales"].sum()
        .sort_values(ascending=False).head(12).index.tolist()
    )
    all_categories = sorted(orders["Category"].dropna().unique().tolist())
    all_discount_bins = ["0%", "1-10%", "11-20%", "21-30%", "31-40%", "41-50%", ">50%"]

    accents = ["#22d3ee", "#34d399", "#c084fc", "#38bdf8", "#fbbf24", "#fb7185"]

    def kpi_card(accent: str, title: str, tag: str, value: str, unit: str = "") -> str:
        return (
            f'<div class="na-kpi" style="--ac:{accent}">'
            f'<div class="na-kpi-top"><span>{title}</span><span class="na-kpi-tag">{tag}</span></div>'
            f'<div class="na-kpi-val">{value}<small>{unit}</small></div></div>'
        )

    payload: dict[str, dict[str, object]] = {}
    for region_name, category_name, segment_name in product(regions, categories, segments):
        subset = orders.copy()
        if region_name != "全部": subset = subset[subset["Region"] == region_name]
        if category_name != "全部": subset = subset[subset["Category"] == category_name]
        if segment_name != "全部": subset = subset[subset["Segment"] == segment_name]
        if subset.empty:
            continue

        key = f"{region_name}|{category_name}|{segment_name}"
        trend = subset.set_index("Order Date").resample("MS").agg(
            Sales=("Sales", "sum"), Profit=("Profit", "sum")
        )
        trend.index = trend.index.strftime("%Y-%m")
        state = subset.groupby("State/Province")["Sales"].sum().sort_values(ascending=False)
        cat = subset.groupby("Category").agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"))
        cat["Margin"] = cat["Profit"] / cat["Sales"]

        disc_bins = pd.cut(subset["Discount"], bins=[-0.001, 0.001, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8], labels=all_discount_bins)
        disc = subset.assign(Band=disc_bins).groupby("Band", observed=True)["Profit"].mean()

        recent = subset.sort_values("Order Date", ascending=False).head(20)
        total_sales = float(subset["Sales"].sum())
        total_profit = float(subset["Profit"].sum())
        margin = total_profit / total_sales if total_sales > 0 else 0.0

        kpi_html = (
            kpi_card(accents[0], "销售额", "现价", f"${total_sales:,.0f}")
            + kpi_card(accents[1], "利润", "净额", f"${total_profit:,.0f}")
            + kpi_card(accents[2], "利润率", "净利率", f"{margin * 100:.1f}", "%")
            + kpi_card(accents[3], "订单量", "去重订单", f"{subset['Order ID'].nunique():,}", "单")
            + kpi_card(accents[4], "客户数", "去重客户", f"{subset['Customer ID'].nunique():,}", "人")
            + kpi_card(accents[5], "退货率", "明细行口径", f"{subset['Returned'].mean() * 100:.1f}", "%")
        )

        # 将数据对齐到全局 X 轴，缺失值补 0
        t_sales = [float(trend.loc[m, "Sales"]) if m in trend.index else 0.0 for m in all_months]
        t_profit = [float(trend.loc[m, "Profit"]) if m in trend.index else 0.0 for m in all_months]
        s_sales = [float(state.loc[s]) if s in state.index else 0.0 for s in all_states]
        c_margin = [float(cat.loc[c, "Margin"] * 100) if c in cat.index else 0.0 for c in all_categories]
        c_sales = [float(cat.loc[c, "Sales"]) if c in cat.index else 0.0 for c in all_categories]
        d_profit = [float(disc.loc[b]) if b in disc.index else 0.0 for b in all_discount_bins]

        table_data = {
            "order": recent["Order ID"].tolist(),
            "date": recent["Order Date"].dt.strftime("%Y-%m-%d").tolist(),
            "state": recent["State/Province"].tolist(),
            "category": recent["Category"].tolist(),
            "sales": [float(x) for x in recent["Sales"].round(2)],
            "profit": [float(x) for x in recent["Profit"].round(2)],
        }

        payload[key] = {
            "kpi": kpi_html,
            "table_html": build_html_table(table_data),
            "trend": {"x": all_months, "sales": t_sales, "profit": t_profit},
            "state": {"x": all_states, "y": s_sales},
            "category": {"x": all_categories, "y": c_margin},
            "discount": {"x": all_discount_bins, "y": d_profit},
            "donut": {"x": all_categories, "y": c_sales},
        }

    payload = sanitize_for_js(payload)
    data_json = json.dumps(
        {
            "filters": {"region": regions, "category": categories, "segment": segments},
            "payload": payload,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    echarts_tag = get_echarts_tag()
    fragment = (
        DASH_TEMPLATE
        .replace("/*__STYLE__*/", DASH_CSS)
        .replace("__ECHARTS__", echarts_tag)
        .replace("__DATA__", data_json)
        .replace("__APP__", DASH_APP)
    )
    html = (
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Superstore 零售经营数据大屏</title>\n</head>\n<body>\n'
        + fragment + '\n</body>\n</html>\n'
    )
    with open(DASHBOARD, "w", encoding="utf-8", newline="\n") as file:
        file.write(html)
    mode = "内联离线" if echarts_tag.startswith("<script>\n") else "CDN 在线"
    print(f"交互看板已生成：{DASHBOARD}（{len(html.encode('utf-8')) / 1024:.0f} KB，ECharts {mode}）")


def print_summary(analytics: dict[str, object], audit: dict[str, object]) -> None:
    kpi = analytics["kpi"]
    forecast = analytics["forecast"]
    print("\n=== 分析完成 ===")
    print(f"清洗后明细：{audit['clean_rows']:,}；订单：{audit['orders']:,}；客户：{audit['customers']:,}")
    print(f"销售额：${kpi['sales']:,.2f}；利润：${kpi['profit']:,.2f}；利润率：{kpi['margin']:.2%}")
    print(f"退货订单率：{kpi['return_rate']:.2%}；亏损明细占比：{kpi['loss_row_rate']:.2%}")
    print(f"亏损预警AUC：{analytics['classification']['auc']:.3f}")
    print(f"销量预测MAPE：{forecast['mape']:.2f}%；RMSE：${forecast['rmse']:,.2f}")
    print(f"模板图与业务图：{len(CHART_INDEX)} 张")
    print(f"交互看板：{DASHBOARD}")
    print(f"论文数据表：{TABLES}")

def main() -> None:
    ensure_dependencies()
    orders_raw, returns_raw, people = read_source()
    orders, audit = clean_data(orders_raw, returns_raw, people)
    analytics = calculate_analytics(orders)
    build_selected_template_charts(orders, analytics)
    build_model_charts(orders, analytics)
    export_tables(orders, analytics, audit)
    build_dashboard(orders)
    print_summary(analytics, audit)

if __name__ == "__main__":
    main()
