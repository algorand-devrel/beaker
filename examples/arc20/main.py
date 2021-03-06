from algosdk.future.transaction import (
    PaymentTxn,
    wait_for_confirmation,
    AssetOptInTxn,
    OnComplete,
)
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    TransactionWithSigner,
)
from beaker.contracts.arcs import ARC20
from beaker.sandbox import get_accounts, get_algod_client
from beaker.client import ApplicationClient

accts = get_accounts()
algod_client = get_algod_client()


def demo():

    addr, sk, signer = accts.pop()

    app = ARC20()

    app_client = ApplicationClient(algod_client, app=app, signer=signer)

    app_id, app_addr, txid = app_client.create()
    print(f"Created app: {app_id} with address {app_addr}")

    sp = algod_client.suggested_params()
    txid = algod_client.send_transaction(
        PaymentTxn(addr, sp, app_addr, int(1e6)).sign(sk)
    )
    wait_for_confirmation(algod_client=algod_client, txid=txid, wait_rounds=4)

    sp = algod_client.suggested_params()
    sp.flat_fee = True
    sp.fee = sp.min_fee * 2

    result = app_client.call(
        app.asset_create,
        suggested_params=sp,
        total=100,
        decimals=0,
        default_frozen=False,
        unit_name="tst",
        name="Tester",
        url="https://test.com",
        metadata_hash="",
        manager_addr=addr,
        freeze_addr=addr,
        clawback_addr=addr,
        reserve_addr=addr,
    )

    smart_asa_id = result.return_value

    print(f"Created asset with asset id: {smart_asa_id}")

    result = app_client.call(
        app.asset_config,
        suggested_params=sp,
        config_asset=smart_asa_id,
        total=200,
        decimals=0,
        default_frozen=False,
        unit_name="tst",
        name="Tester",
        url="https://test.com",
        metadata_hash="",
        manager_addr=addr,
        freeze_addr=addr,
        clawback_addr=addr,
        reserve_addr=addr,
    )

    print(f"Reconfigured asset id: {smart_asa_id}")

    try:
        result = app_client.call(
            app.asset_app_optin,
            suggested_params=sp,
            on_complete=OnComplete.OptInOC,
            asset=smart_asa_id,
            opt_in_txn=TransactionWithSigner(
                txn=AssetOptInTxn(addr, sp, smart_asa_id),
                signer=signer,
            ),
        )
    except Exception as e:
        print(app_client.wrap_approval_exception(e, 100))


if __name__ == "__main__":

    demo()
