# BuildingManager v18.8

## Fixes
- Core smoke tests now fail the CI job when checks fail.
- Translation table validation reports malformed, empty, and duplicate entries as test failures.
- Multi-month PDF reports require consecutive selected months to keep opening/closing balances consistent.
- PDF table fonts can grow up to the configured maximum when column space permits.
- Installer and release workflow versioning follows the v18.8 release identifier.

## Validation
The Windows build and application smoke tests are performed by the GitHub Actions release workflow. This release should only be considered stable after that workflow succeeds and the installer asset is attached.
