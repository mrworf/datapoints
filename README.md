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

REST API:

/register

  Expects the following:
    { name : <name of source>, type : <int>, (accuracy : <int>, parameters : <str>) }

  accuracy defaults to 1 if not defined
  parameters defaults to blank if not defined

  accuracy is essentially a divider which must be applied to the value of a data point to
  get the actual value. This allows for complete control of accuracy (ie, fractions).

  Neither accuracy nor parameters is used by the server at this point and is just passed
  on to the application using the data.

  type is used to indicate what the data represents from this source. Again, server does
  not use this and it's up to the calling application to use this when visualizing.

  If successful, the call will return a UUID which must be used when sending data points.

  Result 200:
    { status : <result of operation>, data : { uuid : <uuid> } }
  Result 400:
    --- happens when data is corrupt, ie, not JSON ---
  Result 500:
    { status : <result of operation> }

/source
/source/<uuid>

  Returns a list of all registered sources or just one if uuid is provided:
  [
    { uuid : <uuid>, name : <str>, type : <int>, accuracy : <int>, parameters : <str> },
    ...
  ]


/query

 Requests information from server, format is as follows:

  {
   uuid : [ <uuid>, ... ],
   (count : <nbr of results>),
   (groupby : <period>, mode : <sum/average/median>),
   (reverse : <bool>),
   (range : { (start : <ts>), (end : <ts>) })
  }

  uuid is special, it can either be a <uuid> or an array of <uuid>'s
  range requires either start, end or both

  Server returns:

  {
    status : <msg>,
    data : [
      { ts : <timestamp>, uuid : <uuid>, value : <int> },
      ...
    ]
  }

  Please note that the value isn't corrected with the accuracy defined in source!



WebSocket communication

IN:
  {uuid : <uuid of source>, data : <same as PUT>, (id : <str/int>) }
or
  [
    {uuid : <uuid of source>, data : <same as PUT>, (id : <str/int>) }
    {uuid : <uuid of source>, data : <same as PUT>, (id : <str/int>) }
    ...
  ]

OUT:
  { status : <status>, status_code : <code>, (id : <str/int>) }
or
  [
    { status : <status>, status_code : <code>, (id : <str/int>) }
    { status : <status>, status_code : <code>, (id : <str/int>) }
    ...
  ]