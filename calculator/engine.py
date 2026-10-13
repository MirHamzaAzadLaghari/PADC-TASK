"""Calculation engine for the Premium Calculator.

A small hand-written tokenizer and recursive-descent parser that evaluates
while it parses (no AST is built, no ``eval``/``exec`` is used). It is pure
Python with zero dependencies and has no knowledge of the UI.

Grammar (lowest to highest precedence)::

    expr    := term (('+' | '-') term)*
    term    := unary (('*' | '/' | implicit) unary)*
    unary   := ('+' | '-') unary | power
    power   := postfix ('^' unary)?          # right-associative
    postfix := primary ('!' | '%')*
    primary := NUMBER | NAME | NAME '(' args ')' | NAME postfix | '(' expr ')'
"""

from __future__ import annotations

import math
import re
import sys
from decimal import Decimal, localcontext

# Allow exact display of very large integers such as 500!
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

MAX_EXPRESSION_LENGTH = 500
MAX_FACTORIAL = 1000
SIGNIFICANT_DIGITS = 12


class CalcError(Exception):
    """A user-facing calculation error (message is safe to show as-is)."""


# --------------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------------- #
NUM, NAME, OP = 0, 1, 2

_TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
      | (?P<name>log10|log2|[a-z]+)
      | (?P<op>[-+*/^%!(),])
    )""",
    re.VERBOSE,
)

_NORMALISE = str.maketrans({"×": "*", "÷": "/", "−": "-", "–": "-", "π": "pi", "τ": "tau"})


def _normalise(text: str) -> str:
    return text.translate(_NORMALISE).replace("√", "sqrt ").replace("∛", "cbrt ").replace("**", "^").lower()


def tokenize(text: str) -> list[tuple[int, object]]:
    s = _normalise(text)
    tokens: list[tuple[int, object]] = []
    pos, n = 0, len(s)
    match = _TOKEN_RE.match
    while pos < n:
        m = match(s, pos)
        if m is None:
            rest = s[pos:].strip()
            if not rest:
                break
            raise CalcError(f"Unexpected '{rest[0]}'")
        pos = m.end()
        kind = m.lastgroup
        if kind == "num":
            t = m.group("num")
            tokens.append((NUM, float(t) if ("." in t or "e" in t) else int(t)))
        elif kind == "name":
            tokens.append((NAME, m.group("name")))
        else:
            tokens.append((OP, m.group("op")))
    return tokens


# --------------------------------------------------------------------------- #
# Number helpers
# --------------------------------------------------------------------------- #
def _pow(a, b):
    if a == 0 and b < 0:
        raise CalcError("Cannot divide by zero")
    if isinstance(a, int) and isinstance(b, int):
        if b >= 0:
            if a.bit_length() * b > 40_000:  # keep exact ints to ~12k digits
                return float(a) ** b
            return a**b
        return a**b  # int ** negative int -> float
    if a < 0 and not float(b).is_integer():
        raise CalcError("Invalid input")
    return float(a) ** b


def _factorial(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if not isinstance(v, int) or v < 0:
        raise CalcError("Factorial needs a whole number ≥ 0")
    if v > MAX_FACTORIAL:
        raise CalcError("Number too large")
    return math.factorial(v)


def format_number(x) -> str:
    """Format a result with up to 12 significant digits, hiding float noise."""
    if isinstance(x, bool):
        x = int(x)
    if isinstance(x, int):
        if abs(x) < 10**15:
            return str(x)
        with localcontext() as ctx:
            ctx.prec = SIGNIFICANT_DIGITS
            s = format(+Decimal(x), "e")
        return _tidy_sci(s)
    if x != x:
        raise CalcError("Invalid input")
    if x in (math.inf, -math.inf):
        raise CalcError("Result too large")
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    s = format(x, f".{SIGNIFICANT_DIGITS}g")
    return _tidy_sci(s) if "e" in s.lower() else s


def _tidy_sci(s: str) -> str:
    mant, _, exp = s.lower().partition("e")
    if "." in mant:
        mant = mant.rstrip("0").rstrip(".")
    return f"{mant}e{int(exp):+d}"


# --------------------------------------------------------------------------- #
# Parser / evaluator
# --------------------------------------------------------------------------- #
class _Parser:
    __slots__ = ("t", "i", "n", "calc")

    def __init__(self, tokens, calc):
        self.t, self.i, self.n, self.calc = tokens, 0, len(tokens), calc

    def _is_op(self, ch) -> bool:
        if self.i < self.n:
            k, v = self.t[self.i]
            return k == OP and v == ch
        return False

    def parse(self):
        if not self.n:
            raise CalcError("Empty expression")
        value = self.expr()
        if self.i < self.n:
            raise CalcError(f"Unexpected '{self.t[self.i][1]}'")
        return value

    def expr(self):
        t, n = self.t, self.n
        left = self.term()
        while self.i < n:
            k, v = t[self.i]
            if k != OP or v not in ("+", "-"):
                break
            self.i += 1
            start = self.i
            right = self.term()
            # "200 + 10%" means 200 + (10% of 200)
            if self.i - start == 2 and t[start][0] == NUM and t[start + 1][1] == "%":
                right = left * right
            left = left + right if v == "+" else left - right
        return left

    def term(self):
        t, n = self.t, self.n
        left = self.unary()
        while self.i < n:
            k, v = t[self.i]
            if k == OP:
                if v == "*":
                    self.i += 1
                    left = left * self.unary()
                elif v == "/":
                    self.i += 1
                    right = self.unary()
                    if right == 0:
                        raise CalcError("Cannot divide by zero")
                    left = left / right
                elif v == "(":  # implicit multiplication: 2(3+4)
                    left = left * self.unary()
                else:
                    break
            elif k == NAME:  # implicit multiplication: 2pi, 3sin(30)
                left = left * self.unary()
            else:
                raise CalcError(f"Unexpected number '{v}'")
        return left

    def unary(self):
        if self.i < self.n:
            k, v = self.t[self.i]
            if k == OP and v in ("-", "+"):
                self.i += 1
                x = self.unary()
                return -x if v == "-" else x
        return self.power()

    def power(self):
        base = self.postfix()
        if self._is_op("^"):
            self.i += 1
            return _pow(base, self.unary())
        return base

    def postfix(self):
        v = self.primary()
        while self.i < self.n:
            k, op = self.t[self.i]
            if k != OP:
                break
            if op == "!":
                v = _factorial(v)
            elif op == "%":
                v = v / 100
            else:
                break
            self.i += 1
        return v

    def primary(self):
        if self.i >= self.n:
            raise CalcError("Incomplete expression")
        k, v = self.t[self.i]
        self.i += 1
        if k == NUM:
            return v
        if k == NAME:
            return self._name(v)
        if v == "(":
            value = self.expr()
            if self._is_op(")"):
                self.i += 1
            elif self.i < self.n:
                raise CalcError(f"Unexpected '{self.t[self.i][1]}'")
            return value  # missing ')' at the end is auto-closed
        raise CalcError(f"Unexpected '{v}'")

    def _name(self, name):
        calc = self.calc
        if name in calc.constants:
            return calc.constants[name]()
        if name not in calc.functions:
            raise CalcError(f"Unknown name '{name}'")
        if self._is_op("("):
            self.i += 1
            args = []
            if self._is_op(")"):
                self.i += 1
            else:
                while True:
                    args.append(self.expr())
                    if self._is_op(","):
                        self.i += 1
                    elif self._is_op(")"):
                        self.i += 1
                        break
                    elif self.i >= self.n:
                        break  # auto-close
                    else:
                        raise CalcError(f"Unexpected '{self.t[self.i][1]}'")
        else:
            args = [self.postfix()]  # "sqrt 9", "sin30"
        return calc.call(name, args)


class Calculator:
    """Stateful calculator: angle mode, last answer and a memory register."""

    def __init__(self, angle_mode: str = "DEG", auto_save_timing: bool = True):
        self.angle_mode = angle_mode  # "DEG" or "RAD"
        self.ans = 0
        self.memory = 0
        self.last_execution_time_us = 0.0
        self.auto_save_timing = auto_save_timing
        self.constants = {
            "pi": lambda: math.pi,
            "e": lambda: math.e,
            "tau": lambda: math.tau,
            "ans": lambda: self.ans,
        }
        # name -> (allowed argument counts, implementation)
        self.functions = {
            "sin": ((1,), self._sin), "cos": ((1,), self._cos), "tan": ((1,), self._tan),
            "asin": ((1,), lambda x: self._from_rad(math.asin(x))),
            "acos": ((1,), lambda x: self._from_rad(math.acos(x))),
            "atan": ((1,), lambda x: self._from_rad(math.atan(x))),
            "sinh": ((1,), math.sinh), "cosh": ((1,), math.cosh), "tanh": ((1,), math.tanh),
            "ln": ((1,), self._ln), "log": ((1, 2), self._log), "log10": ((1,), self._log),
            "log2": ((1,), lambda x: self._ln_base(x, 2)),
            "exp": ((1,), math.exp),
            "sqrt": ((1,), self._sqrt), "cbrt": ((1,), self._cbrt), "root": ((2,), self._root),
            "abs": ((1,), abs), "fact": ((1,), _factorial),
            "floor": ((1,), math.floor), "ceil": ((1,), math.ceil),
            "round": ((1, 2), self._round), "mod": ((2,), self._mod),
        }

    # -- execution time logging --------------------------------------------- #
    def _save_execution_time(self, expr: str, result: str, duration_us: float) -> None:
        """Append calculation timing record to execution_times.log and execution_times.csv."""
        try:
            import os
            from datetime import datetime
            log_dir = os.path.dirname(os.path.abspath(__file__))
            if os.path.basename(log_dir) == "calculator":
                log_dir = os.path.dirname(log_dir)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            duration_ms = duration_us / 1000.0

            log_path = os.path.join(log_dir, "execution_times.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] Expr: {expr:<30} | Result: {result:<15} | Time: {duration_us:>8.2f} µs ({duration_ms:.4f} ms)\n")

            csv_path = os.path.join(log_dir, "execution_times.csv")
            write_header = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
            with open(csv_path, "a", encoding="utf-8") as f:
                if write_header:
                    f.write("timestamp,expression,result,execution_time_us,execution_time_ms\n")
                safe_expr = f'"{expr}"' if ("," in expr or '"' in expr) else expr
                safe_res = f'"{result}"' if ("," in result or '"' in result) else result
                f.write(f"{timestamp},{safe_expr},{safe_res},{duration_us:.2f},{duration_ms:.4f}\n")
        except Exception:
            pass

    # -- public API --------------------------------------------------------- #
    def evaluate(self, text: str):
        """Return the numeric value of ``text`` (int or float)."""
        if len(text) > MAX_EXPRESSION_LENGTH:
            raise CalcError("Expression too long")
        try:
            return _Parser(tokenize(text), self).parse()
        except ZeroDivisionError:
            raise CalcError("Cannot divide by zero") from None
        except OverflowError:
            raise CalcError("Result too large") from None
        except ValueError:
            raise CalcError("Invalid input") from None
        except RecursionError:
            raise CalcError("Expression too complex") from None

    def calculate(self, text: str) -> str:
        """Evaluate, store the result as ``ans``, measure execution time and return it formatted."""
        import time
        t0 = time.perf_counter_ns()
        value = self.evaluate(text)
        formatted = format_number(value)  # raises CalcError for nan/inf
        elapsed_us = (time.perf_counter_ns() - t0) / 1000.0
        self.last_execution_time_us = elapsed_us
        self.ans = value
        if self.auto_save_timing:
            self._save_execution_time(text, formatted, elapsed_us)
        return formatted

    def call(self, name: str, args: list):
        counts, fn = self.functions[name]
        if len(args) not in counts:
            raise CalcError(f"{name}() takes {' or '.join(map(str, counts))} argument(s)")
        return fn(*args)

    # -- memory register ---------------------------------------------------- #
    def memory_add(self, value):
        self.memory += value

    def memory_subtract(self, value):
        self.memory -= value

    def memory_clear(self):
        self.memory = 0

    # -- angle helpers ------------------------------------------------------ #
    def _to_rad(self, x):
        return math.radians(x) if self.angle_mode == "DEG" else x

    def _from_rad(self, x):
        return math.degrees(x) if self.angle_mode == "DEG" else x

    def _sin(self, x):
        if self.angle_mode == "DEG":
            r = x % 360
            if r % 90 == 0:  # exact values at multiples of 90 degrees
                return (0, 1, 0, -1)[int(r // 90)]
        return self._snap(math.sin(self._to_rad(x)), x)

    def _cos(self, x):
        if self.angle_mode == "DEG":
            r = x % 360
            if r % 90 == 0:
                return (1, 0, -1, 0)[int(r // 90)]
        return self._snap(math.cos(self._to_rad(x)), x)

    def _tan(self, x):
        if self.angle_mode == "DEG":
            r = x % 180
            if r == 0:
                return 0
            if r == 90:
                raise CalcError("tan is undefined here")
        elif abs(math.cos(x)) < 1e-15:
            raise CalcError("tan is undefined here")
        return self._snap(math.tan(self._to_rad(x)), x)

    @staticmethod
    def _snap(result, arg):
        """Turn float dust such as sin(pi) = 1.2e-16 into an exact 0."""
        return 0 if abs(result) < 1e-14 and abs(arg) > 1e-3 else result

    # -- other functions ---------------------------------------------------- #
    @staticmethod
    def _sqrt(x):
        if x < 0:
            raise CalcError("Invalid input")
        if isinstance(x, int):
            r = math.isqrt(x)
            if r * r == x:
                return r
        return math.sqrt(x)

    @staticmethod
    def _cbrt(x):
        r = round(abs(x) ** (1 / 3))
        if isinstance(x, int) and r**3 == abs(x):
            return r if x >= 0 else -r
        return math.copysign(abs(x) ** (1 / 3), x)

    @staticmethod
    def _root(x, n):
        if n == 0:
            raise CalcError("Invalid input")
        if x < 0:
            if float(n).is_integer() and int(n) % 2 == 1:
                return -((-x) ** (1 / n))
            raise CalcError("Invalid input")
        return x ** (1 / n)

    @staticmethod
    def _ln(x):
        if x <= 0:
            raise CalcError("Invalid input")
        return math.log(x)

    @staticmethod
    def _ln_base(x, base):
        if x <= 0:
            raise CalcError("Invalid input")
        return math.log(x, base)

    @staticmethod
    def _log(x, base=10):
        if x <= 0 or base <= 0 or base == 1:
            raise CalcError("Invalid input")
        if base == 10:
            return math.log10(x)
        return math.log(x) / math.log(base)

    @staticmethod
    def _round(x, digits=0):
        return round(x, int(digits)) if digits else int(round(x))

    @staticmethod
    def _mod(a, b):
        if b == 0:
            raise CalcError("Cannot divide by zero")
        return a % b
