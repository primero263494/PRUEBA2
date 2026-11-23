"""Calculadora científica segura (no usa eval de Python sobre texto libre).

Acepta: + − × ÷ ^ (o **), %, paréntesis, coma o punto decimal y las
funciones raiz, raiz3, sen/sin, cos, tan, asen, acos, atan, log, ln, exp,
abs, redondear, fact, pi, e, ans (último resultado) y m (memoria).
Ángulos en grados o radianes.
"""
from __future__ import annotations

import ast
import math
import operator as op
import re

_BIN = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow,
        ast.Mod: op.mod, ast.FloorDiv: op.floordiv}
_UNI = {ast.UAdd: op.pos, ast.USub: op.neg}


def _funciones(grados: bool) -> dict:
    a = math.radians if grados else (lambda x: x)
    d = math.degrees if grados else (lambda x: x)
    return {
        "raiz": math.sqrt, "sqrt": math.sqrt, "raiz3": lambda x: math.copysign(abs(x) ** (1 / 3), x),
        "sen": lambda x: math.sin(a(x)), "sin": lambda x: math.sin(a(x)), "cos": lambda x: math.cos(a(x)),
        "tan": lambda x: math.tan(a(x)), "asen": lambda x: d(math.asin(x)), "asin": lambda x: d(math.asin(x)),
        "acos": lambda x: d(math.acos(x)), "atan": lambda x: d(math.atan(x)),
        "log": math.log10, "ln": math.log, "exp": math.exp, "abs": abs,
        "redondear": lambda x, n=0: round(x, int(n)), "round": lambda x, n=0: round(x, int(n)),
        "fact": lambda x: math.factorial(int(x)), "hipot": math.hypot,
    }


def _normalizar(expr: str) -> str:
    e = expr.strip().replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**").replace("π", "pi")
    e = re.sub(r"(\d),(\d)", r"\1.\2", e)                    # 2,5 -> 2.5
    e = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", e)        # 15% -> (15/100)
    return e


def evaluar(expr: str, grados: bool = True, ans: float = 0.0, memoria: float = 0.0) -> float:
    if not expr.strip():
        raise ValueError("Expresión vacía.")
    if len(expr) > 300:
        raise ValueError("Expresión demasiado larga.")
    funcs = _funciones(grados)
    nombres = {"pi": math.pi, "e": math.e, "ans": ans, "m": memoria}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            izq, der = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(der) > 1000:
                raise ValueError("Exponente demasiado grande.")
            return _BIN[type(n.op)](izq, der)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNI:
            return _UNI[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name) and n.id in nombres:
            return nombres[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs and not n.keywords:
            return funcs[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("Expresión no válida.")

    try:
        arbol = ast.parse(_normalizar(expr), mode="eval")
        r = float(ev(arbol))
    except ZeroDivisionError:
        raise ValueError("División por cero.")
    except (SyntaxError, TypeError):
        raise ValueError("Expresión no válida.")
    if math.isnan(r) or math.isinf(r):
        raise ValueError("Resultado no definido.")
    return r
