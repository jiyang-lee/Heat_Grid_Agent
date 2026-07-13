from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[1]
SRC: Final = ROOT / "src"
BACKEND_FRAGMENT: Final = "v2_postgres_react_ops/backend"


def test_core_graph_imports_without_backend_path() -> None:
    script = "\n".join(
        [
            "from pathlib import Path",
            "import sys",
            f"sys.path.insert(0, {str(SRC)!r})",
            "assert not any(" + repr(BACKEND_FRAGMENT) + " in path.replace(chr(92), '/') for path in sys.path)",
            "import heatgrid_ops.agent.graph as graph",
            "assert graph.build_agent_graph",
            "assert not any(" + repr(BACKEND_FRAGMENT) + " in str(module_file).replace(chr(92), '/') for module in sys.modules.values() if (module_file := getattr(module, '__file__', '')))",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
