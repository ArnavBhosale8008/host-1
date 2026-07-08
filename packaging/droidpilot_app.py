"""PyInstaller entry point.

PyInstaller needs a real script file as its entry point (it cannot freeze a
``python -m`` invocation directly), so this thin wrapper just delegates to the
package's :func:`droidpilot.__main__.main`. When frozen with no arguments it
launches the GUI, exactly like running ``droidpilot``.
"""

from __future__ import annotations

import sys

from droidpilot.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
