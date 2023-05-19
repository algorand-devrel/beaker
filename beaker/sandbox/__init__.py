from warnings import warn

from .clients import get_algod_client, get_indexer_client
from .kmd import SandboxAccount, add_account, get_accounts

__all__ = [
    "SandboxAccount",
    "add_account",
    "get_accounts",
    "get_algod_client",
    "get_indexer_client",
]

warn("beaker.sandbox is being deprecated, use beaker.localnet instead")
