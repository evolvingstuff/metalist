import sys

from main import run_orchestrated_namespace_server


def main(argv: list[str]) -> None:
    run_orchestrated_namespace_server(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
