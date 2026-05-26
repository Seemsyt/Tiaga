"""Language-specific parsers for dependency graph extraction.

Supports: Python, JavaScript, TypeScript, Java, Go, Rust, C, C++
Uses tree-sitter for consistent AST parsing across languages.
"""

import ast
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

# Try importing tree-sitter; fallback to regex-based extraction if unavailable
try:
    import tree_sitter
    from tree_sitter import Language, Parser
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False


@dataclass
class ExtractedDefinition:
    """Extracted function/class definition."""
    name: str
    type: str  # "function", "class", "method", "interface", "struct", "enum"
    lineno: int
    scope: List[str]  # Parent class/namespace hierarchy


@dataclass
class ExtractedDependency:
    """Extracted call/import/inheritance relationship."""
    source: str  # Full name of caller
    target: str  # Full name of callee
    dep_type: str  # "calls", "imports", "inherits", "implements"


class LanguageParser(ABC):
    """Abstract base class for language-specific parsers."""

    SUPPORTED_EXTENSIONS = []
    LANGUAGE_NAME = ""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.module_name = str(file_path)
        self.content = file_path.read_text(encoding="utf-8")
        self.definitions: List[ExtractedDefinition] = []
        self.dependencies: List[ExtractedDependency] = []

    @abstractmethod
    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse file and extract definitions and dependencies."""
        pass

    def get_full_id(self, name: str, scope: Optional[List[str]] = None) -> str:
        """Generate full ID for a node."""
        if scope is None:
            scope = []
        scope_str = "::".join(scope)
        if scope_str:
            return f"{self.module_name}::{scope_str}::{name}"
        return f"{self.module_name}::{name}"


class PythonParser(LanguageParser):
    """Python parser using AST."""

    SUPPORTED_EXTENSIONS = [".py"]
    LANGUAGE_NAME = "Python"

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse Python file using AST."""
        try:
            tree = ast.parse(self.content, filename=str(self.file_path))
            visitor = PythonASTVisitor(self.module_name)
            visitor.visit(tree)
            return visitor.definitions, visitor.dependencies
        except SyntaxError as e:
            print(f"Warning: Could not parse {self.file_path}: {e}")
            return [], []


class PythonASTVisitor(ast.NodeVisitor):
    """AST visitor for Python files."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.definitions: List[ExtractedDefinition] = []
        self.dependencies: List[ExtractedDependency] = []
        self.scope: List[str] = []
        self.imports: Dict[str, str] = {}

    def get_full_id(self, name: str) -> str:
        scope_str = "::".join(self.scope)
        if scope_str:
            return f"{self.module_name}::{scope_str}::{name}"
        return f"{self.module_name}::{name}"

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = alias.name
            # File-level dependency (resolved later by the graph builder).
            self.dependencies.append(
                ExtractedDependency(self.module_name, alias.name, "imports")
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        # Resolve imported symbols to the originating module (not symbol),
        # so module-level dependency graphs remain stable and readable.
        module_part = node.module or ""
        level_prefix = "." * getattr(node, "level", 0)
        target_module = f"{level_prefix}{module_part}" if (level_prefix or module_part) else ""
        if target_module:
            self.dependencies.append(
                ExtractedDependency(self.module_name, target_module, "imports")
            )

        if node.module:
            for alias in node.names:
                name = alias.asname or alias.name
                self.imports[name] = node.module
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        full_id = self.get_full_id(node.name)
        self.definitions.append(
            ExtractedDefinition(node.name, "class", node.lineno, self.scope.copy())
        )

        # Handle inheritance
        for base in node.bases:
            if isinstance(base, ast.Name):
                target_id = f"{self.module_name}::{base.id}"
                self.dependencies.append(
                    ExtractedDependency(full_id, target_id, "inherits")
                )

        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        full_id = self.get_full_id(node.name)
        func_type = "method" if self.scope else "function"
        self.definitions.append(
            ExtractedDefinition(node.name, func_type, node.lineno, self.scope.copy())
        )

        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call):
        caller_id = (
            self.get_full_id("__module__")
            if not self.scope
            else self.get_full_id(self.scope[-1])
        )

        if isinstance(node.func, ast.Name):
            target_name = node.func.id
            if target_name in self.imports:
                external_module = self.imports[target_name]
                target_id = f"{external_module}::{target_name}"
            else:
                target_id = f"{self.module_name}::{target_name}"
            self.dependencies.append(ExtractedDependency(caller_id, target_id, "calls"))

        elif isinstance(node.func, ast.Attribute):
            method_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                if obj_name in self.imports:
                    external_module = self.imports[obj_name]
                    target_id = f"{external_module}::{method_name}"
                else:
                    target_id = f"{self.module_name}::{obj_name}::{method_name}"
                self.dependencies.append(
                    ExtractedDependency(caller_id, target_id, "calls")
                )

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


class TreeSitterParser(LanguageParser):
    """Base class for tree-sitter based parsers."""

    TREE_SITTER_LANG = None  # Override in subclass

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse using tree-sitter."""
        if not HAS_TREE_SITTER:
            return [], []

        try:
            parser = Parser()
            parser.set_language(Language(self.TREE_SITTER_LANG))
            tree = parser.parse(self.content.encode("utf-8"))
            return self._extract_from_tree(tree.root_node), []
        except Exception as e:
            print(f"Warning: Could not parse {self.file_path} with tree-sitter: {e}")
            return [], []

    def _extract_from_tree(self, node, scope: Optional[List[str]] = None):
        """Extract definitions from tree-sitter AST."""
        if scope is None:
            scope = []

        definitions = []

        # Common node type patterns across languages
        if node.type in ["function_declaration", "method_declaration", "func", "function"]:
            name_node = self._find_child_by_type(node, ["identifier", "name"])
            if name_node:
                name = name_node.text.decode() if isinstance(name_node.text, bytes) else name_node.text
                definitions.append(
                    ExtractedDefinition(name, "function", node.start_point[0], scope.copy())
                )

        elif node.type in ["class_declaration", "class", "class_definition"]:
            name_node = self._find_child_by_type(node, ["identifier", "name"])
            if name_node:
                name = name_node.text.decode() if isinstance(name_node.text, bytes) else name_node.text
                new_scope = scope + [name]
                definitions.append(
                    ExtractedDefinition(name, "class", node.start_point[0], scope.copy())
                )
                # Recurse into class body
                for child in node.children:
                    definitions.extend(self._extract_from_tree(child, new_scope))
                return definitions

        # Recurse into children
        for child in node.children:
            definitions.extend(self._extract_from_tree(child, scope))

        return definitions

    @staticmethod
    def _find_child_by_type(node, types: List[str]):
        """Find first child with given type."""
        for child in node.children:
            if child.type in types:
                return child
        return None


class JavaScriptParser(TreeSitterParser):
    """JavaScript/TypeScript parser using tree-sitter."""

    # Include common JS/TS module formats and Vue SFCs (.vue) via regex fallback.
    SUPPORTED_EXTENSIONS = [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".vue"]
    LANGUAGE_NAME = "JavaScript"
    TREE_SITTER_LANG = "javascript"

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse JavaScript/TypeScript with fallback to regex."""
        if HAS_TREE_SITTER:
            definitions, _ = super().parse()
            if not definitions:
                # tree-sitter might be installed but not configured with languages.
                return self._parse_with_regex()
            _, dependencies = self._parse_with_regex()
            return definitions, dependencies
        return self._parse_with_regex()

    def _parse_with_regex(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Fallback regex-based parsing for JS/TS."""
        definitions = []
        dependencies = []

        # Function declarations: function foo() or async function foo()
        func_pattern = r"(?:async\s+)?(?:export\s+)?(?:default\s+)?(?:function|const|let|var)\s+(\w+)\s*(?:=|:)?.*?(?:=>|:.*?=>|\{|\(|;)"
        for match in re.finditer(func_pattern, self.content):
            name = match.group(1)
            if name not in ('if', 'for', 'while', 'switch', 'async'):  # Filter keywords
                lineno = self.content[:match.start()].count("\n")
                definitions.append(ExtractedDefinition(name, "function", lineno, []))

        # Class declarations: class Foo
        class_pattern = r"(?:export\s+)?(?:abstract\s+)?(?:default\s+)?class\s+(\w+)"
        for match in re.finditer(class_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "class", lineno, []))

        # Import statements
        import_pattern = r"import\s+(?:[\w\s,{}*as]*\s+)?from\s+['\"](.+?)['\"]"
        for match in re.finditer(import_pattern, self.content):
            module = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            dependencies.append(
                ExtractedDependency(self.module_name, module, "imports")
            )

        # Side-effect imports: import "./x";
        side_effect_pattern = r"import\s+['\"](.+?)['\"]\s*;"
        for match in re.finditer(side_effect_pattern, self.content):
            module = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            dependencies.append(
                ExtractedDependency(self.module_name, module, "imports")
            )

        # CommonJS requires: require("./x")
        require_pattern = r"require\(\s*['\"](.+?)['\"]\s*\)"
        for match in re.finditer(require_pattern, self.content):
            module = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            dependencies.append(
                ExtractedDependency(self.module_name, module, "imports")
            )

        # Function calls and method calls (foo(), obj.method(), Class.staticMethod())
        call_pattern = r"([a-zA-Z_]\w*)\s*\("
        for match in re.finditer(call_pattern, self.content):
            func_name = match.group(1)
            # Skip common keywords
            if func_name not in ('if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'new', 'async', 'await', 'typeof', 'throw', 'else'):
                lineno = self.content[:match.start()].count("\n")
                caller_id = f"{self.module_name}::__module__"
                target_id = f"{self.module_name}::{func_name}"
                dependencies.append(
                    ExtractedDependency(caller_id, target_id, "calls")
                )

        return definitions, dependencies


class JavaParser(TreeSitterParser):
    """Java parser using tree-sitter."""

    SUPPORTED_EXTENSIONS = [".java"]
    LANGUAGE_NAME = "Java"
    TREE_SITTER_LANG = "java"

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse Java with fallback to regex."""
        if HAS_TREE_SITTER:
            definitions, _ = super().parse()
            if not definitions:
                return self._parse_with_regex()
            _, dependencies = self._parse_with_regex()
            return definitions, dependencies
        return self._parse_with_regex()

    def _parse_with_regex(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Fallback regex-based parsing for Java."""
        definitions = []
        dependencies = []

        # Method declarations (more precise pattern)
        method_pattern = r"(?:public|private|protected|static|\s)+(?:\w+\s+)*(\w+)\s*\("
        for match in re.finditer(method_pattern, self.content):
            name = match.group(1)
            # Skip keywords
            if name not in ('if', 'for', 'while', 'switch', 'catch', 'synchronized'):
                lineno = self.content[:match.start()].count("\n")
                definitions.append(ExtractedDefinition(name, "method", lineno, []))

        # Class declarations: class Foo or class Foo extends Bar
        class_pattern = r"(?:public|private)?\s*(?:final\s+)?(?:abstract\s+)?class\s+(\w+)"
        for match in re.finditer(class_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "class", lineno, []))

        # Interface declarations
        interface_pattern = r"(?:public)?\s*interface\s+(\w+)"
        for match in re.finditer(interface_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "interface", lineno, []))

        # Import statements
        import_pattern = r"import\s+(.+?);"
        for match in re.finditer(import_pattern, self.content):
            module = match.group(1).strip()
            lineno = self.content[:match.start()].count("\n")
            dependencies.append(
                ExtractedDependency(self.module_name, module, "imports")
            )

        # Method/constructor calls: methodName( or ClassName(
        call_pattern = r"([a-zA-Z_]\w*)\s*\("
        for match in re.finditer(call_pattern, self.content):
            func_name = match.group(1)
            # Skip keywords
            if func_name not in ('if', 'for', 'while', 'switch', 'catch', 'synchronized', 'return', 'new', 'throw'):
                lineno = self.content[:match.start()].count("\n")
                caller_id = f"{self.module_name}::__module__"
                target_id = f"{self.module_name}::{func_name}"
                dependencies.append(
                    ExtractedDependency(caller_id, target_id, "calls")
                )

        return definitions, dependencies


class GoParser(TreeSitterParser):
    """Go parser using tree-sitter."""

    SUPPORTED_EXTENSIONS = [".go"]
    LANGUAGE_NAME = "Go"
    TREE_SITTER_LANG = "go"

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse Go with fallback to regex."""
        if HAS_TREE_SITTER:
            definitions, _ = super().parse()
            if not definitions:
                return self._parse_with_regex()
            _, dependencies = self._parse_with_regex()
            return definitions, dependencies
        return self._parse_with_regex()

    def _parse_with_regex(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Fallback regex-based parsing for Go."""
        definitions = []
        dependencies = []

        # Function declarations: func Foo() or func (receiver) Foo()
        func_pattern = r"func\s+(?:\(.*?\)\s+)?(\w+)\s*\("
        for match in re.finditer(func_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "function", lineno, []))

        # Struct declarations: type Foo struct
        struct_pattern = r"type\s+(\w+)\s+struct"
        for match in re.finditer(struct_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "struct", lineno, []))

        # Interface declarations: type Foo interface
        interface_pattern = r"type\s+(\w+)\s+interface"
        for match in re.finditer(interface_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "interface", lineno, []))

        # Import statements (single + block)
        for match in re.finditer(r'^\s*import\s+"([^"]+)"', self.content, flags=re.MULTILINE):
            module = match.group(1).strip()
            dependencies.append(ExtractedDependency(self.module_name, module, "imports"))
        for match in re.finditer(r"^\s*import\s*\(([\s\S]*?)\)", self.content, flags=re.MULTILINE):
            block = match.group(1)
            for inner in re.finditer(r'"([^"]+)"', block):
                module = inner.group(1).strip()
                dependencies.append(ExtractedDependency(self.module_name, module, "imports"))

        # Function/method calls: functionName( or package.functionName(
        call_pattern = r"([a-zA-Z_]\w*)\s*\("
        for match in re.finditer(call_pattern, self.content):
            func_name = match.group(1)
            # Skip keywords
            if func_name not in ('if', 'for', 'range', 'switch', 'select', 'defer', 'go', 'make', 'len', 'cap', 'append', 'copy', 'close', 'complex', 'real', 'imag', 'new', 'panic', 'recover'):
                lineno = self.content[:match.start()].count("\n")
                caller_id = f"{self.module_name}::__module__"
                target_id = f"{self.module_name}::{func_name}"
                dependencies.append(
                    ExtractedDependency(caller_id, target_id, "calls")
                )

        return definitions, dependencies


class RustParser(TreeSitterParser):
    """Rust parser using tree-sitter."""

    SUPPORTED_EXTENSIONS = [".rs"]
    LANGUAGE_NAME = "Rust"
    TREE_SITTER_LANG = "rust"

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse Rust with fallback to regex."""
        if HAS_TREE_SITTER:
            definitions, _ = super().parse()
            if not definitions:
                return self._parse_with_regex()
            _, dependencies = self._parse_with_regex()
            return definitions, dependencies
        return self._parse_with_regex()

    def _parse_with_regex(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Fallback regex-based parsing for Rust."""
        definitions = []
        dependencies = []

        # Function declarations: fn foo() or pub fn foo() or async fn foo()
        func_pattern = r"(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\("
        for match in re.finditer(func_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "function", lineno, []))

        # Struct declarations: struct Foo
        struct_pattern = r"(?:pub\s+)?struct\s+(\w+)"
        for match in re.finditer(struct_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "struct", lineno, []))

        # Enum declarations: enum Foo
        enum_pattern = r"(?:pub\s+)?enum\s+(\w+)"
        for match in re.finditer(enum_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "enum", lineno, []))

        # Trait declarations: trait Foo
        trait_pattern = r"(?:pub\s+)?trait\s+(\w+)"
        for match in re.finditer(trait_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "trait", lineno, []))

        # Impl declarations: impl Foo
        impl_pattern = r"impl\s+(?:<[^>]*>)?\s*(\w+)"
        for match in re.finditer(impl_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "impl", lineno, []))

        # Use statements (imports)
        import_pattern = r"^\s*(?:pub\s+)?use\s+([^;]+);"
        for match in re.finditer(import_pattern, self.content, flags=re.MULTILINE):
            module = match.group(1).strip()
            lineno = self.content[:match.start()].count("\n")
            dependencies.append(
                ExtractedDependency(self.module_name, module, "imports")
            )

        # Function/method calls: functionName( or Self::method(
        call_pattern = r"([a-zA-Z_]\w*)\s*\("
        for match in re.finditer(call_pattern, self.content):
            func_name = match.group(1)
            # Skip keywords
            if func_name not in ('if', 'for', 'while', 'match', 'loop', 'unsafe', 'fn', 'let', 'return', 'panic', 'assert', 'dbg', 'println', 'vec', 'format'):
                lineno = self.content[:match.start()].count("\n")
                caller_id = f"{self.module_name}::__module__"
                target_id = f"{self.module_name}::{func_name}"
                dependencies.append(
                    ExtractedDependency(caller_id, target_id, "calls")
                )

        return definitions, dependencies


class CParser(TreeSitterParser):
    """C/C++ parser using tree-sitter."""

    SUPPORTED_EXTENSIONS = [".c", ".h", ".cpp", ".cc", ".cxx", ".hpp"]
    LANGUAGE_NAME = "C/C++"
    TREE_SITTER_LANG = "cpp"

    def parse(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Parse C/C++ with fallback to regex."""
        if HAS_TREE_SITTER:
            definitions, _ = super().parse()
            if not definitions:
                return self._parse_with_regex()
            _, dependencies = self._parse_with_regex()
            return definitions, dependencies
        return self._parse_with_regex()

    def _parse_with_regex(self) -> Tuple[List[ExtractedDefinition], List[ExtractedDependency]]:
        """Fallback regex-based parsing for C/C++."""
        definitions = []
        dependencies = []

        # Function definitions: type func_name() - more flexible
        func_pattern = r"(?:inline\s+)?(?:static\s+)?(?:virtual\s+)?(?:const\s+)?\w+[\s\*&]*(?:::(\w+))?::)?(\w+)\s*\([^)]*\)\s*(?:const)?\s*(?:override)?\s*(?:final)?\s*(?:\{|;)"
        # Simpler pattern for function-like calls/definitions
        func_pattern_simple = r"([a-zA-Z_]\w*)\s*\(.*?\)\s*(?:\{|;|const|override)"
        
        lines = self.content.split('\n')
        for i, line in enumerate(lines):
            # Skip comments and preprocessor directives
            if line.strip().startswith('//') or line.strip().startswith('/*') or line.strip().startswith('#'):
                continue
            
            # Detect function definitions (rough heuristic)
            if re.search(r'\)\s*(?:\{|;|const|override)', line) and not any(kw in line for kw in ['if', 'for', 'while', 'switch', 'catch']):
                # Try to extract function name
                match = re.search(r'(\w+)\s*\([^)]*\)', line)
                if match:
                    name = match.group(1)
                    if name and name not in ('if', 'for', 'while', 'switch', 'catch', 'return', 'else'):
                        definitions.append(ExtractedDefinition(name, "function", i, []))

        # Class/struct declarations: class Foo or struct Foo
        class_pattern = r"(?:class|struct)\s+(\w+)"
        for match in re.finditer(class_pattern, self.content):
            name = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            definitions.append(ExtractedDefinition(name, "class", lineno, []))

        # Include statements
        include_pattern = r'#include\s+[<"](.+?)[>"]'
        for match in re.finditer(include_pattern, self.content):
            module = match.group(1)
            lineno = self.content[:match.start()].count("\n")
            dependencies.append(
                ExtractedDependency(self.module_name, module, "imports")
            )

        # Function/method calls: functionName( or Class::method(
        call_pattern = r"([a-zA-Z_]\w*)\s*\("
        for match in re.finditer(call_pattern, self.content):
            func_name = match.group(1)
            # Skip keywords
            if func_name not in ('if', 'for', 'while', 'switch', 'return', 'sizeof', 'alignof', 'typeid', 'catch', 'new', 'delete', 'throw'):
                lineno = self.content[:match.start()].count("\n")
                caller_id = f"{self.module_name}::__module__"
                target_id = f"{self.module_name}::{func_name}"
                dependencies.append(
                    ExtractedDependency(caller_id, target_id, "calls")
                )

        return definitions, dependencies


# Language registry
PARSER_MAP = {
    ".py": PythonParser,
    ".js": JavaScriptParser,
    ".jsx": JavaScriptParser,
    ".mjs": JavaScriptParser,
    ".cjs": JavaScriptParser,
    ".ts": JavaScriptParser,
    ".tsx": JavaScriptParser,
    ".mts": JavaScriptParser,
    ".cts": JavaScriptParser,
    ".vue": JavaScriptParser,
    ".java": JavaParser,
    ".go": GoParser,
    ".rs": RustParser,
    ".c": CParser,
    ".h": CParser,
    ".cpp": CParser,
    ".cc": CParser,
    ".cxx": CParser,
    ".hpp": CParser,
}

SUPPORTED_LANGUAGES = {
    "Python": [".py"],
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs", ".vue"],
    "TypeScript": [".ts", ".tsx", ".mts", ".cts"],
    "Java": [".java"],
    "Go": [".go"],
    "Rust": [".rs"],
    "C": [".c", ".h"],
    "C++": [".cpp", ".cc", ".cxx", ".hpp"],
}


def get_parser(file_path: Path) -> Optional[LanguageParser]:
    """Get appropriate parser for file."""
    suffix = file_path.suffix.lower()
    parser_class = PARSER_MAP.get(suffix)
    if parser_class:
        return parser_class(file_path)
    return None
