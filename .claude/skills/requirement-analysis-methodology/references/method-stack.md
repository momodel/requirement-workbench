# Method Stack

Use the stack as internal guidance, not as something to lecture to the user.

## BABOK

Use for coverage. It helps check whether the current picture includes:

- goals
- stakeholders and roles
- process and systems
- business rules
- constraints and risks
- acceptance and scope boundaries

If one of these is missing, that often becomes a `pending_item`.

## JTBD

Use for truth-testing the stated request.

Typical questions:

- what job is the user actually trying to get done
- what pain makes the current request feel urgent
- what outcome matters more than the stated feature

Use JTBD when the customer says something broad like "make it automatic" or "build a dashboard."

## Event Storming

Use for process reconstruction and exception discovery.

Look for:

- business events
- upstream inputs
- downstream postings or records
- handoffs
- exception paths

This is especially useful when the customer problem is really a process mismatch rather than a missing page.
