"""Existing named-profile authentication; SQL parameters and explicit session roles."""

import json
from typing import Any

import snowflake.connector

from .config import Config


class Database:
    def __init__(self, config: Config, role: str, *, bootstrap: bool = False):
        self.config = config
        self.role = role
        self.bootstrap = bootstrap
        options: dict[str, Any] = {
            "connection_name": config.connection,
            "role": role,
            "login_timeout": 60,
            "network_timeout": 60,
            "session_parameters": {
                "QUERY_TAG": f"snow_analytical_search:{config.snapshot}",
                "STATEMENT_TIMEOUT_IN_SECONDS": 900,
                "STATEMENT_QUEUED_TIMEOUT_IN_SECONDS": 60,
            },
        }
        if not bootstrap:
            options.update(warehouse=config.warehouse, database=config.prefix, schema="SCRATCH")
        self.connection = snowflake.connector.connect(**options)
        self.query_id = ""
        self.run("USE SECONDARY ROLES NONE")
        self.assert_context()

    def assert_context(self) -> None:
        identity = self.run(
            "SELECT CURRENT_ACCOUNT_NAME() ACCOUNT_NAME, CURRENT_USER() USER_NAME, "
            "CURRENT_ROLE() ROLE_NAME, CURRENT_REGION() REGION, "
            "CURRENT_WAREHOUSE() WAREHOUSE_NAME, CURRENT_SECONDARY_ROLES() SECONDARY_ROLES"
        )[0]
        if identity["ACCOUNT_NAME"].upper() != self.config.expected_account.upper():
            self.close()
            raise ValueError("Connected account does not match expected_account; no changes made")
        if identity["ROLE_NAME"] != self.role:
            self.close()
            raise ValueError("Unexpected active Snowflake role")
        secondary = json.loads(identity["SECONDARY_ROLES"])
        if secondary.get("roles") not in ("", [], None) or secondary.get("value") not in (
            "",
            "NONE",
            None,
        ):
            self.close()
            raise ValueError("Secondary roles must be disabled")
        if not self.bootstrap and identity["WAREHOUSE_NAME"] != self.config.warehouse:
            self.close()
            raise ValueError("Unexpected active Snowflake warehouse")
        self.identity = identity

    def run(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        with self.connection.cursor(snowflake.connector.DictCursor) as cursor:
            # The connector otherwise uses network_timeout as a query-cancellation timer.
            cursor.execute(sql, params, timeout=900)
            self.query_id = cursor.sfqid or ""
            return cursor.fetchall()

    def scalar(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        rows = self.run(sql, params)
        return next(iter(rows[0].values()))

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
