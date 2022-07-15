from base64 import b64decode
import copy
from math import ceil
from typing import Any

from algosdk.account import address_from_private_key
from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AccountTransactionSigner,
    MultisigTransactionSigner,
    LogicSigTransactionSigner,
    AtomicTransactionComposer,
    ABIResult,
    TransactionWithSigner,
    abi,
)
from algosdk.future import transaction
from algosdk.logic import get_application_address
from algosdk.v2client.algod import AlgodClient

from beaker.application import Application, get_method_spec
from beaker.decorators import HandlerFunc, MethodHints
from beaker.consts import APP_MAX_PAGE_SIZE


class ApplicationClient:
    def __init__(
        self,
        client: AlgodClient,
        app: Application,
        app_id: int = 0,
        signer: TransactionSigner = None,
        sender: str = None,
        suggested_params: transaction.SuggestedParams = None,
    ):
        self.client = client
        self.app = app
        self.app_id = app_id

        self.signer = signer
        self.sender = sender

        self.suggested_params = suggested_params

    def compile_approval(self) -> tuple[bytes, bytes]:
        approval_result = self.client.compile(self.app.approval_program)
        return b64decode(approval_result["result"])

    def compile_clear(self) -> bytes:
        clear_result = self.client.compile(self.app.clear_program)
        return b64decode(clear_result["result"])

    def create(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> tuple[int, str, str]:

        approval = self.compile_approval()
        clear = self.compile_clear()

        extra_pages = ceil(
            ((len(approval) + len(clear)) - APP_MAX_PAGE_SIZE) / APP_MAX_PAGE_SIZE
        )

        sp = self.get_suggested_params(sp)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationCreateTxn(
                    sender=sender,
                    sp=sp,
                    on_complete=transaction.OnComplete.NoOpOC,
                    approval_program=approval,
                    clear_program=clear,
                    global_schema=self.app.app_state.schema(),
                    local_schema=self.app.acct_state.schema(),
                    extra_pages=extra_pages,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        create_result = atc.execute(self.client, 4)
        create_txid = create_result.tx_ids[0]

        result = self.client.pending_transaction_info(create_txid)
        app_id = result["application-index"]
        app_addr = get_application_address(app_id)

        self.app_id = app_id

        return app_id, app_addr, create_txid

    def update(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        approval = self.compile_approval()
        clear = self.compile_clear()

        sp = self.get_suggested_params(sp)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationUpdateTxn(
                    sender=sender,
                    sp=sp,
                    index=self.app_id,
                    approval_program=approval,
                    clear_program=clear,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        update_result = atc.execute(self.client, 4)
        return update_result.tx_ids[0]

    def opt_in(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        sp = self.get_suggested_params(sp)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationOptInTxn(
                    sender=sender,
                    sp=sp,
                    index=self.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        opt_in_result = atc.execute(self.client, 4)
        return opt_in_result.tx_ids[0]

    def close_out(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        sp = self.get_suggested_params(sp)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationCloseOutTxn(
                    sender=sender,
                    sp=sp,
                    index=self.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        close_out_result = atc.execute(self.client, 4)
        return close_out_result.tx_ids[0]

    def clear_state(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:
        sp = self.get_suggested_params(sp)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationClearStateTxn(
                    sender=sender,
                    sp=sp,
                    index=self.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )
        clear_state_result = atc.execute(self.client, 4)
        return clear_state_result.tx_ids[0]

    def delete(
        self,
        sender: str = None,
        signer: TransactionSigner = None,
        args: list[Any] = [],
        sp: transaction.SuggestedParams = None,
        **kwargs,
    ) -> str:

        sp = self.get_suggested_params(sp)
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        atc = AtomicTransactionComposer()
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationDeleteTxn(
                    sender=sender,
                    sp=sp,
                    index=self.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

        delete_result = atc.execute(self.client, 4)
        return delete_result.tx_ids[0]

    def prepare(self, signer: TransactionSigner, **kwargs) -> "ApplicationClient":
        ac = copy.copy(self)
        ac.signer = signer
        ac.__dict__.update(**kwargs)
        return ac

    def call(
        self,
        method: abi.Method | HandlerFunc,
        sender: str = None,
        signer: TransactionSigner = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        local_schema: transaction.StateSchema = None,
        global_schema: transaction.StateSchema = None,
        approval_program: bytes = None,
        clear_program: bytes = None,
        extra_pages: int = None,
        accounts: list[str] = None,
        foreign_apps: list[int] = None,
        foreign_assets: list[int] = None,
        note: bytes = None,
        lease: bytes = None,
        rekey_to: str = None,
        **kwargs,
    ) -> ABIResult:

        sp = self.get_suggested_params()
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        if not isinstance(method, abi.Method):
            method = get_method_spec(method)

        hints = self.method_hints(method.name)

        args = []
        for method_arg in method.args:
            name = method_arg.name
            if name in kwargs:
                args.append(kwargs[name])
            elif name in hints.resolvable:
                result = self.call(hints.resolvable[name])
                args.append(result.return_value)
            else:
                raise Exception(f"Unspecified argument: {name}")

        if hints.read_only:
            # TODO: do dryrun
            pass

        atc = AtomicTransactionComposer()
        atc.add_method_call(
            self.app_id,
            method,
            sender,
            sp,
            signer,
            method_args=args,
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            extra_pages=extra_pages,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
        )

        result = atc.execute(self.client, 4)
        return result.abi_results.pop()

    def add_method_call(
        self,
        atc: AtomicTransactionComposer,
        method: abi.Method | HandlerFunc,
        sender: str = None,
        signer: TransactionSigner = None,
        on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
        local_schema: transaction.StateSchema = None,
        global_schema: transaction.StateSchema = None,
        approval_program: bytes = None,
        clear_program: bytes = None,
        extra_pages: int = None,
        accounts: list[str] = None,
        foreign_apps: list[int] = None,
        foreign_assets: list[int] = None,
        note: bytes = None,
        lease: bytes = None,
        rekey_to: str = None,
        **kwargs,
    ):
        sp = self.get_suggested_params()
        signer = self.get_signer(signer)
        sender = self.get_sender(sender, signer)

        if not isinstance(method, abi.Method):
            method = get_method_spec(method)

        hints = self.method_hints(method.name)

        args = []
        for method_arg in method.args:
            name = method_arg.name
            if name in kwargs:
                args.append(kwargs[name])
            elif name in hints.resolvable:
                result = self.call(hints.resolvable[name])
                args.append(result.return_value)
            else:
                raise Exception(f"Unspecified argument: {name}")

        atc.add_method_call(
            self.app_id,
            method,
            sender,
            sp,
            signer,
            method_args=args,
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            extra_pages=extra_pages,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
        )

        return atc

    def method_hints(self, method_name: str) -> MethodHints:
        if method_name not in self.app.hints:
            return MethodHints()
        return self.app.hints[method_name]

    def get_suggested_params(
        self, sp: transaction.SuggestedParams = None
    ) -> transaction.SuggestedParams:
        if sp is not None:
            return sp

        if self.suggested_params is not None:
            return self.suggested_params

        return self.client.suggested_params()

    def get_signer(
        self, signer: TransactionSigner = None
    ) -> tuple[TransactionSigner, str]:

        if signer is not None:
            return signer

        if self.signer is not None:
            return self.signer

        raise Exception("No signer provided")

    def get_sender(self, sender: str = None, signer: TransactionSigner = None):
        if sender is not None:
            return sender

        if self.sender is not None:
            return self.sender

        if self.signer is not None and signer is None:
            signer = self.signer

        match signer:
            case AccountTransactionSigner():
                return address_from_private_key(signer.private_key)
            case MultisigTransactionSigner():
                return signer.msig.address()
            case LogicSigTransactionSigner():
                return signer.lsig.address()
