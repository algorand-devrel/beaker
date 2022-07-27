import pytest
from algosdk.atomic_transaction_composer import *
from beaker.sandbox import get_accounts, get_client
from beaker.client import ApplicationClient
from .arc18 import ARC18

algod_client = get_client()
accts = get_accounts()


@pytest.fixture(scope="session")
def creator_acct() -> tuple[str, str, AccountTransactionSigner]:
    addr, sk = accts[0]
    return (addr, sk, AccountTransactionSigner(sk))


@pytest.fixture(scope="session")
def user_acct() -> tuple[str, str, AccountTransactionSigner]:
    addr, sk = accts[1]
    return (addr, sk, AccountTransactionSigner(sk))


@pytest.fixture(scope="session")
def creator_app_client(creator_acct) -> ApplicationClient:
    _, _, signer = creator_acct
    app = ARC18()
    app_client = ApplicationClient(algod_client, app, signer=signer)
    return app_client


def test_arc18():
    pass
