Reader: an AI coding agent that will be asked to debug or change this notebook. It needs facts it can rely on and checks it can run, not prose.

Be terse and specific. Each claim is one rule the agent must respect or one check it can perform. Name exact variables, columns, values and cells.

Use these sections, in this order:
1. "Invariants": properties that must stay true for the output to be correct (e.g. an invoice is never allocated more than its open amount, each receipt is allocated at most once, totals balance). State each one and cite the code that establishes or relies on it.
2. "Implicit contracts": assumptions the code makes about its inputs (columns, types, uniqueness, sign of amounts, currencies, date formats, non-null values) without checking them.
3. "Risky areas": code where a small change can silently change results: ordering and tie-breaks, floating-point comparisons, rounding, join types, filters, mutable state across cells, overwrite modes. Mark as "inference" where appropriate.
4. "Coupling between cells": which cells depend on names defined in other cells, so moving, deleting or re-running a cell would break them.
5. "How to check a change is safe": concrete checks to run before and after a change, e.g. compare row counts, reconcile allocated totals with receipt totals, assert no invoice is over-allocated, diff outputs on the sample data. Each check cites the code it protects.
