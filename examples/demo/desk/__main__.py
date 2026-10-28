"""python -m examples.demo.desk --root out/demo"""

import argparse
import sys
from pathlib import Path

from .server import make_server

REPO = Path(__file__).resolve().parents[3]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Low Tide desk")
    parser.add_argument("--root", default=str(REPO / "out" / "demo"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    httpd = make_server(args.root, args.host, args.port)
    host, port = httpd.server_address[:2]
    print("Low Tide desk  http://%s:%s/" % (host, port))
    print("root  %s" % httpd.root)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        httpd.server_close()


if __name__ == "__main__":
    sys.exit(main())
