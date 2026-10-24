# Changelog

## Unreleased

### Added

- The `command` and `group` decorators turn functions into commands and groups, and a group's `add` method puts commands and groups into it.
- The `argument`, `option` and `flag` decorators fill a function's parameters from the command line, converted to the types of their annotations.
- Invalid input is reported all at once, with suggestions for close matches, and exits with code 2.
- `cliron.testing` provides `run`, which runs a CLI in the same process, and `validate`, which checks its whole definition.
- Every command and group shows its help for `-h` and `--help`, built from its docstring and the `help` text of its arguments, options and flags, and listing the options of the groups around it.
- The `help_flags` parameter of `command` and `group` renames or turns off the help flags, and `version` adds a `--version` flag that prints it.
- Invalid input ends with a line that says how to get help, and a group run with nothing after it shows its help.

### Changed

- Cliron is now a pure Python package, so one wheel installs on every platform.

## v0.1.0

### Added

- Initial release.
