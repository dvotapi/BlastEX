"""Level 0–1 intelligence: datasets (BDX-011), calibration (BDX-012),
outcomes (BDX-013), prediction uncertainty (BDX-014) and explainability
(BDX-015). Design-scenario comparison lives in ``design.scenarios`` (BDX-016).
Deterministic multi-objective search lives in ``design.optimization`` (BDX-017).
ML design recommendation (profiles, never auto-applied) lives in
``design.recommendation`` (BDX-018). Two-level learning (global prior plus
per-site adaptation, tenant isolation) lives in ``intelligence.learning``
(BDX-019). Formal model-registry lifecycle (human-gated promotion, checksum,
dataset lineage) lives in ``intelligence.registry`` (BDX-020). Feature /
target / prediction drift monitoring (alerts only, never auto-deploy) lives
in ``intelligence.drift`` (BDX-021). Hole- / neighborhood-level predictions
and residual maps live in ``intelligence.spatial`` (BDX-022).

Training never reads mutable production records. Predictions are overlays and
do not silently modify or approve an engineering design. A point estimate is
never returned without an interval, confidence, similarity, applicability
check and a driver / recommendation explanation. Snapshots and models of one
tenant never leak into another. Registry promotion is explicit and never
auto-deploys a candidate. Drift alerts never retrain or swap the live model.
Spatial overlays stay on the predicted layer and never overwrite designed
charges or the approved pattern.
"""
