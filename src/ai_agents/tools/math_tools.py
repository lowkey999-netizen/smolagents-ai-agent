import ast
import math

from smolagents import tool

# Whitelist safe functions and constants from the standard math library
SAFE_MATH: dict[str, object] = {
    name: getattr(math, name)
    for name in dir(math)
    if not name.startswith("_")
}
SAFE_MATH.update({
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pi": math.pi,
    "e": math.e,
})

# Allowed AST node types for safe mathematical evaluation
ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)


MAX_RESULT_DIGITS = 1_000
MAX_EXPONENT = 10_000


def _check_pow(node: ast.BinOp) -> tuple[bool, str]:
    """Guards against computationally expensive exponentiation expressions.

    Rejects power operations where the result would exceed MAX_RESULT_DIGITS digits,
    preventing computational denial-of-service via expressions like 10**10**8.
    """
    base_node = node.left
    exp_node = node.right

    # Block nested power expressions like 10**10**8 entirely.
    # ast.walk processes nodes bottom-up so inner BinOps are checked before outer ones,
    # but the outer node's exponent is still a BinOp at inspection time.
    if isinstance(exp_node, ast.BinOp) and isinstance(exp_node.op, ast.Pow):
        return False, "Nested exponentiation expressions like a**b**c are not allowed."

    # Only validate constant operands statically; skip dynamic expressions.
    if not (isinstance(base_node, ast.Constant) and isinstance(exp_node, ast.Constant)):
        return True, ""

    base = base_node.value
    exp = exp_node.value

    if not (isinstance(base, (int, float)) and isinstance(exp, (int, float))):
        return True, ""

    # Reject excessively large exponents outright.
    if abs(exp) > MAX_EXPONENT:
        return False, (
            f"Exponent {exp} exceeds the maximum allowed value of {MAX_EXPONENT}."
        )

    # Estimate digit count of the result to catch cases like 2**9999.
    if base != 0 and exp > 0:
        import math as _math
        try:
            estimated_digits = exp * _math.log10(abs(base))
        except ValueError:
            estimated_digits = 0
        if estimated_digits > MAX_RESULT_DIGITS:
            return False, (
                f"Expression {base}**{exp} would produce a number with roughly "
                f"{int(estimated_digits):,} digits, exceeding the {MAX_RESULT_DIGITS:,}-digit limit."
            )

    return True, ""


def _validate_ast(node: ast.AST) -> tuple[bool, str]:
    """Ensures expression AST contains only safe mathematical operations."""
    for child in ast.walk(node):
        if not isinstance(child, ALLOWED_NODES):
            return False, f"Disallowed syntax element: {type(child).__name__}"
        if isinstance(child, ast.Name) and child.id not in SAFE_MATH:
            return False, f"Disallowed variable or identifier: '{child.id}'"
        if isinstance(child, ast.Call):  # noqa: SIM102
            if not isinstance(child.func, ast.Name) or child.func.id not in SAFE_MATH:
                func_name = child.func.id if isinstance(child.func, ast.Name) else "unknown"
                return False, f"Disallowed function call: '{func_name}'"
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Pow):
            is_safe, error_msg = _check_pow(child)
            if not is_safe:
                return False, error_msg
    return True, ""


@tool
def calculate(expression: str) -> str:
    """A safe mathematical calculator tool that evaluates arithmetic and mathematical expressions.

    Supports arithmetic operations (+, -, *, /, //, %, **), parentheses, and math functions
    such as sqrt, sin, cos, tan, log, log10, ceil, floor, radians, degrees, abs, round, min, max, pi, and e.

    Args:
        expression: The mathematical expression string to evaluate (e.g. '125 * 4 + 2**5', 'sqrt(144) + 10', 'sin(pi / 2)').

    Returns:
        The evaluated numerical result as a string, or an error message if the expression is invalid.
    """
    cleaned = expression.strip()
    if not cleaned:
        return "Error: Empty expression provided."

    try:
        parsed_tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as e:
        return f"Syntax error in mathematical expression '{cleaned}': {e}"

    is_safe, error_msg = _validate_ast(parsed_tree)
    if not is_safe:
        return f"Security error: {error_msg}. Only basic arithmetic and standard math functions are allowed."

    try:
        compiled_code = compile(parsed_tree, filename="<math_expression>", mode="eval")
        result = eval(compiled_code, {"__builtins__": {}}, SAFE_MATH)
        return str(result)
    except ZeroDivisionError:
        return "Math error: Division by zero is undefined."
    except OverflowError:
        return "Math error: Numerical calculation resulted in an overflow."
    except Exception as e:  # noqa: BLE001
        return f"Evaluation error: {e}"
