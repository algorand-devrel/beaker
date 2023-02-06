from pyteal import abi
from beaker import sandbox, client
from beaker.testing.legacy import LegacyApplication


class ExternalExample(LegacyApplication):
    def __init__(self):
        super().__init__(implement_default_create=False)

        @self.create
        def create(input: abi.String, *, output: abi.String):
            return output.decode(input.encode())


def demo():

    app_client = client.ApplicationClient(
        sandbox.get_algod_client(),
        ExternalExample(),
        signer=sandbox.get_accounts().pop().signer,
    )
    app_client.create(input="yo")
    # print(result.return_value)


if __name__ == "__main__":
    demo()
