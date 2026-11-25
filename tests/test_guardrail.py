"""Track A automated tests: write-path permission guardrail."""

from pathlib import Path

import pytest

from src.paths import UnsafeOutputPathError, safe_output_path


def test_relative_path_under_default_repo_out_is_resolved():
    from src.paths import ALLOWED_OUTPUT_ROOT
    resolved = safe_output_path("out/rows.jsonl")
    assert resolved == (ALLOWED_OUTPUT_ROOT / "rows.jsonl").resolve()


def test_absolute_path_inside_allowed_root_accepted(tmp_path):
    out_root = tmp_path / "out"
    target = out_root / "nested" / "rows.jsonl"
    assert safe_output_path(target, allowed_root=out_root) == target.resolve()


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/absolutely_elsewhere.jsonl",
        "../escape.jsonl",
        "../../etc/passwd.jsonl",
    ],
)
def test_paths_outside_out_are_refused(tmp_path, bad_path):
    out_root = tmp_path / "out"
    with pytest.raises(UnsafeOutputPathError):
        safe_output_path(bad_path, allowed_root=out_root)


def test_symlink_escape_is_refused(tmp_path):
    out_root = tmp_path / "out"
    out_root.mkdir()
    outside = tmp_path / "outside.jsonl"
    link = out_root / "link.jsonl"
    link.symlink_to(outside)
    with pytest.raises(UnsafeOutputPathError):
        safe_output_path(link, allowed_root=out_root)


def test_non_jsonl_suffix_refused(tmp_path):
    with pytest.raises(UnsafeOutputPathError):
        safe_output_path(tmp_path / "out" / "rows.csv", allowed_root=tmp_path / "out")


def test_empty_path_refused(tmp_path):
    with pytest.raises(UnsafeOutputPathError):
        safe_output_path("  ", allowed_root=tmp_path / "out")


def test_default_repo_root_is_the_out_directory():
    from src.paths import ALLOWED_OUTPUT_ROOT
    assert ALLOWED_OUTPUT_ROOT.name == "out"
    accepted = safe_output_path(ALLOWED_OUTPUT_ROOT / "rows.jsonl")
    assert accepted.parent == ALLOWED_OUTPUT_ROOT.resolve()
    with pytest.raises(UnsafeOutputPathError):
        safe_output_path("/tmp/css5120_guardrail_probe.jsonl")
