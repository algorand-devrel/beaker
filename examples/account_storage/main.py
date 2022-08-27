import random
import string
from typing import cast
import algosdk.future.transaction as txns
from algosdk.atomic_transaction_composer import *
from pyteal import *
from beaker import *

# Simple logic sig, will approve _any_ transaction
# Used to expand our apps available state by
# creating unique account that will do whatever we need.
# In this case, we need it to opt in and rekey to the app address
class KeySig(LogicSignature):
    nonce = TemplateVariable(TealType.bytes)

    def evaluate(self):
        return Approve()


# App that needs lots of storage so we use the local storage of
# unique lsig accounts that have been rekeyed to the app address.
# This allows us to use the local storage of the unique accounts
# to get an extra 2k of storage for each account
class DiskHungry(Application):
    # Reserve all 16 keys for the blob in local state
    data = AccountStateBlob(max_keys=16)

    # Signal to beaker that this should be compiled
    # prior to compiling the main application
    tmpl_acct = Precompile(KeySig(version=6))

    # Add account during opt in  by checking the sender against the address
    # we expect given the precompile && nonce
    @external(method_config=MethodConfig(opt_in=CallConfig.CALL))
    def add_account(self, nonce: abi.DynamicBytes):
        return Seq(
            Assert(
                # Make sure the opt-in'er is our lsig
                Txn.sender() == self.tmpl_acct.template_address(nonce.get()),
                # and that its being rekeyed to us
                Txn.rekey_to() == self.address,
            ),
            self.initialize_account_state(),
        )

    # Inline these
    def byte_idx(self, bit_idx) -> Int:
        return bit_idx / Int(8)

    def bit_in_byte_idx(self, bit_idx) -> Int:
        return bit_idx % Int(8)

    @external
    def flip_bit(self, nonce_acct: abi.Account, bit_idx: abi.Uint32):
        """
        Allows caller to flip a bit at a given index for some account that has already opted in
        """

        return Seq(
            # Read byte
            (byte := ScratchVar()).store(
                self.data[nonce_acct.address()].read_byte(self.byte_idx(bit_idx.get()))
            ),
            # Flip bit
            byte.store(
                SetBit(
                    byte.load(),
                    self.bit_in_byte_idx(bit_idx.get()),
                    Not(GetBit(byte.load(), self.bit_in_byte_idx(bit_idx.get()))),
                )
            ),
            # Write byte
            self.data[nonce_acct.address()].write_byte(
                self.byte_idx(bit_idx.get()), byte.load()
            ),
        )


def demo():

    # Create app client
    app_client = client.ApplicationClient(
        client=sandbox.get_algod_client(),
        app=DiskHungry(),
        signer=sandbox.get_accounts().pop().signer,
    )
    # Create the app
    app_client.create()
    app_client.fund(2 * consts.algo)

    # Get the `precompile` wrapped LSig from the app instance
    tmpl_lsig: Precompile = cast(DiskHungry, app_client.app).tmpl_acct

    # Create 10 random nonces for unique lsig accounts
    # and make them opt in to the app
    for _ in range(10):
        # Get a rando val
        nonce = get_nonce()

        # Populate the binary template with the nonce and get back a Signer obj
        # to submit transactions
        lsig_signer = tmpl_lsig.template_signer(nonce)

        # Create the account and opt it into the app, also rekeys it to the app address
        create_and_opt_in_account(app_client, lsig_signer, nonce)

        # Max is 8 (bits per byte) * 127 (bytes per key) * 16 (max keys) == 16256
        idx = 16255
        app_client.call(
            DiskHungry.flip_bit, nonce_acct=lsig_signer.lsig.address(), bit_idx=idx
        )

        # Get the full state for the lsig we used to store this bit
        acct_state = app_client.get_account_state(lsig_signer.lsig.address(), raw=True)

        # Make sure the blob is in the right order
        blob = b""
        for x in range(16):
            blob += cast(bytes, acct_state[x.to_bytes(1, "big")])

        # Did the expected byte have the expected integer value?
        assert int(blob[idx // 8]) == 2 ** (idx % 8)
        print(f"bit set correctly at index {idx}")


def get_nonce(n: int = 10) -> bytes:
    return ("".join(random.choice(string.ascii_uppercase) for _ in range(n))).encode()


def create_and_opt_in_account(
    app_client: client.ApplicationClient,
    lsig_signer: LogicSigTransactionSigner,
    nonce: bytes,
):
    lsig_client = app_client.prepare(signer=lsig_signer)

    print(
        f"Creating templated lsig with nonce {nonce} and address {lsig_signer.lsig.address()}"
    )

    atc = AtomicTransactionComposer()

    sp = app_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 2 * consts.milli_algo
    atc.add_transaction(
        TransactionWithSigner(
            txn=txns.PaymentTxn(
                # Give the lsig 1 algo for min balance (really less than that needed but I'm lazy)
                # TODO: get min bal reqs for optin from app?
                app_client.get_sender(),
                sp,
                lsig_signer.lsig.address(),
                consts.algo,
            ),
            signer=app_client.signer,
        )
    )

    sp = app_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 0
    lsig_client.add_method_call(
        atc,
        DiskHungry.add_account,
        nonce=nonce,
        suggested_params=sp,
        rekey_to=app_client.app_addr,
        on_complete=txns.OnComplete.OptInOC,
    )

    atc.execute(app_client.client, 4)


if __name__ == "__main__":
    demo()
