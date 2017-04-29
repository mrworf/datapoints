# Python client for DataPoints

Initial version of the client, only supports websockets and atomic recording of values
There is no automatic retry logic if connection is lost, user must check return value
from record() function and resend when it returns False

The main benefit with this as opposed to using the REST API as-is comes from the fact
that it uses websockets. It will establish and keep a connection open allowing fast
and easy recording of values. Multiple sources can be attached to the same connection
allowing more than one source to use one connection.

This is handy for devices like weatherstation which usually report multiple temperature
readings and other data.

The client exposes a register() call to register sources but does NOT stop a client
from register the same source multiple times. It's up to the client to remember the 
UUID returned from the register call.