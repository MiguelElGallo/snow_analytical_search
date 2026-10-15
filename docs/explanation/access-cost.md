# Access and cost

## Scope of access

`ACCOUNTADMIN` provisions the dedicated database, roles, and warehouse. The
project owner creates and loads its objects. The runner can read the corpus and
stage, use Search/Agent/warehouse resources, and create tables in `SCRATCH`.
It receives no project write grants on the source corpus tables.

Every client connection selects its intended role and disables secondary roles.
Account, role, secondary-role state, and warehouse are checked; agent calls
recheck that context immediately before execution. User defaults are unchanged.

Both project roles are granted to the existing user. This is a demo separation
of privileges, not a dedicated identity with no other available roles. Inherited
`PUBLIC` privileges can also expose other objects in the account. Instructions
such as “use only the project database” are not a security boundary.

[Cortex authorization](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-setup)
depends on the request context. The SQL helper's downstream execution context
must be demonstrated for your deployment. `verify-runtime` requests a bounded
Search-to-SQL aggregate that projects the actual context functions. It checks
same-user query history and independently reads that query's cached result.
A mismatch or unknown secondary-role state stops evaluation.

Each later evaluation call is audited separately for actual user, primary role,
warehouse, successful execution, SQL text and run timestamps. A previous probe
does not certify a later call's secondary roles. Those remain explicitly
unverified unless that call supplies its own context evidence. Information Schema
query history does not provide secondary-role statistics; account-wide history
has different access requirements and can lag. The demo does not add monitoring
grants to conceal that gap.

If the runtime does not expose its implicit SQL tool, the gate fails even when
AI functions and ordinary Search work. Client context, a bounded Studio success,
and full programmatic analytical acceptance remain distinct claims.

The demo reports the current cross-region inference setting without changing
it or other account-wide model settings. Review your region and data-handling
requirements before using non-public data.

## What consumes credits

Costs can come from warehouse compute, stored originals/tables, Search indexing
and serving, and model/AI-function calls. These are separate components.
Native parsing and OCR also consume AI credits.

The warehouse has a 60-second auto-suspend setting. Search serving is configured
to auto-suspend after 1800 seconds of query inactivity; that setting does not
suspend indexing. `sas pause` explicitly suspends both service layers and the
warehouse. Stored data remains and can still incur storage charges.

See [Search lifecycle controls](https://docs.snowflake.com/en/sql-reference/sql/alter-cortex-search)
and [Snowflake trial usage](https://docs.snowflake.com/en/user-guide/admin-trial-account).
Free trial usage can cover AI; adding a card and upgrading to paid billing are
separate actions under the documented current trial rules.

The agent's time/token limits and SQL timeout bound individual requests. They
are not an account-wide spending cap. Monitor usage in Snowflake and pause after
the session. The report does not estimate a monetary total from token counts.

## Trial billing terms

Checked against the official documentation on **2026-10-15**. Self-service trials
require a credit card to enable AI. Adding the card alone does not upgrade the
account or start paid billing; covered usage consumes the trial allowance.
The trial lasts up to 30 days or until that allowance is exhausted, then suspends
unless you upgrade. Upgrading is a separate action that permits paid usage.

**Always recheck [Snowflake's current trial rules](https://docs.snowflake.com/en/user-guide/admin-trial-account)
and your account status before adding a card or running the demo.** This project
does not change billing settings or guarantee that usage is free after an upgrade.
