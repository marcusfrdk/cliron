from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, final

from cliron._names import joined

Label = Callable[[str], str]
CountKind = Literal["at_least", "at_most", "exactly"]

_EXAMPLE = 'dependency.together("user", "password")'
_PAIR = 2


@dataclass(frozen=True)
class Given:
    names: tuple[str, ...]
    env: frozenset[str]


@dataclass(frozen=True)
class Requires:
    name: str
    others: tuple[str, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.others)

    @property
    def call(self) -> str:
        return _call("requires", self.names)

    def met(self, given: Given) -> bool:
        return self.name not in given.names or all(
            other in given.names for other in self.others
        )

    def sentence(self, label: Label) -> str:
        return f"{label(self.name)} requires {_and(label, self.others)}."

    def problem(self, given: Given, label: Label) -> str:
        missing = [other for other in self.others if other not in given.names]
        return f"{label(self.name)} requires {_and(label, missing)}."


@dataclass(frozen=True)
class RequiresAny:
    name: str
    others: tuple[str, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.others)

    @property
    def call(self) -> str:
        return _call("requires_any", self.names)

    def met(self, given: Given) -> bool:
        return self.name not in given.names or any(
            other in given.names for other in self.others
        )

    def sentence(self, label: Label) -> str:
        return f"{label(self.name)} requires {_or(label, self.others)}."

    def problem(self, given: Given, label: Label) -> str:
        _ = given
        return self.sentence(label)


@dataclass(frozen=True)
class Conflicts:
    name: str
    others: tuple[str, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.others)

    @property
    def call(self) -> str:
        return _call("conflicts", self.names)

    def met(self, given: Given) -> bool:
        return self.name not in given.names or not any(
            other in given.names for other in self.others
        )

    def sentence(self, label: Label) -> str:
        return f"{label(self.name)} can't be used with {_or(label, self.others)}."

    def problem(self, given: Given, label: Label) -> str:
        present = [other for other in self.others if other in given.names]
        return f"{label(self.name)} can't be used with {_and(label, present)}."


@dataclass(frozen=True)
class Together:
    names: tuple[str, ...]

    @property
    def call(self) -> str:
        return _call("together", self.names)

    def met(self, given: Given) -> bool:
        return len(_present(self.names, given)) in {0, len(self.names)}

    def sentence(self, label: Label) -> str:
        return f"{_and(label, self.names)} must be given together."

    def problem(self, given: Given, label: Label) -> str:
        what = _what(label, _present(self.names, given), self.names, too_few=True)
        return f"{_and(label, self.names)} must be given together, but {what}."


@dataclass(frozen=True)
class Alone:
    name: str

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name,)

    @property
    def call(self) -> str:
        return _call("alone", self.names)

    def met(self, given: Given) -> bool:
        return self.name not in given.names or not self._others(given)

    def sentence(self, label: Label) -> str:
        return f"{label(self.name)} must be given alone."

    def problem(self, given: Given, label: Label) -> str:
        others = self._others(given)
        verb = "was" if len(others) == 1 else "were"
        return (
            f"{label(self.name)} must be given alone, "
            f"but {_and(label, others)} {verb} too."
        )

    def _others(self, given: Given) -> list[str]:
        return [
            name for name in given.names if name != self.name and name not in given.env
        ]


@dataclass(frozen=True)
class Count:
    kind: CountKind
    count: int
    names: tuple[str, ...]

    @property
    def call(self) -> str:
        return _call(self.kind, self.names, self.count)

    def met(self, given: Given) -> bool:
        present = len(_present(self.names, given))
        if self.kind == "at_least":
            return present >= self.count
        if self.kind == "at_most":
            return present <= self.count
        return present == self.count

    def sentence(self, label: Label) -> str:
        names = _and(label, self.names)
        number = self.count
        if self.kind == "at_least":
            return f"At least {number} of {names} must be given."
        if self.kind == "at_most":
            return f"At most {number} of {names} can be given."
        return f"Exactly {number} of {names} must be given."

    def problem(self, given: Given, label: Label) -> str:
        present = _present(self.names, given)
        what = _what(label, present, self.names, too_few=len(present) < self.count)
        sentence = self.sentence(label)
        return f"{sentence[0].lower()}{sentence[1:-1]}, but {what}."


Dependency = Requires | RequiresAny | Conflicts | Together | Alone | Count

_KINDS = (Requires, RequiresAny, Conflicts, Together, Alone, Count)


@final
class Dependencies:
    """
    The dependencies that relate a command's or group's inputs to each other.

    Pass them to the ``dependencies`` parameter of ``command`` or ``group``,
    such as ``dependencies=[dependency.together("user", "password")]``.
    Inputs are named by their parameters' names, and a dependency only looks
    at which inputs were given, never at their values.
    """

    def requires(self, name: str, other: str, *others: str) -> Dependency:
        """
        Require other inputs whenever an input is given.

        :param name: The input that needs the others.
        :param other: An input it needs.
        :param others: More inputs it needs.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If a name isn't a string.
        :raises ValueError: If a name is given twice.
        """
        names = _names("requires", (name, other, *others))
        return Requires(names[0], names[1:])

    def requires_any(
        self, name: str, first: str, second: str, *others: str
    ) -> Dependency:
        """
        Require at least one of several inputs whenever an input is given.

        :param name: The input that needs one of the others.
        :param first: An input that would do.
        :param second: Another input that would do.
        :param others: More inputs that would do.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If a name isn't a string.
        :raises ValueError: If a name is given twice.
        """
        names = _names("requires_any", (name, first, second, *others))
        return RequiresAny(names[0], names[1:])

    def conflicts(self, name: str, other: str, *others: str) -> Dependency:
        """
        Forbid other inputs whenever an input is given.

        The others may still be given together.

        :param name: The input that excludes the others.
        :param other: An input it can't be used with.
        :param others: More inputs it can't be used with.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If a name isn't a string.
        :raises ValueError: If a name is given twice.
        """
        names = _names("conflicts", (name, other, *others))
        return Conflicts(names[0], names[1:])

    def together(self, first: str, second: str, *others: str) -> Dependency:
        """
        Require all of several inputs, or none of them.

        :param first: An input.
        :param second: Another input.
        :param others: More inputs.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If a name isn't a string.
        :raises ValueError: If a name is given twice.
        """
        return Together(_names("together", (first, second, *others)))

    def alone(self, name: str) -> Dependency:
        """
        Forbid every other input that is typed or piped in with an input.

        Environment variables don't count, so one set in the shell never
        stands in the way.

        :param name: The input that must be given alone.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If the name isn't a string.
        """
        return Alone(_names("alone", (name,))[0])

    def at_least(self, count: int, first: str, second: str, *others: str) -> Dependency:
        """
        Require at least a number of several inputs.

        :param count: How many must be given, from 1 to one less than the
            number of inputs.
        :param first: An input.
        :param second: Another input.
        :param others: More inputs.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If ``count`` isn't an int or a name isn't a string.
        :raises ValueError: If a name is given twice, or ``count`` is out of
            range.
        """
        return _counted("at_least", count, (first, second, *others))

    def at_most(self, count: int, first: str, second: str, *others: str) -> Dependency:
        """
        Allow at most a number of several inputs.

        :param count: How many may be given, from 1 to one less than the
            number of inputs.
        :param first: An input.
        :param second: Another input.
        :param others: More inputs.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If ``count`` isn't an int or a name isn't a string.
        :raises ValueError: If a name is given twice, or ``count`` is out of
            range.
        """
        return _counted("at_most", count, (first, second, *others))

    def exactly(self, count: int, first: str, second: str, *others: str) -> Dependency:
        """
        Require exactly a number of several inputs.

        :param count: How many must be given, from 1 to one less than the
            number of inputs.
        :param first: An input.
        :param second: Another input.
        :param others: More inputs.
        :returns: A dependency for the ``dependencies`` parameter.
        :raises TypeError: If ``count`` isn't an int or a name isn't a string.
        :raises ValueError: If a name is given twice, or ``count`` is out of
            range.
        """
        return _counted("exactly", count, (first, second, *others))


dependency = Dependencies()


def dependencies_for(value: object, decorator: str) -> tuple[Dependency, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        shown = value.call if isinstance(value, _KINDS) else repr(value)
        message = (
            f"@{decorator} takes dependencies as a list, such as "
            f"dependencies=[{_EXAMPLE}], not {shown}."
        )
        raise TypeError(message)
    found: list[Dependency] = []
    for item in value:
        if not isinstance(item, _KINDS):
            message = (
                f"@{decorator} takes dependencies made with dependency, "
                f"such as {_EXAMPLE}, not {item!r}."
            )
            raise TypeError(message)
        found.append(item)
    return tuple(found)


def cycle_problem(
    dependencies: Sequence[Dependency], labels: Mapping[str, str]
) -> str | None:
    needs: dict[str, list[str]] = {}
    for found in dependencies:
        if isinstance(found, Requires):
            needs.setdefault(found.name, []).extend(found.others)
    for start in needs:
        cycle = _cycle_from(start, needs, [start])
        if cycle is not None:
            each_other = (
                "each other" if len(cycle) == _PAIR else "each other in a cycle"
            )
            return (
                f"{_and(labels.__getitem__, cycle)} require {each_other}. "
                f"Use {_call('together', cycle)} instead."
            )
    return None


def check_combinations(
    dependencies: Sequence[Dependency], env: frozenset[str], labels: Mapping[str, str]
) -> None:
    label = labels.__getitem__
    for names, related in _groups(dependencies, env):
        valid = [given for given in _combinations(names, env) if _meets(related, given)]
        calls = joined([found.call for found in related], "and")
        if not valid:
            message = (
                f"these dependencies can never all be met: {calls}. Change one of them."
            )
            raise ValueError(message)
        never = [name for name in names if not any(name in g.names for g in valid)]
        if never:
            message = (
                f"{_and(label, never)} can never be given, because these "
                f"dependencies contradict each other: {calls}. Change one of them."
            )
            raise ValueError(message)
        _check_redundancy(names, env, related, valid)


def _check_redundancy(
    names: list[str],
    env: frozenset[str],
    related: list[Dependency],
    valid: list[Given],
) -> None:
    for index, found in enumerate(related):
        others = related[:index] + related[index + 1 :]
        without = [
            given for given in _combinations(names, env) if _meets(others, given)
        ]
        if without == valid:
            implied_by = joined([other.call for other in others], "and")
            message = f"{found.call} is already implied by {implied_by}. Remove it."
            raise ValueError(message)


def _groups(
    dependencies: Sequence[Dependency], env: frozenset[str]
) -> list[tuple[list[str], list[Dependency]]]:
    mentioned = list(dict.fromkeys(name for d in dependencies for name in d.names))
    typed = [name for name in mentioned if name not in env]
    leader = {name: name for name in mentioned}

    def find(name: str) -> str:
        while leader[name] != name:
            name = leader[name]
        return name

    for found in dependencies:
        linked = [*found.names, *(typed if isinstance(found, Alone) else ())]
        for name in linked[1:]:
            leader[find(name)] = find(linked[0])
    groups: dict[str, list[str]] = {}
    for name in mentioned:
        groups.setdefault(find(name), []).append(name)
    return [
        (names, [d for d in dependencies if find(d.names[0]) == key])
        for key, names in groups.items()
    ]


def _combinations(names: list[str], env: frozenset[str]) -> list[Given]:
    return [
        Given(tuple(name for index, name in enumerate(names) if mask >> index & 1), env)
        for mask in range(1 << len(names))
    ]


def _meets(dependencies: Sequence[Dependency], given: Given) -> bool:
    return all(found.met(given) for found in dependencies)


def _cycle_from(
    name: str, needs: Mapping[str, list[str]], path: list[str]
) -> list[str] | None:
    for other in needs.get(name, []):
        if other == path[0]:
            return path
        if other not in path:
            cycle = _cycle_from(other, needs, [*path, other])
            if cycle is not None:
                return cycle
    return None


def _names(
    method: str, values: Sequence[object], count: int | None = None
) -> tuple[str, ...]:
    names: list[str] = []
    for value in values:
        if not isinstance(value, str):
            message = (
                f"dependency.{method} takes the names of inputs as strings, "
                f'such as "user", not {value!r}.'
            )
            raise TypeError(message)
        names.append(value)
    for name in names:
        if names.count(name) > 1:
            message = f"{_call(method, names, count)} names {name!r} twice. Remove one."
            raise ValueError(message)
    return tuple(names)


def _counted(kind: CountKind, count: object, values: Sequence[object]) -> Count:
    if not isinstance(count, int) or isinstance(count, bool):
        message = (
            f"dependency.{kind} takes the count as an int, such as 1, not {count!r}."
        )
        raise TypeError(message)
    names = _names(kind, values, count)
    if 1 <= count < len(names):
        return Count(kind, count, names)
    if count < 1:
        effect = (
            "needs none of them, so it changes nothing"
            if kind == "at_least"
            else "allows none of them, so none of them can be given"
        )
    elif kind == "at_most":
        effect = "allows all of them, so it changes nothing"
    else:
        effect = "needs all of them, so every one of them is always given"
    message = (
        f"{_call(kind, names, count)} {effect}. Use a count from 1 to {len(names) - 1}."
    )
    raise ValueError(message)


def _present(names: Sequence[str], given: Given) -> list[str]:
    return [name for name in names if name in given.names]


def _what(
    label: Label, present: list[str], names: Sequence[str], *, too_few: bool
) -> str:
    if not present:
        return "none was"
    if len(present) == len(names):
        return "both were" if len(names) == _PAIR else f"all {len(names)} were"
    shown = _and(label, present)
    verb = "was" if len(present) == 1 else "were"
    return f"only {shown} {verb}" if too_few else f"{shown} {verb}"


def _call(method: str, names: Sequence[str], count: int | None = None) -> str:
    arguments = [f'"{name}"' for name in names]
    if count is not None:
        arguments.insert(0, str(count))
    return f"dependency.{method}({', '.join(arguments)})"


def _and(label: Label, names: Sequence[str]) -> str:
    return joined([label(name) for name in names], "and")


def _or(label: Label, names: Sequence[str]) -> str:
    return joined([label(name) for name in names], "or")
