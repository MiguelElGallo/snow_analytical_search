"""Non-secret configuration and deterministic snapshot identity."""

import hashlib
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

CHUNK_SIZE = 3500
CHUNK_OVERLAP = 300
NATIVE_PIPELINE_VERSION = (
    "pages-v3:ai-parse-document-layout-page-split:"
    "snowflake.cortex.split_text_recursive_character:"
    "pdf-md-markdown-json-none:3500:300:per-page"
)
REPOSITORY = "Azure-Samples/azure-search-openai-demo"


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", value):
        raise ValueError(f"Expected an uppercase SQL identifier, got {value!r}")
    return value


def literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


@dataclass(frozen=True)
class Config:
    connection: str
    expected_account: str
    prefix: str
    source_commit: str
    state_dir: Path
    native_ocr: bool = True

    def __post_init__(self) -> None:
        identifier(self.prefix)
        if len(self.prefix) > 48:
            raise ValueError("Resource prefix must be at most 48 characters")
        if not self.expected_account or self.expected_account == "YOUR_ACCOUNT_NAME":
            raise ValueError("Set expected_account to your Snowflake CURRENT_ACCOUNT_NAME()")
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_commit):
            raise ValueError("source_commit must be a full lowercase 40-character Git commit SHA")
        if type(self.native_ocr) is not bool:
            raise ValueError("native_ocr must be a boolean")

    @property
    def parser_identity(self) -> str:
        return "ai-parse-document-layout-page-split"

    @property
    def pipeline_identity(self) -> str:
        return NATIVE_PIPELINE_VERSION + (":ocr-image-pages-v1" if self.native_ocr else "")

    @property
    def snapshot(self) -> str:
        value = f"{self.source_commit}:{self.pipeline_identity}"
        return hashlib.sha256(value.encode()).hexdigest()[:24]

    @property
    def warehouse(self) -> str:
        return identifier(f"{self.prefix}_WH")

    @property
    def owner(self) -> str:
        return identifier(f"{self.prefix}_OWNER")

    @property
    def runner(self) -> str:
        return identifier(f"{self.prefix}_RUNNER")

    @property
    def service(self) -> str:
        return f"{self.prefix}.APP.DOCUMENTS_{self.snapshot.upper()}"

    @property
    def agent(self) -> str:
        return f"{self.prefix}.APP.CORPUS_AGENT"

    @property
    def stage(self) -> str:
        return f"{self.prefix}.RAW.DOCUMENTS"

    @property
    def corpus_dir(self) -> Path:
        return self.state_dir / "corpus" / self.source_commit


def load_config(path: Path) -> Config:
    path = path.expanduser()
    data = tomllib.loads(path.read_text())
    # Reject retired configurations before a previously offline workflow can incur AI costs.
    if data.get("pdf_parser", "snowflake") != "snowflake":
        raise ValueError(
            "Local ingestion has been removed; follow "
            "docs/how-to/operate.md#upgrade-from-retired-local-preparation "
            "to configure Snowflake native ingestion"
        )
    state_dir = Path(data.get("state_dir", "~/.local/state/snow-analytical-search")).expanduser()
    return Config(
        connection=data["connection"],
        expected_account=data["expected_account"],
        prefix=data["prefix"],
        source_commit=data["source_commit"],
        state_dir=(path.parent / state_dir).resolve(),
        native_ocr=data.get("native_ocr", True),
    )
