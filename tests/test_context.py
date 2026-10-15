import json
from unittest.mock import MagicMock

import pytest

from snow_analytical_search.config import Config
from snow_analytical_search.db import Database


@pytest.mark.parametrize(
    "override",
    [
        {"ROLE_NAME": "ACCOUNTADMIN"},
        {"WAREHOUSE_NAME": "OTHER_WH"},
        {"SECONDARY_ROLES": '{"roles":"ACCOUNTADMIN","value":"ALL"}'},
    ],
)
def test_context_checks_reject_role_or_warehouse_drift(tmp_path, override):
    config = Config("test", "ACCT", "DEMO", "a" * 40, tmp_path)
    db = object.__new__(Database)
    db.config, db.role, db.bootstrap = config, config.runner, False
    db.connection = MagicMock()
    row = {
        "ACCOUNT_NAME": "ACCT",
        "ROLE_NAME": config.runner,
        "WAREHOUSE_NAME": config.warehouse,
        "SECONDARY_ROLES": json.dumps({"roles": "", "value": ""}),
        **override,
    }
    db.run = MagicMock(return_value=[row])
    with pytest.raises(ValueError):
        db.assert_context()
    db.connection.close.assert_called_once()
