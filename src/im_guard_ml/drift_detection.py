"""Statistical drift detection for production monitoring.

Extends basic threshold alerting with proper statistical tests to detect
distribution shifts that may indicate:
  - Covariate shift: input distribution changed (upstream feature pipeline issue)
  - Label shift: output distribution changed (model degradation or new patterns)
  - Concept drift: relationship between input and output changed

Tests implemented:
  - Chi-square test: categorical distribution comparison (risk_level, handling, topic)
  - Kolmogorov-Smirnov test: continuous distribution comparison (gift_value, latency)
  - Population Stability Index (PSI): industry-standard drift metric for scoring models
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DriftTestResult:
    """Result of a single drift test."""
    test_name: str
    field_name: str
    statistic: float
    p_value: float | None
    threshold: float
    is_significant: bool
    severity: str  # "none" | "warning" | "critical"
    detail: str = ""


@dataclass
class DriftReport:
    """Comprehensive drift report across all monitored fields."""
    status: str  # "stable" | "drift_warning" | "drift_critical"
    tests: list[DriftTestResult] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Chi-square test for categorical distributions
# ---------------------------------------------------------------------------


def chi_square_test(
    observed: dict[str, int],
    expected: dict[str, int],
) -> tuple[float, float]:
    """Pearson's chi-square goodness-of-fit test.

    Args:
        observed: Category -> count in current window
        expected: Category -> count in baseline window

    Returns:
        (chi2_statistic, p_value)
    """
    all_keys = sorted(set(observed) | set(expected))
    total_obs = sum(observed.values()) or 1
    total_exp = sum(expected.values()) or 1

    # Normalize expected to same total as observed
    scale = total_obs / total_exp

    chi2 = 0.0
    df = max(len(all_keys) - 1, 1)

    for key in all_keys:
        obs = observed.get(key, 0)
        exp = expected.get(key, 0) * scale
        if exp < 1e-10:
            exp = 0.5  # Continuity correction for zero-expected cells
        chi2 += (obs - exp) ** 2 / exp

    # Approximate p-value using chi-square CDF (Wilson-Hilferty approximation)
    p_value = _chi2_survival(chi2, df)

    return chi2, p_value


def _chi2_survival(x: float, df: int) -> float:
    """Approximate chi-square survival function (1 - CDF).

    Uses Wilson-Hilferty normal approximation for df > 2.
    """
    if df <= 0 or x <= 0:
        return 1.0
    # Wilson-Hilferty approximation
    z = ((x / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    # Standard normal survival (Abramowitz & Stegun approximation)
    return _normal_survival(z)


def _normal_survival(z: float) -> float:
    """Approximate standard normal survival function."""
    if z < -6:
        return 1.0
    if z > 6:
        return 0.0
    # Rational approximation
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p = d * math.exp(-z * z / 2) * t * (
        0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))
    )
    return p if z > 0 else 1.0 - p


# ---------------------------------------------------------------------------
# Kolmogorov-Smirnov test for continuous distributions
# ---------------------------------------------------------------------------


def ks_test(
    sample_a: list[float],
    sample_b: list[float],
) -> tuple[float, float]:
    """Two-sample Kolmogorov-Smirnov test.

    Args:
        sample_a: Current window values
        sample_b: Baseline window values

    Returns:
        (ks_statistic, approximate_p_value)
    """
    if not sample_a or not sample_b:
        return 0.0, 1.0

    n_a = len(sample_a)
    n_b = len(sample_b)

    # Combine and sort
    combined = [(v, "a") for v in sample_a] + [(v, "b") for v in sample_b]
    combined.sort(key=lambda x: x[0])

    # Compute empirical CDFs and find max difference
    cdf_a = 0.0
    cdf_b = 0.0
    d_max = 0.0

    for value, source in combined:
        if source == "a":
            cdf_a += 1.0 / n_a
        else:
            cdf_b += 1.0 / n_b
        d_max = max(d_max, abs(cdf_a - cdf_b))

    # Approximate p-value (Kolmogorov distribution)
    n_eff = (n_a * n_b) / (n_a + n_b)
    lambda_val = (math.sqrt(n_eff) + 0.12 + 0.11 / math.sqrt(n_eff)) * d_max

    # Kolmogorov survival function approximation
    if lambda_val <= 0:
        p_value = 1.0
    else:
        p_value = 2.0 * math.exp(-2.0 * lambda_val * lambda_val)
        p_value = max(0.0, min(1.0, p_value))

    return d_max, p_value


# ---------------------------------------------------------------------------
# Population Stability Index (PSI)
# ---------------------------------------------------------------------------


def population_stability_index(
    baseline_dist: dict[str, float],
    current_dist: dict[str, float],
) -> float:
    """Calculate Population Stability Index (PSI).

    PSI < 0.1: no significant shift
    PSI 0.1-0.25: moderate shift, investigate
    PSI > 0.25: significant shift, action required

    Args:
        baseline_dist: Category -> proportion in baseline
        current_dist: Category -> proportion in current window
    """
    all_keys = sorted(set(baseline_dist) | set(current_dist))
    psi = 0.0
    eps = 1e-6  # Avoid log(0)

    for key in all_keys:
        p = max(baseline_dist.get(key, 0.0), eps)
        q = max(current_dist.get(key, 0.0), eps)
        psi += (q - p) * math.log(q / p)

    return psi


# ---------------------------------------------------------------------------
# Comprehensive drift detection
# ---------------------------------------------------------------------------


def detect_drift(
    current_report: dict[str, Any],
    baseline_report: dict[str, Any],
    *,
    chi2_alpha: float = 0.05,
    ks_alpha: float = 0.05,
    psi_warning: float = 0.1,
    psi_critical: float = 0.25,
) -> DriftReport:
    """Run all drift tests comparing current window to baseline.

    Args:
        current_report: Output of build_monitoring_report() for current window
        baseline_report: Output of build_monitoring_report() for baseline window
        chi2_alpha: Significance level for chi-square tests
        ks_alpha: Significance level for KS tests
        psi_warning: PSI threshold for warning
        psi_critical: PSI threshold for critical

    Returns:
        DriftReport with all test results and overall status
    """
    tests: list[DriftTestResult] = []

    # 1. Chi-square tests on categorical prediction distributions
    for field_name in ("risk_level", "final_judgment", "handling_suggestion"):
        cur_dist = current_report.get("prediction_distribution", {}).get(field_name, {})
        base_dist = baseline_report.get("prediction_distribution", {}).get(field_name, {})

        if cur_dist and base_dist:
            # Convert proportions to counts (approximate)
            cur_total = current_report.get("total", 1000)
            base_total = baseline_report.get("total", 1000)
            cur_counts = {k: int(v * cur_total) for k, v in cur_dist.items()}
            base_counts = {k: int(v * base_total) for k, v in base_dist.items()}

            chi2, p_val = chi_square_test(cur_counts, base_counts)
            is_sig = p_val < chi2_alpha

            # PSI for severity
            psi = population_stability_index(base_dist, cur_dist)
            severity = "none"
            if psi >= psi_critical:
                severity = "critical"
            elif psi >= psi_warning:
                severity = "warning"

            tests.append(DriftTestResult(
                test_name="chi_square",
                field_name=field_name,
                statistic=chi2,
                p_value=p_val,
                threshold=chi2_alpha,
                is_significant=is_sig,
                severity=severity,
                detail=f"PSI={psi:.4f}",
            ))

    # 2. KS test on continuous input distributions
    cur_input = current_report.get("input_distribution", {})
    base_input = baseline_report.get("input_distribution", {})

    for field_name in ("gift_total_value",):
        cur_stats = cur_input.get(field_name, {})
        base_stats = base_input.get(field_name, {})

        # Reconstruct approximate samples from summary stats
        cur_samples = _reconstruct_samples(cur_stats)
        base_samples = _reconstruct_samples(base_stats)

        if cur_samples and base_samples:
            ks_stat, p_val = ks_test(cur_samples, base_samples)
            is_sig = p_val < ks_alpha
            severity = "critical" if is_sig and ks_stat > 0.3 else (
                "warning" if is_sig else "none"
            )

            tests.append(DriftTestResult(
                test_name="kolmogorov_smirnov",
                field_name=field_name,
                statistic=ks_stat,
                p_value=p_val,
                threshold=ks_alpha,
                is_significant=is_sig,
                severity=severity,
                detail=f"D={ks_stat:.4f}",
            ))

    # 3. Determine overall status
    severities = [t.severity for t in tests]
    if "critical" in severities:
        status = "drift_critical"
    elif "warning" in severities:
        status = "drift_warning"
    else:
        status = "stable"

    significant_tests = [t for t in tests if t.is_significant]
    summary = (
        f"{len(significant_tests)}/{len(tests)} tests significant. "
        f"Status: {status}."
    )

    return DriftReport(status=status, tests=tests, summary=summary)


def _reconstruct_samples(stats: dict[str, Any]) -> list[float]:
    """Reconstruct approximate sample distribution from summary statistics.

    Uses min, p50, p95, max to create a rough distribution for KS testing.
    """
    if not stats or stats.get("count", 0) == 0:
        return []

    count = int(stats.get("count", 0))
    if count == 0:
        return []

    # Create approximate distribution from percentiles
    min_val = float(stats.get("min", 0))
    p50 = float(stats.get("p50", 0))
    p95 = float(stats.get("p95", 0))
    max_val = float(stats.get("max", 0))
    mean = float(stats.get("mean", 0))

    # Generate approximate samples matching the summary stats
    samples: list[float] = []
    n = min(count, 100)  # Cap at 100 for efficiency

    # Distribute samples across percentile ranges
    n_below_50 = n // 2
    n_50_to_95 = int(n * 0.45)
    n_above_95 = n - n_below_50 - n_50_to_95

    for i in range(n_below_50):
        t = i / max(n_below_50, 1)
        samples.append(min_val + t * (p50 - min_val))

    for i in range(n_50_to_95):
        t = i / max(n_50_to_95, 1)
        samples.append(p50 + t * (p95 - p50))

    for i in range(n_above_95):
        t = i / max(n_above_95, 1)
        samples.append(p95 + t * (max_val - p95))

    return samples
