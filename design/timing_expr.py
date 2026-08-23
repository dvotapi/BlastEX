"""Safe timing-expression language. Never uses Python eval/exec.

Supported:
  numbers, + - * / % **, parentheses
  comparisons < > <= >= == != (yield 0 or 1)
  boolean and / or / not
  functions: abs, min, max, floor, ceil, round, sqrt
  variables: row, col, x, y, z, index, hole_index, interval, base, n, i
"""
from __future__ import annotations

import math
from typing import Any, Callable

ALLOWED_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": lambda value: abs(float(value)),
    "min": lambda *values: float(min(float(v) for v in values)),
    "max": lambda *values: float(max(float(v) for v in values)),
    "floor": lambda value: float(math.floor(float(value))),
    "ceil": lambda value: float(math.ceil(float(value))),
    "round": lambda value, digits=0: float(round(float(value), int(digits))),
    "sqrt": lambda value: math.sqrt(float(value)),
}

ALLOWED_VARIABLES = frozenset(
    {"row", "col", "x", "y", "z", "index", "hole_index", "interval", "base", "n", "i"}
)

_COMPARISONS = {"==", "!=", "<=", ">=", "<", ">"}
_ADDS = {"+", "-"}
_MULS = {"*", "/", "%"}


class TimingExprError(ValueError):
    """Expression is empty, unsafe, or cannot be evaluated."""


def _tokenize(source: str) -> list[tuple[str, Any]]:
    text = source.strip()
    if not text:
        raise TimingExprError("Пустое выражение.")
    if len(text) > 400:
        raise TimingExprError("Выражение слишком длинное.")
    tokens: list[tuple[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            name = text[start:i]
            lowered = name.lower()
            if lowered in {"and", "or", "not"}:
                tokens.append(("op", lowered))
            else:
                tokens.append(("id", lowered))
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            start = i
            i += 1
            while i < n and (text[i].isdigit() or text[i] == "."):
                i += 1
            if i < n and text[i] in {"e", "E"}:
                i += 1
                if i < n and text[i] in {"+", "-"}:
                    i += 1
                while i < n and text[i].isdigit():
                    i += 1
            raw = text[start:i]
            try:
                tokens.append(("num", float(raw)))
            except ValueError as exc:
                raise TimingExprError(f"Некорректное число: {raw}") from exc
            continue
        if text.startswith("**", i):
            tokens.append(("op", "**"))
            i += 2
            continue
        if text.startswith("==", i) or text.startswith("!=", i) or text.startswith("<=", i) or text.startswith(">=", i):
            tokens.append(("op", text[i : i + 2]))
            i += 2
            continue
        if ch in "+-*/%()<>," :
            tokens.append(("op", ch))
            i += 1
            continue
        raise TimingExprError(f"Недопустимый символ: {ch!r}")
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, Any]], variables: dict[str, float]):
        self.tokens = tokens
        self.pos = 0
        self.variables = variables

    def peek(self) -> tuple[str, Any] | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def eat(self, kind: str | None = None, value: Any = None) -> tuple[str, Any]:
        token = self.peek()
        if token is None:
            raise TimingExprError("Неожиданный конец выражения.")
        if kind is not None and token[0] != kind:
            raise TimingExprError("Неожиданный фрагмент выражения.")
        if value is not None and token[1] != value:
            raise TimingExprError(f"Ожидалось {value!r}.")
        self.pos += 1
        return token

    def parse(self) -> float:
        value = self.parse_or()
        if self.peek() is not None:
            raise TimingExprError("Лишние символы в конце выражения.")
        return float(value)

    def parse_or(self) -> float:
        value = self.parse_and()
        while self.peek() == ("op", "or"):
            self.eat()
            other = self.parse_and()
            value = 1.0 if (value or other) else 0.0
        return value

    def parse_and(self) -> float:
        value = self.parse_not()
        while self.peek() == ("op", "and"):
            self.eat()
            other = self.parse_not()
            value = 1.0 if (value and other) else 0.0
        return value

    def parse_not(self) -> float:
        if self.peek() == ("op", "not"):
            self.eat()
            return 0.0 if self.parse_not() else 1.0
        return self.parse_comparison()

    def parse_comparison(self) -> float:
        value = self.parse_add()
        token = self.peek()
        if token and token[0] == "op" and token[1] in _COMPARISONS:
            op = self.eat()[1]
            other = self.parse_add()
            if op == "==":
                return 1.0 if value == other else 0.0
            if op == "!=":
                return 1.0 if value != other else 0.0
            if op == "<":
                return 1.0 if value < other else 0.0
            if op == ">":
                return 1.0 if value > other else 0.0
            if op == "<=":
                return 1.0 if value <= other else 0.0
            return 1.0 if value >= other else 0.0
        return value

    def parse_add(self) -> float:
        value = self.parse_mul()
        while self.peek() and self.peek()[0] == "op" and self.peek()[1] in _ADDS:
            op = self.eat()[1]
            other = self.parse_mul()
            value = value + other if op == "+" else value - other
        return value

    def parse_mul(self) -> float:
        value = self.parse_power()
        while self.peek() and self.peek()[0] == "op" and self.peek()[1] in _MULS:
            op = self.eat()[1]
            other = self.parse_power()
            if op == "*":
                value = value * other
            elif op == "%":
                if other == 0:
                    raise TimingExprError("Деление по модулю на ноль.")
                value = value % other
            else:
                if other == 0:
                    raise TimingExprError("Деление на ноль.")
                value = value / other
        return value

    def parse_power(self) -> float:
        value = self.parse_unary()
        if self.peek() == ("op", "**"):
            self.eat()
            exponent = self.parse_power()
            if abs(exponent) > 12 or abs(value) > 1e6:
                raise TimingExprError("Слишком большая степень.")
            return float(value**exponent)
        return value

    def parse_unary(self) -> float:
        if self.peek() == ("op", "+"):
            self.eat()
            return self.parse_unary()
        if self.peek() == ("op", "-"):
            self.eat()
            return -self.parse_unary()
        return self.parse_primary()

    def parse_primary(self) -> float:
        token = self.peek()
        if token is None:
            raise TimingExprError("Ожидалось значение.")
        if token[0] == "num":
            return float(self.eat()[1])
        if token == ("op", "("):
            self.eat()
            value = self.parse_or()
            self.eat("op", ")")
            return value
        if token[0] == "id":
            name = self.eat()[1]
            if self.peek() == ("op", "("):
                return self._call(name)
            if name not in ALLOWED_VARIABLES:
                raise TimingExprError(f"Неизвестная переменная: {name}")
            if name not in self.variables:
                raise TimingExprError(f"Переменная {name} не задана.")
            return float(self.variables[name])
        raise TimingExprError("Неожиданный фрагмент выражения.")

    def _call(self, name: str) -> float:
        if name not in ALLOWED_FUNCTIONS:
            raise TimingExprError(f"Неизвестная функция: {name}")
        self.eat("op", "(")
        args: list[float] = []
        if self.peek() != ("op", ")"):
            args.append(self.parse_or())
            while self.peek() == ("op", ","):
                self.eat()
                args.append(self.parse_or())
        self.eat("op", ")")
        if not args:
            raise TimingExprError(f"Функция {name} требует аргументы.")
        try:
            return float(ALLOWED_FUNCTIONS[name](*args))
        except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
            raise TimingExprError(f"Ошибка функции {name}.") from exc


def evaluate_timing_expression(source: str, variables: dict[str, float]) -> float:
    """Evaluate a timing expression against a whitelist of names. No eval."""
    safe_vars = {key: float(value) for key, value in variables.items() if key in ALLOWED_VARIABLES}
    parser = _Parser(_tokenize(source), safe_vars)
    result = parser.parse()
    if not math.isfinite(result):
        raise TimingExprError("Результат выражения не является конечным числом.")
    return result


def try_evaluate_timing_expression(
    source: str, variables: dict[str, float]
) -> tuple[float | None, str | None]:
    try:
        return evaluate_timing_expression(source, variables), None
    except TimingExprError as exc:
        return None, str(exc)
