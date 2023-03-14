from tests.conftest import check_application_artifacts_output_stability

from examples.wormhole.contract import oracle_data_cache_app
from examples.wormhole.demo import main


def test_demo() -> None:
    main()


def test_output_stability() -> None:
    check_application_artifacts_output_stability(
        oracle_data_cache_app, dir_name="spec", dir_per_test_file=False
    )
