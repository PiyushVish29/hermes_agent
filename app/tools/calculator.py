"""A bounded arithmetic tool for the first agent loop."""

from __future__ import annotations

import ast
import operator
from typing import Any

from app.tools.base import Tool


class CalculatorTool(Tool):
    """Evaluate small arithmetic expressions without executing arbitrary code."""

    name = "calculator"
    description = "Evaluate a basic arithmetic expression."
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any]) -> int | float:
        self.validate(arguments)
        expression = arguments["expression"]
        tree = ast.parse(expression, mode="eval")
        return self._evaluate(tree.body)

    def _evaluate(self, node: ast.AST) -> int | float:
        binary_operations = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }
        unary_operations = {ast.UAdd: operator.pos, ast.USub: operator.neg}
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                raise ValueError("boolean values are not allowed")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in binary_operations:
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent is too large")
            return binary_operations[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary_operations:
            return unary_operations[type(node.op)](self._evaluate(node.operand))
        raise ValueError("expression contains unsupported syntax")