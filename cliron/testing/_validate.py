from cliron._roots import Command, Group


def validate(cli: Command | Group) -> None:
    """
    Check a CLI's whole definition, including commands no test runs.

    A run only checks the commands on its own command line.

    :param cli: The command or group to check, with everything it contains.
    :raises TypeError: If a function, parameter or annotation doesn't fit its
        decorators.
    :raises ValueError: If a default doesn't fit its decorator.
    """
    _ = cli.definition()
    for child in cli.commands.values():
        validate(child)
