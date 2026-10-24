# Changelog

## Unreleased

### Added

- The `command` and `group` decorators turn functions into commands and groups, and a group's `add` method puts commands and groups into it.
- The `argument`, `option` and `flag` decorators fill a function's parameters from the command line, converted to the types of their annotations.
- Invalid input is reported all at once, with suggestions for close matches, and exits with code 2.
- `cliron.testing` provides `run`, which runs a CLI in the same process, and `validate`, which checks its whole definition.

### Changed

- Cliron is now a pure Python package, so one wheel installs on every platform.

## v0.1.0

### Added

- Initial release.
