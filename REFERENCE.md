# Reference

Every public function and class in cliron, with its parameters and defaults. The [guide](GUIDE.md) shows how they fit together.

A wrong argument to any of them, such as a name that isn't snake_case, raises `TypeError` or `ValueError` when your module is imported, with a message that says what to change.

| Name                                                   | What it does                                                       |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| [`command`, `group`](#command-and-group)               | Turn a function into a command, or a group of commands             |
| [`notes()`, `notes.add`](#running-and-filling-a-group) | Run a command or group, and add commands to a group                |
| [`notes.lazy`](#noteslazy)                             | Adds a command that's imported only when it's needed               |
| [`argument`](#argument)                                | Fills a parameter from a word on the command line                  |
| [`option`](#option)                                    | Fills a parameter from an option with a value, such as `--count 3` |
| [`flag`](#flag)                                        | Fills a parameter from a flag without a value, such as `--verbose` |
| [`env`](#env)                                          | Fills a parameter from an environment variable                     |
| [`stdin`](#stdin)                                      | Fills a parameter from the text piped into the program             |
| [`fallback`](#fallback)                                | Fills a parameter when the parent above has no value               |
| [`parent`](#parent), [`Parent`](#parent-1)             | Make your own parent                                               |
| [`between`](#between)                                  | Checks that a value lies between two bounds                        |
| [`length`](#length)                                    | Checks the number of characters in a text                          |
| [`matches`](#matches)                                  | Checks a text against a regular expression                         |
| [`choices`](#choices)                                  | Checks that a value is one of several                              |
| [`file`, `directory`](#file-and-directory)             | Check that a path is a file, or a directory                        |
| [`child`](#child), [`Child`](#child-1)                 | Make your own child                                                |
| [`dependency`](#dependencies)                          | Rules between inputs, such as two that go together                 |
| [`hook`, `on`](#hook)                                  | Run a function around a command or group, or handle its errors     |
| [`state`](#state)                                      | Shares your own data between the functions of a run                |
| [`Context`](#context)                                  | Holds the path and the values of a run                             |
| [`cliron.testing.run`](#run)                           | Runs a CLI in a test                                               |
| [`cliron.testing.validate`](#validate)                 | Checks a CLI's whole definition                                    |
| `__version__`                                          | The installed version of cliron, as a string                       |

## Commands and groups

### `command` and `group`

Turn a function into a command, or a group of commands.

```python
command(name, *, aliases=(), help_flags=True, version=None, dependencies=(), platforms=None, enabled=None)
group(name, *, aliases=(), help_flags=True, version=None, dependencies=(), platforms=None, enabled=None)
```

| Parameter      | Default  | What it does                                                                                                                                |
| -------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`         | required | Its name, in snake_case. Users type it in kebab-case                                                                                        |
| `aliases`      | `()`     | Other names that run it, such as `"ls"` or `["ls", "l"]`. Help lists them next to the name                                                  |
| `help_flags`   | `True`   | The flags that show help. `True` takes the enclosing group's, or `-h` and `--help` at the top. `False` or `[]` turns help off               |
| `version`      | `None`   | What `--version` prints, such as `"1.4.0"`. `None` takes the enclosing group's                                                              |
| `dependencies` | `()`     | [Rules between its inputs](#dependencies), such as `[dependency.together("user", "password")]`                                              |
| `platforms`    | `None`   | The platforms it runs on, from `"linux"`, `"macos"` and `"windows"`, such as `"linux"` or `["linux", "macos"]`. `None` means every platform |
| `enabled`      | `None`   | A function without arguments that says whether it can be used, such as one that checks the user's role. `None` means always                 |

A group's `help_flags` and `version` also apply to everything in it that doesn't set its own.

When `enabled` returns `False`, help and suggestions leave it out, and running it is an error. A completion script made at that moment leaves it out too. For a group, this covers everything in it. `enabled` can't be `async def`.

On a platform that `platforms` doesn't name, it's left out the same way, and running it says where it runs, such as `'tool mount' runs only on Linux.` `enabled` is called only on the platforms it names. Other systems, such as FreeBSD, match none of them.

|                        | Command                            | Group                                                                   |
| ---------------------- | ---------------------------------- | ----------------------------------------------------------------------- |
| Its function runs      | When it's the command asked for    | Before the command asked for, with its own options, flags and variables |
| Its function returns   | What's written to stdout, as below | `None`                                                                  |
| Its function can yield | No                                 | Once. The code after `yield` runs when the command has finished         |

A command succeeds by returning and fails by raising. cliron writes the return value to stdout, followed by a line break, and exits with 0. A `str` is written as it is, nothing is written for `None`, and anything else is written as JSON, indented by two spaces. A value JSON can't represent, such as a `Path`, a `set` or `float("nan")`, is an error, with exit code 1. An exception goes to stderr, with the [exit code](GUIDE.md#exit-codes) it causes, and help goes to stdout.

When the command fails, the exception is raised at the group's `yield`, so `finally` and `except` around it run. The exception still goes on, even when the group catches it.

### Running and filling a group

Below, `notes` is a command or group. `add` and `lazy` exist on groups only.

| Call                | Does                                                                                                        |
| ------------------- | ----------------------------------------------------------------------------------------------------------- |
| `notes()`           | Runs the command line in `sys.argv`, and exits with its [exit code](GUIDE.md#exit-codes)                    |
| `notes.add(*nodes)` | Adds commands and groups to the group, in the order given. A name or alias can't be used twice in one group |

What `notes()` does when the run doesn't go as planned:

| When                                       | It                                                                                                                    |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| Ctrl+C is pressed                          | Ends without a traceback                                                                                              |
| SIGTERM arrives, or Ctrl+Break on Windows  | Raises `SystemExit(143)` on the main thread, so cleanup runs, unless the program handles or ignores the signal itself |
| Output goes to a closed pipe               | Ends quietly with exit code 1, on Linux and macOS                                                                     |
| It finds a mistake in the CLI's definition | Prints it with where it was made, instead of a traceback, and exits with 1                                            |

These environment variables make it print a [measurement](GUIDE.md#10-measuring) on stderr when the run ends:

| Variable        | Prints                                   |
| --------------- | ---------------------------------------- |
| `CLIRON_TIME`   | The time since `cliron` was imported     |
| `CLIRON_CPU`    | The CPU time since `cliron` was imported |
| `CLIRON_MEMORY` | The process's peak memory                |

The value is the unit. Time takes `ns`, `us`, `ms` or `s`, and memory takes `b`, `kb`, `mb` or `gb`. An empty value or `0` turns it off, and any other value uses `ms` or `mb`.

### `notes.lazy`

Adds a command or group to the group, and imports it only when it's needed.

```python
notes.lazy(name, target, *, aliases=(), help=None, platforms=None, enabled=None)
```

| Parameter   | Default  | What it does                                                                                                   |
| ----------- | -------- | -------------------------------------------------------------------------------------------------------------- |
| `name`      | required | Its name, in snake_case                                                                                        |
| `target`    | required | Where it is, as `"module:attribute"`, such as `"notes.archive:archive"`                                        |
| `aliases`   | `()`     | Other names that run it, such as `"ar"` or `["ar", "old"]`                                                     |
| `help`      | `None`   | The line the group's help shows for it                                                                         |
| `platforms` | `None`   | The platforms it runs on, as for [`command`](#command-and-group). They're checked without importing the module |
| `enabled`   | `None`   | Whether it can be used, as for [`command`](#command-and-group). It's checked without importing the module      |

The module, and everything it imports, is imported only when:

- the command line runs it or shows its help;
- Tab completes one of its values;
- a completion script is made while it's enabled;
- [`validate`](#validate) checks the CLI.

Once imported, its name, aliases, `platforms` and `enabled` must be the ones given here. The platforms may be listed in any order.

## Parents

A parent fills one parameter of the function with what users give, converted to the parameter's [annotation](GUIDE.md#types). When they give nothing, the parameter's default is used.

### `argument`

Fills a parameter of a command from a word on the command line.

```python
argument(name, *, help=None, completions=None)
```

| Parameter     | Default  | What it does                                                                                                                                                                                      |
| ------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`        | required | The parameter to fill. Help and errors show it in capitals, such as `NAME`                                                                                                                        |
| `help`        | `None`   | What help says about it                                                                                                                                                                           |
| `completions` | `None`   | What Tab offers, as a list of values or a function that takes the text typed so far and returns the values. It replaces the files or choices offered otherwise, and doesn't limit what's accepted |

Arguments are filled in the order of their decorators. A `list` or `tuple` argument takes every remaining word, so it comes last.

A `completions` function runs each time Tab is pressed, and may be `async def`.

### `option`

Fills a parameter of a command or group from an option that takes a value.

```python
option(name, short=None, *, long=None, help=None, completions=None)
```

| Parameter     | Default  | What it does                                                                    |
| ------------- | -------- | ------------------------------------------------------------------------------- |
| `name`        | required | The parameter to fill. Users type it in kebab-case, so `dry_run` is `--dry-run` |
| `short`       | `None`   | A short flag, such as `"-c"`                                                    |
| `long`        | `None`   | The flag users type instead of the derived one, such as `"--output"`            |
| `help`        | `None`   | What help says about it                                                         |
| `completions` | `None`   | What Tab offers for its value, as for [`argument`](#argument)                   |

Users type `--count 3`, `--count=3`, `-c 3` or `-c3`. An option annotated `list[X]` can be given several times.

### `flag`

Fills a parameter of a command or group from a flag that takes no value.

```python
flag(name, short=None, *, long=None, help=None)
```

| Parameter | Default  | What it does                                                                    |
| --------- | -------- | ------------------------------------------------------------------------------- |
| `name`    | required | The parameter to fill. Users type it in kebab-case, so `dry_run` is `--dry-run` |
| `short`   | `None`   | A short flag, such as `"-v"`                                                    |
| `long`    | `None`   | The flag users type instead of the derived one, such as `"--output"`            |
| `help`    | `None`   | What help says about it                                                         |

A `bool` parameter is `True` when the flag is given. An `int` parameter counts how often it's given, so `-vvv` is `3`.

### `env`

Fills a parameter of a command or group from an environment variable.

```python
env(name, *, variable=None, help=None)
```

| Parameter  | Default  | What it does                                                                                |
| ---------- | -------- | ------------------------------------------------------------------------------------------- |
| `name`     | required | The parameter to fill. The variable is the name in capitals, so `notes_db` reads `NOTES_DB` |
| `variable` | `None`   | A variable to read instead, such as `"GITHUB_TOKEN"`                                        |
| `help`     | `None`   | What help says about it, under Environment                                                  |

A variable set to an empty value counts as not set.

### `stdin`

Fills a parameter of a command from the text piped into the program.

```python
stdin(name, *, help=None)
```

| Parameter | Default  | What it does                         |
| --------- | -------- | ------------------------------------ |
| `name`    | required | The parameter to fill                |
| `help`    | `None`   | What help says about it, under Input |

It never reads from a terminal, so the program never waits for typing. One final line break is dropped, and a `list` or `tuple` gets one item per line.

### `fallback`

Fills the parameter of the parent above when that parent has no value.

```python
fallback(*, env=None, fn=None, prompt=None, hidden=False)
```

| Parameter | Default | What it does                                                                                                                                |
| --------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `env`     | `None`  | An environment variable to read, such as `"API_TOKEN"`. An empty value counts as not set                                                    |
| `fn`      | `None`  | A function that takes the parameter's name and returns its text, or `None` if there's none. It may be `async def`, or a [`parent`](#parent) |
| `prompt`  | `None`  | `True` to ask at the terminal, such as `Api token:` for `api_token`, or the question to ask instead                                         |
| `hidden`  | `False` | Whether the answer to `prompt` stays hidden while it's typed, as for a password                                                             |

Give exactly one of `env`, `fn` and `prompt`. A fallback goes below its parent, above the parent's children, and the parent's parameter takes one value, not a list or tuple.

When the parent has no text, each fallback below it is tried top-down, and the first one with text gives the value. It's converted, and checked by the parent's children, like the parent's own text. When none has text, the parameter's default is used.

`prompt` asks only when stdin is a terminal. It doesn't ask when the command line has words that fit nowhere, or when an input before it has failed. An empty answer counts as no text.

### `parent`

Turns a function into your own parent.

```python
parent(function)
```

The function takes the parameter's name, and returns its text or `None` if there's none. It may be `async def`. `def git_branch(name: str) -> str | None` is used as `@git_branch("branch", help="The branch to deploy.")`, like any parent.

The parameter takes one value, not a list or tuple. For a parent with options of its own, subclass [`Parent`](#parent-1).

### `Parent`

The class of every parent, from `option` to `env`. Subclass it for a parent with options of its own.

```python
Parent(name, *, help=None)
```

| Method      | What it does                                                                                                                                                   |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `load()`    | Returns the parameter's text, or `None` if there's none. Every subclass implements it, and it may be `async def`                                               |
| `label()`   | Returns the parent's name in help and errors, such as `--keep` or `$API_KEY`. By default, the parameter's name. Two parents of one command can't share a label |
| `missing()` | Returns the error for a required input without a value, such as `"--host is required."`                                                                        |

An instance, such as `@DotEnv("api_key")`, goes above the function like any parent. cliron converts the text to the parameter's annotation and runs the children below it. `self.name` and `self.help` hold what it was created with. The parameter takes one value, not a list or tuple.

## Children

A child goes below the parent whose value it checks or changes. The children of one parent run top-down, each on what the one above returned.

### `between`

Checks that a value lies between two bounds, both included.

```python
between(low=None, high=None)
```

Give one bound or both. One alone leaves the other side open, so `between(low=1)` allows 1 and up, and `between(high=100)` allows up to 100.

It checks `int`, `float`, `date`, `datetime` and `time` values, with bounds of the same kind. Give both bounds a time zone, or neither. A value whose time zone doesn't match the bounds' is invalid.

### `length`

Checks that a text has a number of characters between two bounds, both included.

```python
length(low=None, high=None)
```

Give one bound or both, each 1 or more. `length(low=1)` allows any text that isn't empty, and `length(high=20)` allows at most 20 characters.

### `matches`

Checks that the whole text matches a regular expression, such as `matches(r"[a-z0-9-]+")`.

```python
matches(pattern)
```

### `choices`

Checks that a value is one of several.

```python
choices(*values)
```

Give the values one by one, such as `choices("zip", "tar")`, or as one list, tuple, set or frozenset. They're of the parameter's type, and help lists them in place of the value's placeholder.

For an Enum, annotate the parameter with it, and use `choices` to allow only some of its members.

### `file` and `directory`

Check that a path is a file, or a directory.

```python
file(*, exists=True)
directory(*, exists=True)
```

| `exists` | The path           |
| -------- | ------------------ |
| `True`   | Must exist         |
| `False`  | Must not exist yet |
| `None`   | May exist or not   |

Anything but a directory counts as a file, such as `/dev/null`. Both follow symbolic links, and check the parameter's default on each run that uses it.

### `child`

Turns a function into your own child.

```python
child(function)
```

The function takes the value as its first parameter, and returns the value passed on. To reject the value, it raises `ValueError` with a message that says why.

Its other parameters become the child's options, so `def slug(value: str, separator: str = "-") -> str` is used as `@slug()` or `@slug(separator="_")`.

### `Child`

The class of every child. Subclass it for a child with its own sentence in help.

```python
class Even(Child[int, int]):
    def process(self, value: int, /) -> int: ...
```

| Member              | What it does                                                                                                                                                                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `process(value, /)` | Returns the value passed on, or raises `ValueError` with a message that says why it isn't valid, such as `"3 isn't even."`. Every subclass implements it, and it may be `async def`                                                           |
| `describe()`        | Returns a sentence that help adds to the parameter's, or `None` for nothing. By default, `None`                                                                                                                                               |
| `default_check`     | When the parameter's default is checked. `"definition"`, the default, checks it once with the CLI's definition, and `"run"` checks it on each run that uses it, for a child that depends on more than the value, such as the files that exist |

The types in `Child[int, int]` are the value it takes and the value it returns. cliron reads them from the annotations of `process`, so a first child whose `process` takes `str` gets the text, and can convert it. An async `process` checks the default on each run, as with `default_check = "run"`.

An instance, such as `@Even()`, goes below the parent like any child.

## Dependencies

Rules between the inputs of one command or group. Pass them to `dependencies`, naming each input by its parameter:

```python
@command("login", dependencies=[dependency.together("user", "password")])
```

| Dependency                                    | Means                                                                        |
| --------------------------------------------- | ---------------------------------------------------------------------------- |
| `dependency.requires("a", "b", ...)`          | If `a` is given, all the others must be too                                  |
| `dependency.requires_any("a", "b", "c", ...)` | If `a` is given, at least one of the others must be                          |
| `dependency.conflicts("a", "b", ...)`         | If `a` is given, none of the others may be. The others may still go together |
| `dependency.together("a", "b", ...)`          | All of them, or none                                                         |
| `dependency.alone("a")`                       | If `a` is given, no other input may be                                       |
| `dependency.at_least(n, "a", "b", ...)`       | At least `n` of them                                                         |
| `dependency.at_most(n, "a", "b", ...)`        | At most `n` of them                                                          |
| `dependency.exactly(n, "a", "b", ...)`        | Exactly `n` of them                                                          |

A dependency looks only at which inputs were given, never at their values. It names only inputs with a default. `n` is from 1 to one less than the number of inputs.

For `alone`, inputs filled by `env` or a `fallback` don't count, so a variable set in the shell never stands in the way. When `a` itself comes from `env`, setting its variable counts as giving it.

## Running

### `hook`

Runs a function when an event happens around a command or group.

```python
hook(event, callback)
```

| Parameter  | Default  | What it does                      |
| ---------- | -------- | --------------------------------- |
| `event`    | required | When to run, such as `on.start()` |
| `callback` | required | The function to run               |

It goes right below `@command` or `@group`, above the first parent, as in `@hook(on.exit(), log)`. Its function gets `Context` and `@state` classes by their annotations, like a command's, and returns `None`, except for `on.error()`.

| Event          | Runs                                                                                                                                                                 |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `on.start()`   | Before the command or group, and before everything inside a group                                                                                                    |
| `on.success()` | After it succeeded, a group's code after `yield` included, or after its error hook handled an exception. Its own error hooks don't cover this hook                   |
| `on.exit()`    | After it, whether it succeeded or failed, like `finally`. If one of its start hooks fails, none of its exit hooks run, even when an error hook handles the exception |
| `on.error()`   | When an exception leaves it                                                                                                                                          |

The hooks of one event run in the order they're written. A hook that raises fails the run, as the command would, unless an error hook handles it. The later hooks of the same event don't run.

An `on.error()` hook's function takes the exception as the parameter annotated with the exceptions it handles, such as `exc: FileNotFoundError`. The first matching hook of the command or group runs.

- It covers the start hooks, the function, and everything inside a group. It doesn't cover the success and exit hooks, `SystemExit`, `KeyboardInterrupt` or mistakes in the definition.
- When it returns, the exception is handled. What a command's hook returns becomes the command's result, so it must fit the command's return annotation, such as a `str` for `-> str`. A value that doesn't fit is an error, with exit code 1. A group's hook returns `None`.
- When it raises, the exception goes on to the groups outside.

Only `on.error()` can also go below a parent or a child. There, its function takes only the exception, and returns the parameter's value.

### `state`

Makes a class hold your own data during a run.

```python
@state
class Session:
    user: str
```

A parameter annotated with the class, in a command's or group's function or one of their hooks, gets the run's one instance of it, whatever the parameter is called. cliron creates it without arguments when a function first asks for it, so every function in a run shares it, and the next run starts with a new one.

A field without a default stays unset until a function sets it. A field can't default to a list, dict or set, since every run would share it.

### `Context`

What cliron knows about the run. A parameter annotated `Context`, in a command's or group's function or one of their hooks, gets it, whatever the parameter is called.

| Attribute | Holds                                                                                                                        |
| --------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `path`    | The names on the path to what runs, in kebab-case, with aliases replaced by names, such as `("notes", "tags", "rename-tag")` |
| `values`  | The values of each command and group on the path, in the same order, by parameter name, so `ctx.values[-1]` is the command's |

## Testing

These come from `cliron.testing`.

### `run`

Runs a CLI in this process, as a test would run it in its own.

```python
run(cli, args, *, env=None, input=None, terminal=False)
```

| Parameter  | Default  | What it does                                                                                                                                    |
| ---------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `cli`      | required | The command or group to run                                                                                                                     |
| `args`     | required | The command line after the program's name, one word per item, such as `["add", "milk"]`                                                         |
| `env`      | `None`   | The environment variables to run with, in place of `os.environ`, which is restored afterwards. `None` keeps the environment as it is            |
| `input`    | `None`   | The text to pipe in. `None` pipes nothing, as when stdin is the null device                                                                     |
| `terminal` | `False`  | Whether stdin is a terminal, so that a `prompt` fallback asks and reads its answers from `input`, one line each, and `stdin` sees nothing piped |

It returns a `subprocess.CompletedProcess` with `returncode`, `stdout` and `stderr`. An exception the CLI doesn't handle is raised, so the test fails with its traceback, and so is a mistake in the definition. A `SystemExit` the CLI raises becomes the exit code.

`CLIRON_TIME`, `CLIRON_CPU` and `CLIRON_MEMORY` count only when they're in `env`, so a shell's variables don't change a test's output. The time and CPU time count from the start of the run.

### `validate`

Checks a CLI's whole definition, including commands no test runs.

```python
validate(cli)
```

A run checks only the commands on its own command line, and only `validate` checks whether dependencies contradict or repeat each other. It raises:

| Exception     | When                                                                                                                                                          |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TypeError`   | A function, parameter or annotation doesn't fit its decorators, or a lazy command's target isn't a command or group                                           |
| `ValueError`  | A default doesn't fit its decorator, a flag is used twice, or a lazy command's name, aliases, `platforms` or `enabled` differ from the ones it was added with |
| `ValueError`  | Dependencies name an input without a default, require each other in a cycle, or contradict or repeat each other                                               |
| `ImportError` | A lazy command's module or attribute doesn't exist                                                                                                            |
