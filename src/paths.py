"""Write-path guardrail (Track A permission rule).

Hard rule: the pipeline may only write *inside* the repository ``out/``
directory. Any output path that resolves outside that root is refused before
any file handle is opened, including ``..`` traversal and absolute paths.
Rationale: an extraction batch job must never be able to overwrite source
data, config, or arbitrary host files because of a bad ``-o`` argument.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_OUTPUT_ROOT = REPO_ROOT / "out"


class UnsafeOutputPathError(ValueError):
    """Raised when an output path escapes the allowed out/ root."""


def safe_output_path(
    raw_path: str | Path,
    allowed_root: str | Path = ALLOWED_OUTPUT_ROOT,
) -> Path:
    """Validate and resolve an output path.

    Rules
    -----
    * relative paths are resolved against the current working directory;
    * symlinks and ``..`` segments are fully resolved before the check;
    * the resolved path must be the allowed root itself or inside it;
    * the suffix must be ``.jsonl`` (the pipeline only emits JSON Lines).

    Returns the resolved absolute path; raises UnsafeOutputPathError otherwise.
    """
    if raw_path is None or str(raw_path).strip() == "":
        raise UnsafeOutputPathError("output path must not be empty")

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve(strict=False)

    root = Path(allowed_root).resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise UnsafeOutputPathError(
            f"refusing to write outside {root}: {raw_path!r} resolves to {resolved}"
        )

    if resolved.suffix != ".jsonl":
        raise UnsafeOutputPathError(
            f"output must be a .jsonl file, got {resolved.suffix!r}"
        )

    return resolved
