"""Tests for the mcp.py module in serena."""

import asyncio

import pytest
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.tools.base import Tool as MCPTool

from serena.agent import Tool, ToolRegistry
from serena.config.context_mode import SerenaAgentContext
from serena.mcp import SerenaMCPFactory
from serena.repl.facade import ApiScope
from serena.repl.repl import SerenaRepl

make_tool = SerenaMCPFactory.make_mcp_tool


# Create a mock agent for tool initialization
class MockAgent:
    def __init__(self):
        self.project_config = None
        self.serena_config = None

    @staticmethod
    def get_context() -> SerenaAgentContext:
        return SerenaAgentContext.load_default()

    @staticmethod
    def get_repl() -> SerenaRepl:
        return SerenaRepl([], ApiScope())

    @staticmethod
    def is_single_project() -> bool:
        return False


class BaseMockTool(Tool):
    """A mock Tool class for testing."""

    def __init__(self):
        super().__init__(MockAgent())


class BasicTool(BaseMockTool):
    """A mock Tool class for testing."""

    def apply(self, name: str, age: int = 0) -> str:
        """This is a test function.

        :param name: The person's name
        :param age: The person's age
        :return: A greeting message
        """
        return f"Hello {name}, you are {age} years old!"

    def apply_ex(
        self,
        log_call: bool = True,
        catch_exceptions: bool = True,
        mcp_ctx: Context | None = None,
        **kwargs,
    ) -> str:
        """Mock implementation of apply_ex."""
        return self.apply(**kwargs)


def test_make_tool_basic() -> None:
    """Test that make_tool correctly creates an MCP tool from a Tool object."""
    mock_tool = BasicTool()

    mcp_tool = make_tool(mock_tool)

    # Test that the MCP tool has the correct properties
    assert isinstance(mcp_tool, MCPTool)
    assert mcp_tool.name == "basic"
    assert "This is a test function. Returns A greeting message." in mcp_tool.description

    # Test that the parameters were correctly processed
    parameters = mcp_tool.parameters
    assert "properties" in parameters
    assert "name" in parameters["properties"]
    assert "age" in parameters["properties"]
    assert parameters["properties"]["name"]["description"] == "The person's name."
    assert parameters["properties"]["age"]["description"] == "The person's age."


def test_make_tool_execution() -> None:
    """Test that the execution function created by make_tool works correctly."""
    mock_tool = BasicTool()
    mcp_tool = make_tool(mock_tool)

    # Execute the MCP tool function
    result = mcp_tool.fn(name="Alice", age=30)

    assert result == "Hello Alice, you are 30 years old!"


def test_make_tool_no_params() -> None:
    """Test make_tool with a function that has no parameters."""

    class NoParamsTool(BaseMockTool):
        def apply(self) -> str:
            """This is a test function with no parameters.

            :return: A simple result
            """
            return "Simple result"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply()

    tool = NoParamsTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.name == "no_params"
    assert "This is a test function with no parameters. Returns A simple result." in mcp_tool.description
    assert mcp_tool.parameters["properties"] == {}


def test_make_tool_no_return_description() -> None:
    """Test make_tool with a function that has no return description."""

    class NoReturnTool(BaseMockTool):
        def apply(self, param: str) -> str:
            """This is a test function.

            :param param: The parameter
            """
            return f"Processed: {param}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = NoReturnTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.name == "no_return"
    assert mcp_tool.description == "This is a test function."
    assert mcp_tool.parameters["properties"]["param"]["description"] == "The parameter."


def test_make_tool_parameter_not_in_docstring() -> None:
    """Test make_tool when a parameter in properties is not in the docstring."""

    class MissingParamTool(BaseMockTool):
        def apply(self, name: str, missing_param: str = "") -> str:
            """This is a test function.

            :param name: The person's name
            """
            return f"Hello {name}! Missing param: {missing_param}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = MissingParamTool()
    mcp_tool = make_tool(tool)

    assert "name" in mcp_tool.parameters["properties"]
    assert "missing_param" in mcp_tool.parameters["properties"]
    assert mcp_tool.parameters["properties"]["name"]["description"] == "The person's name."
    assert "description" not in mcp_tool.parameters["properties"]["missing_param"]


def test_make_tool_multiline_docstring() -> None:
    """Test make_tool with a complex multi-line docstring."""

    class ComplexDocTool(BaseMockTool):
        def apply(self, project_file_path: str, host: str, port: int) -> str:
            """Create an MCP server.

            This function creates and configures a Model Context Protocol server
            with the specified settings.

            :param project_file_path: The path to the project file, or None
            :param host: The host to bind to
            :param port: The port to bind to
            :return: A configured FastMCP server instance
            """
            return f"Server config: {project_file_path}, {host}:{port}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = ComplexDocTool()
    mcp_tool = make_tool(tool)

    assert "Create an MCP server" in mcp_tool.description
    assert "Returns A configured FastMCP server instance" in mcp_tool.description
    assert mcp_tool.parameters["properties"]["project_file_path"]["description"] == "The path to the project file, or None."
    assert mcp_tool.parameters["properties"]["host"]["description"] == "The host to bind to."
    assert mcp_tool.parameters["properties"]["port"]["description"] == "The port to bind to."


def test_make_tool_capitalization_and_periods() -> None:
    """Test that make_tool properly handles capitalization and periods in descriptions."""

    class FormatTool(BaseMockTool):
        def apply(self, param1: str, param2: str, param3: str) -> str:
            """Test function.

            :param param1: lowercase description
            :param param2: description with period.
            :param param3: description with Capitalized word.
            """
            return f"Formatted: {param1}, {param2}, {param3}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = FormatTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.parameters["properties"]["param1"]["description"] == "Lowercase description."
    assert mcp_tool.parameters["properties"]["param2"]["description"] == "Description with period."
    assert mcp_tool.parameters["properties"]["param3"]["description"] == "Description with Capitalized word."


def test_make_tool_missing_apply() -> None:
    """Test make_tool with a tool that doesn't have an apply method."""

    class BadTool(BaseMockTool):
        pass

    tool = BadTool()

    with pytest.raises(AttributeError):
        make_tool(tool)


@pytest.mark.parametrize(
    "docstring, expected_description",
    [
        (
            """This is a test function.

            :param param: The parameter
            :return: A result
            """,
            "This is a test function. Returns A result.",
        ),
        (
            """
            :param param: The parameter
            :return: A result
            """,
            "Returns A result.",
        ),
        (
            """
            :param param: The parameter
            """,
            "",
        ),
        ("Description without params.", "Description without params."),
    ],
)
def test_make_tool_descriptions(docstring, expected_description) -> None:
    """Test make_tool with various docstring formats."""

    class TestTool(BaseMockTool):
        def apply(self, param: str) -> str:
            return f"Result: {param}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    # Dynamically set the docstring
    TestTool.apply.__doc__ = docstring

    tool = TestTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.name == "test"
    assert mcp_tool.description == expected_description


def is_test_mock_class(tool_class: type) -> bool:
    """Check if a class is a test mock class."""
    # Check if the class is defined in a test module
    module_name = tool_class.__module__
    return (
        module_name.startswith(("test.", "tests."))
        or "test_" in module_name
        or tool_class.__name__
        in [
            "BaseMockTool",
            "BasicTool",
            "BadTool",
            "NoParamsTool",
            "NoReturnTool",
            "MissingParamTool",
            "ComplexDocTool",
            "FormatTool",
            "NoDescriptionTool",
        ]
    )


@pytest.mark.parametrize("tool_class", ToolRegistry().get_all_tool_classes())
def test_make_tool_all_tools(tool_class) -> None:
    """Test that make_tool works for all tools in the codebase."""
    # Create an instance of the tool
    tool_instance = tool_class(MockAgent())

    # Try to create an MCP tool from it
    mcp_tool = make_tool(tool_instance)

    # Basic validation
    assert isinstance(mcp_tool, MCPTool)
    assert mcp_tool.name == tool_class.get_name_from_cls()

    # The description should be a string (either from docstring or default)
    assert isinstance(mcp_tool.description, str)


NAME_PATH_SPELLINGS = ("name_path", "name_path_pattern")

NAME_PATH_TOOL_CLASSES = [
    tool_class
    for tool_class in ToolRegistry().get_all_tool_classes()
    if any(spelling in tool_class.get_apply_fn_metadata_from_cls().arg_model.model_fields for spelling in NAME_PATH_SPELLINGS)
]


def _placeholder_arguments(parameters: dict) -> dict:
    """
    :return: a placeholder value for each required parameter of the given JSON schema
    """
    placeholders = {"string": "x", "integer": 0, "number": 0, "boolean": False, "array": [], "object": {}}
    result = {}
    for name in parameters.get("required", []):
        schema = parameters["properties"][name]
        schema_type = schema.get("type") or schema.get("anyOf", [{}])[0].get("type", "string")
        result[name] = placeholders[schema_type]
    return result


def test_name_path_tools_found() -> None:
    names = {tool_class.get_name_from_cls() for tool_class in NAME_PATH_TOOL_CLASSES}
    assert {"find_symbol", "find_referencing_symbols", "replace_symbol_body", "safe_delete_symbol"} <= names


@pytest.mark.parametrize("tool_class", NAME_PATH_TOOL_CLASSES)
def test_name_path_accepted_under_both_spellings(tool_class: type[Tool]) -> None:
    """
    A tool takes a symbol's name path under whichever of the two spellings the caller uses; its schema names only the
    one the tool declares.
    """
    tool_instance = tool_class(MockAgent())
    received_kwargs: list[dict] = []

    def apply_ex(log_call: bool = True, catch_exceptions: bool = True, mcp_ctx: Context | None = None, **kwargs) -> str:
        received_kwargs.append(kwargs)
        return "ok"

    tool_instance.apply_ex = apply_ex  # type: ignore[method-assign]
    mcp_tool = make_tool(tool_instance)
    properties = mcp_tool.parameters["properties"]
    declared = [spelling for spelling in NAME_PATH_SPELLINGS if spelling in properties]
    assert len(declared) == 1, f"{tool_class.__name__} should declare exactly one spelling of the name path"

    for spelling in NAME_PATH_SPELLINGS:
        arguments = _placeholder_arguments(mcp_tool.parameters)
        arguments.pop(declared[0], None)
        arguments[spelling] = "Outer/inner"
        assert asyncio.run(mcp_tool.run(arguments, Context())) == "ok"
        assert received_kwargs[-1][declared[0]] == "Outer/inner"
        assert spelling == declared[0] or spelling not in received_kwargs[-1]


def test_both_spellings_given_keeps_the_declared_one() -> None:
    class NamePathTool(BaseMockTool):
        def apply(self, name_path: str) -> str:
            """
            :param name_path: the name path
            """
            return name_path

        def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, mcp_ctx: Context | None = None, **kwargs) -> str:
            return self.apply(**kwargs)

    assert NamePathTool.get_param_aliases() == {"name_path_pattern": "name_path"}
    mcp_tool = make_tool(NamePathTool())
    # the alias is not rewritten over a value given under the declared spelling
    assert asyncio.run(mcp_tool.run({"name_path": "A", "name_path_pattern": "B"}, Context())) == "A"
