import sys

from main import run_namespace_server


def main(argv: list[str]) -> None:
    run_namespace_server(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
