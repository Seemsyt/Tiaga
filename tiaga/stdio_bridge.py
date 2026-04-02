#!/usr/bin/env python3
"""
Compatibility entrypoint for older bridge imports.
"""

import asyncio

from .bridge import main


if __name__ == "__main__":
    asyncio.run(main())
