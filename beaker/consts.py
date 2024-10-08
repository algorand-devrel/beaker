from math import ceil
from typing import Final

from algosdk.constants import APP_PAGE_MAX_SIZE
from pyteal import Int

#: number of microalgos in 1 Algo
algo: Final[int] = int(1e6)
#: number of microalgos in 1 MilliAlgo
milli_algo: Final[int] = int(1e3)

#: Used for runtime algo calculations `Txn.amount()==Algo`
Algo: Final[Int] = Int(algo)
#: Used for runtime algo calculations `Txn.fee()==MilliAlgo`
MilliAlgo: Final[Int] = Int(milli_algo)


#: Used for shorthand for Int(10*algo) like Algos(10)
def Algos(v: int | float) -> Int:  # noqa: N802
    return Int(int(v * algo))


#: Used for shorthand for Int(10*milli_algo) like MilliAlgos(10)
def MilliAlgos(v: int | float) -> Int:  # noqa: N802
    return Int(int(v * milli_algo))


#: Max number of inner transactions that may be called
MAX_INNERS = 255
#: Single app call opcode budget
APP_CALL_BUDGET = 700
#: Max possible opcode budget
MAX_OPS = MAX_INNERS * APP_CALL_BUDGET

#: Single app call budget
AppCallBudget = Int(APP_CALL_BUDGET)
#: Max app call budget possible
MaxOps = Int(MAX_OPS)


#: TRUE used as an alias for 1
TRUE: Final[Int] = Int(1)
#: FALSE used as an alias for 0
FALSE: Final[Int] = Int(0)

#: The max number of local state values that may be declared
MAX_LOCAL_STATE = 16
#: The max number of global state values that may be declared
MAX_GLOBAL_STATE = 64

#: The maximum number of args that may be included in an lsig
LSIG_MAX_ARGS = 255

#: The prefix used when hashing bytecode to produce a unique hash
PROGRAM_DOMAIN_SEPARATOR = "Program"

#: The min balance increase per box created
BOX_FLAT_MIN_BALANCE = 2500

#: The min balance increase per byte of boxes (key included)
BOX_BYTE_MIN_BALANCE = 400

#: The min balance increase for each asset opted into
ASSET_MIN_BALANCE = 100000


def num_extra_program_pages(approval: bytes, clear: bytes) -> int:
    return ceil(((len(approval) + len(clear)) - APP_PAGE_MAX_SIZE) / APP_PAGE_MAX_SIZE)
