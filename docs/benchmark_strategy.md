# Benchmark Strategy

The Text-to-SQL pack is built for public proof of work.

## Primary ladder

1. **Spider 1.0 dev**
   - Fast, well-known, local iteration benchmark.
   - Useful for basic schema linking, joins, nesting, grouping, and ordering.
   - Weakness: older benchmark and more contamination risk.

2. **BIRD dev**
   - More realistic databases and external knowledge.
   - Better proxy for production Text-to-SQL.
   - Good intermediate proof before larger enterprise workflows.

3. **Spider 2.0 Lite/Snow**
   - Enterprise-style workflows across SQLite, BigQuery, and Snowflake.
   - Much harder than classic Spider.
   - Best public target once the pipeline has a strong agentic/eval harness.

4. **LiveSQLBench**
   - Dynamic benchmark intended to reduce contamination.
   - Best target for credible public proof once the model and harness are stable.

## Success criteria

The first proof should be a published eval table with:

- Base model score.
- Fine-tuned model score.
- Same prompt/scaffold for both models.
- Exact benchmark version and commit.
- Evaluation command.
- Rejection rate during dataset generation.
- Number of accepted rows used for training.
- Training recipe and adapter checksum.

## What not to do

- Do not train on benchmark rows.
- Do not generate near-paraphrases of benchmark rows.
- Do not optimize for exact-match SQL only; execution accuracy matters more.
- Do not hide rejection rates. A high rejection rate is evidence that the filter is doing real work.
