# AGENTS.md

## Vision

Every change moves cliron toward these three goals. Ask the user before making a change that weakens one of them, or when two of them conflict.

- **Easy to use.** A working CLI takes as little code as possible, and the obvious way to write it is the right way. Defaults cover the common case, and every error says what went wrong and how to fix it.
- **Customizable.** Users can extend or replace cliron's behavior from their own code, for example with their own decorators, without forking cliron or touching its internals. cliron's own features are built on the same public extension points users get.
- **Dependency-free.** Installing cliron installs nothing else: `[project] dependencies` in `pyproject.toml` stays empty.

## Planning

- Agents propose a plan and wait for the user's approval before changing any file in this repository that git does not ignore.
- A plan names every dependency, tool, configuration file and workflow it adds or changes. Anything the approved plan did not name needs a new approval.

## Principles

- **YAGNI.** Build and change only what the task needs now. No option, parameter, abstraction or file for a need that has not arrived.
- **KISS.** Write the simplest code that works.
- **DRY.** Never write a second copy of a piece of logic. Code that looks alike but changes for different reasons is not a copy.
- **Chesterton's fence.** Before removing or changing something that looks pointless, find out why it exists: its tests, its callers, its history. Keep it if the reason holds, and ask if the task wants it changed anyway. Ask too if it is unclear whether the reason holds, or if none is found.
- **No cargo cult.** Copy a pattern only when its reason holds here.
- **Ask before deciding what is the user's.** A choice the task or approved plan does not settle is the user's when it changes the architecture, how the program behaves, a design or the user experience, and so is a workaround for a missing piece or a change beyond what was asked. Ask before making one. A technical choice inside those bounds needs no question.

## Git

- Agents must never create, change or delete any git repository, local or remote, by any means. This covers git itself, any other tool, script, subprocess or agent, and direct edits inside a `.git` directory.
- Repository state includes history, the index, refs, branches, tags, the stash, configuration, hooks and remotes, as well as working tree files whenever git is what changes them.
- Agents may only run git in ways that leave all of that unchanged. Refreshing the cached file information in the index does not count as a change. If an agent is not certain an action changes nothing, it must not take it.
- Agents never change anything on GitHub or PyPI.
- There are no exceptions.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org) on a single line, without a scope. For example, `docs: Added a README and LICENSE file`, not `docs(readme): Added a README`.
- When asked, agents may draft a commit message or pull request title in this format.
- Development happens on feature branches merged into `main` through pull requests. Pull request titles follow the same format as commit messages.

## Project

- The public API is the names in the `__all__` of `cliron` and of its public subpackages, such as `cliron.testing`. Their code lives in private modules, and `cliron` loads its names lazily. Users never import a module whose name starts with an underscore.
- Everything used to write a CLI is exported from `cliron`. A public subpackage exists only for a different audience or moment, such as tests, never to split the API along internal lines.
- Python code runs on Python 3.11: no syntax or standard library APIs newer than that.
- Agents run other Python versions only through `uv run --isolated`, never in `.venv`.
- Lock files change only through the tools that own them.

## Architecture

- A CLI is a tree of nodes. The root nodes are `group` and `command`: a group contains groups and commands, and is never called their parent.
- A parent node provides the value of exactly one function parameter. A child node processes the value of the parent above it. A dependency relates inputs to each other, and a hook runs around a node.
- Decorators are read top-down. A parent belongs to the root node above it, a child attaches to the nearest parent above it, and a hook attaches to the nearest node of any kind above it.
- Types and defaults live only in the function signature, never on parent nodes.
- Classes use CapWords and functions snake_case, as PEP 8 says. Node classes are no exception.
- Node names are snake_case. What users type is derived from them: kebab-case for commands and flags, SCREAMING_SNAKE_CASE for environment variables.

## Testing

- New behavior comes with tests. A bug fix comes with a test that fails without it.
- Tests in `tests/` exercise the public `cliron` API.
- Tests never use the network and write files only inside `tmp_path`.

## Definition of done

- `just check` passes.
- An agent's final message lists the changed files and anything left unverified.

## Changelog

- Every change that affects users adds an entry under `## Unreleased` in `CHANGELOG.md`.
- A change affects users when it changes the public API, behavior, performance, output, errors, supported Python versions, platforms or wheels. Tests, CI, refactors and development tooling do not.
- Entries are grouped under these headings, in this order, leaving out empty ones: `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`.
- Each entry is one sentence written for users, ending with a period.
- A release renames `## Unreleased` to `## vX.Y.Z` and adds a new, empty `## Unreleased` above it. Version headings carry no date.
- Released sections are never edited.

## Comments and docstrings

- These rules apply to code everywhere, including TOML, YAML, the justfile and code blocks in Markdown and other documentation.
- Code examples use only cliron and the standard library, unless they show an integration that needs more.
- Code must be self-documenting. If code cannot be understood without a comment, it is bad code: refactor it instead of commenting it.
- Docstrings are the only allowed form of documentation in code. They use reStructuredText field lists, and a multiline docstring never starts on the same line as its opening quotes:

  ```python
  def parse_port(value: str) -> int:
      """
      Parse a TCP port number.

      :param value: The port as text, for example ``"8080"``.
      :returns: The port as an integer.
      :raises ValueError: If ``value`` is not a number between 1 and 65535.
      """
  ```

- Every public module, class, function and method in `cliron` has a docstring. Types belong in annotations, never in docstring fields.
- Justfile recipes are described with the `[doc]` attribute.
- Apart from the version comments on pinned GitHub Actions, the only allowed comment documents hidden behavior that our code cannot explain, such as why a workaround for a bug in a dependency exists. Such a comment links the upstream issue.
- Lint and type-check suppressions go in `pyproject.toml`, never in comments.
- Never explain how third-party tools or libraries behave, in code or in documentation. That is their documentation's job, and our copy drifts when they change.

## GitHub Actions

- Every action is pinned to a full commit hash, followed by a comment naming its version: `uses: actions/checkout@<commit hash> # v7.0.1`.
