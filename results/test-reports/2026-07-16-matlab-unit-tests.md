# MATLAB Unit Test Report — 2026-07-16

## Scope

- Function: `src/classifyNumericalRange.m`
- Test class: `tests/classifyNumericalRangeTest.m`
- Runner: `experiments/run_unit_tests.m`
- MATLAB: R2024b

## Result

```text
Running classifyNumericalRangeTest
.........
Done classifyNumericalRangeTest

17 Passed, 0 Failed, 0 Incomplete.
4.0209 seconds testing time.
```

## Covered Behaviors

- strict sectorial positive-definite matrix;
- rotated strict-sectorial matrix;
- boundary matrix;
- non-sectorial nilpotent matrix;
- degenerate zero matrix;
- positive scale invariance;
- invalid non-square input;
- invalid non-finite input;
- invalid angular grid size.
- off-grid strict-sectorial case with and without local refinement;
- analytic Jordan boundary and non-sectorial cases;
- unitary-similarity invariance;
- complex-valued invalid options;
- conservative lower/upper-bound behavior.

## Limitations

- This test set does not yet distinguish semi-sectorial from quasi-sectorial;
- paper-frequency regression cases are not yet included;
- closed-loop stability is outside this unit test scope.
