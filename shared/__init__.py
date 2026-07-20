"""Core: the tower model, the Jira HTTP client, field resolution.

Nothing in this package may import jira_config, fixtures or app. The dependency
direction is one-way: everything imports shared, shared imports only stdlib.

"Vendor-neutral" applies at module granularity, not package granularity:

  * domain.py IS neutral. Towers, the priority matrix, SLA targets and calendars,
    status lifecycles, field NAMES. No Jira string appears in it, and app/ needs
    nothing beyond it. This is the module rule 3 is about.
  * jira_client.py and fields.py are the Jira ADAPTER. They speak the wire format
    by definition - fields.py resolves names against /rest/api/3/field and must
    therefore know custom-field type keys to break ties on duplicate names.

So jira_config/jira_schema.py importing the four type keys from fields.py is the
intended direction, not drift: one definition, no chance of the duplicate-name
tie-break silently disagreeing with what the builder creates. jira_schema.py
still owns everything else Jira-specific - searcher keys, template keys, project
identity, statusCategory constants.
"""
