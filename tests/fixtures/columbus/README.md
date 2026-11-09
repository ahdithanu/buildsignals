# Synthetic Columbus Intake Fixtures

These records are synthetic, non-qualified test data. They do not come from
Columbus, do not establish source rights, and must not be used as corpus or
coverage evidence.

The fixture contains two synthetic site-engineering permits, each represented
by a `permit.filed_at` observation and an `permit.approval_stage=approved`
observation. `first_observed_at` and `recorded_at` are deliberately set to the
2026-10-20 test receipt time so the fixture exercises the non-backdating policy.

The replay harness uses the bounded source ID `columbus-site-engineering`;
`catalog_source_key` preserves the longer catalog key for traceability.

The small fixture is intentionally below the historical qualification depth
threshold. It exists only to let offline tests and the replay harness exercise
the fixed TemporalObservation contract without network access or activation.
