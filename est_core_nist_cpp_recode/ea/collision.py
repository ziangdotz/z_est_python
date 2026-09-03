"""NIST SP 800-90B Entropy Assessment - Collision Estimate (Section 6.3.2)"""

from __future__ import annotations

import math

import numpy as np

from ._config import ZALPHA


def collision_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.2: Collision Estimate.
    Binary data only. Returns min-entropy estimate.
    """
    i = 0
    v = 0
    sum_t = 0
    sum_t2 = 0.0

    while i < length - 1:
        if int(data[i]) == int(data[i + 1]):
            t_v = 2
        elif i < length - 2:
            t_v = 3
        else:
            break
        v += 1
        sum_t += t_v
        sum_t2 += t_v * t_v
        i += t_v

    if v == 0:
        if verbose > 1:
            print(f"{label} Collision Estimate: No collisions found.")
        return -1.0

    X_bar = sum_t / v
    sigma_hat = math.sqrt((sum_t2 - sum_t * X_bar) / (v - 1))

    if verbose == 2:
        print(f"{label} Collision Estimate: X-bar = {X_bar:.17g}, sigma-hat = {sigma_hat:.17g}, ", end="")
    elif verbose == 3:
        print(f"{label} Collision Estimate: v = {v}")
        print(f"{label} Collision Estimate: Sum t_i = {sum_t}")
        print(f"{label} Collision Estimate: X-bar = {X_bar:.17g}")
        print(f"{label} Collision Estimate: sigma-hat = {sigma_hat:.17g}")

    # Directly calculate p
    X_prime = X_bar - ZALPHA * sigma_hat / math.sqrt(v)
    # 2.0 is the smallest meaningful value: every wait time is 2 or 3, so a mean
    # below 2.0 can only be the confidence bound overshooting. Left alone it puts
    # p above 1.0 and makes the estimate negative instead of 0.
    if X_prime < 2.0:
        X_prime = 2.0

    if verbose == 3:
        print(f"{label} Collision Estimate: X-bar' = {X_prime:.17g}")

    if X_prime < 2.5:
        p = 0.5 + math.sqrt(1.25 - 0.5 * X_prime)
        ent_est = -math.log2(p)
        if verbose == 3:
            print(f"{label} Collision Estimate: Found p.")
    else:
        if verbose == 3:
            print(f"{label} Collision Estimate: Could Not Find p. Proceeding with the lower bound for p.")
        p = 0.5
        ent_est = 1.0

    if verbose == 2:
        print(f"p = {p:.17g}")
    elif verbose == 3:
        print(f"{label} Collision Estimate: p = {p:.17g}")
        print(f"{label} Collision Estimate: min entropy = {ent_est:.17g}")

    return ent_est
