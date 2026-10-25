from cliron._builtin_options import DEFAULT_BUILTINS, Builtins
from cliron._dependencies import check_combinations
from cliron._roots import Command, Group, location


def validate(cli: Command | Group) -> None:
    """
    Check a CLI's whole definition, including commands no test runs.

    A run only checks the commands on its own command line.

    :param cli: The command or group to check, with everything it contains.
    :raises TypeError: If a function, parameter or annotation doesn't fit its
        decorators.
    :raises ValueError: If a default doesn't fit its decorator, a flag is used
        twice, or dependencies name an input without a default, require each
        other in a cycle, contradict each other or repeat each other.
    """
    _validate(cli, DEFAULT_BUILTINS)


def _validate(cli: Command | Group, inherited: Builtins) -> None:
    builtins = cli.builtins(inherited)
    definition = cli.definition()
    try:
        check_combinations(definition.dependencies, definition.env, definition.labels)
    except ValueError as error:
        error.add_note(location(cli))
        raise
    for child in cli.commands.values():
        _validate(child, builtins)
