# -*- coding: utf-8 -*-
"""HITL 审核动作事务回归测试。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from backend.core.exceptions import ConflictError, ResourceNotFoundError
from backend.governance.hitl_center.hitl import approve_case, edit_case


def _row(mapping: dict):
    row = MagicMock()
    row._mapping = mapping
    return row


def _result(*, rowcount: int = 1):
    result = MagicMock()
    result.rowcount = rowcount
    return result


def test_approve_case_rolls_back_when_case_was_changed_concurrently(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(fetchone=lambda: _row({"case_id": "case-1", "status": "pending"})),
        _result(rowcount=0),
    ]

    with pytest.raises(ConflictError, match="状态已变化"):
        approve_case(mock_db, "case-1", "reviewer-a", "ok")

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()
    assert mock_db.execute.call_count == 2


def test_approve_case_returns_not_found_for_missing_case(mock_db):
    mock_db.execute.return_value = MagicMock(fetchone=lambda: None)

    with pytest.raises(ResourceNotFoundError, match="不存在"):
        approve_case(mock_db, "missing-case", "reviewer-a", "ok")

    mock_db.commit.assert_not_called()
    mock_db.rollback.assert_called_once()


def test_edit_case_commits_single_transaction_with_payload(mock_db):
    mock_db.execute.side_effect = [
        MagicMock(fetchone=lambda: _row({"case_id": "case-9", "status": "pending"})),
        _result(rowcount=1),
        _result(),
    ]

    action_id = edit_case(
        mock_db,
        "case-9",
        "reviewer-b",
        {"risk_level": "low", "reason": "manual override"},
        "adjusted",
    )

    assert action_id
    mock_db.commit.assert_called_once()
    mock_db.rollback.assert_not_called()

    insert_params = mock_db.execute.call_args_list[2].args[1]
    assert insert_params["action_type"] == "edit"
    assert json.loads(insert_params["payload"]) == {
        "risk_level": "low",
        "reason": "manual override",
    }
