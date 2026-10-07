"""Check that the project DAG imports in the Astro runtime."""

from airflow.models import DagBag


def test_dag_integrity() -> None:
    """Fail when an Airflow DAG raises an import error."""
    bag = DagBag(include_examples=False)
    assert not bag.import_errors
