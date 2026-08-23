"""Level 0–1 intelligence: datasets (BDX-011), calibration (BDX-012),
outcomes (BDX-013), prediction uncertainty (BDX-014) and explainability
(BDX-015). Design-scenario comparison lives in ``design.scenarios`` (BDX-016).

Training never reads mutable production records. Predictions are overlays and
do not silently modify or approve an engineering design. A point estimate is
never returned without an interval, confidence, similarity, applicability
check and a driver / recommendation explanation.
"""
