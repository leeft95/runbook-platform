import math

import numpy as np
import pandas as pd
import scipy.optimize


def mva(x, n, type="s"):
    """
    moving average for series x in window n
    input and output are numpy ndarray or pandas series or one column dataframe
    type:
    's' - simple moving average
    'e' - exponential moving average
    'sm' - smoothed moving average: a[i] = (a[i - 1] * (n - 1) + x[i]) / n
    """
    p = np.asarray(x)
    length = len(p)
    if len(p.shape) == 2:
        if p.shape[1] == 1:
            p = p.reshape(-1)
        else:
            raise IndexError("Input DataFrame can only have one column")
    if type == "s":
        weights = np.ones(n)
        weights /= weights.sum()
        a = np.convolve(p, weights, mode="full")[:length]
        a[: n - 1] = np.nan
    elif type == "e":
        alpha = 2.0 / (n + 1)
        p_ = np.insert(p, 0, p[0] * np.ones(n * 5))
        weights = [(1 - alpha) ** x for x in range(0, n * 5)]
        weights = np.asarray(weights)
        weights /= weights.sum()
        a_ = np.convolve(p_, weights, mode="full")[: length + n * 5]
        pass_check = n * 5
        a = a_[pass_check:]
        a[: n - 1] = np.nan
        idx = 0
        pass_check_1 = n + idx
        a[n - 1 + idx] = np.mean(p[idx:pass_check_1])
        for i in range(n + idx, np.min([length, n + idx + n * 5])):
            a[i] = alpha * p[i] + (1 - alpha) * a[i - 1]
    elif type == "sm":
        a = np.empty((length,))
        a.fill(np.NaN)
        idx = np.where(~np.isnan(p))[0][0]
        pass_check_2 = n + idx
        a[n - 1 + idx] = np.mean(p[idx:pass_check_2])
        for i in range(n + idx, length):
            a[i] = (a[i - 1] * (n - 1) + p[i]) / n
    if isinstance(x, pd.Series):
        return pd.Series(a, index=x.index)
    elif isinstance(x, pd.DataFrame):
        return pd.DataFrame(a, index=x.index, columns=x.columns)
    else:
        return a


def bollinger(p, window, thr):
    """
    bollinger band
    """
    try:
        if p.shape[1] == 1:
            p = p[:, 0]
    except Exception:
        pass
    mv = mva(p, window)
    sd = np.empty(len(p))
    sd.fill(np.NaN)
    sloc = window - 1
    sd[sloc:] = np.std(rolling_window(p, window), axis=1)
    upper_band = mv + thr * sd
    lower_band = mv - thr * sd
    band_width = (upper_band - lower_band) / mv
    pctb = (p - lower_band) / (upper_band - lower_band)
    return upper_band, lower_band, band_width, pctb, mv


def calc_chg(a, flag=None, n=1):
    """
    calculating difference, percent change and log change
    a is input array, n is gap
    flag: None - do nothing to original series; p - percentage;
    d - difference; l/ln/log - log return
    """

    if n == 0 or flag is None:
        return a

    if n < 0:
        print("n must be above 0")
        n = abs(n)

    z = np.zeros(n)

    if flag == "d":
        b = np.subtract(a[n:], a[:-n])
    elif flag == "p":
        b = np.subtract(a[n:], a[:-n]) / a[:-n]
    elif flag == "ln" or flag == "l" or flag == "log":
        b = np.subtract(np.log(a)[n:], np.log(a)[:-n])

    result = np.hstack([z, b])
    return result


def realizedvol(p, flag=None, rollwindow=0, annualize=260, returnseries=True, decay_factor=0):
    """
    p is series, dataframe or ndarray
    flag: None - do nothing to original series; p - percentage;
    d - difference; l/ln/log - log return
    """

    if isinstance(p, pd.Series) or isinstance(p, pd.DataFrame):
        a = p.values
    else:
        a = p

    a = a.reshape(-1)
    a = calc_chg(a, flag, 1)
    if rollwindow != 0:

        if decay_factor == 0:
            weights = np.ones(int(rollwindow)) / rollwindow
        else:
            weights = [(1 - decay_factor) * pow(decay_factor, i) / (1 - pow(decay_factor, rollwindow)) for i in range(0, rollwindow)]
        am = np.convolve(a, weights, "full")
        am2 = am**2.0
        a2 = a**2.0
        rv = np.sqrt(np.convolve(a2, weights, "full") - am2)
        rv = rv[: -1 * (rollwindow - 1)]
        rv[: rollwindow - 1] = np.nan

    else:
        rv = a.std()

    rv = rv * math.sqrt(annualize)

    if returnseries is True:
        df = pd.Series(rv, index=p.index)
        return df
    else:
        return rv


def percentilerank(x, p):
    """
    calculate percentile rank, return a number between 0 and 1
    """
    if p >= max(x):
        prank = 1
    elif p <= min(x):
        prank = 0
    else:
        n = len(x)
        b = sum(float(num) < p for num in x)
        eq = sum(float(num) == p for num in x)
        r = b + eq
        s = np.sort(x)
        x1 = s[r - 1]
        x2 = s[r]
        rx1 = float(r - 1) / n
        rx2 = float(r) / n
        prank = float(b + 0.5 * eq) / n + (p - x1) / (x2 - x1) * (rx2 - rx1)
    return prank


def rolling_ols(y, x, window, const=True):
    """
    calculate univariate rolling regression beta, with or without constant
    """

    window = int(window)
    x2 = np.power(x, 2)
    y2 = np.power(y, 2)
    xy = x * y
    w = np.ones(window)

    a1 = np.convolve(xy, w, "full") * window
    a2 = np.convolve(x, w, "full") * np.convolve(y, w, "full")
    b1 = np.convolve(x2, w, "full") * window
    b2 = np.power(np.convolve(x, w, "full"), 2)
    b3 = np.convolve(y2, w, "full") * window
    b4 = np.power(np.convolve(y, w, "full"), 2)

    if const:
        betas = (a1 - a2) / (b1 - b2)
        alphas = (np.convolve(y, w, "full") - betas * np.convolve(x, w, "full")) / float(window)
        raise NotImplementedError("Clipped rolling_ols const=True formulas in IMG_5772")
        rsqr = (sum_y2_hat - b4) / (b3 - b4)
    else:
        betas = a1 / b1
        alphas = np.zeros(len(y) + window - 1)
        rsqr = (betas * betas * b1) / b3
        sqrmse = np.sqrt((b3 + betas * betas * b1 - 2 * betas * a1) / (window * (window - 1)))

    alphas = alphas[: -1 * (window - 1)]
    betas = betas[: -1 * (window - 1)]
    rsqr = rsqr[: -1 * (window - 1)]
    sqrmse = sqrmse[: -1 * (window - 1)]
    alphas[: window - 1] = 0
    betas[: window - 1] = 0
    rsqr[: window - 1] = 0
    sqrmse[: window - 1] = 0
    return alphas, betas, rsqr, sqrmse


def rolling_residual(y, x, window, const=True):
    """
    get rolling residual zscore
    """
    alphas, betas, rsqr, sqrmse = rolling_ols(y=y, x=x, window=window, const=const)
    result = (y - (alphas + betas * x)) / sqrmse
    result[result == np.inf] = 0
    return result


def rolling_window(p, window):
    """
    rolling window for rolling calculation
    """
    shape = p.shape[:-1] + (p.shape[-1] - window + 1, window)
    strides = p.strides + (p.strides[-1],)
    return np.lib.stride_tricks.as_strided(p, shape=shape, strides=strides)


def stochastic(highp, lowp, closep, k, d, sd):
    """
    stochastic indicator
    """
    p_max = np.empty(len(closep))
    p_max.fill(np.NaN)
    sloc = k - 1
    p_max[sloc:] = np.max(rolling_window(highp, k), axis=1)
    p_min = np.empty(len(closep))
    p_min.fill(np.NaN)
    p_min[sloc:] = np.min(rolling_window(lowp, k), axis=1)
    pctk = (closep - p_min) / (p_max - p_min) * 100
    pctd = mva(pctk, d)
    pctds = mva(pctd, sd)
    return pctk, pctd, pctds


def tr(highp, lowp=None, closep=None, window=1):
    """
    true range of price series in rolling window
    true range = max(current high - current low, current high - prev close,
    current low - prev close)
    The first element is assumed to be the oldest data.
    If input is only one array, then take it as close price and calculate
    input and output are ndarray
    """

    if highp is not None and lowp is None and closep is None:
        len_highp = len(highp)
        if len_highp == 1:
            out = 0
        else:
            out = np.append(0, abs(np.diff(highp)) * 2)
    else:
        if isinstance(highp, np.float64):
            out = highp - lowp
        else:
            len_highp = len(highp)
            len_lowp = len(lowp)
            len_closep = len(closep)

            if len_highp != len_lowp or len_highp != len_closep or len_lowp != len_closep:
                print("The length of price vectors must be the same.")
                return

            if len_closep == 1:
                out = highp - lowp
            else:
                if (lowp == closep).all() and (highp == closep).all():
                    out = np.append(0, abs(np.diff(closep)) * 2)
                else:
                    range1 = highp - lowp
                    range2 = np.append(highp[0] - lowp[0], abs(highp[1:] - closep[0:-1]))
                    range3 = np.append(highp[0] - lowp[0], abs(lowp[1:] - closep[0:-1]))
                    out = np.amax([range1, range2, range3], axis=0)
    return out


def atr(highp, lowp=None, closep=None, window=14):
    """
    exp moving average of true range
    """

    if isinstance(highp, np.float64):
        out = tr(highp, lowp, closep)
    else:
        length = len(highp)
        if window > length:
            print("Period of ATR cannot be larger than length of prices.")
            return

        if window is None or window == 0:
            true_range = tr(highp, lowp, closep)
            out = np.mean(true_range)
        elif window == 1:
            out = tr(highp, lowp, closep)
        else:
            true_range = tr(highp, lowp, closep)
            out = mva(true_range, window, "e")
    return out


def fisher_indicator(highp, lowp, closep):
    fh = (highp + lowp + closep) / 3 + abs((highp + lowp + closep) / 3 - (highp + lowp) / 2)
    fl = (highp + lowp + closep) / 3 - abs((highp + lowp + closep) / 3 - (highp + lowp) / 2)
    return fh, fl


def exp_avg(p, a=0.98):
    """
    generates exponential weighted average for input array p, with a
    """

    w = [(1 - a) * pow(a, i) / (1 - pow(a, len(p))) for i in range(0, len(p))]
    return (p * w).sum()


def seasonal_sd(tdd, yrs=5, window=10):
    """
    Calculate seasonal standard deviation on the last point of tdd
    """
    i = len(tdd) - 1
    if tdd.index[i].month == 2 and tdd.index[i].day == 29:
        center_dates = [idx for idx, val in enumerate(tdd.index) if val.month == 2 and val.day == 28]
    else:
        center_dates = [idx for idx, val in enumerate(tdd.index) if val.month == tdd.index[i].month and val.day == tdd.index[i].day]
    center_loc = [val for idx, val in enumerate(center_dates) if val <= i]
    expand_loc = [list(range(x - window, x + window)) for x in center_loc[-yrs:]]
    expand_loc = [x for sublist in expand_loc for x in sublist if (x >= 0) & (x < i)]
    return tdd.iloc[expand_loc].std()


def donchian(highp, lowp=None, closep=None, window=20):
    """
    donchian channel
    """
    if lowp is None and closep is None:
        lowp = highp
        closep = highp
    length = len(closep)
    p_max = np.empty(length)
    p_max.fill(np.NaN)
    p_min = np.empty(length)
    p_min.fill(np.NaN)
    don = np.empty(length)
    don.fill(np.NaN)
    sloc = window - 1
    p_max[sloc:] = np.max(rolling_window(highp, window), axis=1)
    p_min[sloc:] = np.min(rolling_window(lowp, window), axis=1)
    don = np.empty(len(closep))
    don.fill(np.NaN)
    for i in range(window, len(closep)):
        if closep[i] > p_max[i - 1]:
            don[i] = 1
        elif closep[i] < p_min[i - 1]:
            don[i] = -1
        else:
            don[i] = don[i - 1]
    return p_max, p_min, don


def ERC(cov, options=None):
    """
    Calculate the weights associated with the equal risk contribution
    portfolio. Refer to "On the Properties of Equally-Weighted Risk
    Contributions Portfolios" by Maillard, Roncalli, and Teiletche for
    definitions.
    Parameters
    ----------
    cov: numpy.ndarray
        (N, N) covariance matrix of assets, must be positive definite
    options: dictionary
        A dictionary of solver options. See scipy.optimize.minimize.
    Returns
    -------
    w: numpy.ndarray
        (N,) array of asset weights
    """


    cov = np.asarray(cov, float)
    np.linalg.cholesky(cov)

    if not options:
        options = {"ftol": 1e-10, "maxiter": 2000}

    N = cov.shape[0]
    x0 = np.ones(N) / N


    def fun(w):
        w = np.clip(w, 0, 1.0)
        m = cov @ w
        port_var = float(w @ m)
        port_vol = np.sqrt(port_var)

        rc = (w * m) / port_vol  # sum(rc) = port_vol

        s1 = float(np.sum(rc))
        s2 = float(np.sum(rc * rc))
        return 2.0 * N * s2 - 2.0 * (s1 * s1)

    bounds = [(0, 1) for i in range(N)]
    constraints = {"type": "eq", "fun": lambda x: np.sum(x) - 1}
    res = scipy.optimize.minimize(fun, x0, method="SLSQP", bounds=bounds, constraints=constraints, options=options)
    if not res.success:
        raise RuntimeError(f"SLSQP failed: {res.message}")

    weights = res.x
    m = cov @ weights
    port_var = float(weights @ m)
    return weights, np.sqrt(port_var)


