from dataclasses import replace

from cliron import Help, HelpRow, HelpSection


def test_a_row_needs_only_its_names() -> None:
    row = HelpRow(("-v", "--verbose"))

    assert (row.value, row.text, row.notes, row.default, row.required) == (
        None,
        "",
        (),
        None,
        False,
    )


def test_a_changed_copy_leaves_the_original_alone() -> None:
    row = HelpRow(("--keep",), "INT", "How many to keep.", ("1 to 100.",), "10")
    original = Help(
        ("backup", "[OPTIONS]"),
        "Archive a directory.",
        (HelpSection("options", "Options", (row,)),),
    )

    changed = replace(original, summary="Archive a folder.")

    assert changed.sections == original.sections
    assert (original.summary, changed.summary) == (
        "Archive a directory.",
        "Archive a folder.",
    )
