"""SQL safety guard for the user-facing /api/sql endpoint.

We only allow a single read-only SELECT/WITH statement. We use sqlglot to
parse and inspect the AST rather than rely on regex.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,  # catch-all for non-DML verbs
    exp.Pragma,
)


class UnsafeSQLError(ValueError):
    pass


def ensure_safe(sql: str, *, max_limit: int = 1000) -> str:
    """Parse `sql`, ensure it is a single read-only statement, and enforce a
    LIMIT. Returns the normalised SQL text to execute.
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("Empty SQL.")

    try:
        statements = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.ParseError as e:
        raise UnsafeSQLError(f"Parse error: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise UnsafeSQLError("Only a single statement is allowed.")

    tree = statements[0]

    # Reject any DML/DDL or PRAGMA.
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_EXPRESSIONS):
            raise UnsafeSQLError(
                f"Statement type not allowed: {type(node).__name__}"
            )

    # Must be SELECT or a WITH-wrapped SELECT.
    if not isinstance(tree, (exp.Select, exp.Union, exp.With, exp.Subquery)):
        # Allow subqueries wrapped etc. Bail otherwise.
        raise UnsafeSQLError(
            f"Only SELECT queries are allowed (got {type(tree).__name__})."
        )

    # Enforce a LIMIT on the outermost query.
    existing_limit = tree.args.get("limit")
    if existing_limit is None:
        tree.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
    else:
        # Clamp if user-supplied limit is too large.
        try:
            n = int(existing_limit.expression.this)  # type: ignore[attr-defined]
            if n > max_limit:
                tree.set(
                    "limit", exp.Limit(expression=exp.Literal.number(max_limit))
                )
        except (AttributeError, ValueError, TypeError):
            pass

    return tree.sql(dialect="sqlite")
