set default-list

[doc('Format the Rust and Python code')]
fmt:
    cargo fmt
    uv run --locked ruff check --fix-only
    uv run --locked ruff format

[doc('Check formatting, lint, type-check and audit the workflows')]
lint:
    cargo fmt --check
    uv run --locked cargo clippy --locked --all-targets -- -D warnings
    uv run --locked ruff format --check
    uv run --locked ruff check --ignore-noqa
    uv run --locked basedpyright
    uv run --locked zizmor .

[doc('Run the Rust and Python tests with coverage')]
test:
    uv run --locked cargo test --locked
    uv run --locked coverage run -m pytest
    uv run --locked coverage report

[doc('Build a release wheel and a source distribution into dist')]
build:
    rm -rf dist
    uv run --locked maturin sdist --out dist
    uv run --locked maturin build --release --locked --out dist

[doc('Lint, test, build and test the built distributions')]
check: lint test build
    uv run --no-project --isolated --python 3.11 --with pytest --with dist/*.whl pytest
    uv run --no-project --isolated --python 3.15 --with pytest --with dist/*.whl pytest
    uv run --no-project --isolated --python 3.11 --with pytest --with dist/*.tar.gz pytest
    uv run --no-project --isolated --python 3.15 --with pytest --with dist/*.tar.gz pytest

[arg('version', pattern='(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)')]
[doc('Bump the version and move the Unreleased changelog entries under it')]
[script('bash', '-euo', 'pipefail')]
prepare $version:
    current=$(cargo pkgid)
    current=${current##*[#@]}
    if [[ $(printf '%s\n' "$current" "$version" | sort -V | tail -n 1) != "$version" || $current == "$version" ]]; then
        echo "error: $version is not newer than the current version $current" >&2
        exit 1
    fi
    if [[ -z $(awk '$0 == "## Unreleased" { found = 1; next } found && /^## / { exit } found && NF' CHANGELOG.md) ]]; then
        echo "error: CHANGELOG.md has no entries under ## Unreleased" >&2
        exit 1
    fi
    awk -v version="$version" '!done && /^version = / { print "version = \"" version "\""; done = 1; next } { print }' Cargo.toml > Cargo.toml.tmp
    mv Cargo.toml.tmp Cargo.toml
    awk -v version="$version" '{ print } $0 == "## Unreleased" { print ""; print "## v" version }' CHANGELOG.md > CHANGELOG.md.tmp
    mv CHANGELOG.md.tmp CHANGELOG.md
    cargo update --workspace --quiet
    echo "Prepared v$version"
