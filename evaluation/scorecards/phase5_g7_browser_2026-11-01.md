# Phase 5 G7 browser renderer scorecard

- **gate:** G7-browser-renderer-smoke
- **status:** PARTIAL_PASS
- **executed at utc:** 2026-11-01 (local browser run)
- **fixture:** temporary in-memory synthetic scene with observed, fitted, counterfactual, and rival paths
- **browser:** local app in IAB, route `/phase5-render-check`
- **visual result:** all four trajectories and legend entries visible; persistent synthetic `ILLUSTRATIVE` banner visible; camera pose remained explicitly unknown and no frustum was shown
- **controls checked:** fitted/counterfactual/rival layer toggles, zoom range, reset view, source-time slider exposed and initial timestamp displayed
- **source-frame links:** not exercised; fixture has no original media
- **orbit/pan:** not verified; pointer automation API did not support the browser's PointerEvent constructor
- **production data:** not exercised; no SAM tracking credentials or calibrated production case were available
- **limitations:** synthetic QA route only; no WebGL or 2D fallback is involved because the viewer is a Canvas 2D ground-plane projection; screenshot was visually reviewed during the browser run

This is a renderer smoke check, not a pass of the full G7 browser acceptance gate. The temporary fixture route was removed after inspection.
