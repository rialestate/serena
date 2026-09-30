from serena.lsp.lsp_diagnostics import DiagnosticIdentity, DiagnosticsDiff
from solidlsp import ls_types
from solidlsp.lsp_protocol_handler.lsp_types import DiagnosticSeverity


def _diagnostic(message: str, line: int) -> ls_types.Diagnostic:
    return ls_types.Diagnostic(
        uri="file:///sample.ts",
        range={"start": {"line": line, "character": 4}, "end": {"line": line, "character": 12}},
        message=message,
        severity=DiagnosticSeverity.Error,
        code=2304,
        source="typescript",
    )


def _identities(*diagnostics: ls_types.Diagnostic) -> set[DiagnosticIdentity]:
    return {DiagnosticIdentity.from_diagnostic(diagnostic) for diagnostic in diagnostics}


class TestNewDiagnostics:
    def test_a_diagnostic_that_stayed_where_it_was_is_not_new(self) -> None:
        before = _diagnostic("Cannot find name 'a'.", 3)
        assert DiagnosticsDiff._new_diagnostics([_diagnostic("Cannot find name 'a'.", 3)], _identities(before)) == []

    def test_a_diagnostic_moved_by_lines_added_above_it_is_not_new(self) -> None:
        before = _diagnostic("Cannot find name 'a'.", 3)
        assert DiagnosticsDiff._new_diagnostics([_diagnostic("Cannot find name 'a'.", 5)], _identities(before)) == []

    def test_a_diagnostic_the_edit_introduced_is_new(self) -> None:
        before = _diagnostic("Cannot find name 'a'.", 3)
        introduced = _diagnostic("Cannot find name 'b'.", 7)
        after = [_diagnostic("Cannot find name 'a'.", 3), introduced]
        assert DiagnosticsDiff._new_diagnostics(after, _identities(before)) == [introduced]

    def test_a_second_occurrence_of_an_existing_diagnostic_is_new(self) -> None:
        """A diagnostic that stays where it was cannot also account for an identical one elsewhere."""
        before = _diagnostic("Cannot find name 'a'.", 3)
        second = _diagnostic("Cannot find name 'a'.", 9)
        after = [_diagnostic("Cannot find name 'a'.", 3), second]
        assert DiagnosticsDiff._new_diagnostics(after, _identities(before)) == [second]

    def test_one_moved_diagnostic_accounts_for_one_occurrence_only(self) -> None:
        before = _diagnostic("Cannot find name 'a'.", 3)
        moved = _diagnostic("Cannot find name 'a'.", 5)
        second = _diagnostic("Cannot find name 'a'.", 9)
        assert DiagnosticsDiff._new_diagnostics([moved, second], _identities(before)) == [second]

    def test_a_diagnostic_reported_twice_is_new_once(self) -> None:
        introduced = _diagnostic("Cannot find name 'b'.", 7)
        assert DiagnosticsDiff._new_diagnostics([introduced, _diagnostic("Cannot find name 'b'.", 7)], set()) == [introduced]
