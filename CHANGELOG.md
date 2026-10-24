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
- Ctrl+C ends a CLI without a traceback, SIGTERM runs cleanup before exiting with 143 unless the program already handles or ignores it, and on Linux and macOS output into a pipe that closes early ends quietly.
- The `env` decorator fills a parameter from an environment variable, and help lists the variables a command reads under Environment.
- `cliron.testing.run` takes `env`, the environment variables to run the CLI with in place of the test's own.

### Changed

- Cliron is now a pure Python package, so one wheel installs on every platform.

## v0.1.0

### Added

- Initial release.
