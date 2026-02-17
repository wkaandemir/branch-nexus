"""Module entrypoint for `python -m branchnexus`."""

try:
    from .cli import run
except ImportError:
    # Frozen one-file builds can execute this module outside package context.
    from branchnexus.cli import run


if __name__ == "__main__":
    raise SystemExit(run())
