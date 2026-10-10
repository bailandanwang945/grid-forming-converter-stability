# Virtual-reactance frequency-factor pilot (pre-run plan)

This is a bounded, deterministic, single-converter mechanism pilot, not an established innovation or two-converter interaction study. The sole change is virtual-reactance voltage reference from `-Xv*(1+frequency_deviation)*J*ig` to `-Xv*J*ig`. Capacitor and inductor frequency terms, PI gains, outer loops and network equations remain unchanged.

Author-model boundary: the parent audit identifies dynamic virtual admittance `Yv(s)=1/(s*Lv+Rv)` with a dq coordinate-transform `omega*Lv*J*i_ref` term. This pilot instead compares two team algebraic virtual-reactance variants. It is not a correction of an author omission, does not implement dynamic virtual admittance, and cannot establish a two-machine relative update-offset contribution.

- Fixed anchor: existing average-dq ablation preset, P=0.5 pu, Q=0.1 pu, D=60; external-line resistance and every other parameter unchanged.
- Fixed grid: line X=[0.2,0.4] pu; Xv=[0,0.1,0.3] pu; voltage/current PI gains at their existing baseline values. Six operating points, two variants each.
- Fixed sampled-command grid: Ts=[0.0001,0.0005,0.001] s; complete one-sample delay buffer absent/present (0/1); local-control-dq envelope hold. 72 records; retain all outcomes, including instability and pending labels.
- Independent control equations replace all affected voltage-integrator, current-integrator and modulation derivatives in a baseline nonlinear RHS; no production monkeypatch or direct one-entry matrix edit. Independent command Jacobian supplies F.
- Jacobian centered relative steps=[1e-5,5e-6]. Baseline production-matrix agreement, two-step agreement, analytic fixed-minus-frequency difference matrix, command split/reconstruction, equilibrium residual and exact common nominal-frequency equilibrium must pass.
- Tolerances fixed before execution: equilibrium absolute=1e-7; matrix/command relative=2e-7; analytic-difference relative=2e-7; spectral eigenpair relative residual=1e-9; numerical-pending label band=1e-5 per second. A step-dependent classification is pending. Classification uses the full spectrum (14 roots without delay, 16 with delay).
- Controls: Xv=0 removes RHS/Jacobian differences; zero-current artificial state removes RHS difference, and zero-current plus nominal frequency removes Jacobian difference. At zero current but nonnominal frequency the derivative with respect to current need not vanish, and is not falsely required to vanish.
- Main outputs: complete continuous/period-map spectra, alpha/log(rho)/Ts, matrix/source provenance, checks, all 72 sampled comparisons and observed classification disagreements. No grid tuning to find a favorable disagreement.
- Failure: any prescribed check fails or internal runtime exceeds 90 s -> save failure detail and exit nonzero. Tests also exit nonzero on failure.
- Boundaries: no physical digital controller/PWM/EMT/hardware validation, no two-machine interconnection, no theorem or novelty claim. No stability benefit is presupposed; an unchanged classification is a valid result.
