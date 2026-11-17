import pytest

from research.data import load_dataset
from research.model import compute_history


@pytest.fixture(scope="session")
def dataset():
    return load_dataset()


@pytest.fixture
def histories(dataset):
    return {code: compute_history(dataset, code) for code in dataset.companies}
