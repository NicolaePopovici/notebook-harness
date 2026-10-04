Reader: a developer new to this code who must maintain it. They can read Python, PySpark and SQL, but have never seen this notebook.

Be precise and technical. Name the actual variables, DataFrames, tables, columns and functions. When a name is cryptic, say what it really holds.

Use these sections, in this order:
1. "Overview": purpose and overall approach in 3-5 claims.
2. "Structure": what each cell or group of cells is responsible for. Cover every code cell.
3. "Data flow": sources read, each intermediate DataFrame or view (what produces it, what consumes it), and the outputs written. Follow the order data moves through the notebook.
4. "Rules and logic": every business rule, condition, join key, filter, ordering, tie-break, rounding and tolerance, with the exact values used.
5. "Configuration and constants": hard-coded values, parameters, widgets and paths, and what each controls.
6. "External dependencies and side effects": tables, files, other notebooks (%run), libraries, and anything written or overwritten.
7. "Gotchas": surprising behaviour, dead code, misleading names, order-dependent cells.
