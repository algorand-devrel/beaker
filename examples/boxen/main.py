from algosdk.abi import ABIType
from algosdk.encoding import encode_address, decode_address
from algosdk.atomic_transaction_composer import TransactionWithSigner
from algosdk.future.transaction import *

from pyteal import *
from beaker import *

from application import AppMember, MembershipRecord, MembershipClub


record_codec = ABIType.from_string(str(MembershipRecord().type_spec()))


affirmations = [
    "I am successful.",
    "I am confident.",
    "I am powerful.",
    "I am strong.",
    "I am getting better and better every day.",
    "All I need is within me right now.",
    "I wake up motivated.",
    "I am an unstoppable force of nature.",
    "I am a living, breathing example of motivation.",
    "All I need is GM.",
]


def print_boxes(app_client: client.ApplicationClient):
    boxes = app_client.get_box_names()
    print(f"{len(boxes)} boxes found")
    for box_name in boxes:
        contents = app_client.get_box_contents(box_name)
        if box_name == b"affirmations":
            print(contents)
        else:
            membership_record = record_codec.decode(contents)
            print(f"\t{encode_address(box_name)} => {membership_record} ")


def demo():
    accts = sandbox.get_accounts()
    acct = accts.pop()
    member_acct = accts.pop()

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(), MembershipClub(), signer=acct.signer
    )
    print("Creating app")
    app_client.create()

    ##
    # Bootstrap
    ##
    print("Bootstrapping app")
    sp = app_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 2000
    ptxn = PaymentTxn(
        acct.address, sp, app_client.app_addr, MembershipClub._min_balance
    )
    result = app_client.call(
        MembershipClub.bootstrap,
        seed=TransactionWithSigner(ptxn, acct.signer),
        token_name="fight club",
        boxes=[[app_client.app_id, "affirmations"]] * 8,
    )
    membership_token = result.return_value
    print(f"Created asset id: {membership_token}")

    ##
    # Add Member
    ##

    app_client.client.send_transaction(
        AssetOptInTxn(member_acct.address, sp, membership_token).sign(
            member_acct.private_key
        )
    )

    app_client.call(
        MembershipClub.add_member,
        new_member=member_acct.address,
        suggested_params=sp,
        boxes=[[app_client.app_id, decode_address(member_acct.address)]],
    )
    print_boxes(app_client)

    result = app_client.call(
        MembershipClub.get_membership_record,
        member=member_acct.address,
        boxes=[[app_client.app_id, decode_address(member_acct.address)]],
    )
    print(result.return_value)

    member_client = app_client.prepare(signer=member_acct.signer)
    for idx, aff in enumerate(affirmations):
        result = member_client.call(
            MembershipClub.set_affirmation,
            idx=idx,
            affirmation=aff.ljust(64, " ").encode(),
            boxes=[[app_client.app_id, "affirmations"]] * 2,
        )

    result = member_client.call(
        MembershipClub.get_affirmation,
        boxes=[[app_client.app_id, "affirmations"]] * 2,
    )
    print(bytes(result.return_value).decode("utf-8").strip())

    app_client.call(
        MembershipClub.remove_member,
        boxes=[[app_client.app_id, decode_address(member_acct.address)]],
        member=member_acct.address,
    )
    print_boxes(app_client)

    add_app_member(app_client, membership_token)


def add_app_member(app_client: client.ApplicationClient, membership_token: int):

    # Create App as member of club
    print("Creating app member")

    app_member_client = client.ApplicationClient(
        sandbox.get_algod_client(), AppMember(), signer=app_client.signer
    )
    _, app_member_addr, _ = app_member_client.create()

    print("Bootstrapping app member")
    sp = app_member_client.get_suggested_params()
    sp.flat_fee = True
    sp.fee = 2000
    ptxn = PaymentTxn(app_client.sender, sp, app_member_addr, consts.algo * 1)
    app_member_client.call(
        AppMember.bootstrap,
        seed=TransactionWithSigner(ptxn, app_client.signer),
        app_id=app_client.app_id,
        membership_token=membership_token,
    )

    # Add app to club using the member_club client
    app_client.call(
        MembershipClub.add_member,
        new_member=app_member_addr,
        suggested_params=sp,
        boxes=[[app_client.app_id, decode_address(app_member_addr)]],
    )

    app_member_client.call(
        AppMember.get_affirmation, boxes=[[app_client.app_id, "affirmations"]] * 2
    )

    app_state = app_member_client.get_application_state()
    print(f"Last affirmation received by app member: {app_state['last_affirmation']}")


if __name__ == "__main__":
    demo()
