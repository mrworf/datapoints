#!/usr/bin/env python
#

import datapoints
import time
import sys

SID='some unique id'
TYPE='f702f4c6-2d20-11e7-827a-000c29c98a28'

print("Example for the Python Client")

c = datapoints.client(atomic=False)

t = c.get_type(TYPE)
if t is None:
	c.register_type(TYPE, 'Temperature Farenheit', '')
sys.exit(0)

# Source with two decimal accuracy
uuid = c.resolvesid(SID)
if uuid is None:
	uuid = c.register(SID, 'Test Source', 0, accuracy=100, parameters=None)

id = c.attach(uuid)

# Record entry for right now
if c.record(id, 10):
    print("Success!")
else:
    print("Failed!")

# Record an entry 2min in the past
if c.record(id, 11, int(round(time.time())) - 180):
    print("Success!")
else:
    print("Failed")

