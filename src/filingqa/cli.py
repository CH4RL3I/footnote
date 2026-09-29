"""Command line: filingqa ingest | index | ask | eval."""

from __future__ import annotations

import argparse
import sys
import time

from . import config


def _progress(prefix: str):
    def show(done: int, total: int) -> None:
        print(f"\r{prefix}: embedded {done}/{total}", end="", file=sys.stderr, flush=True)
        if done == total:
            print(file=sys.stderr)

    return show


def cmd_ingest(args) -> None:
    from .corpus import ingest

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    filings = ingest(tickers, args.years)
    print(f"ingested {len(filings)} filings")


def _expand(value: str, options: tuple[str, ...]) -> list[str]:
    return list(options) if value == "all" else [value]


def cmd_index(args) -> None:
    from .index import build_index

    retrievers = _expand(args.retriever, config.RETRIEVERS)
    needs_vectors = any(r in ("dense", "hybrid") for r in retrievers)
    for chunking in _expand(args.chunking, config.CHUNKINGS):
        t = time.time()
        idx = build_index(chunking, needs_vectors, progress=_progress(chunking))
        secs = time.time() - t
        print(f"{chunking}: {len(idx.chunks)} chunks, vectors={needs_vectors} ({secs:.0f}s)")


def cmd_ask(args) -> None:
    from .answer import answer_question
    from .generate import make_generator
    from .index import load_index

    index = load_index(args.chunking)
    retriever = index.retriever(args.retriever)
    result = answer_question(args.question, index, retriever, make_generator(args.backend), args.k)
    print(result.text)
    print("\nSources:")
    for chunk in result.chunks:
        mark = "*" if chunk.id in result.cited else " "
        print(f" {mark} [{chunk.id}] {chunk.citation}")


def cmd_eval(args) -> None:
    from .evaluate import run_eval

    run_eval(
        chunkings=_expand(args.chunking, config.CHUNKINGS),
        retrievers=_expand(args.retriever, config.RETRIEVERS),
        e2e=args.e2e,
        e2e_config=tuple(args.e2e_config.split("+")),
        e2e_limit=args.e2e_limit,
        backend=args.backend,
        qualitative=not args.no_qualitative,
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="filingqa", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="download and parse 10-K filings from SEC EDGAR")
    s.add_argument("--tickers", default=",".join(config.DEFAULT_TICKERS))
    s.add_argument("--years", type=int, default=config.DEFAULT_YEARS)
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("index", help="chunk the corpus and build retrieval indexes")
    s.add_argument("--chunking", choices=[*config.CHUNKINGS, "all"], default="section")
    s.add_argument("--retriever", choices=[*config.RETRIEVERS, "all"], default="hybrid")
    s.set_defaults(fn=cmd_index)

    s = sub.add_parser("ask", help="answer one question with citations")
    s.add_argument("question")
    s.add_argument("--chunking", choices=config.CHUNKINGS, default="section")
    s.add_argument("--retriever", choices=config.RETRIEVERS, default="hybrid")
    s.add_argument("--backend", choices=["ollama", "anthropic"], default="ollama")
    s.add_argument("-k", type=int, default=6, help="chunks passed to the generator")
    s.set_defaults(fn=cmd_ask)

    s = sub.add_parser("eval", help="retrieval metrics for every configuration (+ optional e2e)")
    s.add_argument("--chunking", choices=[*config.CHUNKINGS, "all"], default="all")
    s.add_argument("--retriever", choices=[*config.RETRIEVERS, "all"], default="all")
    s.add_argument("--e2e", action="store_true", help="also score generated answers")
    s.add_argument("--e2e-config", default="section+hybrid", help="chunking+retriever for e2e")
    s.add_argument("--e2e-limit", type=int, default=None, help="cap number of e2e questions")
    s.add_argument("--backend", choices=["ollama", "anthropic"], default="ollama")
    s.add_argument("--no-qualitative", action="store_true")
    s.set_defaults(fn=cmd_eval)

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except Exception as exc:  # user-facing failures: missing env var, Ollama down, ...
        from .edgar import MissingUserAgent

        if isinstance(exc, MissingUserAgent):
            raise SystemExit(f"error: {exc}") from None
        raise


if __name__ == "__main__":
    main()
