from migration_contract import inspect_tree


def test_revision_chain_is_linear() -> None:
    report = inspect_tree()
    assert report.problems == ()
    assert report.revisions >= 50
    assert report.head


def test_enum_revision_is_called_out_as_a_manual_downgrade() -> None:
    report = inspect_tree()
    assert "20261123_0015" in report.irreversible
