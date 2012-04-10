#!/usr/bin/env python
# Copyright 2011 (C) Adam Greig
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
Read in an XML payload configuration doc and upload it to CouchDB as a sandbox
flight document, used to aid transition from the old dl system to habitat.
"""

import sys
if len(sys.argv) != 4:
    n = sys.argv[0]
    print "Usage: {0} <payload xml file> <couch URI> <couch db>".format(n)
    sys.exit(1)

import couchdbkit
import os.path
import time
import pprint
import elementtree.ElementTree as ET
from xml.parsers.expat import ExpatError

try:
    tree = ET.parse(sys.argv[1])
except (IOError, ExpatError, AttributeError) as e:
    print "Could not parse XML: {0}".format(e)
    sys.exit(1)

callsign = tree.findtext("sentence/callsign")
if not callsign:
    print "Could not find a callsign in the document."
    sys.exit(1)

frequency = tree.findtext("frequency", default="434.075.000")
frequency = '.'.join(frequency.split('.')[0:2])
mode = tree.findtext("mode", default="usb").upper()
shift = int(tree.findtext("txtype/rtty/shift", default="300"))
encoding = tree.findtext("txtype/rtty/coding", default="ascii-8")
baud = int(tree.findtext("txtype/rtty/baud", default="50"))
parity = tree.findtext("txtype/rtty/parity", default="none")
stop = float(tree.findtext("txtype/rtty/stop", default="1"))

doc = {
    "type": "flight",
    "name": os.path.basename(sys.argv[1]).split(".")[0],
    "start": int(time.time()),
    "end": "sandbox",
    "metadata": {
        "imported_from_xml": True
    },
    "payloads": {
        callsign : {
            "radio": {
                "frequency": frequency,
                "mode": mode
            },
            "telemetry": {
                "modulation": "rtty",
                "shift": shift,
                "encoding": encoding,
                "baud": baud,
                "parity": parity,
                "stop": stop
            },
            "sentence": {
                "protocol": "UKHAS",
                "checksum": "crc16-ccitt",
                "payload": callsign,
                "fields": []
            }
        }
    }
}

type_map = {
    "fixed": "base.ascii_float",
    "char": "base.ascii_string",
    "integer": "base.ascii_int",
    "time": "stdtelem.time",
    "decimal": "base.ascii_float",
    "custom": "base.ascii_string",
    "custom_data": "base.string"
}

server = couchdbkit.Server(sys.argv[2])
db = server[sys.argv[3]]

for field in tree.getiterator("field"):
    if field.findtext("dbfield") == "callsign":
        continue

    new_field = {
        "name": field.findtext("dbfield"),
        "type": type_map.get(field.findtext("datatype"), "base.ascii_string")
    }
    
    if new_field["name"] == "cycle_count":
        new_field["name"] = "count"

    if field.findtext("dbfield") in ("latitude", "longitude"):
        if field.findtext("format"):
            new_field["format"] = field.findtext("format")

            if new_field["format"] == "dddmm.mm":
                new_field["format"] = "ddmm.mm"
        else:
            new_field["format"] = "dd.dddd"
        new_field["type"] = "stdtelem.coordinate"

    doc["payloads"][callsign]["sentence"]["fields"].append(new_field)

print "Saving document:"
pprint.pprint(doc)
db.save_doc(doc)
