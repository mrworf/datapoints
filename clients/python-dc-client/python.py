#!/usr/bin/env python
#

import datapoints
import time

print("Example for the Python Client")

c = datapoints.client()

# Source with two decimal accuracy
uuid = c.register('Test Source', 0, accuracy=100, parameters=None)
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

