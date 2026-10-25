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
- The `stdin` decorator fills a parameter from piped text, never waits for typing, and gives a list one item per line.
- `cliron.testing.run` takes `input`, the text to pipe into the CLI.
- The `dependencies` parameter of `command` and `group` relates inputs to each other with `dependency.requires`, `requires_any`, `conflicts`, `together`, `alone`, `at_least`, `at_most` and `exactly`, reports every broken dependency with the other input errors, and lists them under Dependencies in the help.
- `cliron.testing.validate` reports dependencies that contradict or repeat each other.
- A mistake in a CLI's definition that is found when it runs is printed as an error that says where the mistake is, instead of a traceback, and exits with 1.
- The `between`, `choices`, `length` and `matches` decorators check a parameter's value below its parent, and help shows what they accept.
- `Child` and `child` let you write your own children, as a subclass with `process` and `describe` methods or as a function whose other parameters become its options.
- A first child that takes `str` receives the text as typed, so a parameter can have any type that the child converts the text to.
- A child that doesn't fit its parameter's type, returns a value of another type or is written without parentheses is reported as a mistake in the definition.
- The `file` and `directory` decorators check that a path is an existing file or directory, or with `exists=False` that nothing is there yet, and check a default path on each run that uses it.
- A child class can set `default_check = "run"` to have the default checked on each run that uses it, instead of once with the definition.
- `Parent` and `parent` let you write your own parents, which load a parameter's text from anywhere, as a subclass with `load`, `label` and `missing` methods or as a function that takes the parameter's name.
- Every parent, built-in or your own, is a `Parent`, so `isinstance` recognizes all of them.
- Errors and help name an option or flag that has a short flag by both flags, such as `-k/--keep`.
- A function's parameter annotated `Context` receives the path of the run, as users typed it.
- The `state` decorator marks a class for your own data: every parameter annotated with it receives the run's one instance, so groups and commands can share it.
- A group's function that yields once runs the code after its `yield` when everything inside the group has finished, even on failure, and the command's output is printed only once every teardown has succeeded.
- The `hook` decorator runs a function when a command or group starts, succeeds or exits, chosen with `on.start()`, `on.success()` and `on.exit()`, and a group's hooks wrap everything inside it.
- `Context.values` holds the values of every command and group on the path, in the same order as `Context.path`.

### Changed

- Cliron is now a pure Python package, so one wheel installs on every platform.

## v0.1.0

### Added

- Initial release.
