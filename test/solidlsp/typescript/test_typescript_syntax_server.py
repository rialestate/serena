"""typescript-language-server must run without its syntax server.

By default it spawns a second, partialSemantic tsserver and, while the semantic one is loading a project, routes
references, rename, definition, implementation and navto to it; that server knows only the open files. After a git
checkout had the semantic server reload its projects, a references request was answered from the defining file alone
(8 references instead of 338 in 61 files), and a rename in that window would have edited one file and reported success.
"""

import os
from pathlib import Path

import psutil
import pytest

from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import start_ls_context


def test_initialize_params_disable_the_syntax_server() -> None:
    server = object.__new__(TypeScriptLanguageServer)

    initialization_options = server._create_base_initialize_params()["initializationOptions"]

    assert initialization_options["tsserver"] == {"useSyntaxServer": "never"}
    assert initialization_options["disableAutomaticTypingAcquisition"] is True


@pytest.mark.typescript
def test_running_server_spawns_no_partial_semantic_tsserver() -> None:
    parent = psutil.Process(os.getpid())
    existing_pids = {child.pid for child in parent.children(recursive=True)}

    with start_ls_context(LanguageServerId.TYPESCRIPT) as ls:
        symbols = ls.request_document_symbols("index.ts").get_all_symbols_and_roots()[0]
        assert any(symbol["name"] == "DemoClass" for symbol in symbols)

        tsservers = []
        for child in parent.children(recursive=True):
            if child.pid in existing_pids:
                continue
            try:
                command = child.cmdline()
            except psutil.NoSuchProcess:
                continue
            if "tsserver.js" in {Path(arg).name for arg in command}:
                tsservers.append(command)

        assert tsservers, "No tsserver was observed after a successful symbol request"
        assert not [command for command in tsservers if "partialSemantic" in command or "--syntaxOnly" in command], tsservers
