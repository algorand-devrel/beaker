Beaker
------
<img align="left" src="beaker.png" margin="10px" >

Beaker is a smart contract development framework for [PyTeal](https://github.com/algorand/pyteal) inspired by Flask


With Beaker, we build a class that represents our entire application including state and routing.

*Mostly Untested - Expect Breaking Changes* 


## Hello, Beaker


```py
from pyteal import *
from beaker import *

# Create a class, subclassing Application from beaker
class HelloBeaker(Application):
    # Add an external method with ABI method signature `hello(string)string`
    @external
    def hello(self, name: abi.String, *, output: abi.String):
        # Set output to the result of `Hello, `+name
        return output.set(Concat(Bytes("Hello, "), name.get()))


# Create an Application client
app_client = client.ApplicationClient(
    # Get sandbox algod client
    client=sandbox.get_algod_client(),
    # Instantiate app, pass it to client
    app=HelloBeaker(),
    # Get acct from sandbox and pass the signer
    signer=sandbox.get_accounts().pop().signer,
)

# Deploy the app on-chain
app_id, app_addr, txid = app_client.create()
print(
    f"""Deployed app in txid {txid}
    App ID: {app_id} 
    Address: {app_addr} 
"""
)

# Call the `hello` method
result = app_client.call(HelloBeaker.hello, name="Beaker")
print(result.return_value)  # "Hello, Beaker"

```

## Install

You can install from pip:

`pip install beaker-pyteal`

Or from github directly (no promises on stability): 

`pip install git+https://github.com/algorand-devrel/beaker`


# Dev Environment 

Requires a local [sandbox](https://github.com/algorand/sandbox).

*NOTE:* Currently requires a sandbox running with the `source` config (or any config that contains [this commit](https://github.com/algorand/go-algorand/pull/4198))

```sh
$ git clone git@github.com:algorand/sandbox.git
$ cd sandbox
$ sandbox up source
```

## Testing

You can run tests from the root of the project using `pytest`

## Use

[Examples](/examples/)

[Docs](https://beaker.algo.xyz)

*Please feel free to file issues/prs*