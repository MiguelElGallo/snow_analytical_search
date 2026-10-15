---
hide:
  - toc
---

<div class="hero" markdown>

<p class="eyebrow">Documents · Search · Evidence</p>

# Answers you can trace to the source

<p class="lead">Turn a complete document collection into searchable, page-aware evidence with Snowflake Cortex. Then test what the agent can actually prove.</p>

[Build your first corpus](tutorials/first-run.md){ .md-button .md-button--primary }
[Use the LLM setup skill](how-to/llm-setup.md){ .md-button }

</div>

Seven PDFs. Five JSON files. One Markdown document. Every file in the pinned
Azure sample folder is included, with original bytes, page references and source
versions retained. Snowflake parses the PDFs, supplements printed image labels
with OCR, and splits all content into bounded passages.

!!! info "Know what passed"
    Native ingestion, exact index coverage and document Q&A have been tested.
    Bounded native analysis also succeeded in Studio. Complete programmatic analytical
    acceptance additionally requires the agent's native SQL tool and verified
    search-to-AI execution. That gate has not passed in the recorded evaluation.
    See [capabilities and limits](reference/capabilities.md) before treating a
    retrieved sample as a complete answer.

<div class="path-grid" markdown>
<div class="path-card" markdown>

### Learn by doing

Download, parse, index and ask your first question. Each step includes the result
that tells you it worked.

[Follow the tutorial →](tutorials/first-run.md)

</div>
<div class="path-card" markdown>

### Run it with confidence

Resume a session, change a source version, diagnose a failure and pause compute
when you finish.

[Open the how-to guides →](how-to/operate.md)

</div>
<div class="path-card" markdown>

### Find the exact detail

Look up configuration fields, CLI commands, the source inventory and the
question-evaluation criteria.

[Browse the reference →](reference/cli.md)

</div>
<div class="path-card" markdown>

### Understand the design

Learn why source integrity, page boundaries, citations and exhaustive coverage
are separate checks.

[Read the architecture →](explanation/architecture.md)

</div>
</div>

You need a Snowflake account with AI access. A self-service trial can be used
under Snowflake's current trial rules; see [access and cost](explanation/access-cost.md).
