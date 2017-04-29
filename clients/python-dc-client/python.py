#!/usr/bin/env python
#

import datapoints
import time

SID='some unique id'

print("Example for the Python Client")

c = datapoints.client(atomic=False)

# Source with two decimal accuracy
uuid = c.resolvesid(SID)
if uuid is None:
	uuid = c.register(SID, 'Test Source', 0, accuracy=100, parameters=None)

id = c.attach(uuid)

print("Waiting 5s...")
time.sleep(5)

# Record entry for right now
if c.record(id, 10):
    print("Success!")
else:
    print("Failed!")

print("Waiting 5s...")
time.sleep(5)

# Record an entry 2min in the past
if c.record(id, 11, int(round(time.time())) - 180):
    print("Success!")
else:
    print("Failed")

