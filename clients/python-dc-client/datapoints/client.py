"""Client for DataPoints server
Uses websockets for a more streamlined reporting functionality
Only external dependency is websocket library.
"""
from __future__ import print_function
import sys
import re
import urllib2, urllib
import time

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class client:
  def __init__(self, atomic=True, server="localhost", port=8088):
    """Setup the class
    atomic If true, any recorded value must be acked and cannot be sent later (default)
    If you set atomic to false, it will cache entries until they can be sent (not yet implemented)
    server By default localhost
    port By default 8088
    """
    self.tokens = []
    self.counter = 0
    self.connected = False
    self.server = server
    self.port = port
    self.queue = []
    self.atomic = atomic

    try:
      import websocket
    except:
      eprint("This library requires websocket from https://pypi.python.org/pypi/websocket-client/")
      sys.exit(255)
    self.ws = websocket.WebSocket()
    self._connect()
    return

  def _connect(self):
    if self.connected:
      return True
    try:
      self.ws.connect("ws://%s:%d/stream" % (self.server, self.port))
      self.connected = True
    except:
      eprint("Unable to connect to server")
      self.connected = False
    return self.connected

  def resolve_source_id(self, sid):
    """Resolve the UUID for a SID.
    """
    url = 'http://%s:%d/resolve' % (self.server, self.port)
    data = '{"sid":"%s"}' % (sid)
    req = urllib2.Request(url, data)
    req.add_header('Content-Type', 'application/json')    
    try:
      response = urllib2.urlopen(req)
      result = response.read()
      m = re.search('{"status": "([^"]+)", "data": {"uuid": "([^"]+)"}}', result)
      if m is not None:
        return m.group(2)
    except:
      eprint("Server error")
    return None

  def get_type(self, uuid):
    url = 'http://%s:%d/type/%s' % (self.server, self.port, uuid)
    req = urllib2.Request(url)
    try:
      response = urllib2.urlopen(req)
      result = response.read()
      m = re.search('{"status": "([^"]+)", "data": \[{"description": "([^"]*)", "uuid": "([^"]+)", "name": "([^"]+)"}\]}', result)
      if m is not None:
        return {"description": m.group(2), "name": m.group(3)}
    except:
      eprint("Server error")
    return None

  def register_type(self, uuid, name, description):
    url = 'http://%s:%d/type/register' % (self.server, self.port)
    data = '{"uuid":"%s","name":"%s", "description":"%s"}' % (uuid, name, description)
    req = urllib2.Request(url, data)
    req.add_header('Content-Type', 'application/json')
    try:
      response = urllib2.urlopen(req)
      result = response.read()
      return True
    except:
      eprint("Server error")
    return False

  def register_source(self, sid, name, type, accuracy=1, parameters=""):
    """Register a new source on the backend and return the UUID for it
    name is a human readable name for the source
    type is a number starting from zero, used by visualizer
    accuracy is a divider which by default is 1 for integers, 10 for 1 decimal, etc...
    parameters is useful if the source has special abilities
    """
    url = 'http://%s:%d/register' % (self.server, self.port)
    data = '{"sid":"%s","name":"%s", "type":"%s", "accuracy":%d,"parameters":"%s"}' % (sid, name, type, accuracy, parameters)
    req = urllib2.Request(url, data)
    req.add_header('Content-Type', 'application/json')    
    try:
      response = urllib2.urlopen(req)
      result = response.read()
      m = re.search('{"status": "([^"]+)", "data": {"uuid": "([^"]+)"}}', result)
      if m is not None:
        return m.group(2)
    except:
      eprint("Server error")
    return None

  def attach(self, token):
    """Attach a previously registered source to the client so we can record values
    Returns a local ID which is used for other functions
    """
    if token not in self.tokens:
      self.tokens.append(token)
    return self.tokens.index(token)

  def detach(self, token):
    """Removes an attached source"""
    if token in self.tokens:
      self.tokens.pop(self.tokens.index(token))

  def record(self, reference, value, timestamp=None):
    """Records a value for an attached source, timestamp is optional, uses current time if not provided"""

    # Avoid allowing anyone to record values without attaching
    if reference >= len(self.tokens) or len(self.tokens) == 0:
      return False

    extras = ""
    myid = self.counter
    self.counter += 1

    if not self.atomic and timestamp is None:
      # Generate local timestamp, otherwise queuing with fail
      timestamp = int(round(time.time()))

    if timestamp is not None:
      extras = ',"timestamp":%d' % timestamp

    json = '{"uuid":"%s","data":{"value":%d%s},"id":"%s"}' % (self.tokens[reference], value, extras, myid)

    # If we fail but aren't in atomic mode, store entry to send later...
    sent = self._send(myid, json)
    if not sent and not self.atomic:
      eprint('Failed to send, queuing')
      self.queue.append({"id": myid, "data": json})
      return True
    elif sent and len(self.queue) != 0:
      # Since we succeeded and we have queued items, fire them off now too before returning
      eprint('Sending queued items')
      while len(self.queue):
        item = self.queue[0]
        if not self._send(item['id'], item['data']):
          break
        self.queue.pop(0)
    return sent

  def _send(self, id, data):
    if not self._connect():
      return False

    try:
        if self.ws.send(data) == 0:
          eprint("Not connected")
          self.connected = False
          return False
    except:
      self.connected = False
      eprint("Fatal error: %s" % repr(sys.exc_info()))
      return False

    try:
      result = self.ws.recv()
    except:
      self.connected = False
      eprint("Fatal error: %s" % repr(sys.exc_info()))
      return False

    # {"status": "OK", "status_code": 200, "id": "0"}
    m = re.search('{"status": "([^"]+)", "status_code": ([0-9]+), "id": "([^"]+)"}', result)
    if m is not None and m.group(1) == "OK":
      if int(m.group(3)) != id:
        # We should be able to handle multiple concurrent calls, but for now...
        eprint("WARNING: Result was not the same ID as sent (%d != %d)" % (int(m.group(3)), id))
      return True
    return False
