## Code Review Guidelines

The primary goal of review is to detect bugs and regressions before merge.

Prioritize:
1. Correctness
2. Regression risks
3. Error and edge-case handling
4. Security
5. Data integrity
6. Concurrency and resource management
7. Performance regressions
8. Missing or inadequate tests

Only report actionable issues.

A finding must:
- identify a concrete problem,
- explain when the problem occurs,
- point to the relevant code,
- explain its likely impact.

Do not report:
- purely stylistic preferences,
- formatting issues handled by automated tools,
- speculative problems without a realistic failure scenario,
- refactoring suggestions that do not fix a bug or material maintainability issue,
- issues in unchanged code unless the current change makes them relevant.

Prefer a small number of high-confidence findings over many low-confidence comments.

## Severity

- P0: Critical. Must not merge.
- P1: Serious bug or regression likely to affect users.
- P2: Real issue that occurs under specific conditions.
- P3: Minor issue with limited impact.

Do not report P3 findings unless explicitly asked for a thorough review.

## Project-specific review rules

- Reproducibility is important.
- Flag nondeterministic behavior that may change experiment results.
- Check that random seeds are handled consistently.
- Do not silently change dataset preprocessing behavior.
- Pay particular attention to off-by-one errors and incorrect filtering.
- Verify that evaluation code does not leak gold labels into model inputs.
- Existing experiment result formats must remain backward compatible.

## Investigation workflow

- Whenever the user asks for an investigation, always save the code that provides the evidence for the findings under `investigation/`.
- Keep investigation code reproducible and executable; do not leave the supporting analysis only as an ad hoc shell command or an explanation in chat.
