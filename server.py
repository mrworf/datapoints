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
class Storage:
  VALIDATION_OK = 0
  VALIDATION_NOT_SETUP = 1
  VALIDATION_NEED_UPGRADE = 2
  VALIDATION_ERROR = 255

  def __init__(self):
    # Holds all the sources AND the last recorded value (based on time)
    self.cache = {}

  def connect(self, user, pw, host, database):
    try:
      self.cnx = mysql.connector.connect(user=user, 
                                         password=pw,
                                         host=host,
                                         database=database)
      return True
    except mysql.connector.Error as err:
      if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        logging.error("Something is wrong with your user name or password")
      elif err.errno == errorcode.ER_BAD_DB_ERROR:
        logging.error("Database does not exist")
      else:
        logging.error(err)
    return False

  def validate(self):
    """
    Tests if the database is setup properly or if it needs to be installed
    or upgraded.

        0 = All is OK
        1 = Missing table(s)
        2 = Needs to upgrade
      255 = Things went terribly wrong
    """
    cursor = self.cnx.cursor(buffered=True)
    for table in [ 'sources', 'data' ]:
      query = ("DESCRIBE " + table)
      try:
        cursor.execute(query)
      except mysql.connector.Error as err:
        cursor.close()
        if err.errno == errorcode.ER_NO_SUCH_TABLE:
          return Storage.VALIDATION_NOT_SETUP
        else:
          logging.error(err)
          return Storage.VALIDATION_ERROR
    cursor.close()
    return Storage.VALIDATION_OK

  def setup(self, force):
    if force:
      cursor = self.cnx.cursor(buffered=True)
      for table in [ 'sources', 'data' ]:
        query = ("DROP TABLE " + table)
        try:
          logging.info(query)
          cursor.execute(query)
        except mysql.connector.Error as err:
          pass
      cursor.close()

    if self.validate() != Storage.VALIDATION_NOT_SETUP:
      logging.error('Database is not in a state where it can be setup')
      return False

    sql = [
      'CREATE TABLE sources (id int primary key auto_increment, name varchar(128) not null, uuid varchar(32) not null unique, type int not null, accuracy int not null, parameters text not null)',
      'CREATE TABLE data (ts datetime not null, source int not null, value int not null)'
    ]

    cursor = self.cnx.cursor(buffered=True)
    for s in sql:
      try:
        cursor.execute(s)
      except mysql.connector.Error as err:
        cursor.close()
        logging.error('Failed to execute: ' + s)
        logging.error(err)
        return False
    cursor.close()
    return True

  def disconnect(self):
    self.cnx.close()

  def prepare(self):
    """
    Loads up the cache and is now ready to be used
    """
    query = 'SELECT id, uuid, name, type, accuracy, parameters FROM sources'
    cursor = self.cnx.cursor(dictionary=True, buffered=True)
    try:
      cursor.execute(query)
      for row in cursor:
        self.cache[row['uuid']] = row
        self.cache[row['uuid']]['latest'] = None
      return True
    except mysql.connector.Error as err:
      logging.error('Failed to add source: ' + repr(err));
    finally:
      cursor.close()
    return False

  def add_source(self, uuid, name, type = 0, accuracy = 1, parameters = ''):
    query = 'INSERT INTO sources (uuid, name, type, accuracy, parameters) VALUES (%s, %s, %s, %s, %s)'
    cursor = self.cnx.cursor(buffered=True)
    try:
      cursor.execute(query, (uuid, name, type, accuracy, parameters))
      self.cnx.commit()
      self.cache[uuid] = {
        'id' : cursor.lastrowid,
        'uuid' : uuid,
        'name' : name,
        'type' : type,
        'accuracy' : accuracy,
        'parameters' : parameters,
        'latest' : None
      }
      return True
    except mysql.connector.Error as err:
      logging.error('Failed to add source: ' + repr(err));
    finally:
      cursor.close()
    return False


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

if not storage.add_source("abc", "testing"):
  logging.debug('Adding source failed')
storage.prepare()

print repr(storage.cache)

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
