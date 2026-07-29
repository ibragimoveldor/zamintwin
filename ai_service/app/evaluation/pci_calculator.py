"""
Pavement Condition Index (PCI) calculator.

Computes PCI scores from crack detection/width data using deduct value curves
and corrected deduct value models (polynomial regression).
"""

import os
import glob
import logging
import warnings

import numpy as np
import pandas as pd
import joblib as jb
from sklearn.preprocessing import PolynomialFeatures

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

# PCI rating thresholds
PCI_RATINGS = [
    (85, "Good"),
    (70, "Satisfactory"),
    (55, "Fair"),
    (40, "Poor"),
    (25, "Very Poor"),
    (10, "Serious"),
    (0, "Failed"),
]


def _pci_rating(cdv: float) -> str:
    """Convert corrected deduct value to pavement condition rating."""
    pci = 100 - cdv
    for threshold, rating in PCI_RATINGS:
        if pci > threshold:
            return rating
    return "Not Damaged"


def _to_density_length(x):
    return float(f"{x / 3700:.2f}")


def _to_density_area(x):
    return float(f"{x / 370000:.2f}")


def _to_meters(x):
    return x / 1000


def _to_sq_meters(x):
    return x / 1000000


def compute_pci(path: str, dv_path: str) -> None:
    """
    Compute PCI scores and save results to CSV.

    Args:
        path: Processing directory (10m/).
        dv_path: Path to deduct value curve models.
    """
    base_path = path.replace("10m", "")
    crack_info = os.path.join(base_path, "pci", "crack_info_may.txt")

    if not os.path.exists(crack_info):
        logger.error(f"Crack info file not found: {crack_info}")
        return

    # Load crack data
    df = pd.read_csv(
        crack_info,
        names=["image", "crackType", "length", "severity", "width"],
        encoding="utf-8",
    )
    df["crackType"] = df["crackType"].replace("trans", "crack")

    # Calculate areas
    df["areaAlr"] = df.loc[df["crackType"] == "alr", "length"]
    df["areaPatch"] = df.loc[df["crackType"] == "patching", "length"]
    df["areaPothole"] = df.loc[df["crackType"] == "pothole", "length"]
    df.loc[df["length"] > 10000, "length"] = 0

    # Group by image, crack type, severity
    grouped = (
        df.groupby(["image", "crackType", "severity"])[["length", "areaAlr", "areaPatch", "areaPothole"]]
        .sum()
        .reset_index()
    )

    # Calculate density
    grouped["density"] = np.nan
    crack_mask = grouped["crackType"] == "crack"
    grouped.loc[crack_mask, "density"] = grouped.loc[crack_mask, "length"].apply(_to_density_length)
    grouped.loc[grouped["crackType"] == "alr", "density"] = grouped.loc[grouped["crackType"] == "alr", "areaAlr"].apply(_to_density_area)
    grouped.loc[grouped["crackType"] == "patching", "density"] = grouped.loc[grouped["crackType"] == "patching", "areaPatch"].apply(_to_density_area)
    grouped.loc[grouped["crackType"] == "pothole", "density"] = grouped.loc[grouped["crackType"] == "pothole", "areaPothole"].apply(_to_density_area)

    # Convert units
    grouped = grouped.astype({"length": float, "areaAlr": float, "areaPatch": float, "areaPothole": float})
    grouped.loc[crack_mask, "length"] = grouped.loc[crack_mask, "length"].apply(_to_meters)
    grouped.loc[grouped["crackType"] == "alr", "areaAlr"] = grouped.loc[grouped["crackType"] == "alr", "areaAlr"].apply(_to_sq_meters)
    grouped.loc[grouped["crackType"] == "patching", "areaPatch"] = grouped.loc[grouped["crackType"] == "patching", "areaPatch"].apply(_to_sq_meters)
    grouped.loc[grouped["crackType"] == "pothole", "areaPothole"] = grouped.loc[grouped["crackType"] == "pothole", "areaPothole"].apply(_to_sq_meters)

    grouped = grouped[["image", "crackType", "severity", "length", "areaAlr", "areaPatch", "areaPothole", "density"]]

    # Load deduct value models
    poly = PolynomialFeatures(degree=7)
    dv_models = {
        ("crack", "low"): jb.load(os.path.join(dv_path, "dv_curve/long_trans_low.pkl")),
        ("crack", "med"): jb.load(os.path.join(dv_path, "dv_curve/long_trans_med.pkl")),
        ("crack", "high"): jb.load(os.path.join(dv_path, "dv_curve/long_trans_high.pkl")),
        ("alr", "high"): jb.load(os.path.join(dv_path, "dv_curve/alligator_dv_high.pkl")),
        ("patching", "med"): jb.load(os.path.join(dv_path, "dv_curve/patching_med.pkl")),
        ("pothole", "med"): jb.load(os.path.join(dv_path, "dv_curve/alligator_dv_high.pkl")),
    }

    def _predict_dv(model, x):
        result = model.predict(poly.fit_transform([[x]]))
        val = np.array(result).flatten()[0]
        return float(val)

    # Calculate deduct values per row
    grouped["dv"] = 0.0
    for idx in grouped.index:
        ct = grouped.at[idx, "crackType"]
        sev = grouped.at[idx, "severity"]
        density = grouped.at[idx, "density"]
        key = (ct, sev)
        if key in dv_models and pd.notna(density):
            grouped.at[idx, "dv"] = _predict_dv(dv_models[key], density)

    grouped["dv"] = grouped["dv"].astype(float)
    grouped["q_num"] = grouped["dv"].apply(lambda x: 1 if x > 4 else 0)

    # Corrected deduct values
    cdv_grouped = (
        grouped.groupby("image")[["dv", "q_num", "length", "areaAlr", "areaPatch", "areaPothole"]]
        .sum()
        .reset_index()
    )

    # Load CDV models
    cdv_models = {}
    for q in range(2, 8):
        model_path = os.path.join(dv_path, f"cdv_py2/q{q}.pkl")
        if os.path.exists(model_path):
            cdv_models[q] = jb.load(model_path)

    cdv_grouped["cdv"] = 0.0
    for idx in cdv_grouped.index:
        q = int(cdv_grouped.at[idx, "q_num"])
        dv_val = float(cdv_grouped.at[idx, "dv"])
        if q == 1:
            cdv_grouped.at[idx, "cdv"] = dv_val
        elif q in cdv_models:
            cdv_grouped.at[idx, "cdv"] = _predict_dv(cdv_models[q], dv_val)

    # Format
    for col in ["dv", "cdv", "areaAlr", "areaPatch", "areaPothole"]:
        cdv_grouped[col] = cdv_grouped[col].astype(float).map("{:.2f}".format)

    cdv_grouped["PCI"] = 100 - cdv_grouped["cdv"].astype(float)
    cdv_grouped["Pavement Condition"] = cdv_grouped["cdv"].astype(float).apply(_pci_rating)

    # Merge with result images to fill gaps
    result_dir = os.path.join(base_path, "result")
    if os.path.isdir(result_dir):
        image_names = [os.path.splitext(f)[0] for f in glob.glob(f"{result_dir}/*.jpg")]
        imgs_df = pd.DataFrame(image_names, columns=["image"])
        result = pd.merge(imgs_df, cdv_grouped, on="image", how="outer").fillna(0)
        result.loc[result["Pavement Condition"] == 0, "Pavement Condition"] = "Not Damaged"
    else:
        result = cdv_grouped

    result = result[["image", "PCI", "length", "areaAlr", "areaPatch", "areaPothole", "PCI", "Pavement Condition"]]

    output_path = os.path.join(base_path, "pci", "pci100_final.csv")
    result.to_csv(output_path, index=False)
    logger.info(f"PCI results saved to {output_path}")