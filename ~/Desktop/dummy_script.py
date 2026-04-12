#!/usr/bin/env python3
"""
Dummy Python script for testing purposes.
"""

def greet(name):
    """Return a greeting message."""
    return f"Hello, {name}!"

def calculate_sum(a, b):
    """Calculate the sum of two numbers."""
    return a + b

def main():
    print("This is a dummy Python script.")
    print(greet("World"))
    result = calculate_sum(5, 3)
    print(f"5 + 3 = {result}")

if __name__ == "__main__":
    main()