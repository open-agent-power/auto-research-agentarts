"""Dependency-free command help for the opt-in AgentArts runtime adapter."""

import argparse
from importlib import import_module
import sys


_OPTIONAL_IMPORTS = {
    "agentarts", "agentarts.sdk", "agentarts.sdk.runtime",
    "starlette", "starlette.middleware", "starlette.responses",
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="autoresearch-runtime",
        description="Run the optional AgentArts HTTP adapter using existing operator environment settings.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Optional dependency installation:\n"
                "  python -m pip install 'agentarts-autoresearch[runtime]'\n\n"
                "Set AUTORESEARCH_WORKSPACE to an absolute storage directory before starting.\n"
                "AUTORESEARCH_BIND_HOST and AGENT_RUN_PORT retain the adapter's existing\n"
                "behavior (defaults: 127.0.0.1 and 8080). No server starts when displaying help."),
    )
    parser.parse_args(argv)
    try:
        runtime = import_module(".runtime", package=__package__)
    except ModuleNotFoundError as error:
        if error.name not in _OPTIONAL_IMPORTS:
            raise
        print(
            f"Missing optional runtime dependency: {error.name}. "
            "Install the runtime extra with: python -m pip install 'agentarts-autoresearch[runtime]'. "
            "No runtime server was started.",
            file=sys.stderr,
        )
        return 2
    return runtime.main()


if __name__ == "__main__":
    raise SystemExit(main())
