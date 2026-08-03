# Rotated-Hermitian geometry experiment

`run_inf_bus_hermitian_geometry` evaluates a tracked frequency-response
fixture derived from the author's stable and unstable infinite-bus converter
admittances over 0.1--5 Hz. A clean clone therefore does not require MATLAB
workspace snapshots or the full Simplus model to reproduce this experiment.

The fixture was generated with
`export_author_inf_bus_frequency_fixture` from these ignored source files:

- stable `baseline_workspace.mat` SHA-256:
  `7E8AF40D6F3EF19ED8024325BEED39587506003C5668009238DFB7B3917F72AB`;
- unstable `baseline_workspace.mat` SHA-256:
  `5CBF8616A37CD66DC04DDF02BAC5957595251F664B2F0800FD2452682C5668BC`;
- author code: repository release `v1.0.0`, commit
  `ef67c7a4ac84e4e1142e95b072d241db89eb64ba`.

The output records the numerical-range classification state separately from
the reliability of the critical-direction contribution decomposition. An
unresolved classification always makes `overall_numerical_status` pending.

The H/G terms are only an algebraic decomposition at one selected rotation
and critical direction. They are not controller contributions, parameter
causes, instability causes, or closed-loop stability margins. The two public
workbooks also differ in damping, grid impedance, operating point, and
reactive-power control, so their comparison is descriptive rather than a
single-parameter causal experiment.

Run:

```matlab
run_inf_bus_hermitian_geometry();
```
