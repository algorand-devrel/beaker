from functools import cached_property
from typing import TypeVar, Any, Generic

from algosdk.transaction import StateSchema
from pyteal import TealType, Expr, Seq, Txn

from beaker.application_specification import AppSpecStateDict
from beaker.consts import MAX_GLOBAL_STATE, MAX_LOCAL_STATE
from beaker.state._abc import (
    StateStorage,
    AppSpecSchemaFragment,
    ApplicationStateStorage,
    AccountStateStorage,
)

ST = TypeVar("ST", bound=StateStorage)
T = TypeVar("T")


def _get_attrs_of_type(namespace: Any, type_: type[T]) -> dict[str, T]:
    result = {}
    for name in dir(namespace):
        if not name.startswith("__"):
            try:
                value = getattr(namespace, name, None)
            except Exception:
                value = None
            if isinstance(value, type_):
                result[name] = value
    return result


class StateAggregate(Generic[ST]):
    def __init__(self, namespace: Any, storage_class: type[ST]):
        self._fields = _get_attrs_of_type(namespace, storage_class)

    def dictify(self) -> AppSpecStateDict:
        """Convert the state to a dict for encoding"""
        result: AppSpecStateDict = {"declared": {}, "reserved": {}}
        for name, field in self._fields.items():
            match field.app_spec_json():
                case AppSpecSchemaFragment(section, data):
                    result.setdefault(section, {})[name] = data
                case None:
                    pass
                case other:
                    raise TypeError(f"Unhandled type: {type(other)}")
        return result

    @cached_property
    def schema(self) -> StateSchema:
        result = StateSchema(num_uints=0, num_byte_slices=0)
        for field in self._fields.values():
            match field.value_type():
                case TealType.uint64:
                    result.num_uints += field.num_keys()
                case TealType.bytes:
                    result.num_byte_slices += field.num_keys()
                case _:
                    raise TypeError("Only uint64 and bytes supported")
        return result

    @property
    def total_keys(self) -> int:
        return self.schema.num_uints + self.schema.num_byte_slices


class ApplicationStateAggregate(StateAggregate[ApplicationStateStorage]):
    def __init__(self, namespace: Any):
        super().__init__(namespace=namespace, storage_class=ApplicationStateStorage)  # type: ignore[type-abstract]

        if self.total_keys > MAX_GLOBAL_STATE:
            raise ValueError(
                f"Too much application state, expected {self.total_keys} <= {MAX_GLOBAL_STATE}"
            )

    def initialize(self) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(*filter(None, (f.initialize() for f in self._fields.values())))


class AccountStateAggregate(StateAggregate[AccountStateStorage]):
    def __init__(self, namespace: Any):
        super().__init__(namespace=namespace, storage_class=AccountStateStorage)  # type: ignore[type-abstract]

        if self.total_keys > MAX_LOCAL_STATE:
            raise ValueError(
                f"Too much account state, expected {self.total_keys} <= {MAX_LOCAL_STATE}"
            )

    def initialize(self, acct: Expr = Txn.sender()) -> Expr:
        """Generate expression from state values to initialize a default value"""
        return Seq(
            *filter(None, (f.initialize(acct=acct) for f in self._fields.values()))
        )