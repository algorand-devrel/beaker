Application
============

.. module:: beaker.application

This is the base class that all Beaker Applications should inherit from.


.. autoclass:: Application


    .. automethod:: application_spec

    .. automethod:: initialize_application_state
    .. automethod:: initialize_account_state

    Override the following methods to define custom behavior

    .. automethod:: create
    .. automethod:: update
    .. automethod:: delete 
    .. automethod:: opt_in
    .. automethod:: clear_state 
    .. automethod:: close_out 



