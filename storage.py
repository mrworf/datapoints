import sys
import time
import threading
import logging
import datetime
import traceback
import random

import mysql.connector
from mysql.connector import errorcode

class Storage:
  VALIDATION_OK = 0
  VALIDATION_NOT_SETUP = 1
  VALIDATION_NEED_UPGRADE = 2
  VALIDATION_ERROR = 255

  GROUP_MODE_SUM = 0
  GROUP_MODE_AVERAGE = 1
  GROUP_MODE_MEDIAN = 2

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
      'CREATE TABLE sources (id int primary key auto_increment, name varchar(128) not null, uuid varchar(64) not null unique, type int not null, accuracy int not null, parameters text not null)',
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
    cursor2 = self.cnx.cursor(dictionary=True, buffered=True)
    try:
      cursor.execute(query)
      for row in cursor:
        self.cache[row['uuid']] = row
        self.cache[row['uuid']]['latest'] = None
        cursor2.execute('SELECT UNIX_TIMESTAMP(ts) AS ts,value FROM data WHERE source = %s ORDER BY ts DESC LIMIT 1', (self.cache[row['uuid']]['id'],))
        for r2 in cursor2:
          self.cache[row['uuid']]['latest'] = {
            'value' : r2['value'],
            'ts' : r2['ts']
          } 
      return True
    except mysql.connector.Error as err:
      logging.error('Failed to prepare cache: ' + repr(err));
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

  def record(self, uuid, value, ts = None):
    if ts is None:
      ts = int(round(time.time()))
    if ts < 1:
      logging.warn('Cannot have timestamps less than 1, typically indicate issue :)')
      return False
    query = 'INSERT INTO data (source, value, ts) VALUES (%s, %s, FROM_UNIXTIME(%s))'
    cursor = self.cnx.cursor(buffered=True)
    if uuid in self.cache:
      id = self.cache[uuid]['id']
    else:
      logging.warn('UUID %s does not exist' % uuid)
      return False

    try:
      cursor.execute(query, (id, value, ts))
      self.cnx.commit()
      if self.cache[uuid]['latest'] is None or self.cache[uuid]['latest']['ts'] <= ts:
        self.cache[uuid]['latest'] = {
          'value' : value,
          'ts' : ts
        }
      return True
    except mysql.connector.Error as err:
      logging.error('Failed to record data: ' + repr(err));
    finally:
      cursor.close()
    return False

  def query(self, uuids, count = 0, groupby = 0, mode = Storage.GROUP_BY_SUM):
    """
    Retrieves data points from UUIDs
    Limit to count (zero means no limit)
    Group it by groupby seconds (zero means no grouping)

    Grouping essentially breaks it down to groups of X seconds, using
    the described method in mode (default is sum)

    Returns iterator which allows streaming of data
    """
    pass

  def query_range(self, uuids, start_ts, end_ts, groupby = 0, mode = Storage.GROUP_BY_SUM):
    """
    Retrieves data points from UUIDs
    Limit by specifying start and end timestamp (both inclusive)
    Group it by groupby seconds (zero means no grouping)

    Grouping essentially breaks it down to groups of X seconds, using
    the described method in mode (default is sum)

    Returns iterator which allows streaming of data
    """
    pass

class Iterator:
  def __init__(self, resultset, error=None):
    pass

  def getError(self):
    """
    Returns any potential error, if no error condition exist,
    it will return None
    """
    pass

  def next(self):
    """
    Advances to the next record, returning current
    Record is a dict of source, ts, value

    If no more record exists, the function returns None
    """
    pass

  def cancel(self):
    """
    Early bailout, after calling this function, the iterator
    resources are freed and you should not use it anymore.
    """
    pass
