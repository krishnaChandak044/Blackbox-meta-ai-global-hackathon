"""
engine/dynamics/models.py
─────────────────────────
Pure dataclasses for Phase 4 Physics & Simulation.
Framework-free: no FastAPI / SQLAlchemy / Celery.

All numeric fields carry explicit units in their name or docstring.
Interval types are declared, never silently assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ── Identifiability ───────────────────────────────────────────────────────────

IdentifiabilityStatus = Literal["measurable", "conditional", "not_identifiable"]
IntervalType = Literal["percentile_range", "illustrative_range", "not_available"]


@dataclass(frozen=True, slots=True)
class IdentifiabilityCertificate:
    """
    Per-quantity identifiability certificate.

    status:
      measurable      — recoverable from current evidence within stated interval
      conditional     — requires an additional assumption listed in `condition`
      not_identifiable— cannot be determined from available footage; state why

    interval_type:
      percentile_range  — empirically validated coverage (use only after G5 evaluation)
      illustrative_range— Monte Carlo spread under listed assumptions; coverage not validated
      not_available     — quantity is not_identifiable; no interval can be stated
    """
    quantity: str
    status: IdentifiabilityStatus
    interval_type: IntervalType
    condition: str | None          # required when status == "conditional"
    reason: str                    # human-readable justification
    limiting_source: str | None    # which of the 5 uncertainty sources dominates
    improving_observation: str | None  # what additional evidence would help most


# ── Five uncertainty contributions ────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class UncertaintyContribution:
    """One of the five tracked uncertainty sources."""
    source: Literal[
        "pixel_localisation",
        "homography_reprojection",
        "scale_calibration",
        "frame_timestamp",
        "model_assumption",
    ]
    # Half-width of the 1-sigma contribution in the quantity's native unit
    sigma_metres_or_ms: float
    distribution: str   # e.g. "gaussian", "uniform", "unknown"
    metadata: str       # e.g. "RMSE=2.3 px from homography fit 2024-01-01"
    propagation_method: str  # e.g. "Monte Carlo N=1000 seed=42"


@dataclass(frozen=True, slots=True)
class UncertaintyBundle:
    """All five contributions plus combined effect."""
    pixel_localisation: UncertaintyContribution
    homography_reprojection: UncertaintyContribution
    scale_calibration: UncertaintyContribution
    frame_timestamp: UncertaintyContribution
    model_assumption: UncertaintyContribution
    # Combined: Monte Carlo over all 5 sources
    combined_lo: float   # lower bound (native unit), e.g. 5th percentile
    combined_hi: float   # upper bound (native unit), e.g. 95th percentile
    interval_type: IntervalType
    seed: int
    n_samples: int


# ── Per-frame fit outputs ─────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FittedPoint:
    """Smoothed position + velocity at one frame."""
    frame_index: int
    presentation_ts_s: float
    # Smoothed ground-plane position
    world_x_m: float
    world_y_m: float
    # Velocity vector
    vx_ms: float   # m/s
    vy_ms: float   # m/s
    speed_ms: float
    speed_kmh: float
    # 1-sigma uncertainty ellipse semi-axes (metres)
    pos_sigma_x_m: float
    pos_sigma_y_m: float
    # Speed interval (illustrative range)
    speed_lo_kmh: float
    speed_hi_kmh: float


# ── Braking onset ─────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class BrakingOnset:
    """
    Detected deceleration change-point.
    Only produced when the trajectory has a supported change-point;
    otherwise the field in DynamicsResult is None.
    """
    frame_index_lo: int   # earliest consistent frame
    frame_index_hi: int   # latest consistent frame
    ts_lo_s: float
    ts_hi_s: float
    decel_before_ms2: float  # m/s² — positive = deceleration
    decel_after_ms2: float
    certificate: IdentifiabilityCertificate


# ── Fit quality ───────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class FitQuality:
    """
    Diagnostics from the least-squares fit.
    Never used to inflate confidence — only to flag poor fits.
    """
    rmse_metres: float            # residual RMS in ground-plane metres
    max_residual_metres: float    # worst single-frame residual
    n_observations: int
    n_parameters: int
    converged: bool
    convergence_message: str
    reduced_chi_squared: float    # < 1 ↔ over-fit; >> 1 ↔ systematic error
    # Parameter correlation matrix stored as flat list (row-major, n_params²)
    param_correlation_flat: list[float]
    param_names: list[str]


# ── Full dynamics result ──────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class DynamicsResult:
    """
    Immutable output of one inference run.
    Versioned, reproducible, linked to exact input IDs.
    """
    # Provenance
    run_id: str
    track_id: str
    track_version_hash: str
    calibration_fit_id: str
    media_sha256: str
    model_name: str               # e.g. "piecewise_const_accel_2d_v1"
    model_version: str
    software_revision: str        # git SHA
    seed: int
    # Input parameter snapshot (JSON string)
    params_json: str

    # Fitted trajectory
    fitted_points: list[FittedPoint]

    # Derived quantities
    entry_speed_kmh: float | None
    entry_speed_lo_kmh: float | None
    entry_speed_hi_kmh: float | None
    mean_decel_ms2: float | None
    mean_decel_lo_ms2: float | None
    mean_decel_hi_ms2: float | None
    braking_onset: BrakingOnset | None

    # Uncertainty
    uncertainty: UncertaintyBundle

    # Identifiability certificates per quantity
    certificates: dict[str, IdentifiabilityCertificate]

    # Fit diagnostics
    fit_quality: FitQuality

    # Interval type declaration
    interval_type: IntervalType


# ── Counterfactual ────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CounterfactualIntervention:
    """User-declared intervention for the simulator — never mutates the baseline."""
    braking_onset_shift_s: float = 0.0   # positive = later, negative = earlier
    entry_speed_override_kmh: float | None = None
    decel_override_ms2: float | None = None


@dataclass(frozen=True, slots=True)
class CounterfactualResult:
    """
    Simulated alternative path under explicit intervention.
    Always labeled ILLUSTRATIVE — model scenario, not observed fact.
    """
    baseline_run_id: str
    intervention: CounterfactualIntervention
    simulated_points: list[FittedPoint]
    stopping_distance_m: float | None
    stopping_time_s: float | None
    # Extrapolation warning: True if the slider is outside observed support
    extrapolation_outside_support: bool
    illustrative_label: str = "ILLUSTRATIVE — model scenario, not observed fact"
    assumptions_json: str = "{}"     # JSON dict of all declared assumptions


@dataclass(frozen=True, slots=True)
class SensitivityEntry:
    """How much does one input perturbation change stopping distance?"""
    parameter: str
    perturbation_value: float
    stopping_distance_delta_m: float
    # The measurement that would reduce this sensitivity most
    reducing_observation: str


# ── Rival hypotheses ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class RivalManifest:
    """
    Records the exact search that was performed — never implies exhaustiveness.
    """
    search_id: str
    primary_run_id: str
    dimensions_searched: list[str]
    bounds: dict[str, tuple[float, float]]
    strategy: str        # e.g. "grid_N50"
    seed: int
    objective: str       # e.g. "sum_squared_residuals"
    acceptance_threshold: float
    n_candidates_evaluated: int
    primary_observation_hash: str
    second_view_observation_hash: str | None


@dataclass(frozen=True, slots=True)
class RivalHypothesis:
    """One alternative reconstruction within the acceptance residual."""
    rank: int
    params: dict[str, float]
    residual: float           # objective value (lower = better fit)
    primary_residual: float   # primary fit residual for comparison
    materially_different: bool
    distinguishing_evidence: str | None   # what observation would reject it
    disambiguation_status: Literal["unresolved", "rejected_by_evidence", "rejected_by_residual"]
    rejection_reason: str | None


@dataclass(frozen=True, slots=True)
class RivalSearchResult:
    """Full output of the bounded rival search."""
    manifest: RivalManifest
    rivals: list[RivalHypothesis]
    # If rivals is empty: explicit message, not silence
    empty_search_message: str
    # True only when a second calibrated clip disambiguated a rival
    second_view_used: bool
    second_view_notes: str
