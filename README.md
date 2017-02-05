dataPoints

This server aims to simplify the reporting of data from IoT devices and other sources.
It uses REST and/or WebSocket communication depending on how often a source needs to
send data.

The stored data is then exposed via REST to any client, facilitating easy implementation of
other services that take advantage of the collected data.

There is also a caching mechanism where any service may easily read the latest reported value
of a source without ever hitting the storage. This simplifies use of data such as rain and
temperature which would allow easy integration in sprinkler systems or thermostats.

Lastly, the storage itself is written to allow any underlying technology to be used.

Right now, it utilizes MariaDB/mySQL but the intention is also to provide MongoDB storage
in the future.