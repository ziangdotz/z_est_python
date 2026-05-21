"""NIST SP 800-90B Entropy Assessment - Conditioning Evaluation"""

from __future__ import annotations

import math

import mpmath as mp


def compute_output_entropy(
    h_in: float, n_in: int, n_out: int, nw: int,
    precision_bits: int = 128,
) -> tuple[float, float, float, float]:
    """
    Section 3.1.5.1.2 Output_Entropy.
    Uses mpmath for arbitrary precision arithmetic.
    Returns (h_out, nout_epsilon_exp, hin_epsilon_exp, nw_epsilon_exp).
    """
    mp.mp.dps = precision_bits // 4 + 10

    n = min(n_out, nw)

    p_high = mp.power(2, -mp.mpf(h_in))
    if p_high <= 0 or p_high >= 1:
        return compute_output_entropy(h_in, n_in, n_out, nw, precision_bits * 2)

    p_low = (1 - p_high) / (mp.power(2, n_in) - 1)
    if p_low <= 0 or p_low >= 1:
        return compute_output_entropy(h_in, n_in, n_out, nw, precision_bits * 2)

    power_term = mp.power(2, n_in - n)
    psi = power_term * p_low + p_high
    psi = min(psi, mp.mpf(1))

    omega = (power_term + mp.sqrt(mp.log(2) * power_term * 2 * n)) * p_low
    omega = min(omega, mp.mpf(1))

    h_out = -mp.log(max(omega, psi), 2)

    if h_out >= n_out or h_out >= h_in:
        return compute_output_entropy(h_in, n_in, n_out, nw, precision_bits * 2)

    nout_eps = _calc_epsilon(h_out, n_out)
    hin_eps = _calc_epsilon(h_out, h_in)
    nw_eps = _calc_epsilon(h_out, nw)

    return float(h_out), float(nout_eps), float(hin_eps), float(nw_eps)


def _calc_epsilon(h_out: mp.mpf, bound: float) -> float:
    """epsilon = -log2(1 - h_out/bound)"""
    ratio = h_out / mp.mpf(bound)
    if ratio >= 1:
        return float('inf')
    return float(-mp.log(1 - ratio, 2))


def conditioning_test(
    h_in: float, n_in: int, n_out: int, nw: int,
    verbose: int = 1,
) -> dict:
    """
    Full conditioning assessment.
    Returns dict with h_out and epsilon values.
    """
    h_out, nout_eps, hin_eps, nw_eps = compute_output_entropy(h_in, n_in, n_out, nw)

    result = {
        "h_in": h_in,
        "n_in": n_in,
        "n_out": n_out,
        "nw": nw,
        "h_out": h_out,
        "nout_epsilon": nout_eps,
        "hin_epsilon": hin_eps,
        "nw_epsilon": nw_eps,
    }

    if verbose >= 2:
        print(f"Conditioning: h_in = {h_in}")
        print(f"Conditioning: n_in = {n_in}")
        print(f"Conditioning: n_out = {n_out}")
        print(f"Conditioning: nw = {nw}")
        print(f"Conditioning: h_out = {h_out}")
        print(f"Conditioning: nout_epsilon = {nout_eps}")
        print(f"Conditioning: hin_epsilon = {hin_eps}")
        print(f"Conditioning: nw_epsilon = {nw_eps}")

    return result
