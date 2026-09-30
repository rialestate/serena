# SPDX-License-Identifier: GPL-3.0-or-later

"""
Detection of the comment block that documents a symbol from above.

Language servers commonly exclude such a block from the symbol's range: tsserver's range for a function starts at
`export function`, below its JSDoc, and Python servers start a function's range at its first decorator, below any
`#` comments. Edits anchored at the start of the range (inserting before a symbol, deleting it) must treat the
attached block as part of the symbol, or they separate the documentation from the code it documents.
"""

import os
from dataclasses import dataclass
from enum import Enum


class CommentSyntax(Enum):
    C_STYLE = "c_style"
    """`//` line comments and `/* ... */` block comments (JSDoc, Javadoc, rustdoc, ...)"""
    HASH = "hash"
    """`#` line comments"""


_C_STYLE_EXTENSIONS = {
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".java",
    ".kt",
    ".kts",
    ".cs",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cc",
    ".cpp",
    ".cxx",
    ".hh",
    ".hpp",
    ".swift",
    ".dart",
    ".scala",
}
_HASH_EXTENSIONS = {".py", ".pyi", ".sh", ".bash", ".zsh", ".rb", ".pl", ".pm", ".r"}
_C_STYLE_INTERPRETERS = {"node", "deno", "bun", "tsx", "ts-node"}
_HASH_INTERPRETERS = {"python", "sh", "bash", "zsh", "ruby", "perl", "rscript"}


@dataclass
class LeadingCommentScanner:
    """
    Finds the first line of the comment block directly above a symbol, i.e. the comment lines that precede the
    symbol's first line with no empty line in between.
    """

    lines: list[str]
    syntax: CommentSyntax

    @classmethod
    def for_file(cls, relative_path: str, contents: str) -> "LeadingCommentScanner | None":
        """
        :param relative_path: the path of the file, whose extension determines the comment syntax
        :param contents: the file's contents; for a file without extension, its shebang determines the comment syntax
        :return: the scanner, or None if the file's comment syntax is not known (no comment is then considered attached)
        """
        lines = contents.splitlines()
        syntax = cls._comment_syntax(relative_path, lines[0] if lines else "")
        if syntax is None:
            return None
        return cls(lines, syntax)

    @staticmethod
    def _comment_syntax(relative_path: str, first_line: str) -> CommentSyntax | None:
        extension = os.path.splitext(relative_path)[1].lower()
        if extension in _C_STYLE_EXTENSIONS:
            return CommentSyntax.C_STYLE
        if extension in _HASH_EXTENSIONS:
            return CommentSyntax.HASH
        if extension == "" and first_line.startswith("#!"):
            words = first_line[2:].split()
            if words and os.path.basename(words[0]) == "env":
                words = [w for w in words[1:] if not w.startswith("-")]
            interpreter = os.path.basename(words[0]).lower() if words else ""
            interpreter = interpreter.rstrip("0123456789.")
            if interpreter in _C_STYLE_INTERPRETERS:
                return CommentSyntax.C_STYLE
            if interpreter in _HASH_INTERPRETERS:
                return CommentSyntax.HASH
        return None

    def find_start_line(self, symbol_start_line: int) -> int:
        """
        :param symbol_start_line: the 0-based line on which the symbol's range starts
        :return: the 0-based first line of the comment block attached to the symbol, or `symbol_start_line` if there is none
        """
        start_line = symbol_start_line
        while start_line > 0:
            comment_start_line = self._find_comment_start_line(start_line - 1)
            if comment_start_line is None:
                break
            start_line = comment_start_line
        return start_line

    def _find_comment_start_line(self, end_line: int) -> int | None:
        """
        :param end_line: the line that may end a comment
        :return: the first line of the comment ending on `end_line`, or None if that line does not end a comment
            that occupies its lines entirely
        """
        stripped = self.lines[end_line].strip()
        match self.syntax:
            case CommentSyntax.HASH:
                is_shebang = end_line == 0 and stripped.startswith("#!")
                return end_line if stripped.startswith("#") and not is_shebang else None
            case CommentSyntax.C_STYLE:
                if stripped.startswith("//"):
                    return end_line
                if stripped.endswith("*/"):
                    return self._find_block_comment_start_line(end_line)
                return None

    def _find_block_comment_start_line(self, end_line: int) -> int | None:
        line = end_line
        while True:
            stripped = self.lines[line].strip()
            if stripped.startswith("/*"):
                return line
            # an opening delimiter that does not start its line is preceded by code
            if "/*" in stripped or line == 0:
                return None
            line -= 1
