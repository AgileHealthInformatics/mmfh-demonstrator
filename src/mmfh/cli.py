"""Command-line entry points.

    mmfh serve            # start the API and demo UI on http://127.0.0.1:8000
    mmfh scenario         # run the renal scenario and print a summary
    mmfh scenario --json  # ...or the full federated result
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _scenario(as_json: bool, purpose: str, deadline: float) -> int:
    from .broker import FederationBroker
    from .catalogue import Catalogue
    from .identity import IdentityIndex
    from .scenario import renal_lir

    broker = FederationBroker(Catalogue.load(), IdentityIndex.load())
    result = asyncio.run(broker.handle(renal_lir(purpose=purpose, deadline_seconds=deadline)))
    if as_json:
        print(result.model_dump_json(indent=2))
        return 0

    print(f"Request {result.request_id}  catalogue {result.catalogue_version}  purpose {result.purpose}")
    print(f"Overall: {result.overall_status.upper()}\n")
    print(f"{'Source':<14}{'Status':<22}{'Items':>6}  Detail")
    for s in result.sources:
        print(f"{s.source:<14}{s.status.value:<22}{s.items_returned:>6}  {s.detail}")
    for e in result.excluded:
        print(f"{e.source:<14}{'excluded':<22}{'-':>6}  {e.reason}")
    print()
    for i in result.items:
        shown = f"{i.rendered_value} {i.rendered_unit}" if i.rendered_value is not None else f"{i.native_value} {i.native_unit or ''}"
        native = f"(native {i.native_value} {i.native_unit})" if "derived" in i.flags else ""
        text = shown if len(str(shown)) < 40 else str(shown)[:37] + "..."
        print(f"{i.effective_time:%Y-%m-%d}  {i.represented_label:<40} {text:<22} {native:<22} {i.source:<11} {','.join(i.flags)}")
    for w in result.warnings:
        print(f"\n! {w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mmfh", description="Metadata-Mediated Federated Health demonstrator")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="Run the API and demo UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    sc = sub.add_parser("scenario", help="Run the renal-function scenario")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--purpose", default="direct-care", choices=["direct-care", "secondary-use", "research"])
    sc.add_argument("--deadline", type=float, default=2.0)
    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("mmfh.api:app", host=args.host, port=args.port)
        return 0
    return _scenario(args.json, args.purpose, args.deadline)


if __name__ == "__main__":
    sys.exit(main())
