from __future__ import annotations

import argparse

from aiohttp import web

from .app import create_app


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ld2460-server", description="LD2460 presence dashboard server"
    )
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8099)
    args = p.parse_args(argv)
    web.run_app(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
