from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re


_DIFF_HEADER_RE = re.compile(r"^diff --git a/(?P<old>.+?) b/(?P<new>.+?)$")
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


@dataclass(slots=True)
class DiffLine:
    kind: str
    content: str
    old_lineno: int | None = None
    new_lineno: int | None = None


@dataclass(slots=True)
class GitHunk:
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(1 for line in self.lines if line.kind == "add")

    @property
    def deleted(self) -> int:
        return sum(1 for line in self.lines if line.kind == "delete")


@dataclass(slots=True)
class GitFileChange:
    old_path: str
    new_path: str
    change_type: str = "modified"
    hunks: list[GitHunk] = field(default_factory=list)
    renamed_from: str | None = None
    renamed_to: str | None = None

    @property
    def added(self) -> int:
        return sum(hunk.added for hunk in self.hunks)

    @property
    def deleted(self) -> int:
        return sum(hunk.deleted for hunk in self.hunks)

    @property
    def path(self) -> str:
        return self.new_path if self.new_path != "/dev/null" else self.old_path

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class GitDiff:
    files: list[GitFileChange] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(file.added for file in self.files)

    @property
    def deleted(self) -> int:
        return sum(file.deleted for file in self.files)

    def to_dict(self) -> dict:
        return {
            "files": [file.to_dict() for file in self.files],
            "summary": {
                "file_count": len(self.files),
                "added": self.added,
                "deleted": self.deleted,
            },
        }


def parse_git_diff(diff_text: str) -> GitDiff:
    files: list[GitFileChange] = []
    current: GitFileChange | None = None
    current_hunk: GitHunk | None = None
    old_lineno = 0
    new_lineno = 0

    def flush_file() -> None:
        nonlocal current, current_hunk
        if current is not None:
            files.append(current)
        current = None
        current_hunk = None

    for raw_line in diff_text.splitlines():
        line = raw_line.lstrip("\ufeff").rstrip("\n")
        match = _DIFF_HEADER_RE.match(line)
        if match:
            flush_file()
            current = GitFileChange(old_path=match.group("old"), new_path=match.group("new"))
            continue
        if current is None:
            continue
        if line.startswith("rename from "):
            current.renamed_from = line.removeprefix("rename from ").strip()
            current.change_type = "renamed"
            continue
        if line.startswith("rename to "):
            current.renamed_to = line.removeprefix("rename to ").strip()
            current.new_path = current.renamed_to
            current.change_type = "renamed"
            continue
        if line.startswith("new file mode "):
            current.change_type = "added"
            continue
        if line.startswith("deleted file mode "):
            current.change_type = "deleted"
            continue
        if line.startswith("--- "):
            old_path = line.removeprefix("--- ").strip()
            current.old_path = old_path.removeprefix("a/") if old_path.startswith("a/") else old_path
            if current.old_path == "/dev/null":
                current.change_type = "added"
            continue
        if line.startswith("+++ "):
            new_path = line.removeprefix("+++ ").strip()
            current.new_path = new_path.removeprefix("b/") if new_path.startswith("b/") else new_path
            if current.new_path == "/dev/null":
                current.change_type = "deleted"
            continue
        match = _HUNK_HEADER_RE.match(line)
        if match:
            current_hunk = GitHunk(
                header=line,
                old_start=int(match.group("old_start")),
                old_count=int(match.group("old_count") or "1"),
                new_start=int(match.group("new_start")),
                new_count=int(match.group("new_count") or "1"),
            )
            current.hunks.append(current_hunk)
            old_lineno = current_hunk.old_start
            new_lineno = current_hunk.new_start
            continue
        if current_hunk is None:
            continue
        if line.startswith("\\ No newline at end of file"):
            continue
        prefix = line[:1]
        content = line[1:] if prefix in {" ", "+", "-"} else line
        if prefix == "+":
            current_hunk.lines.append(DiffLine(kind="add", content=content, new_lineno=new_lineno))
            new_lineno += 1
        elif prefix == "-":
            current_hunk.lines.append(DiffLine(kind="delete", content=content, old_lineno=old_lineno))
            old_lineno += 1
        elif prefix == " ":
            current_hunk.lines.append(DiffLine(kind="context", content=content, old_lineno=old_lineno, new_lineno=new_lineno))
            old_lineno += 1
            new_lineno += 1
        else:
            current_hunk.lines.append(DiffLine(kind="meta", content=line))

    flush_file()
    return GitDiff(files=[file for file in files if file.old_path != file.new_path or file.hunks])
