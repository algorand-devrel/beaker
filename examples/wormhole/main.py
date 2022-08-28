from typing import Final
from pyteal import *
from beaker import *
from beaker.contracts.wormhole import ContractTransferVAA, WormholeTransfer


class OracleData(abi.NamedTuple):
    timestamp: abi.Field[abi.Uint64]
    price: abi.Field[abi.Uint64]
    confidence: abi.Field[abi.Uint64]


class OraclePayload:
    def __init__(self):
        self.timestamp = abi.Uint64()
        self.price = abi.Uint64()
        self.confidence = abi.Uint64()

    def decode_msg(self, payload: Expr):
        return Seq(
            self.timestamp.set(JsonRef.as_uint64(Bytes("ts"), payload)),
            self.price.set(JsonRef.as_uint64(Bytes("price"), payload)),
            self.confidence.set(JsonRef.as_uint64(Bytes("confidence"), payload)),
        )

    def encode(self) -> Expr:
        return Seq(
            (od := OracleData()).set(self.timestamp, self.price, self.confidence),
            od.encode(),
        )


class OracleDataCache(WormholeTransfer):
    prices: Final[DynamicApplicationStateValue] = DynamicApplicationStateValue(
        stack_type=TealType.bytes, max_keys=64
    )

    def handle_transfer(
        self, ctvaa: ContractTransferVAA, *, output: abi.DynamicBytes
    ) -> Expr:
        return Seq(
            # TODO: assert foreign sender?
            (op := OraclePayload()).decode_msg(ctvaa.payload.get()),
            self.prices[op.timestamp].set(op.encode()),
            # don't return anything
            output.set(Bytes("")),
        )

    def lookup(self, ts: abi.Uint64, *, output: OracleData):
        return output.decode(self.prices[ts].get_must())


def demo():
    o = OracleDataCache()
    print(o.application_spec())


if __name__ == "__main__":
    demo()
