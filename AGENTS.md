# AGENTS.md

## Git

- Agents must never create, change or delete any git repository, local or remote, by any means. This covers git itself, any other tool, script, subprocess or agent, and direct edits inside a `.git` directory.
- Repository state includes history, the index, refs, branches, tags, the stash, configuration, hooks and remotes, as well as working tree files whenever git is what changes them.
- Agents may only run git in ways that leave all of that unchanged. If an agent is not certain an action changes nothing, it must not take it.
- There are no exceptions.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org) on a single line, without a scope. For example, `docs: Added a README and LICENSE file`, not `docs(readme): Added a README`.
- Development happens on feature branches that are squash-merged into `main` through pull requests. Pull request titles follow the same format as commit messages.

## Changelog

- Every change that affects users adds an entry under `## Unreleased` in `CHANGELOG.md`.
- Entries are grouped under these headings, in this order, leaving out empty ones: `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`.
- A release renames `## Unreleased` to `## vX.Y.Z` and adds a new, empty `## Unreleased` above it. Version headings carry no date.

## Comments and docstrings

- These rules apply to code everywhere, including code blocks in Markdown and other documentation.
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

- PyO3 turns the `///` doc comments on Rust items exposed to Python into their Python docstrings, so those follow the same style. Doc comments on internal Rust items use standard rustdoc Markdown.
- Apart from the version comments on pinned GitHub Actions, the only allowed comment documents hidden behavior that our code cannot explain, such as why a workaround for a bug in a dependency exists.
- Never explain how third-party tools or libraries behave, in code or in documentation. That is their documentation's job, and our copy drifts when they change.

## GitHub Actions

- Every action is pinned to a full commit hash, followed by a comment naming its version: `uses: actions/checkout@<commit hash> # v7.0.1`.
