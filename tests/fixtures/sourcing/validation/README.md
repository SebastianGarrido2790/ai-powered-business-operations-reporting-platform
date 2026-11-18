# Validation fixtures

- `valid.yaml` — a complete single-source configuration covering supplier,
  quote, and delivery sections.
- `sensitive_supplier.yaml` — the same coverage with a sensitive, patterned
  supplier name field.
- `malformed.yaml` — an intentionally unparseable YAML document.

The per-code synthetic records, including positive, negative, boundary,
malformed, and sensitive cases, are typed builders in
`tests/support/validation_cases.py`. Keeping them as Python objects avoids
duplicating the closed catalog and lets the coverage meta-test inspect them
directly. YAML configurations live here because they exercise the real loader.
