import base64
import dataclasses
import inspect
import itertools
import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import (
    Any,
    cast,
    Optional,
    Callable,
    TypeAlias,
    Literal,
    ParamSpec,
    Concatenate,
    TypeVar,
    overload,
    Iterable,
    Iterator,
)

from algosdk.abi import Method, Contract
from algosdk.v2client.algod import AlgodClient
from pyteal import (
    SubroutineFnWrapper,
    Txn,
    MAX_PROGRAM_VERSION,
    ABIReturnSubroutine,
    BareCallActions,
    Expr,
    OnCompleteAction,
    OptimizeOptions,
    Router,
    Approve,
    CallConfig,
    TealType,
    MethodConfig,
)
from pyteal.compiler.compiler import FRAME_POINTERS_VERSION

from beaker.decorators import (
    MethodHints,
    HandlerFunc,
    capture_method_hints_and_remove_defaults,
)
from beaker.decorators.authorize import _authorize
from beaker.logic_signature import LogicSignature, LogicSignatureTemplate
from beaker.precompile import AppPrecompile, LSigPrecompile, LSigTemplatePrecompile
from beaker.state import AccountState, ApplicationState
from beaker.utils import remove_first_match

OnCompleteActionName: TypeAlias = Literal[
    "no_op",
    "opt_in",
    "close_out",
    "update_application",
    "delete_application",
]

Self = TypeVar("Self", bound="Application")
T = TypeVar("T")
P = ParamSpec("P")


@dataclasses.dataclass
class ABIExternal:
    actions: dict[OnCompleteActionName, CallConfig]
    method: ABIReturnSubroutine
    hints: MethodHints


DecoratorResultType: TypeAlias = SubroutineFnWrapper | ABIReturnSubroutine
DecoratorFuncType: TypeAlias = Callable[[HandlerFunc], DecoratorResultType]


@dataclasses.dataclass(frozen=True)
class CompileContext:
    app: "Application" = dataclasses.field(kw_only=True)
    client: AlgodClient | None


_ctx: ContextVar[CompileContext] = ContextVar("beaker.compile_context")


def this_app() -> "Application":
    return _ctx.get().app


@contextmanager
def _set_ctx(app: "Application", client: AlgodClient | None = None) -> Iterator[None]:
    if client is None:
        curr = _ctx.get(None)
        if curr is not None:
            client = curr.client
    token = _ctx.set(CompileContext(app=app, client=client))
    try:
        yield
    finally:
        _ctx.reset(token)


@overload
def precompiled(value: "Application", /) -> AppPrecompile:
    ...


@overload
def precompiled(value: "LogicSignature", /) -> LSigPrecompile:
    ...


@overload
def precompiled(value: "LogicSignatureTemplate", /) -> LSigTemplatePrecompile:
    ...


def precompiled(
    value: "Application | LogicSignature | LogicSignatureTemplate",
    /,
) -> AppPrecompile | LSigPrecompile | LSigTemplatePrecompile:
    try:
        ctx = _ctx.get()
    except LookupError:
        raise LookupError("beaker.precompiled(...) should be called inside a function")
    return ctx.app.precompiled(value)


@dataclasses.dataclass
class CompileOptions:
    avm_version: int = dataclasses.field(default=MAX_PROGRAM_VERSION)
    """avm_version: defines the #pragma version used in output"""
    scratch_slots: bool = dataclasses.field(default=True)
    """scratch_slots: cancel contiguous store/load operations that have no load dependencies elsewhere. 
       Available AVM version 9
       default=True"""
    frame_pointers: bool = dataclasses.field(default=True)
    """frame_pointers: employ frame pointers instead of scratch slots during compilation.
       Available AVM version 8
       default=True"""


class Application:
    def __init__(
        self: Self,
        *,
        compile_options: CompileOptions = CompileOptions(
            avm_version=MAX_PROGRAM_VERSION, scratch_slots=True, frame_pointers=True
        ),
        # TODO
        name: str | None = None,
        descr: str | None = None,
        # state: TState # how to make this generic but also default to empty?!?!!?
        state_class: type | None = None,
        implement_default_create: bool = True,  # for backwards compat, TODO maybe remove
    ) -> None:
        """<TODO>"""
        self._name = name
        self._descr = descr
        self.avm_version = compile_options.avm_version
        self.optimize_options = OptimizeOptions(
            scratch_slots=compile_options.scratch_slots,
            frame_pointers=compile_options.frame_pointers
            and self.avm_version >= FRAME_POINTERS_VERSION,
        )
        self._compiled: CompiledApplication | None = None
        self._bare_externals: dict[OnCompleteActionName, OnCompleteAction] = {}
        self.clear_state_method: SubroutineFnWrapper | None = None
        self._lsig_precompiles: dict[LogicSignature, LSigPrecompile] = {}
        self._lsig_template_precompiles: dict[
            LogicSignatureTemplate, LSigTemplatePrecompile
        ] = {}
        self._app_precompiles: dict[Application, AppPrecompile] = {}
        self._abi_externals: dict[str, ABIExternal] = {}
        self._state_class = state_class or self.__class__
        self.acct_state = AccountState(klass=self._state_class)
        self.app_state = ApplicationState(klass=self._state_class)
        self.bare_methods: dict[str, SubroutineFnWrapper] = {}
        self.abi_methods: dict[str, ABIReturnSubroutine] = {}

        if implement_default_create:
            self.implement(unconditional_create_approval)

    @property
    def name(self) -> str:
        return self._name or self.__class__.__name__

    @property
    def descr(self) -> str | None:
        return self._descr or self.__doc__

    @overload
    def precompiled(self, value: "Application", /) -> AppPrecompile:
        ...

    @overload
    def precompiled(self, value: "LogicSignature", /) -> LSigPrecompile:
        ...

    @overload
    def precompiled(self, value: "LogicSignatureTemplate", /) -> LSigTemplatePrecompile:
        ...

    def precompiled(
        self,
        value: "Application | LogicSignature | LogicSignatureTemplate",
        /,
    ) -> AppPrecompile | LSigPrecompile | LSigTemplatePrecompile:
        try:
            ctx = _ctx.get()
        except LookupError:
            raise LookupError("precompiled(...) should be called inside a function")
        if ctx.app is not self:
            raise ValueError("precompiled() used in another apps context")
        if ctx.client is None:
            raise ValueError(
                "beaker.precompiled(...) requires use of a client when calling Application.compile(...)"
            )
        match value:
            case Application() as app:
                # TODO: check recursion?
                return self._app_precompiles.setdefault(
                    app, AppPrecompile(app, ctx.client)
                )
            case LogicSignature() as lsig:
                return self._lsig_precompiles.setdefault(
                    lsig, LSigPrecompile(lsig, ctx.client)
                )
            case LogicSignatureTemplate() as lsig_template:
                return self._lsig_template_precompiles.setdefault(
                    lsig_template, LSigTemplatePrecompile(lsig_template, ctx.client)
                )
            case _:
                raise TypeError("TODO write error message")

    @property
    def precompiles(
        self,
    ) -> list[AppPrecompile | LSigPrecompile | LSigTemplatePrecompile]:
        return list(
            itertools.chain(
                self.app_precompiles,
                self.lsig_precompiles,
                self.lsig_template_precompiles,
            )
        )

    @property
    def app_precompiles(self) -> Iterable[AppPrecompile]:
        return self._app_precompiles.values()

    @property
    def lsig_precompiles(self) -> Iterable[LSigPrecompile]:
        return self._lsig_precompiles.values()

    @property
    def lsig_template_precompiles(self) -> Iterable[LSigTemplatePrecompile]:
        return self._lsig_template_precompiles.values()

    @property
    def hints(self) -> dict[str, MethodHints]:
        return {ext.method.name(): ext.hints for ext in self._abi_externals.values()}

    def register_abi_external(
        self,
        method: ABIReturnSubroutine,
        *,
        python_func_name: str,
        actions: dict[OnCompleteActionName, CallConfig],
        hints: MethodHints,
        override: bool | None,
    ) -> None:
        if any(cc == CallConfig.NEVER for cc in actions.values()):
            raise ValueError("???")
        method_sig = method.method_signature()
        existing_method = self._abi_externals.get(method_sig)
        if existing_method is None:
            if override is True:
                raise ValueError("override=True, but nothing to override")
        else:
            if override is False:
                raise ValueError(
                    "override=False, but method with matching signature already registered"
                )
            # TODO: should we warn if call config differs?
            self.deregister_abi_method(existing_method.method)
        self._abi_externals[method_sig] = ABIExternal(
            actions=actions,
            method=method,
            hints=hints,
        )
        self.abi_methods[python_func_name] = method

    def deregister_abi_method(
        self,
        name_or_reference: str | ABIReturnSubroutine,
        /,
    ) -> None:
        if isinstance(name_or_reference, str):
            method = self.abi_methods.pop(name_or_reference)
        else:
            method = name_or_reference
            remove_first_match(self.abi_methods, lambda _, v: v is method)
        remove_first_match(self._abi_externals, lambda _, v: v.method is method)

    def register_bare_external(
        self,
        sub: SubroutineFnWrapper,
        *,
        python_func_name: str,
        actions: dict[OnCompleteActionName, CallConfig],
        override: bool | None,
    ) -> None:
        for for_action, call_config in actions.items():
            if call_config == CallConfig.NEVER:
                raise ValueError("???")
            existing_action = self._bare_externals.get(for_action)
            if existing_action is None:
                if override is True:
                    raise ValueError("override=True, but nothing to override")
            else:
                if override is False:
                    raise ValueError(
                        f"override=False, but bare external for {for_action} already exists."
                    )
                assert isinstance(existing_action.action, SubroutineFnWrapper)
                self.deregister_bare_method(existing_action.action)
            self._bare_externals[for_action] = OnCompleteAction(
                action=sub, call_config=call_config
            )
        self.bare_methods[python_func_name] = sub

    def deregister_bare_method(
        self,
        name_or_reference: str | SubroutineFnWrapper,
        /,
    ) -> None:
        if isinstance(name_or_reference, str):
            method = self.bare_methods.pop(name_or_reference)
        else:
            method = name_or_reference
            remove_first_match(self.bare_methods, lambda _, v: v is method)
        remove_first_match(self._bare_externals, lambda _, v: v.action is method)

    @overload
    def external(
        self,
        fn: HandlerFunc,
        /,
    ) -> ABIReturnSubroutine:
        ...

    @overload
    def external(
        self,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def external(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        method_config: MethodConfig
        | dict[OnCompleteActionName, CallConfig]
        | None = None,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = False,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        """
        Add the method decorated to be handled as an ABI method for the Application

        Args:
            fn: The function being wrapped.
            method_config:  <TODO>
            name: Name of ABI method. If not set, name of the python method will be used.
                Useful for method overriding.
            authorize: a subroutine with input of ``Txn.sender()`` and output uint64
                interpreted as allowed if the output>0.
            bare:
            read_only: Mark a method as callable with no fee using dryrun or simulate
            override:

        Returns:
            The original method with additional elements set in it's
            :code:`__handler_config__` attribute
        """

        def decorator(func: HandlerFunc) -> SubroutineFnWrapper | ABIReturnSubroutine:
            python_func_name = func.__name__
            sig = inspect.signature(func)
            nonlocal bare
            if bare is None:
                bare = not sig.parameters

            if bare and read_only:
                raise ValueError("read_only has no effect on bare methods")

            actions: dict[OnCompleteActionName, CallConfig]
            match method_config:
                case None:
                    if bare:
                        raise ValueError("bare requires method_config")
                    else:
                        actions = {"no_op": CallConfig.CALL}
                case MethodConfig():
                    actions = {
                        cast(OnCompleteActionName, key): value
                        for key, value in method_config.__dict__.items()
                        if value != CallConfig.NEVER
                    }
                case _:
                    actions = method_config

            if authorize is not None:
                func = _authorize(authorize)(func)
            if bare:
                sub = SubroutineFnWrapper(func, return_type=TealType.none, name=name)
                if sub.subroutine.argument_count():
                    raise TypeError("Bare externals must take no method arguments")

                self.register_bare_external(
                    sub,
                    python_func_name=python_func_name,
                    actions=actions,
                    override=override,
                )
                return sub
            else:
                hints = capture_method_hints_and_remove_defaults(
                    func, read_only=read_only
                )
                method = ABIReturnSubroutine(func, overriding_name=name)
                setattr(method, "_read_only", read_only)

                self.register_abi_external(
                    method,
                    python_func_name=python_func_name,
                    actions=actions,
                    hints=hints,
                    override=override,
                )
                return method

        if fn is None:
            return decorator

        return decorator(fn)

    def _shortcut_external(
        self,
        *,
        action: OnCompleteActionName,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        if allow_call and allow_create:
            call_config = CallConfig.ALL
        elif allow_call:
            call_config = CallConfig.CALL
        elif allow_create:
            call_config = CallConfig.CREATE
        else:
            raise ValueError("Require one of allow_call or allow_create to be True")
        return self.external(
            method_config={action: call_config},
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )

    @overload
    def create(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def create(
        self,
        /,
        *,
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def create(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="no_op",
            allow_call=allow_call,
            allow_create=True,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def delete(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def delete(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def delete(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="delete_application",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def update(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def update(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def update(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="update_application",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def opt_in(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def opt_in(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def opt_in(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="opt_in",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def clear_state(
        self,
        fn: Callable[[], Expr],
        /,
    ) -> SubroutineFnWrapper:
        ...

    @overload
    def clear_state(
        self,
        /,
        *,
        name: str | None = None,
        override: bool | None = False,
    ) -> Callable[[Callable[[], Expr]], SubroutineFnWrapper]:
        ...

    def clear_state(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        name: str | None = None,
        override: bool | None = False,
    ) -> SubroutineFnWrapper | Callable[[Callable[[], Expr]], SubroutineFnWrapper]:
        def decorator(fun: Callable[[], Expr]) -> SubroutineFnWrapper:
            sub = SubroutineFnWrapper(fun, TealType.none, name=name)
            if override is True and self.clear_state_method is None:
                raise ValueError("override=True but no clear_state defined")
            elif override is False and self.clear_state_method is not None:
                raise ValueError("override=False but clear_state already defined")
            self.clear_state_method = sub
            return sub

        return decorator if fn is None else decorator(fn)

    @overload
    def close_out(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def close_out(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def close_out(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="close_out",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @overload
    def no_op(
        self,
        fn: HandlerFunc,
        /,
    ) -> DecoratorResultType:
        ...

    @overload
    def no_op(
        self,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorFuncType:
        ...

    def no_op(
        self,
        fn: HandlerFunc | None = None,
        /,
        *,
        allow_call: bool = True,
        allow_create: bool = False,
        name: str | None = None,
        authorize: SubroutineFnWrapper | None = None,
        bare: bool | None = None,
        read_only: bool = False,
        override: bool | None = False,
    ) -> DecoratorResultType | DecoratorFuncType:
        decorator = self._shortcut_external(
            action="no_op",
            allow_call=allow_call,
            allow_create=allow_create,
            name=name,
            authorize=authorize,
            bare=bare,
            read_only=read_only,
            override=override,
        )
        return decorator if fn is None else decorator(fn)

    @property
    def on_create(self) -> Method | None:
        return self._compiled.on_create if self._compiled is not None else None

    @property
    def on_update(self) -> Method | None:
        return self._compiled.on_update if self._compiled is not None else None

    @property
    def on_opt_in(self) -> Method | None:
        return self._compiled.on_opt_in if self._compiled is not None else None

    @property
    def on_close_out(self) -> Method | None:
        return self._compiled.on_close_out if self._compiled is not None else None

    @property
    def on_delete(self) -> Method | None:
        return self._compiled.on_delete if self._compiled is not None else None

    def implement(
        self: Self,
        blueprint: Callable[Concatenate[Self, P], T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        return blueprint(self, *args, **kwargs)

    def compile(self, client: Optional[AlgodClient] = None) -> tuple[str, str]:
        """Fully compile the application to TEAL

        Note: If the application has ``Precompile`` fields, the ``client`` must be passed to
        compile them into bytecode.

        Args:
            client (optional): An Algod client that can be passed to ``Precompile`` to have them fully compiled.
        """

        if self._compiled is None:
            with _set_ctx(app=self, client=client):
                bare_call_kwargs = {str(k): v for k, v in self._bare_externals.items()}
                router = Router(
                    name=self.name,
                    bare_calls=BareCallActions(**bare_call_kwargs),
                    descr=self.descr,
                    clear_state=self.clear_state_method,
                )

                # Add method externals
                # TODO: remove this backwards-compat code
                all_creates = []
                all_updates = []
                all_deletes = []
                all_opt_ins = []
                all_close_outs = []
                for abi_external in self._abi_externals.values():
                    method_config = MethodConfig(
                        **{str(a): cc for a, cc in abi_external.actions.items()}
                    )
                    router.add_method_handler(
                        method_call=abi_external.method,
                        method_config=method_config,
                    )
                    if any(
                        cc1 == CallConfig.CREATE or cc1 == CallConfig.ALL
                        for cc1 in dataclasses.astuple(method_config)
                    ):
                        all_creates.append(abi_external.method.method_spec())
                    if method_config.update_application != CallConfig.NEVER:
                        all_updates.append(abi_external.method.method_spec())
                    if method_config.delete_application != CallConfig.NEVER:
                        all_deletes.append(abi_external.method.method_spec())
                    if method_config.opt_in != CallConfig.NEVER:
                        all_opt_ins.append(abi_external.method.method_spec())
                    if method_config.close_out != CallConfig.NEVER:
                        all_close_outs.append(abi_external.method.method_spec())

                kwargs: dict[str, Method | None] = {
                    "on_create": all_creates.pop() if len(all_creates) == 1 else None,
                    "on_update": all_updates.pop() if len(all_updates) == 1 else None,
                    "on_delete": all_deletes.pop() if len(all_deletes) == 1 else None,
                    "on_opt_in": all_opt_ins.pop() if len(all_opt_ins) == 1 else None,
                    "on_close_out": all_close_outs.pop()
                    if len(all_close_outs) == 1
                    else None,
                }
                # Compile approval and clear programs
                approval_program, clear_program, contract = router.compile_program(
                    version=self.avm_version,
                    assemble_constants=True,
                    optimize=OptimizeOptions(scratch_slots=True),
                )

                application_spec = {
                    "hints": {
                        k: v.dictify() for k, v in self.hints.items() if not v.empty()
                    },
                    "source": {
                        "approval": base64.b64encode(approval_program.encode()).decode(
                            "utf8"
                        ),
                        "clear": base64.b64encode(clear_program.encode()).decode(
                            "utf8"
                        ),
                    },
                    "schema": {
                        "local": self.acct_state.dictify(),
                        "global": self.app_state.dictify(),
                    },
                    "contract": contract.dictify(),
                }

                self._compiled = CompiledApplication(
                    approval_program=approval_program,
                    clear_program=clear_program,
                    contract=contract,
                    application_spec=application_spec,
                    **kwargs,
                )

        return self._compiled.approval_program, self._compiled.clear_program

    @property
    def approval_program(self) -> str | None:
        if self._compiled is None:
            return None
        return self._compiled.approval_program

    @property
    def clear_program(self) -> str | None:
        if self._compiled is None:
            return None
        return self._compiled.clear_program

    @property
    def contract(self) -> Contract | None:
        if self._compiled is None:
            return None
        return self._compiled.contract

    def application_spec(self) -> dict[str, Any]:
        """returns a dictionary, helpful to provide to callers with information about the application specification"""
        if self._compiled is None:
            raise ValueError(
                "approval or clear program are none, please build the programs first"
            )
        return self._compiled.application_spec

    def initialize_application_state(self) -> Expr:
        """
        Initialize any application state variables declared

        :return: The Expr to initialize the application state.
        :rtype: pyteal.Expr
        """
        return self.app_state.initialize()

    def initialize_account_state(self, addr: Expr = Txn.sender()) -> Expr:
        """
        Initialize any account state variables declared

        :param addr: Optional, address of account to initialize state for.
        :return: The Expr to initialize the account state.
        :rtype: pyteal.Expr
        """

        return self.acct_state.initialize(addr)

    def dump(self, directory: str = ".", client: Optional[AlgodClient] = None) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory (optional): str path to the directory where the artifacts should be written
            client (optional): AlgodClient to be passed to any precompiles
        """
        self.compile(client)
        assert self._compiled is not None
        self._compiled.dump(Path(directory))


@dataclasses.dataclass
class CompiledApplication:
    approval_program: str
    clear_program: str
    contract: Contract
    application_spec: dict[str, Any]

    on_create: Method | None = dataclasses.field(default=None, kw_only=True)
    on_update: Method | None = None
    on_opt_in: Method | None = None
    on_close_out: Method | None = None
    on_delete: Method | None = None

    def dump(self, directory: Path) -> None:
        """write out the artifacts generated by the application to disk

        Args:
            directory: path to the directory where the artifacts should be written
        """
        directory.mkdir(exist_ok=True, parents=True)

        (directory / "approval.teal").write_text(self.approval_program)
        (directory / "clear.teal").write_text(self.clear_program)
        (directory / "contract.json").write_text(
            json.dumps(self.contract.dictify(), indent=4)
        )
        (directory / "application.json").write_text(
            json.dumps(self.application_spec, indent=4)
        )


TApp = TypeVar("TApp", bound=Application)


def unconditional_create_approval(app: TApp) -> TApp:
    @app.create
    def create() -> Expr:
        return Approve()

    return app
