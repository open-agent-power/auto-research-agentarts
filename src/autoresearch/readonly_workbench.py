"""Serve the saved-study and stored-project views from an existing manager.

This loopback-only host never enables actions or model execution. Its immutable
SQLite readers require that no other process is writing the original manager or
project while they are read; they are not an operating-system isolation boundary.
"""
import argparse
import json
import sys


def _port(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('Use a port from 0 to 65535.') from None
    if not 0 <= number <= 65535:
        raise argparse.ArgumentTypeError('Use a port from 0 to 65535.')
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--root', required=True, help='Existing local manager directory; it will not be created or repaired.')
    parser.add_argument('--port', type=_port, default=18791, help='Loopback port (default: 18791; 0 selects an available port).')
    args = parser.parse_args(argv)

    # Parse help and reject unsupported options before loading product dependencies.
    try:
        from .local_workbench import LocalWorkbench
        from .project_workbench import create_project_server
    except ModuleNotFoundError as error:
        print(json.dumps({'ok': False, 'code': 'DEPENDENCY_NOT_AVAILABLE',
                          'message': 'A required runtime dependency is unavailable.', 'dependency': error.name}), file=sys.stderr)
        return 2
    try:
        workspace = LocalWorkbench.open_readonly(args.root)
        server = create_project_server(local_workspace=workspace, allow_local_actions=False, port=args.port)
    except Exception as error:
        print(json.dumps({'ok': False, 'code': getattr(error, 'code', 'READ_ONLY_START_FAILED'),
                          'message': 'The existing manager could not be opened as a read-only workbench.'}), file=sys.stderr)
        return 2
    try:
        print(f'Read-only workbench: http://127.0.0.1:{server.server_port}/#/saved-study', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
