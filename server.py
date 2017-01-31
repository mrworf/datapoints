#!/usr/bin/env python
#
# DataPoints
#
# As the complexity of my home has increased, the amount of available
# data has also increased. Yet, I don't have an easy way to gather and
# analyze it.
#
# This daemon aims to solve this dilema
#
import sys
import time
import threading
import logging
import argparse
import datetime
import traceback
import random
import uuid
from storage import Storage


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
parser.add_argument('--force', action='store_true', default=False, help="Causes setup to delete tables if necessary (NOTE! YOU'LL LOSE ANY EXISTING DATA)")
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


storage = Storage()
if not storage.connect(cmdline.dbuser, cmdline.dbpassword, cmdline.dbserver, cmdline.database):
  sys.exit(1)

if cmdline.setup:
  if storage.setup(cmdline.force):
    logging.info('Tables created successfully')
    sys.exit(0)
  else:
    logging.error('Setup failed')
    sys.exit(1)

result = storage.validate()
if result == Storage.VALIDATION_NOT_SETUP:
  logging.error('Database is not setup, use --setup to create necessary tables')
  sys.exit(2)
elif result != Storage.VALIDATION_OK:
  logging.error('Internal database error ' + repr(result))
  sys.exit(1)

storage.prepare()

class WebSocket(WebSocketHandler):
  def open(self, remoteId):
    logging.info("Remote %s has connected", remoteId);

  # TODO: We don't care (for now) about origin
  def check_origin(self, origin):
    return True

  def on_message(self, message):
    logging.debug("Remote %s message: %s", self.remoteId, message)

  def on_close(self):
    logging.info("Remote %s has disconnected", self.remoteId)

@app.route("/register", methods=['POST'])
def register():
  result = {'error':None}

  json = request.get_json()
  if json is None or 'name' not in json or 'type' not in json:
    result['error'] = "Invalid or missing JSON data"
  else:
    result['uuid'] = str(uuid.uuid4())
    accuracy = json.get('accuracy', 1)
    parameters = json.get('parameters', '')
    if not storage.add_source(result['uuid'], json['name'], json['type'], accuracy, parameters):
      result['error'] = 'Unable to add the new source'

  ret = jsonify(result)
  if result['error'] == None:
    ret.status_code = 200
  else:
    ret.status_code = 500
  return ret

@app.route('/entry/<uuid>', methods=['PUT'])
def add_data(uuid):
  result = {'error':None}

  json = request.get_json()
  if json is None or 'value' not in json:
    result['error'] = "Invalid or missing JSON data"
  else:
    if not storage.record(uuid, json['value'], json.get('ts', None)):
      result['error'] = 'Unable to add new value. Invalid UUID?'
  ret = jsonify(result)
  if result['error'] == None:
    ret.status_code = 200
  else:
    ret.status_code = 500
  return ret


""" Finally, launch! """
if __name__ == "__main__":
  app.debug = False
  logging.info("dataPoints running")
  container = WSGIContainer(app)
  server = Application([
    (r'/events/(.*)', WebSocket),
    (r'.*', FallbackHandler, dict(fallback=container))
    ])
  server.listen(cmdline.port)
  IOLoop.instance().start()
