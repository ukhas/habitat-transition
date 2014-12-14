# Copyright 2011 (C) Daniel Richman
#
# This file is part of habitat.
#
# habitat is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# habitat is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with habitat.  If not, see <http://www.gnu.org/licenses/>.

"""
This module provides a super lightweight flask application that provides an
easy interface to an Uploader for other processes
"""

import flask
import base64
import json
import time
import couchdbkit
from werkzeug.contrib.cache import SimpleCache as Cache
from xml.sax.saxutils import escape as htmlescape
from habitat import uploader
from . import couch_to_xml
from habitat.utils.startup import load_config, setup_logging

# Monkey patch float precision
json.encoder.FLOAT_REPR = lambda o: format(o, '.5f')

app = flask.Flask("habitat_transition.app")
cache = Cache(threshold=10, default_timeout=60)

# Load config here :S ?
# N.B.: Searches working directory since it won't be specified in argv.
# Configure uwsgi appropriately.
config = load_config()
setup_logging(config, "transition_app")
couch_settings = {"couch_uri": config["couch_uri"],
                  "couch_db": config["couch_db"]}

@app.route("/")
def hello():
    return """
    <html>
    <body>

    <h3>payloads list</h3>
    <p><a href="allpayloads">XML</a></p>

    <h3>receivers list</h3>
    <p><a href="receivers">JSON</a></p>

    <form action="payload_telemetry" method="POST">
    <h3>payload_telemetry</h3>
    <p>Callsign: <input type="text" name="callsign"></p>
    <p>
      String: <input type="text" name="string">
      <select name="string_type">
        <option>ascii-stripped</option>
        <option>ascii</option>
        <option>base64</option>
      </select>
    </p>
    <p>Metadata (json): <input type="text" name="metadata" value="{}"></p>
    <p>Time created (int, POSIX): <input type="text" name="time_created"></p>
    <p><input type="submit" value="GO">
    </form>

    <form action="listener_information" method="POST">
    <h3>listener_information</h3>
    <p>Callsign: <input type="text" name="callsign"></p>
    <p>Data (json): <input type="text" name="data" value="{}"></p>
    <p>Time created (int, POSIX): <input type="text" name="time_created"></p>
    <p><input type="submit" value="GO">
    </form>

    <form action="listener_telemetry" method="POST">
    <h3>listener_telemetry</h3>
    <p>Callsign: <input type="text" name="callsign"></p>
    <p>Data (json): <input type="text" name="data" value="{}"></p>
    <p>Time created (int, POSIX): <input type="text" name="time_created"></p>
    <p><input type="submit" value="GO">
    </form>

    </body>
    </html>
    """

def get_time_created():
    if "time_created" not in flask.request.form:
        return None

    time_created = flask.request.form["time_created"]
    if not time_created:
        return None

    return int(time_created)

@app.route("/payload_telemetry", methods=["POST"])
def payload_telemetry():
    callsign = flask.request.form["callsign"]
    string = flask.request.form["string"]
    string_type = flask.request.form["string_type"]
    metadata = json.loads(flask.request.form["metadata"])
    time_created = get_time_created()

    if string_type == "base64":
        string = base64.b64decode(string)
    elif string_type == "ascii" or string_type == "ascii-stripped":
        string = string.encode("utf8")

    if string_type == "ascii-stripped":
        string += "\n"

    assert callsign and string
    assert isinstance(metadata, dict)

    u = uploader.Uploader(callsign=callsign, **couch_settings)
    try:
        u.payload_telemetry(string, metadata, time_created)
    except uploader.UnmergeableError:
        app.logger.warning("Unmergeable: %s (%r)", callsign, string)

    return "OK"

@app.route("/listener_information", methods=["POST"])
def listener_information():
    callsign = flask.request.form["callsign"]
    data = json.loads(flask.request.form["data"])
    time_created = get_time_created()

    assert callsign and data
    assert isinstance(data, dict)

    u = uploader.Uploader(callsign=callsign, **couch_settings)
    u.listener_information(data, time_created)

    return "OK"

@app.route("/listener_telemetry", methods=["POST"])
def listener_telemetry():
    callsign = flask.request.form["callsign"]
    data = json.loads(flask.request.form["data"])
    time_created = get_time_created()

    assert callsign and data
    assert isinstance(data, dict)

    u = uploader.Uploader(callsign=callsign, **couch_settings)
    u.listener_telemetry(data, time_created)

    return "OK"

@app.route("/allpayloads")
def allpayloads():
    text = cache.get('allpayloads')
    if text is None:
        text = couch_to_xml.dump_xml(**couch_settings)
        cache.set('allpayloads', text)
    response = flask.make_response(text)
    set_expires(response, 60)
    return response

def set_expires(response, diff):
    expires = time.time() + diff
    expires = time.strftime("%a, %d %b %Y %H:%M:%S +0000",
                            time.gmtime(expires))

    response.headers["Expires"] = expires

HTML_DESCRIPTION = u"""
<font size="-2"><BR>
<B>Radio: </B>{radio_safe}<BR>
<B>Antenna: </B>{antenna_safe}<BR>
<B>Last Contact: </B>{tdiff_hours} hours ago<BR>
</font>
"""

def listener_map(callsign, data):
    try:
        info = data["information"]["data"]
        telemetry = data["telemetry"]["data"]

        tdiff = int(time.time()) - data["latest"]
        tdiff_hours = tdiff / 3600

        for key in ["radio", "antenna"]:
            if key not in info:
                info[key] = "Unknown"

        if "altitude" not in telemetry:
            telemetry["altitude"] = 0.0

        info["radio_safe"] = htmlescape(info["radio"])
        info["antenna_safe"] = htmlescape(info["antenna"])
        info["tdiff_hours"] = tdiff_hours

        return {
            "name": callsign,
            "lat": telemetry["latitude"],
            "lon": telemetry["longitude"],
            "alt": telemetry["altitude"],
            "description": HTML_DESCRIPTION.format(**info)
        }
    except KeyError:
        return None

def receivers_load(couch_db):
    listeners = {}

    yesterday = int(time.time() - (24 * 60 * 60))
    startkey = [yesterday, None]
    o = {"startkey": startkey}

    for doc_type in ["information", "telemetry"]:
        view_name = "listener_{0}/time_created_callsign".format(doc_type)
        view = couch_db.view(view_name, **o)

        for result in view:
            (time_uploaded, callsign) = result["key"]

            l = {doc_type: result["id"], "latest": time_uploaded}

            if callsign not in listeners:
                listeners[callsign] = l
            else:
                listeners[callsign].update(l)

    required_ids = {}
    remove_listeners = []
    for callsign in listeners:
        l = listeners[callsign]

        if not callsign or "chase" in callsign \
                or "information" not in l or "telemetry" not in l:
            remove_listeners.append(callsign)
        else:
            required_ids[listeners[callsign]["information"]] = callsign
            required_ids[listeners[callsign]["telemetry"]] = callsign

    for callsign in remove_listeners:
        del listeners[callsign]

    docs = couch_db.all_docs(keys=required_ids.keys(), include_docs=True)

    for result in docs:
        doc_id = result["id"]
        doc = result["doc"]

        callsign = required_ids[doc_id]
        if doc["type"] == "listener_information":
            listeners[callsign]["information"] = doc
        elif doc["type"] == "listener_telemetry":
            listeners[callsign]["telemetry"] = doc
        else:
            raise KeyError("type")

    return listeners

@app.route("/receivers")
def receivers():
    couch_server = couchdbkit.Server(couch_settings["couch_uri"])
    couch_db = couch_server[couch_settings["couch_db"]]

    listeners = receivers_load(couch_db)

    response_data = []
    for callsign in listeners:
        l = listener_map(callsign, listeners[callsign])
        if l is not None:
            response_data.append(l)

    response = flask.make_response(json.dumps(response_data))
    set_expires(response, 10 * 60)
    response.headers["Content-type"] = "application/json"
    return response
