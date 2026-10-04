# Observer-EGA Reference Package Review Copy

This directory contains an extracted review copy of the Observer → EGA reference package from:
`nextone-observer-ega-interop-reference-STAN-READY-FINAL.zip`

## Purpose

This extraction is provided for GitHub review accessibility. The original ZIP file remains unchanged at:
`../nextone-observer-ega-interop-reference-STAN-READY-FINAL.zip`

## Contents

This review copy includes all files from the original ZIP, preserving the directory structure:

- **docs/**: Documentation including `STAN_HANDOFF.md`, evidence contract, architecture, and compatibility notes
- **schemas/**: EvidenceEnvelope v1 schema (`evidence-envelope-v1.schema.json`)
- **fixtures/**: Golden, negative, and conflict test fixtures
- **src/**: Evidence-only Observer reference implementation
- **tests/**: Test suite including seam validation
- **scripts/**: Generation and validation utilities

The original package README is available as `ORIGINAL_PACKAGE_README.md`.

## File Types

All files in this package are text-based (UTF-8, ASCII, JSON, Python) and are directly inspectable through GitHub. No binary files are present.

## Note

This is a read-only review copy. Do not modify the existing EGA implementation, Observer implementation, adapters, schemas, tests, or contracts based on this package. This package is for seam review purposes only.
