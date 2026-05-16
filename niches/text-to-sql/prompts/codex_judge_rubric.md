# Codex Judge Rubric

Score each candidate row from 0 to 100.

Reject immediately if:

- SQL does not execute.
- Result does not match `expected_result`.
- Row contains copied benchmark text or schema.
- Row contains placeholder/meta text.
- Gold SQL is unsafe or mutates data.

Rubric:

- 20 points: valid row contract and complete metadata.
- 25 points: SQL executes deterministically.
- 21 points: expected result exactly matches SQL output.
- 14 points: natural and useful training instruction.
- 10 points: leakage resistance.
- 10 points: meaningful difficulty signal.

Acceptance threshold: 85.

For every rejected row, produce one compact reason that can improve the next generator batch.
