Usage
=====

.. _tutorial:

Tutorial
---------


Lets write a simple calculator app.  `Full source here <https://github.com/algorand-devrel/beaker/blob/master/examples/simple/calculator.py>`_.

First, create a class to represent our application as a subclass of the beaker `Application`. 

.. code-block:: python

    from beaker import Application

    class Calculator(Application):
        pass 


This is a full application, though it doesn't do much.  

Instantiate it and take a look at some of the resulting fields. 

.. literalinclude:: ../../examples/simple/calculator.py 
    :lines: 60-65


Nice!  This is already enough to provide the TEAL programs and ABI specification.

Lets add some methods to be handled by an incoming `ApplicationCallTransaction <https://developer.algorand.org/docs/get-details/transactions/transactions/#application-call-transaction>`_.  
We can do this by tagging a `PyTeal ABI <https://pyteal.readthedocs.io/en/stable/api.html#pyteal.ABIReturnSubroutine>`_ method with with the :ref:`external <external>` decorator. 


.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 9-28


The ``@external`` decorator adds an ABI method to our application and includes it in the routing logic for handling an ABI call. 

The python method must return an ``Expr`` of some kind, invoked when the external is called. 

.. note::
    ``self`` may be omitted if the method does not need to access any instance variables. Class variables or methods may be accessed through the class name like ``MySickApp.do_thing(data)``

Lets now deploy and call our contract using an :ref:`ApplicationClient <application_client>`.

.. literalinclude:: ../../examples/simple/calculator.py
    :lines: 32-47


Thats it! 

To summarize, we:

 * Wrote an application using Beaker and PyTeal
    By subclassing ``Application`` and adding an ``external`` method
 * Compiled it to TEAL 
    Done automatically by the ``Application`` class, and PyTeal's ``Router.compile`` 
 * Assembled the TEAL to binary
    Done automatically by the ``ApplicationClient`` by sending the TEAL to the algod ``compile`` endpoint
 * Deployed the application on-chain
    Done by invoking the ``app_client.create``, which submits an ApplicationCallTransaction including our binary.

    .. note:: 
        Once created, subsequent calls to the app_client are directed to the ``app_id``. 
        The constructor may also be passed an app_id directly if one is already deployed.

 * Called the method we defined
    Using ``app_client.call``, passing the method defined in our class and args the method specified (by name). 

    .. note::
        The args passed must match the type of the method (i.e. don't pass a string when it wants an int). 

    The result contains the parsed ``return_value`` which is a python native type that mirrors the return type of the ABI method.

.. _use_decorators: 

Decorators
-----------

Above, we used the decorator ``@external`` to mark a method as being exposed in the ABI and available to be called from off-chain.

The ``@external`` decorator can take parameters to change how it may be called or what accounts may call it, see examples :ref:`here <external>`.

Other decorators include :ref:`@internal <internal_methods>` which marks the method as being callable only from inside the application or with one of the :ref:`bare <bare_externals>` OnComplete handlers (e.g. ``create``, ``opt_in``, etc...)


.. _manage_state:

State Management
----------------

Beaker provides a way to define state values as class variables and use them throughout our program. This is a convenient way to encapsulate functionality associated with some state values.

.. note:: 
    Throughout the examples, we tend to mark State Values as ``Final[...]``, this is solely for good practice and has no effect on the output of the program.


Lets write a new app with Application State (or `Global State <https://developer.algorand.org/docs/get-details/dapps/smart-contracts/apps/#modifying-state-in-smart-contract>`_ in Algorand parlance) to our Application. 

.. literalinclude:: ../../examples/simple/counter.py
    :lines: 12-38

We've added an :ref:`ApplicationStateValue <application_state_value>` attribute to our class with several configuration options and we can reference it by name throughout our application.

.. note:: 
    The base ``Application`` class has several externals pre-defined, including ``create`` which performs ``ApplicationState`` initialization for us, setting the keys to default values.

You may also define state values for applications, called :ref:`AccountState <account_state>` (or Local storage) and even allow for dynamic state keys.

For more example usage see the example :ref:`here <state_example>`.

.. _inheritance:

Inheritance 
-----------

What about extending our Application with some other functionality?

.. literalinclude:: ../../examples/opup/contract.py
    :lines: 7-42

Here we subclassed the ``OpUp`` contract which provides functionality to create a new Application on chain and store its app id for subsequent calls to increase budget.

We inherit the methods and class variables that ``OpUp`` defined, allowing us to encapsulate and compose behavior.


.. _parameter_annotations:

Parameter Annotations
---------------------

.. currentmodule:: beaker.decorators
.. autoclass:: ParameterAnnotation


A caller of our application should be provided with all the information they might need in order to make a successful application call.

One example of this of information is of course the parameter name and type. These bits of information are already provided by the normal method definition. 

 
.. _parameter_description:

Parameter Description
^^^^^^^^^^^^^^^^^^^^^^

Another example that is harder to provide is the description of the parameter. The plain english explanation of what the parameter _should_ be can be quite helpful in determining what to pass the method. To set a description on a parameter you can use the python ``typing.Annotated`` generic class and pass it an instance of ``ParameterAnnotation``.

.. code-block:: python

    from typing import Annotated

    #...

    @external
    def unhelpful_method_name(self, num: Annotated[
        abi.Uint64, 
        ParameterAnnotation(
            descr="The magic number, which should be prime, else fail"
        )
    ]):
        return is_prime(num.get())


Here we've annotated the ``num`` parameter with a description that should help the caller figure out what should be passed. This description is added to the appropriate method args description field in the json spec.


.. _parameter_default:

Parameter Default Value
^^^^^^^^^^^^^^^^^^^^^^^

In the ``OpUp`` example the argument ``opup_app`` should be the id of the application that we use to increase our budget via inner app calls.  This value should not change frequently, if at all, but is still required to be passed by the caller so we may _use_ it in our logic. 

Using the ``default`` field of the ``ParameterAnnotation``, we can specify a default value for the parameter.  

This allows the caller to know this pseudo-magic number ahead of time and makes calling your application easier.  The information is communicated through the full ApplicationSpec as a hint the caller can use to figure out what the value should be.

Options for default arguments are:

- A constant, `Bytes | Int`
- State Values, `ApplicationStateValue | AccountStateValue`
- A read-only ABI method  

The result is that we can call the method, omitting the `opup_app` argument:

.. code-block:: python

    result = app_client.call(app.hash_it, input="hashme", iters=10)

When invoked, the `ApplicationClient` consults the method definition to check that all the expected arguments are passed. If it finds one missing, it will check for hints for the method that may be resolvable. Upon finding a resolvable it will look up the state value, call the method, or return the constant value. The resolved value is passed in for argument.