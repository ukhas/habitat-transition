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
Connect to CouchDB, read in all the payload configs using payload_config \
view, then output them as XML documents ready for dl-fldigi.
"""

import sys
import couchdbkit
import subprocess
import elementtree.ElementTree as ET
import xml.dom.minidom

def main():
    if len(sys.argv) != 3:
        print "Usage: {0} <couch uri> <couch db>".format(sys.argv[0])
        sys.exit(0)
    try:
        print dump_xml(sys.argv[1], sys.argv[2])
    except Exception as e:
        print "Error getting XML, stopping: {0}: {1}".format(type(e), e)

def dump_xml(couch_uri, couch_db):
    payloads = get_payloads(couch_uri, couch_db)
    root = PayloadsXML()
    for payload in sorted(payloads.keys(), key=lambda x: x.upper()):
        try:
            root.add_payload(payload, payloads[payload])
        except Exception as e:
            print "Error occured processing a payload: {0}: {1}".format(
                type(e), e)
            print "Continuing..."
            continue
    return str(root)

def get_payloads(couch_uri, couch_db):
    server = couchdbkit.Server(couch_uri)
    db = server[couch_db]
    results = db.view("habitat/payload_config", include_docs=True)
    payloads = {}
    # payload_config will be sorted, newest last. New docs will therefore
    # overwrite:
    for result in results:
        payload = result["key"][0]
        payloads[payload] = result["doc"]["payloads"][payload]
    return payloads

class PayloadsXML(object):
    def __init__(self):
        self.tree = ET.Element("payloads")

    def add_payload(self, callsign, config):
        payload = PayloadXML(callsign, config)
        self.tree.append(payload.get_xml())

    def __str__(self):
        string = ET.tostring(self.tree, "utf-8")
        reparsed = xml.dom.minidom.parseString(string)
        xml_string = reparsed.toxml("utf-8")
        p = subprocess.Popen(("tidy", "-xml", "-indent", "-quiet"),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        p.stdin.write(xml_string)
        p.stdin.close()
        return p.stdout.read()

class PayloadXML(object):
    type_map = {
        "stdtelem.time": "time",
        "stdtelem.coordinate": "decimal",
        "base.ascii_int": "integer",
        "base.ascii_float": "decimal",
        "base.string": "char"
    }
    def __init__(self, callsign, config):
        self.callsign = callsign
        self.payload = config
        self.tree = ET.Element("payload")

        name = ET.SubElement(self.tree, 'name')
        name.text = str(self.callsign)

        self.transmission = ET.SubElement(self.tree, 'transmission')
        self._add_basic()
        self._add_txtype()
        self._add_sentence()

    def _add_basic(self):
        frequency = ET.SubElement(self.transmission, 'frequency')
        frequency.text = str(self.payload["radio"]["frequency"])

        mode = ET.SubElement(self.transmission, 'mode')
        mode.text = str(self.payload["radio"]["mode"])

        timings = ET.SubElement(self.transmission, 'timings')
        timings.text = "continuous"

    def _add_txtype(self):
        dominoex_settings = None

        if isinstance(self.payload["telemetry"], list):
            for settings in self.payload["telemetry"]:
                if settings["modulation"] == "rtty":
                    rtty_settings = settings
                elif settings["modulation"] == "dominoex":
                    dominoex_settings = settings
        else:
            rtty_settings = self.payload["telemetry"]

        txtype = ET.SubElement(self.transmission, 'txtype')

        if dominoex_settings:
            dominoex = ET.SubElement(txtype, 'dominoex')
            dominoex.text = str(dominoex_settings["type"])

        rtty = ET.SubElement(txtype, 'rtty')
        shift = ET.SubElement(rtty, 'shift')
        coding = ET.SubElement(rtty, 'coding')
        baud = ET.SubElement(rtty, 'baud')
        parity = ET.SubElement(rtty, 'parity')
        stop = ET.SubElement(rtty, 'stop')

        shift.text = str(rtty_settings.get("shift", 300))
        coding.text = str(rtty_settings.get("encoding", "ascii-8"))
        baud.text = str(rtty_settings.get("baud", 50))
        parity.text = str(rtty_settings.get("parity", "none"))
        payload_stop = float(rtty_settings.get("stop", "1"))
        # dl-fldigi requires exactly '1', '1.5' or '2'.
        if payload_stop == 1.0:
            stop.text = "1"
        elif payload_stop == 1.5:
            stop.text = "1.5"
        elif payload_stop == 2.0:
            stop.text = "2"
        else:
            stop.text = "1"

    def _add_sentence(self):
        self.sentence = ET.SubElement(self.transmission, 'sentence')
        s_delimiter = ET.SubElement(self.sentence, 'sentence_delimiter')
        s_delimiter.text = "$$"
        f_delimiter = ET.SubElement(self.sentence, 'field_delimiter')
        f_delimiter.text = ","
        callsign = ET.SubElement(self.sentence, 'callsign')
        callsign.text = str(self.callsign)
        fields = ET.SubElement(self.sentence, 'fields')
        fields.text = str(len(self.payload["sentence"]["fields"]) + 1)

        cl = len(self.callsign)
        self._add_field(seq=1, dbfield="callsign", minsize=cl, maxsize=cl,
            datatype="char")

        seq = 2
        for field in self.payload["sentence"]["fields"]:
            if field["sensor"] == "stdtelem.coordinate":
                data_format = field["format"]
            else:
                data_format = None
            self._add_field(seq=seq, dbfield=field["name"], minsize=0,
                maxsize=999, datatype=self.type_map[field["sensor"]],
                format=data_format)
            seq += 1

    def _add_field(self, **kwargs):
        field = ET.SubElement(self.sentence, 'field')
        for key, value in kwargs.iteritems():
            if value:
                node = ET.SubElement(field, key)
                node.text = str(value)

    def get_xml(self):
        return self.tree

if __name__ == "__main__":
    main()
