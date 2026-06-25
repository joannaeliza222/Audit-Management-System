import sys
import functools


def parse_int(s: str) -> int:
    return int(s.strip())


def power_of_four(n: int) -> int:
    return n * n * n * n


def collect_cases(n: int, cases: list) -> list:
    if n == 0:
        return cases
    x = parse_int(input())
    yn_line = input().split()
    return collect_cases(n - 1, cases + [(x, yn_line)])


def solve_case(case: tuple) -> str:
    x, yn_line = case
    if len(yn_line) != x:
        return "-1"
    yn_ints = list(map(parse_int, yn_line))
    non_positives = list(filter(lambda y: y <= 0, yn_ints))
    total = functools.reduce(lambda acc, y: acc + power_of_four(y), non_positives, 0)
    return str(total)


def main() -> None:
    sys.setrecursionlimit(100000)
    n = parse_int(input())
    cases = collect_cases(n, [])
    results = list(map(solve_case, cases))
    print('\n'.join(results))


if __name__ == "__main__":
    main()