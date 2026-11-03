"""Select, inspect or serve one explicit sealed local workbench."""
import argparse
import errno
import json
from pathlib import Path
import sys


PRODUCT_ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PRODUCT_ROOT / 'src'))

from autoresearch.current_workbench import select_bundle, status, create_current_server, DEFAULT_PORT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    select = modes.add_parser('select')
    select.add_argument('--bundle', required=True, help='Sealed bundle directory; relative to product root.')
    select.add_argument('--label', help='Local display label, not scientific acceptance.')
    modes.add_parser('status')
    serve = modes.add_parser('serve'); serve.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    try:
        if args.mode == 'select':
            result = select_bundle(args.bundle, label=args.label, product_root=PRODUCT_ROOT)
        elif args.mode == 'status':
            result = status(product_root=PRODUCT_ROOT)
        else:
            server = create_current_server(product_root=PRODUCT_ROOT, port=args.port)
            print('只读封存工作台：http://127.0.0.1:%d/ （不启动研究或模型；Ctrl+C关闭）' % server.server_port, flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally: server.server_close()
            return 0
        print(json.dumps({'ok': True, **result}, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        busy = isinstance(error, OSError) and (error.errno == errno.EADDRINUSE or getattr(error, 'winerror', None) == 10048)
        message = ('端口已被占用；未终止任何进程，也未更换端口。请确认占用情况或显式指定其他端口。' if busy else str(error))
        print(json.dumps({'ok': False, 'error': message, 'model_calls': 0, 'new_fits': 0}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
