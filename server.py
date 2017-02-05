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
import uuid
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
  result = None

  json = request.get_json()
  if json is None or 'name' not in json or 'type' not in json:
    result = createResult(500, "Invalid or missing JSON data")
  else:
    uuid = str(uuid.uuid4())
    accuracy = json.get('accuracy', 1)
    parameters = json.get('parameters', '')
    if not database.add_source(uuid, json['name'], json['type'], accuracy, parameters):
      result = createResult(500, "Invalid or missing JSON data")
    else:
      result = createResult(200, "Source registered", {'uuid':uuid})

  return result

@app.route('/entry/<uuid>', methods=['PUT'])
def add_data(uuid):
  """
  Expects the following format of the data:
    { value : <value>, (ts : <timestamp>) }
  If timestamp is omitted, server fills in with current time
  """
  json = request.get_json()
  return process_data(uuid, json)


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
