# Contributing

Thanks for helping with cliron! You don't need to have contributed to open source before. This page walks you through it, one step at a time.

## Goals

Every change moves cliron toward these:

| Goal            | Means                                                                                               |
| --------------- | --------------------------------------------------------------------------------------------------- |
| Easy to use     | A working CLI takes little code, defaults cover the common case, and every error says how to fix it |
| Customizable    | You can extend or replace cliron's behavior from your own code, without forking it                  |
| Dependency-free | Installing cliron installs nothing else                                                             |

## Ways to help

| You want to                  | Do this                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Report a bug                 | Open an issue with the [bug report form](https://github.com/marcusfrdk/cliron/issues/new?template=bug.yml)        |
| Suggest a feature            | [Open an issue](https://github.com/marcusfrdk/cliron/issues/new) that says what you need and which goal it serves |
| Fix a typo                   | Go straight to [step 2](#2-get-the-code)                                                                          |
| Fix a bug or build a feature | Start at [step 1](#1-pick-something-to-work-on)                                                                   |

## Your first pull request

### 1. Pick something to work on

Find an [open issue](https://github.com/marcusfrdk/cliron/issues), or open one, and comment that you'd like to work on it. That way, nobody does the same work twice, and you can agree on the approach before you write code.

### 2. Get the code

[Fork the repository](https://github.com/marcusfrdk/cliron/fork) to get your own copy on GitHub. Then download it, replacing `YOUR-USERNAME` with your GitHub username:

```bash
git clone https://github.com/YOUR-USERNAME/cliron.git
cd cliron
git remote add upstream https://github.com/marcusfrdk/cliron.git
```

### 3. Set up

Install these:

| Tool                                                          | Version        | For                                    |
| ------------------------------------------------------------- | -------------- | -------------------------------------- |
| [Python](https://www.python.org/downloads/)                   | 3.11 or higher | Running cliron                         |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.13 or higher | Installing the development environment |
| [just](https://github.com/casey/just#installation)            | 1.52 or higher | Running the project's commands         |

Then install the development environment:

```bash
just sync
```

### 4. Make your change

Start a branch named after your change:

```bash
git switch -c fix-between-time-zones
```

Then make the change. Depending on what it is, it needs more than the code:

| Your change                                                                                          | Also needs                                                                               |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| New behavior                                                                                         | Tests in `tests/`                                                                        |
| A bug fix                                                                                            | A test that fails without the fix                                                        |
| Something users notice, such as a change to the API, behavior, output, errors or supported platforms | An entry in `CHANGELOG.md`, and an update to `GUIDE.md` if it changes how cliron is used |
| A docstring                                                                                          | The same change in `REFERENCE.md`, and in `GUIDE.md` where it shows it                   |

A changelog entry is one sentence for users, under `## Unreleased`:

```markdown
## Unreleased

### Fixed

- `between` reports a value whose time zone doesn't match its bounds as invalid input.
```

The code follows a few rules:

| Rule            |                                                                                                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python 3.11     | No syntax or standard library newer than that                                                                                                                                |
| No dependencies | cliron installs nothing else                                                                                                                                                 |
| No comments     | Code should explain itself. Docstrings, with reStructuredText fields such as `:param name:`, are the only documentation in code, and every public function and class has one |
| Tests           | They use the public `cliron` API, never the network, and write files only inside `tmp_path`. Coverage stays at 100%                                                          |

### 5. Check it

Format the code, then run every check, the same ones that run on GitHub:

```bash
just fmt
just check
```

Fix anything it reports, and run it again until it passes.

### 6. Commit

Save your change with a message in the [Conventional Commits](https://www.conventionalcommits.org) format. It's a type, a colon, and what you did, in the past tense.

```bash
git add .
git commit -m "fix: Fixed between crashing on time zones"
```

| Type       | For                                          |
| ---------- | -------------------------------------------- |
| `feat`     | A new feature                                |
| `fix`      | A bug fix                                    |
| `docs`     | Documentation only                           |
| `test`     | Tests only                                   |
| `refactor` | Code that changes, without changing behavior |
| `chore`    | Anything else, such as tooling               |

### 7. Open a pull request

Send your branch to your fork:

```bash
git push -u origin fix-between-time-zones
```

Then [open a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork) into `main`. Give it a title in the same format as a commit message, and a short description:

```markdown
Fixes #12

`between` crashed when a user typed a datetime with a time zone. It now reports invalid input instead.
```

`Fixes #12` links the issue your pull request solves.

### 8. Review

GitHub runs the checks, including that the title follows the format, and that `feat`, `fix` and `perf` pull requests add a changelog entry. A maintainer then reviews your change.

To change something, commit and push to the same branch, and the pull request updates. Once it's approved, it's merged. Thank you!

Before your next change, update your copy:

```bash
git switch main
git pull origin main
```

## Using AI

You're welcome to use AI tools for code, tests or docs, and we use them too. Contributing is still a conversation between people. A person opens each pull request, and a person reviews it. Whatever tools you use, the change is yours to stand behind.

- **Understand what you send.** Read your change before you open a pull request, and be ready to explain what it adds and how it works. A reviewer may ask, and talking it through is how we learn from each other.
- **Check that it works.** Run `just check` and try the change yourself. Before reporting a bug, reproduce it yourself.
- **Post it yourself.** Issues, pull requests and comments come from people, so please don't let an agent open or post them on its own.

## Questions

Ask in the issue or the pull request. There are no wrong questions.
