from codeimpact.diff_parser import parse_git_diff


def test_parse_git_diff_handles_simple_single_file_diff() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/pkg/util.py b/pkg/util.py",
            "--- a/pkg/util.py",
            "+++ b/pkg/util.py",
            "@@ -1,2 +1,3 @@",
            " def helper():",
            "     return 1",
            "+value = 2",
        ]
    )

    parsed = parse_git_diff(diff_text)

    assert parsed.files[0].path == "pkg/util.py"
    assert parsed.files[0].added == 1
