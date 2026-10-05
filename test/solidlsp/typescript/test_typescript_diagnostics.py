import time

import pytest

from solidlsp import SolidLanguageServer, ls_types
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.util.diagnostics import assert_file_diagnostics


def _comparable(diagnostic: ls_types.Diagnostic) -> tuple[object, ...]:
    diagnostic_range = diagnostic["range"]
    return (
        diagnostic["message"],
        diagnostic_range["start"]["line"],
        diagnostic_range["start"]["character"],
        diagnostic_range["end"]["line"],
        diagnostic_range["end"]["character"],
        diagnostic.get("severity"),
        diagnostic.get("code"),
        diagnostic.get("source"),
    )


@pytest.mark.typescript
class TestTypeScriptDiagnostics:
    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "diagnostics_sample.ts",
            ("missingGreeting", "missingConsumerValue"),
            min_count=2,
        )

    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_a_clean_file_answers_at_once(self, language_server: SolidLanguageServer) -> None:
        start = time.monotonic()
        diagnostics = language_server.request_text_document_diagnostics("formatters.ts", min_severity=4)
        elapsed = time.monotonic() - start

        assert diagnostics == []
        # waiting for a non-empty publication instead would take the whole publication timeout (5 s)
        assert elapsed < 2.5, f"a clean file's diagnostics took {elapsed:.1f} s"

    @pytest.mark.parametrize("language_server", [LanguageServerId.TYPESCRIPT], indirect=True)
    def test_pulled_diagnostics_are_the_published_ones(self, language_server: SolidLanguageServer) -> None:
        """The diagnostics pulled from tsserver are converted exactly as typescript-language-server converts those it publishes."""
        pulled = language_server.request_text_document_diagnostics("diagnostics_sample.ts", min_severity=4)
        published = language_server.request_published_text_document_diagnostics("diagnostics_sample.ts", timeout=10, min_severity=4)

        assert published is not None
        assert sorted(map(_comparable, pulled)) == sorted(map(_comparable, published))
