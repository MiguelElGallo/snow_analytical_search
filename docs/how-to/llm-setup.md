# Set up with an LLM

The repository includes a portable
[setup skill](https://github.com/MiguelElGallo/snow_analytical_search/blob/main/skills/setup-snow-analytical-search/SKILL.md).
It guides an assistant through account checks, native ingestion, verification,
evaluation and pausing compute.

From your local clone, give your assistant this request:

```text
Read skills/setup-snow-analytical-search/SKILL.md and use it to set up this repository.
Use my existing Snowflake connection. Keep configuration and run evidence outside
Git, validate native ingestion, and pause the demo resources when finished.
```

An assistant with skill discovery can install the skill folder using its own
supported skill mechanism. Reading the file directly also works; it requires no
particular assistant product or third-party plugin.

Provide the existing connection profile name and intended account privately.
Enter authentication, MFA and payment details yourself in Snowflake. The skill
does not grant permission to upgrade billing, change unrelated resources, publish
account details or bypass a failed native SQL check.

For the same workflow without an assistant, use the
[first-run tutorial](../tutorials/first-run.md).
