from collections.abc import Callable
from typing import Final

from pyteal import (
    Approve,
    Assert,
    Expr,
    Global,
    InnerTxn,
    InnerTxnBuilder,
    Int,
    Seq,
    Subroutine,
    TealType,
    TxnField,
    abi,
)

from beaker import (
    Application,
    Authorize,
    GlobalStateValue,
    precompiled,
    unconditional_create_approval,
)
from beaker.consts import Algos


class OpUpState:
    #: The id of the app created during `bootstrap`
    opup_app_id = GlobalStateValue(stack_type=TealType.uint64, key="ouaid", static=True)


def op_up_blueprint(app: Application[OpUpState]) -> Callable[[], Expr]:
    target_app = Application(
        name="TargetApp",
        descr="""Simple app that allows the creator to call `opup` in order to increase its opcode budget""",
    ).apply(unconditional_create_approval)

    @target_app.external(authorize=Authorize.only(Global.creator_address()))
    def opup() -> Expr:
        return Approve()

    #: The minimum balance required for this class
    min_balance: Final[Expr] = Algos(0.1)

    @app.external
    def opup_bootstrap(ptxn: abi.PaymentTransaction, *, output: abi.Uint64) -> Expr:
        """initialize opup with bootstrap to create a target app"""
        return Seq(
            Assert(ptxn.get().amount() >= min_balance),
            create_opup(),
            output.set(app.state.opup_app_id),
        )

    @Subroutine(TealType.none)
    def create_opup() -> Expr:
        """internal method to create the target application"""
        #: The app to be created to receiver opup requests
        target = precompiled(target_app)

        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    **target.get_create_config(),
                    TxnField.fee: Int(0),
                }
            ),
            InnerTxnBuilder.Submit(),
            app.state.opup_app_id.set(InnerTxn.created_application_id()),
        )

    # No decorator, inline it
    def call_opup() -> Expr:
        """internal method to just return the method call to our target app"""
        return InnerTxnBuilder.ExecuteMethodCall(
            app_id=app.state.opup_app_id,
            method_signature=opup.method_signature(),  # type: ignore[union-attr]
            args=[],
            extra_fields={TxnField.fee: Int(0)},
        )

    return call_opup
