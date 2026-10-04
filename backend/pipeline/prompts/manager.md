Reader: a non-technical manager who owns the business process. They will not read code. They need to know what the notebook does for the business and where it could hurt them.

Write in plain business language. No code terms (DataFrame, join, UDF, null) unless you explain them in everyday words in the same sentence. Express rules as business rules, e.g. "a receipt is matched to an invoice only if the amounts differ by at most 1 cent". Keep each claim to one or two sentences.

Use these sections, in this order:
1. "What this notebook does": the business purpose and the outcome, in 3-6 claims.
2. "What goes in and what comes out": the business data it reads and what it produces.
3. "The business rules it applies": every rule that decides an outcome (matching, allocation, priority, tolerances, cut-offs, exclusions).
4. "What could go wrong": realistic business failures (money misallocated, items silently skipped, duplicates, wrong currency or date handling, hard-coded values that will go stale). Each is an "inference" that cites the code responsible, and says the business impact.
5. "Questions to ask the team": decisions buried in the code that the business should confirm. Each cites the code that raises the question.
