import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor


def calibrate_rth_to_bbg_asof(
    rth: pd.Series,
    bbg: pd.Series,
    *,
    window: int | None = 60,  # fit on last N aligned rows
    method: str = "huber",  # "huber" | "robust" | "ols"
    slope_shrink: float = 0.15,  # light shrink toward 1
    slope_bounds: tuple[float, float] = (0.75, 1.25),
    recenter: str = "last",  # "last" to anchor boundary, or "median"
    tolerance: str = "5D",  # how old a BBG print we're willing to use
):
    rth = rth.sort_index()
    bbg = bbg.sort_index()

    last_bbg_dt = bbg.dropna().index.max()

    bbg_asof = bbg.reindex(rth.index, method="ffill", tolerance=pd.Timedelta(tolerance))

    if pd.notna(last_bbg_dt):
        bbg_asof.loc[bbg_asof.index > last_bbg_dt] = np.nan

    df = pd.concat([rth.rename("RTH"), bbg_asof.rename("TGT")], axis=1).dropna()

    if pd.notna(last_bbg_dt):
        df = df.loc[:last_bbg_dt]
    if window:
        df = df.tail(window)
    R, T = df["RTH"], df["TGT"]

    if method == "huber":
        try:
            reg = HuberRegressor().fit(R.values.reshape(-1, 1), T.values)
            a0, b0 = float(reg.intercept_), float(reg.coef_[0])
        except Exception:
            method = "robust"  # fallback
    if method == "robust":
        mu_r, mu_t = R.median(), T.median()
        iqr_r = R.quantile(0.75) - R.quantile(0.25)
        iqr_t = T.quantile(0.75) - T.quantile(0.25)
        b0 = (iqr_t / iqr_r) if float(iqr_r) != 0 else 1.0
        a0 = mu_t - b0 * mu_r
    elif method == "ols":
        X = np.vstack([np.ones(len(R)), R.values]).T
        a0, b0 = np.linalg.lstsq(X, T.values, rcond=None)[0]

    b = slope_shrink * 1.0 + (1 - slope_shrink) * float(b0)
    b = float(np.clip(b, *slope_bounds))
    a = float(a0)

    resid = T - (a + b * R)
    if recenter == "median":
        a += float(resid.median())
    elif recenter == "last":
        a = float(T.iloc[-1] - b * R.iloc[-1])

    fitted = a + b * R
    diag = pd.DataFrame({"RTH": R, "BBG_asof": T, "fitted": fitted, "resid": T - fitted})

    def nowcast(rth_val: float) -> float:
        return a + b * float(rth_val)

    return a, b, nowcast, diag
