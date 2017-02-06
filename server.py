#!/usr/bin/env python
"""
dataPoints - A data point gathering service for IoT and other sources
Copyright (C) 2017 Henric Andersson (henric@sensenet.nu)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

##############################################################################

DataPoints

As the complexity of my home has increased, the amount of available
data has also increased. Yet, I don't have an easy way to gather and
analyze it.

This daemon aims to solve this dilema
"""
import sys
import time
import threading
import logging
import argparse
import datetime
import traceback
import random
from uuid import uuid4
import Storage
import json

""" Parse command line """
parser = argparse.ArgumentParser(description="dataPoints - Gather all your data points in one place", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('--logfile', metavar="FILE", help="Log to file instead of stdout")
parser.add_argument('--port', default=8088, type=int, help="Port to listen on")
parser.add_argument('--listen', metavar="ADDRESS", default="0.0.0.0", help="Address to listen on")
parser.add_argument('--database', metavar='DATABASE', help='Which database to use')
parser.add_argument('--dbserver', metavar="SERVER", help='Server running mySQL or MariaDB')
parser.add_argument('--dbuser', metavar='USER', help='Username for server access')
parser.add_argument('--dbpassword', metavar='PASSWORD', help='Password for server access')
parser.add_argument('--setup', action='store_true', default=False, help="Create necessary tables")
parser.add_argument('--force', action='store_true', default=False, help="Causes setup to delete tables if necessary (NOTE! YOU'LL LOSE ALL EXISTING DATA)")
cmdline = parser.parse_args()

""" Setup logging first """
logging.getLogger('').handlers = []
logging.basicConfig(filename=cmdline.logfile, level=logging.DEBUG, format='%(asctime)s - %(filename)s@%(lineno)d - %(levelname)s - %(message)s')

from tornado.wsgi import WSGIContainer
from tornado.ioloop import IOLoop
from tornado.web import Application, FallbackHandler
from tornado.websocket import WebSocketHandler

from flask import Flask, jsonify, abort, request

import mysql.connector
from mysql.connector import errorcode

""" Disable some logging by-default """
logging.getLogger("Flask-Cors").setLevel(logging.ERROR)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

""" Initialize the REST server """
app = Flask(__name__)

""" Initiate database connection """

database = Storage.MariaDB()
if not database.connect(cmdline.dbuser, cmdline.dbpassword, cmdline.dbserver, cmdline.database):
  sys.exit(1)

if cmdline.setup:
  if database.setup(cmdline.force):
    logging.info('Tables created successfully')
    sys.exit(0)
  else:
    logging.error('Setup failed')
    sys.exit(1)

result = database.validate()
if result == Storage.VALIDATION_NOT_SETUP:
  logging.error('Database is not setup, use --setup to create necessary tables')
  sys.exit(2)
elif result != Storage.VALIDATION_OK:
  logging.error('Internal database error ' + repr(result))
  sys.exit(1)

database.prepare()

def createResult(http_code, status, data=None):
  content = {"status" : status}
  if data is not None:
    content['data'] = data
  ret = jsonify(content);
  ret.status_code = http_code
  ret.status = status
  return ret

@app.route("/register", methods=['POST'])
def register():
  """
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
  THIS MAY CHANGE IN THE FUTURE!

  If successful, the call will return a UUID which must be used when sending data points.

  Result 200:
    { status : <result of operation>, data : { uuid : <uuid> } }
  Result 400:
    --- happens when data is corrupt, ie, not JSON ---
  Result 500:
    { status : <result of operation> }

  """
  result = None

  json = request.get_json()
  if json is None or 'name' not in json or 'type' not in json:
    result = createResult(500, "Invalid or missing JSON data")
  else:
    uuid = str(uuid4())
    accuracy = json.get('accuracy', 1)
    parameters = json.get('parameters', '')
    if not database.add_source(uuid, json['name'], json['type'], accuracy, parameters):
      result = createResult(500, "Invalid or missing JSON data")
    else:
      result = createResult(200, "Source registered", {'uuid':uuid})

  return result

@app.route('/entry/<uuid>', methods=['PUT', 'GET'])
def add_data(uuid):
  """
  Expects the following format of the data:
    { value : <value>, (ts : <timestamp>) }
  If timestamp is omitted, server fills in with current time

  Result 200:
    { status : OK }
  Result 400:
    --- Malformed JSON or otherwise incorrect data ---
  Result 500:
    { status : <error message> }

  Using GET will retrieve the latest entry reported for the source
  """
  if request.method == 'GET':
    json = database.query_latest([uuid])
    if json is None:
      return createResult(500, 'No such UUID or no data')
    return createResult(200, 'OK', json)
  elif request.method == 'PUT':
    json = request.get_json()
    return process_data(uuid, json)

@app.route('/sources', methods=['GET'], defaults={'uuid' : None})
@app.route('/source/<uuid>', methods=['GET'])
def list_sources(uuid):
  """
  Returns a list of all registered sources or just one if uuid is provided:
  [
    { uuid : <uuid>, name : <str>, type : <int>, accuracy : <int>, parameters : <str> },
    ...
  ]
  """
  data = database.sources(uuid)

  if data is None:
    if uuid is None:
      return createResult(500, "Unable to get list of registered sources")
    else:
      return createResult(500, "Unable to get source, no such uuid?")
  return createResult(200, "OK", data)

@app.route('/query', methods=['POST'])
def query():
  """
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

  """
  json = request.get_json()
  if json is None or 'uuid' not in json:
    return createResult(500, 'Missing uuid(s)')

  uuids = json['uuid']
  if not isinstance(uuids, list):
    uuids = [uuids]
  mode = json.get('mode', 'none').lower()
  if mode == 'sum':
    mode = Storage.GROUP_BY_SUM
  elif mode == 'average':
    mode = Storage.GROUP_BY_AVERAGE
  elif mode == 'median':
    mode = Storage.GROUP_BY_MEDIAN
  elif mode == 'none':
    mode = Storage.GROUP_BY_NONE
  else:
    return createResult(500, 'Unsupported mode')

  ts_start = ts_end = None
  if 'range' in json:
    ts_start = json['range'].get('start', None)
    ts_end   = json['range'].get('end', None)
    if ts_start is None and ts_end is None:
      return createResult(500, 'Using range requires start, end or both')
    if ts_end is not None and ts_start is not None and ts_end < ts_start:
      return createResult(500, 'Start of range has to be before end of range')

  reverse = False
  if json.get('reverse', False) != False:
    reverse = True

  iterator = database.query(uuids,
                            ts_start,
                            ts_end,
                            json.get('count', 0),
                            json.get('groupby', 0),
                            mode,
                            reverse)

  # This part will need to be redone to allow streaming instead of buffering
  result = []
  e = iterator.next()
  while e is not None:
    result.append(e)
    e = iterator.next()
  iterator.release()

  return createResult(200, "OK", result)

def process_data(uuid, json):
  result = None
  if json is None or 'value' not in json:
    result = createResult(500, "Invalid or missing JSON data")
  else:
    if not database.record(uuid, json['value'], json.get('ts', None)):
      result = createResult(500, 'Unable to add new value. Invalid UUID?')
    else:
      result = createResult(200, "OK")
  return result

class WebSocket(WebSocketHandler):
  def open(self):
    logging.info("Source connected to WebSocket")

  def check_origin(self, origin):
    return True

  def on_message(self, message):
    """
    Accepts the following input:
      {uuid : <uuid of source>, data : <same as PUT>, (id : <str/int>) }
    or
      [
        {uuid : <uuid of source>, data : <same as PUT>, (id : <str/int>) }
        {uuid : <uuid of source>, data : <same as PUT>, (id : <str/int>) }
        ...
      ]

    Result of the operation is:
      { status : <status>, status_code : <code>, (id : <str/int>) }
    or
      [
        { status : <status>, status_code : <code>, (id : <str/int>) }
        { status : <status>, status_code : <code>, (id : <str/int>) }
        ...
      ]

    The ID field allows a client to backtrack the result to the request. Server does
    not care about what kind of data it is, as long as it's a string or integer.
    """
    logging.debug("Message from source: " + repr(message))
    result = {'status':'Invalid data', 'status_code':500}
    try:
      j = json.loads(message)
      if isinstance(j, list):
        result = []
        for i in j:
          ret = process_data(i['uuid'], i['data'])
          if 'id' in i:
            result.append({'status' : ret.status, 'status_code' : ret.status_code, 'id' : j['id']})
          else:
            result.append({'status' : ret.status, 'status_code' : ret.status_code})
      else:
        ret = process_data(j['uuid'], j['data'])
        result['status'] = ret.status
        result['status_code'] = ret.status_code
        if 'id' in j:
          result['id'] = j['id']
    except Exception as e:
      logging.error('Source sent invalid message: ' + repr(e))
      result = {'status':'Invalid data', 'status_code':500, 'description' : repr(e)}
    finally:
      self.write_message(json.dumps(result))

    # Try decoding it as json

  def on_close(self):
    logging.info("Source disconnected")

""" Finally, launch! """
if __name__ == "__main__":
  app.debug = False
  logging.info("dataPoints running")
  container = WSGIContainer(app)
  server = Application([
    (r'/stream', WebSocket),
    (r'.*', FallbackHandler, dict(fallback=container))
    ])
  server.listen(cmdline.port)
  IOLoop.instance().start()
