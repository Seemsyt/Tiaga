#!/usr/bin/env python3
"""Lightweight smoke test for Tiaga's supported CLI surfaces."""

import importlib.util
import sys


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None

def test_imports():
    """Test that the main package modules can be imported when deps exist."""
    print("Testing imports...")
    required = ["typer", "prompt_toolkit", "langgraph", "aiosqlite"]
    missing = [name for name in required if not has_module(name)]
    if missing:
        print(f"⚠ Skipping import smoke test, missing dependencies: {', '.join(missing)}")
        return True

    try:
        import tiaga
        print("✓ tiaga package imports")
    except Exception as e:
        print(f"✗ Failed to import tiaga: {e}")
        return False
    
    try:
        from tiaga import main
        print("✓ tiaga.main imports")
    except Exception as e:
        print(f"✗ Failed to import tiaga.main: {e}")
        return False
    
    try:
        from tiaga import __main__
        print("✓ tiaga.__main__ imports")
    except Exception as e:
        print(f"✗ Failed to import tiaga.__main__: {e}")
        return False

    try:
        from tiaga import prompt_toolkit_tui
        print("✓ tiaga.prompt_toolkit_tui imports")
    except Exception as e:
        print(f"✗ Failed to import tiaga.prompt_toolkit_tui: {e}")
        return False
    
    try:
        from tiaga import utils
        print("✓ tiaga.utils imports")
    except Exception as e:
        print(f"✗ Failed to import tiaga.utils: {e}")
        return False
    
    return True

def test_dependencies():
    """Report whether the expected runtime dependencies are available."""
    print("\nTesting dependencies...")
    deps = [
        'prompt_toolkit',
        'pygments',
        'rich',
        'typer',
        'langgraph',
        'aiosqlite',
    ]
    
    all_ok = True
    for dep in deps:
        try:
            __import__(dep.replace('-', '_'))
            print(f"✓ {dep}")
        except ImportError:
            print(f"⚠ {dep} not installed")
            all_ok = False
    
    if not all_ok:
        print("⚠ Runtime dependency check is informational in this smoke test.")
    return True

def test_cli_commands():
    """Test that the supported commands are registered when deps exist."""
    print("\nTesting CLI commands...")
    if not has_module("typer"):
        print("⚠ Skipping CLI registration check, typer is not installed")
        return True
    try:
        from tiaga.main import app
        commands = [command.name for command in app.registered_commands]
        print(f"Registered commands: {', '.join(commands)}")
        if 'chat' in commands and 'tui' in commands:
            print("✓ Both 'chat' and 'tui' commands available")
            return True
        else:
            print("✗ Missing commands")
            return False
    except Exception as e:
        print(f"✗ Failed to load CLI: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Tiaga TUI Test Suite")
    print("=" * 50)
    
    results = []
    results.append(("Imports", test_imports()))
    results.append(("Dependencies", test_dependencies()))
    results.append(("CLI Commands", test_cli_commands()))
    
    print("\n" + "=" * 50)
    print("Summary:")
    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {name}: {status}")
    
    all_ok = all(r[1] for r in results)
    sys.exit(0 if all_ok else 1)
