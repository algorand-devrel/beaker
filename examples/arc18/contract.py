from pyteal import *

from beaker.contracts.arcs import ARC18
from beaker.decorators import external


class MyRoyaltyContract(ARC18):
    pass


if __name__ == "__main__":
    mrc = MyRoyaltyContract()
    print(mrc.contract.dictify())
