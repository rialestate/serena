"""
Edits anchored at a symbol's start keep the comment block documenting the symbol attached to it,
although language servers commonly exclude that block from the symbol's range.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from syrupy import SnapshotAssertion

from serena.code_editor import CodeEditor
from serena.symbol import LanguageServerSymbolRetriever
from serena.util.leading_comments import CommentSyntax, LeadingCommentScanner
from solidlsp.ls_config import LanguageServerId
from test.serena.test_symbol_editing import CodeDiff, EditingTest


class TestLeadingCommentScanner:
    @staticmethod
    def _start_line(relative_path: str, contents: str, symbol_start_line: int) -> int:
        scanner = LeadingCommentScanner.for_file(relative_path, contents)
        assert scanner is not None
        return scanner.find_start_line(symbol_start_line)

    def test_jsdoc_block(self) -> None:
        contents = "const a = 1;\n/**\n * Doc.\n */\nfunction f() {}\n"
        assert self._start_line("x.ts", contents, 4) == 1

    def test_line_comments_and_blocks_chain(self) -> None:
        contents = "// one\n/* two */\n// three\nfunction f() {}\n"
        assert self._start_line("x.ts", contents, 3) == 0

    def test_empty_line_detaches_comment(self) -> None:
        contents = "/** Detached. */\n\nfunction f() {}\n"
        assert self._start_line("x.ts", contents, 2) == 2

    def test_block_comment_after_code_is_not_attached(self) -> None:
        contents = "const a = 1; /* trailing\n comment */\nfunction f() {}\n"
        assert self._start_line("x.ts", contents, 2) == 2

    def test_private_field_is_not_a_comment_in_typescript(self) -> None:
        contents = "class C {\n    #secret = 1;\n    run() {}\n}\n"
        assert self._start_line("x.ts", contents, 2) == 2

    def test_hash_comments(self) -> None:
        contents = "x = 1\n# one\n# two\n@decorator\ndef f(): pass\n"
        assert self._start_line("x.py", contents, 3) == 1

    def test_shebang_is_not_attached(self) -> None:
        contents = "#!/usr/bin/env python3\n# Comment.\ndef main(): pass\n"
        assert self._start_line("x.py", contents, 2) == 1

    @pytest.mark.parametrize(
        ("shebang", "syntax"),
        [
            ("#!/usr/bin/env bash", CommentSyntax.HASH),
            ("#!/bin/sh", CommentSyntax.HASH),
            ("#!/usr/bin/env -S python3.14 -u", CommentSyntax.HASH),
            ("#!/usr/bin/env node", CommentSyntax.C_STYLE),
        ],
    )
    def test_extensionless_script_is_recognised_by_its_shebang(self, shebang: str, syntax: CommentSyntax) -> None:
        scanner = LeadingCommentScanner.for_file("bin/tool", shebang + "\n")
        assert scanner is not None
        assert scanner.syntax == syntax

    def test_unknown_language_has_no_scanner(self) -> None:
        assert LeadingCommentScanner.for_file("x.unknown", "-- comment\n") is None
        assert LeadingCommentScanner.for_file("Makefile", "# comment\nall:\n") is None


TYPESCRIPT_FILE = "documented.ts"
TYPESCRIPT_CONTENTS = """const counter = 0;

/**
 * Formats a name.
 */
export function formatName(name: string): string {
    return name.trim();
}

/** Detached block comment. */

export function detached(): void {}

export class Service {
    #secret = 1;
    /** Documented member. */
    run(): void {}
    #other = 2;
    plain(): void {}
}
"""

PYTHON_FILE = "documented_module.py"
PYTHON_CONTENTS = """import functools

# Leading comment
# for the function.
@functools.cache
def decorated() -> int:
    return 1


class Documented:
    \"\"\"Docstring stays inside.\"\"\"

    # Comment on the method.
    def method(self) -> None:
        pass
"""


class FixtureFileEditingTest(EditingTest):
    """
    Edits a file written into the test repository's temporary copy, leaving the shared test repository unchanged
    """

    def __init__(self, ls_id: LanguageServerId, rel_path: str, contents: str, edit: Callable[[CodeEditor], None]):
        super().__init__(ls_id, rel_path)
        self.contents = contents
        self.edit = edit
        self.modified_content: str | None = None

    @contextmanager
    def _setup(self) -> Iterator[LanguageServerSymbolRetriever]:
        with super()._setup() as symbol_retriever:
            assert self.repo_path is not None
            (self.repo_path / self.rel_path).write_text(self.contents, encoding="utf-8")
            yield symbol_retriever

    def _apply_edit(self, code_editor: CodeEditor) -> None:
        self.edit(code_editor)

    def _test_diff(self, code_diff: CodeDiff, snapshot: SnapshotAssertion | None) -> None:
        self.modified_content = code_diff.modified_content

    def run(self) -> str:
        self.run_test(content_after_ground_truth=None)
        assert self.modified_content is not None
        return self.modified_content


def _edit_typescript(edit: Callable[[CodeEditor], None]) -> str:
    return FixtureFileEditingTest(LanguageServerId.TYPESCRIPT, TYPESCRIPT_FILE, TYPESCRIPT_CONTENTS, edit).run()


@pytest.mark.typescript
class TestTypeScriptLeadingComments:
    def test_insert_before_keeps_jsdoc_attached(self) -> None:
        result = _edit_typescript(lambda e: e.insert_before_symbol("formatName", TYPESCRIPT_FILE, "const inserted = 1;\n"))
        assert "const counter = 0;\n\nconst inserted = 1;\n\n/**\n * Formats a name.\n */\nexport function formatName(" in result

    def test_insert_before_member_keeps_its_jsdoc_attached(self) -> None:
        result = _edit_typescript(lambda e: e.insert_before_symbol("Service/run", TYPESCRIPT_FILE, "    inserted(): void {}\n"))
        assert "    #secret = 1;\n    inserted(): void {}\n\n    /** Documented member. */\n    run(): void {}\n" in result

    def test_insert_before_does_not_take_a_private_field_for_a_comment(self) -> None:
        result = _edit_typescript(lambda e: e.insert_before_symbol("Service/plain", TYPESCRIPT_FILE, "    inserted(): void {}\n"))
        assert "    #other = 2;\n    inserted(): void {}\n\n    plain(): void {}\n" in result

    def test_insert_before_leaves_a_detached_comment_in_place(self) -> None:
        result = _edit_typescript(lambda e: e.insert_before_symbol("detached", TYPESCRIPT_FILE, "const inserted = 1;\n"))
        assert "/** Detached block comment. */\n\nconst inserted = 1;\n\nexport function detached()" in result

    def test_delete_removes_the_jsdoc(self) -> None:
        result = _edit_typescript(lambda e: e.delete_symbol("formatName", TYPESCRIPT_FILE))
        assert "Formats a name" not in result
        assert result.startswith("const counter = 0;\n\n/** Detached block comment. */\n")

    def test_delete_removes_a_member_jsdoc(self) -> None:
        result = _edit_typescript(lambda e: e.delete_symbol("Service/run", TYPESCRIPT_FILE))
        assert "    #secret = 1;\n    #other = 2;\n" in result


def _edit_python(edit: Callable[[CodeEditor], None]) -> str:
    return FixtureFileEditingTest(LanguageServerId.PYTHON, PYTHON_FILE, PYTHON_CONTENTS, edit).run()


@pytest.mark.python
class TestPythonLeadingComments:
    def test_insert_before_decorated_function_keeps_comments_attached(self) -> None:
        result = _edit_python(lambda e: e.insert_before_symbol("decorated", PYTHON_FILE, "def inserted():\n    pass\n"))
        assert "import functools\n\ndef inserted():\n    pass\n\n# Leading comment\n# for the function.\n@functools.cache\n" in result

    def test_insert_before_method_keeps_comment_attached(self) -> None:
        result = _edit_python(
            lambda e: e.insert_before_symbol("Documented/method", PYTHON_FILE, "    def inserted(self) -> None:\n        pass\n")
        )
        assert '"""Docstring stays inside."""\n\n    def inserted(self) -> None:\n        pass\n\n    # Comment on the method.\n' in result

    def test_delete_removes_comments_and_decorator(self) -> None:
        result = _edit_python(lambda e: e.delete_symbol("decorated", PYTHON_FILE))
        assert "Leading comment" not in result
        assert "functools.cache" not in result
