# Build and publish the documentation

The site uses [Zensical](https://zensical.org/) with a modern teal theme, light and
dark modes, local system fonts, searchable navigation and copyable examples.
The content follows the four [Diátaxis](https://diataxis.fr/start-here/) purposes:
learning, tasks, reference and explanation. Tutorial steps follow the progressive
approach of the [FastAPI documentation](https://fastapi.tiangolo.com/tutorial/).

## Preview locally

From the repository root:

```bash
uv sync --locked --python 3.13
uv run zensical serve
```

Open the local URL printed by the command. Stop the preview with Ctrl+C.

## Validate a change

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q
uv run zensical build --clean --strict
```

Generated `site/` and `.cache/` directories are ignored and must not be committed.
Keep personal configuration, raw responses, query IDs, support packets and review
working notes outside the checkout. The public site should explain supported
behavior, not reproduce an operator's debugging session.

## Publish through GitHub Pages

The documentation workflow builds the locked environment and publishes only
`site/`. Publication runs on `main`; pull requests validate the build without
deploying it. The GitHub Pages source must be **GitHub Actions** in the repository
settings. No Snowflake connection or secret is needed by this workflow.

After merging a reviewed change, verify the successful deployment and open
[the public site](https://miguelelgallo.github.io/snow_analytical_search/).
Check navigation, both color modes and a code example. Do not equate a completed
local build with a live deployment.
