#!/usr/bin/env python3
"""
GTekSD Movie Streamer
Lightweight local-network video streaming with HTTP byte-range, WebDAV, and DLNA/UPnP auto-discovery.

Copyright (C) 2026 GTekSD. All rights reserved.
"""

import argparse
import email.utils
import html
import logging
import mimetypes
import os
import platform
import re
import socket
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote, urlsplit

VERSION = "1.6"
DEFAULT_PORT = 8000
CHUNK_SIZE = 256 * 1024
DEFAULT_LOG_FILE = Path(__file__).resolve().parent / "movie_server.log"

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".m4v",
    ".webm", ".ts", ".m2ts", ".wmv", ".flv", ".mpg", ".mpeg",
}

CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
    TimeoutError,
)

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/mp2t", ".ts")
mimetypes.add_type("video/mp2t", ".m2ts")

logger = logging.getLogger("GTekSDMovieStreamer")


def setup_logging(log_file=DEFAULT_LOG_FILE, console_debug=False, disable_file=False):
    """Configure thread-safe console + rotating file logging for debugging."""
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if console_debug else logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%d/%b/%Y %H:%M:%S")
    )
    logger.addHandler(console_handler)

    if disable_file or not log_file:
        return None

    log_path = Path(log_file).expanduser().resolve()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s.%(msecs)03d [%(levelname)-7s] [%(threadName)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)
        return log_path
    except OSError as exc:
        logger.warning("Could not initialize log file (%s): %s", log_path, exc)
        return None


def _build_device_xml(device_uuid, friendly_name):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>
    <friendlyName>{html.escape(friendly_name)}</friendlyName>
    <manufacturer>GTekSD</manufacturer>
    <modelDescription>GTekSD Local Network Movie Streamer</modelDescription>
    <modelName>GTekSD Movie Streamer</modelName>
    <modelNumber>{VERSION}</modelNumber>
    <UDN>uuid:{device_uuid}</UDN>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:ContentDirectory:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:ContentDirectory</serviceId>
        <SCPDURL>/dlna/cds.xml</SCPDURL>
        <controlURL>/dlna/control/cds</controlURL>
        <eventSubURL>/dlna/event/cds</eventSubURL>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>
        <SCPDURL>/dlna/cms.xml</SCPDURL>
        <controlURL>/dlna/control/cms</controlURL>
        <eventSubURL>/dlna/event/cms</eventSubURL>
      </service>
    </serviceList>
  </device>
</root>
""".encode("utf-8")


CDS_SCPD_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <actionList>
    <action>
      <name>Browse</name>
      <argumentList>
        <argument><name>ObjectID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_ObjectID</relatedStateVariable></argument>
        <argument><name>BrowseFlag</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_BrowseFlag</relatedStateVariable></argument>
        <argument><name>Filter</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Filter</relatedStateVariable></argument>
        <argument><name>StartingIndex</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Index</relatedStateVariable></argument>
        <argument><name>RequestedCount</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>
        <argument><name>SortCriteria</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_SortCriteria</relatedStateVariable></argument>
        <argument><name>Result</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Result</relatedStateVariable></argument>
        <argument><name>NumberReturned</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>
        <argument><name>TotalMatches</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Count</relatedStateVariable></argument>
        <argument><name>UpdateID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_UpdateID</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action>
      <name>GetSearchCapabilities</name>
      <argumentList>
        <argument><name>SearchCaps</name><direction>out</direction><relatedStateVariable>SearchCapabilities</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action>
      <name>GetSortCapabilities</name>
      <argumentList>
        <argument><name>SortCaps</name><direction>out</direction><relatedStateVariable>SortCapabilities</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action>
      <name>GetSystemUpdateID</name>
      <argumentList>
        <argument><name>Id</name><direction>out</direction><relatedStateVariable>SystemUpdateID</relatedStateVariable></argument>
      </argumentList>
    </action>
  </actionList>
  <serviceStateTable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_ObjectID</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_BrowseFlag</name><dataType>string</dataType><allowedValueList><allowedValue>BrowseMetadata</allowedValue><allowedValue>BrowseDirectChildren</allowedValue></allowedValueList></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_Filter</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_Index</name><dataType>ui4</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_Count</name><dataType>ui4</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_SortCriteria</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_Result</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_UpdateID</name><dataType>ui4</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>SearchCapabilities</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>SortCapabilities</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="yes"><name>SystemUpdateID</name><dataType>ui4</dataType></stateVariable>
  </serviceStateTable>
</scpd>
"""

CMS_SCPD_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <actionList>
    <action>
      <name>GetProtocolInfo</name>
      <argumentList>
        <argument><name>Source</name><direction>out</direction><relatedStateVariable>SourceProtocolInfo</relatedStateVariable></argument>
        <argument><name>Sink</name><direction>out</direction><relatedStateVariable>SinkProtocolInfo</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action>
      <name>GetCurrentConnectionIDs</name>
      <argumentList>
        <argument><name>ConnectionIDs</name><direction>out</direction><relatedStateVariable>CurrentConnectionIDs</relatedStateVariable></argument>
      </argumentList>
    </action>
    <action>
      <name>GetCurrentConnectionInfo</name>
      <argumentList>
        <argument><name>ConnectionID</name><direction>in</direction><relatedStateVariable>A_ARG_TYPE_ConnectionID</relatedStateVariable></argument>
        <argument><name>RcsID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_RcsID</relatedStateVariable></argument>
        <argument><name>AVTransportID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_AVTransportID</relatedStateVariable></argument>
        <argument><name>ProtocolInfo</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ProtocolInfo</relatedStateVariable></argument>
        <argument><name>PeerConnectionManager</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ConnectionManager</relatedStateVariable></argument>
        <argument><name>PeerConnectionID</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ConnectionID</relatedStateVariable></argument>
        <argument><name>Direction</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_Direction</relatedStateVariable></argument>
        <argument><name>Status</name><direction>out</direction><relatedStateVariable>A_ARG_TYPE_ConnectionStatus</relatedStateVariable></argument>
      </argumentList>
    </action>
  </actionList>
  <serviceStateTable>
    <stateVariable sendEvents="yes"><name>SourceProtocolInfo</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="yes"><name>SinkProtocolInfo</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="yes"><name>CurrentConnectionIDs</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_ConnectionStatus</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_ConnectionManager</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_Direction</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_ProtocolInfo</name><dataType>string</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_ConnectionID</name><dataType>i4</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_RcsID</name><dataType>i4</dataType></stateVariable>
    <stateVariable sendEvents="no"><name>A_ARG_TYPE_AVTransportID</name><dataType>i4</dataType></stateVariable>
  </serviceStateTable>
</scpd>
"""


class SSDPAdvertiser(threading.Thread):
    """Broadcasts UPnP/DLNA presence so VLC and Smart TVs discover the server automatically."""

    SEARCH_TARGETS = (
        "upnp:rootdevice",
        "urn:schemas-upnp-org:device:MediaServer:1",
        "urn:schemas-upnp-org:service:ContentDirectory:1",
        "urn:schemas-upnp-org:service:ConnectionManager:1",
    )

    def __init__(self, lan_ip, http_port, device_uuid):
        super().__init__(name="SSDPAdvertiser", daemon=True)
        self.lan_ip = lan_ip
        self.http_port = http_port
        self.device_uuid = device_uuid
        self.location = f"http://{lan_ip}:{http_port}/dlna/device.xml"
        self.server_banner = (
            f"{platform.system()}/{platform.release()} UPnP/1.0 GTekSD-Movie-Streamer/{VERSION}"
        )
        self._stop_event = threading.Event()
        self._listen_sock = None

    def _service_pairs(self):
        usn_base = f"uuid:{self.device_uuid}"
        pairs = [(usn_base, usn_base)]
        for target in self.SEARCH_TARGETS:
            pairs.append((target, f"{usn_base}::{target}"))
        return pairs

    def _send_notify(self, nts="ssdp:alive"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.lan_ip))
            for nt, usn in self._service_pairs():
                if nts == "ssdp:alive":
                    msg = (
                        "NOTIFY * HTTP/1.1\r\n"
                        f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                        "CACHE-CONTROL: max-age=1800\r\n"
                        f"LOCATION: {self.location}\r\n"
                        f"NT: {nt}\r\n"
                        f"NTS: {nts}\r\n"
                        f"SERVER: {self.server_banner}\r\n"
                        f"USN: {usn}\r\n\r\n"
                    )
                else:
                    msg = (
                        "NOTIFY * HTTP/1.1\r\n"
                        f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
                        f"NT: {nt}\r\n"
                        f"NTS: {nts}\r\n"
                        f"USN: {usn}\r\n\r\n"
                    )
                sock.sendto(msg.encode("utf-8"), (SSDP_ADDR, SSDP_PORT))
        except OSError as exc:
            logger.debug("SSDP NOTIFY (%s) failed: %s", nts, exc)
        finally:
            sock.close()

    def _respond_msearch(self, st_header, client_addr):
        st = st_header.strip()
        matches = []
        if st == "ssdp:all":
            matches = self._service_pairs()
        else:
            for target, usn in self._service_pairs():
                if st.lower() == target.lower():
                    matches.append((target, usn))

        if not matches:
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            date_str = email.utils.formatdate(usegmt=True)
            for target, usn in matches:
                resp = (
                    "HTTP/1.1 200 OK\r\n"
                    "CACHE-CONTROL: max-age=1800\r\n"
                    f"DATE: {date_str}\r\n"
                    "EXT:\r\n"
                    f"LOCATION: {self.location}\r\n"
                    f"SERVER: {self.server_banner}\r\n"
                    f"ST: {target}\r\n"
                    f"USN: {usn}\r\n\r\n"
                )
                sock.sendto(resp.encode("utf-8"), client_addr)
            logger.debug("SSDP M-SEARCH (%s) answered -> %s:%d", st, client_addr[0], client_addr[1])
        except OSError as exc:
            logger.debug("SSDP M-SEARCH reply failed: %s", exc)
        finally:
            sock.close()

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", SSDP_PORT))
            mreq = socket.inet_aton(SSDP_ADDR) + socket.inet_aton(self.lan_ip)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.settimeout(1.0)
            self._listen_sock = sock
            logger.debug("SSDP listener bound on %s:%d (interface %s)", SSDP_ADDR, SSDP_PORT, self.lan_ip)
        except OSError as exc:
            logger.warning("DLNA auto-discovery (UDP 1900) unavailable: %s", exc)
            return

        self._send_notify("ssdp:alive")
        last_announce = time.monotonic()

        while not self._stop_event.is_set():
            if time.monotonic() - last_announce >= 45.0:
                self._send_notify("ssdp:alive")
                last_announce = time.monotonic()

            try:
                data, addr = self._listen_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            text = data.decode("utf-8", errors="ignore")
            if not text.startswith("M-SEARCH"):
                continue

            st_match = re.search(r"^ST:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
            if st_match:
                self._respond_msearch(st_match.group(1), addr)

    def stop(self):
        self._stop_event.set()
        self._send_notify("ssdp:byebye")
        if self._listen_sock:
            try:
                self._listen_sock.close()
            except OSError:
                pass


class MovieHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"GTekSD-Movie-Streamer/{VERSION}"

    def __init__(self, *args, directory=None, device_uuid=None, friendly_name=None, **kwargs):
        self.share_root = Path(directory or os.getcwd()).resolve()
        self.device_uuid = device_uuid or str(uuid.uuid4())
        self.friendly_name = friendly_name or "GTekSD Movie Streamer"
        self._range_length = None
        super().__init__(*args, directory=str(self.share_root), **kwargs)

    def _client_tag(self):
        try:
            host, port = self.client_address[:2]
            return f"{host}:{port}"
        except Exception:
            return self.address_string()

    def _base_url(self):
        host = (
            self.headers.get("Host")
            or f"{self.server.server_address[0]}:{self.server.server_address[1]}"
        )
        return f"http://{host}"

    def handle(self):
        try:
            super().handle()
        except CLIENT_DISCONNECT_ERRORS as exc:
            self.close_connection = True
            logger.debug("%s - Client closed connection (%s)", self._client_tag(), type(exc).__name__)

    def finish(self):
        try:
            super().finish()
        except CLIENT_DISCONNECT_ERRORS:
            pass

    def parse_request(self):
        ok = super().parse_request()
        if ok:
            logger.debug(
                "%s - REQ %s %s | Range=%r | SOAP=%r | UA=%r",
                self._client_tag(),
                self.command,
                self.path,
                self.headers.get("Range"),
                self.headers.get("SOAPACTION"),
                self.headers.get("User-Agent"),
            )
        return ok

    def _send_bytes(self, body, content_type, status=200, head_only=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)
        return None

    def _resolve_dlna_object(self, object_id):
        """Map DLNA ObjectID ('0' for root, or relative POSIX path) to a safe Path."""
        if not object_id or object_id == "0":
            return self.share_root
        rel = Path(*[part for part in object_id.split("/") if part not in ("", ".")])
        candidate = (self.share_root / rel).resolve()
        try:
            candidate.relative_to(self.share_root)
        except ValueError:
            return None
        return candidate if candidate.exists() else None

    def _build_didl_xml(self, target_path, object_id, browse_flag, start_idx, req_count):
        base_url = self._base_url()
        parent_id = "0"
        if target_path != self.share_root:
            parent_rel = target_path.parent.relative_to(self.share_root).as_posix()
            parent_id = "0" if parent_rel == "." else parent_rel

        items = []
        if browse_flag == "BrowseMetadata":
            items = [target_path]
        elif target_path.is_dir():
            try:
                children = sorted(
                    target_path.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
                for child in children:
                    if child.is_dir():
                        items.append(child)
                    elif child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
                        items.append(child)
            except OSError:
                items = []

        total_matches = len(items)
        sliced = items[start_idx:start_idx + req_count] if req_count > 0 else items[start_idx:]

        didl = [
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        ]

        for entry in sliced:
            if entry == self.share_root:
                eid = "0"
                title = self.friendly_name
                pid = "-1"
            else:
                rel_posix = entry.relative_to(self.share_root).as_posix()
                eid = rel_posix
                title = entry.name
                pid = object_id if browse_flag != "BrowseMetadata" else parent_id

            if entry.is_dir():
                didl.append(
                    f'<container id="{html.escape(eid)}" parentID="{html.escape(pid)}" restricted="1">'
                    f'<dc:title>{html.escape(title)}</dc:title>'
                    f'<upnp:class>object.container.storageFolder</upnp:class>'
                    f'</container>'
                )
            else:
                try:
                    size = entry.stat().st_size
                except OSError:
                    continue
                mime = self.guess_type(str(entry))
                rel_posix = entry.relative_to(self.share_root).as_posix()
                encoded_url = f"{base_url}/" + "/".join(quote(p) for p in rel_posix.split("/"))
                proto = f"http-get:*:{mime}:DLNA.ORG_OP=01;DLNA.ORG_CI=0"
                didl.append(
                    f'<item id="{html.escape(eid)}" parentID="{html.escape(pid)}" restricted="1">'
                    f'<dc:title>{html.escape(title)}</dc:title>'
                    f'<upnp:class>object.item.videoItem</upnp:class>'
                    f'<res protocolInfo="{html.escape(proto)}" size="{size}">{html.escape(encoded_url)}</res>'
                    f'</item>'
                )

        didl.append("</DIDL-Lite>")
        return "".join(didl), len(sliced), total_matches

    def do_POST(self):
        """Handle UPnP/DLNA SOAP requests from VLC, Smart TVs, and media players."""
        req_path = urlsplit(self.path).path
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
        soap_action = (self.headers.get("SOAPACTION") or "").strip('"')

        if req_path == "/dlna/control/cds":
            if soap_action.endswith("#Browse"):
                object_id = "0"
                browse_flag = "BrowseDirectChildren"
                start_idx = 0
                req_count = 0
                try:
                    root = ET.fromstring(raw_body)
                    for elem in root.iter():
                        tag = elem.tag.split("}")[-1]
                        if tag == "ObjectID" and elem.text is not None:
                            object_id = elem.text.strip()
                        elif tag == "BrowseFlag" and elem.text:
                            browse_flag = elem.text.strip()
                        elif tag == "StartingIndex" and elem.text:
                            start_idx = max(0, int(elem.text.strip()))
                        elif tag == "RequestedCount" and elem.text:
                            req_count = max(0, int(elem.text.strip()))
                except (ET.ParseError, ValueError):
                    pass

                target = self._resolve_dlna_object(object_id)
                if target is None:
                    self.send_error(404, "DLNA ObjectID not found")
                    return

                didl_xml, returned, total = self._build_didl_xml(
                    target, object_id, browse_flag, start_idx, req_count
                )
                soap_resp = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <Result>{html.escape(didl_xml)}</Result>
      <NumberReturned>{returned}</NumberReturned>
      <TotalMatches>{total}</TotalMatches>
      <UpdateID>1</UpdateID>
    </u:BrowseResponse>
  </s:Body>
</s:Envelope>""".encode("utf-8")
                logger.debug(
                    "%s - DLNA Browse | ObjectID=%r | Flag=%s | Returned=%d/%d",
                    self._client_tag(), object_id, browse_flag, returned, total
                )
                self._send_bytes(soap_resp, 'text/xml; charset="utf-8"')
                return

            if soap_action.endswith("#GetSystemUpdateID"):
                soap_resp = b"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:GetSystemUpdateIDResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <Id>1</Id>
    </u:GetSystemUpdateIDResponse>
  </s:Body>
</s:Envelope>"""
                self._send_bytes(soap_resp, 'text/xml; charset="utf-8"')
                return

            if soap_action.endswith("#GetSearchCapabilities") or soap_action.endswith("#GetSortCapabilities"):
                tag = "GetSearchCapabilitiesResponse" if "Search" in soap_action else "GetSortCapabilitiesResponse"
                cap = "SearchCaps" if "Search" in soap_action else "SortCaps"
                soap_resp = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:{tag} xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <{cap}></{cap}>
    </u:{tag}>
  </s:Body>
</s:Envelope>""".encode("utf-8")
                self._send_bytes(soap_resp, 'text/xml; charset="utf-8"')
                return

        if req_path == "/dlna/control/cms" and soap_action.endswith("#GetProtocolInfo"):
            sources = ",".join(
                f"http-get:*:{m}:*"
                for m in (
                    "video/x-matroska", "video/mp4", "video/x-msvideo",
                    "video/quicktime", "video/webm", "video/mp2t", "video/*",
                )
            )
            soap_resp = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:GetProtocolInfoResponse xmlns:u="urn:schemas-upnp-org:service:ConnectionManager:1">
      <Source>{sources}</Source>
      <Sink></Sink>
    </u:GetProtocolInfoResponse>
  </s:Body>
</s:Envelope>""".encode("utf-8")
            self._send_bytes(soap_resp, 'text/xml; charset="utf-8"')
            return

        self.send_error(404, "Unsupported action")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS, PROPFIND")
        self.send_header("DAV", "1")
        self.send_header("MS-Author-Via", "DAV")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PROPFIND(self):
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        if content_length > 0:
            self.rfile.read(content_length)

        target = self._safe_target_path()
        if target is None:
            self.send_error(404, "Not found")
            return

        depth = self.headers.get("Depth", "1").strip()
        req_path = urlsplit(self.path).path or "/"
        if target.is_dir() and not req_path.endswith("/"):
            req_path += "/"

        entries = [target]
        if target.is_dir() and depth != "0":
            try:
                children = sorted(
                    target.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
                entries.extend(children)
            except OSError:
                self.send_error(403, "Forbidden")
                return

        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<D:multistatus xmlns:D="DAV:">',
        ]
        for entry in entries:
            try:
                st = entry.stat()
            except OSError:
                continue

            is_dir = entry.is_dir()
            if entry == target:
                href = req_path
                display_name = "/" if req_path == "/" else entry.name
            else:
                encoded_name = quote(entry.name)
                href = f"{req_path}{encoded_name}{'/' if is_dir else ''}"
                display_name = entry.name

            last_mod = email.utils.formatdate(st.st_mtime, usegmt=True)
            lines.append("  <D:response>")
            lines.append(f"    <D:href>{html.escape(href)}</D:href>")
            lines.append("    <D:propstat>")
            lines.append("      <D:prop>")
            lines.append(f"        <D:displayname>{html.escape(display_name)}</D:displayname>")
            if is_dir:
                lines.append("        <D:resourcetype><D:collection/></D:resourcetype>")
            else:
                ctype = self.guess_type(str(entry))
                lines.append("        <D:resourcetype/>")
                lines.append(f"        <D:getcontentlength>{st.st_size}</D:getcontentlength>")
                lines.append(f"        <D:getcontenttype>{html.escape(ctype)}</D:getcontenttype>")
            lines.append(f"        <D:getlastmodified>{last_mod}</D:getlastmodified>")
            lines.append("      </D:prop>")
            lines.append("      <D:status>HTTP/1.1 200 OK</D:status>")
            lines.append("    </D:propstat>")
            lines.append("  </D:response>")

        lines.append("</D:multistatus>")
        body = "\n".join(lines).encode("utf-8")
        self._send_bytes(body, 'application/xml; charset="utf-8"', status=207)

    def _safe_target_path(self):
        raw_path = urlsplit(self.path).path
        translated = Path(self.translate_path(raw_path))
        try:
            resolved = translated.resolve(strict=True)
            resolved.relative_to(self.share_root)
        except (OSError, ValueError, RuntimeError):
            return None
        return resolved

    def _safe_file_path(self):
        resolved = self._safe_target_path()
        return resolved if (resolved and resolved.is_file()) else None

    def _file_etag(self, path, stat_result):
        token = f"{stat_result.st_size:x}-{stat_result.st_mtime_ns:x}"
        return f'"{token}"'

    def _not_modified(self, etag, mtime):
        if_none_match = self.headers.get("If-None-Match")
        if if_none_match:
            return if_none_match.strip() == etag or if_none_match.strip() == "*"
        if_modified_since = self.headers.get("If-Modified-Since")
        if if_modified_since:
            try:
                since = email.utils.parsedate_to_datetime(if_modified_since)
                modified = email.utils.parsedate_to_datetime(
                    email.utils.formatdate(mtime, usegmt=True)
                )
                return modified <= since
            except (TypeError, ValueError, OverflowError):
                pass
        return False

    def _send_range_error(self, file_size):
        self.send_response(416, "Range Not Satisfiable")
        self.send_header("Content-Range", f"bytes */{file_size}")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return None

    def _serve_m3u_playlist(self, head_only=False):
        base_url = self._base_url()
        videos = sorted(
            (
                p for p in self.share_root.rglob("*")
                if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
            ),
            key=lambda p: p.relative_to(self.share_root).as_posix().lower(),
        )
        lines = ["#EXTM3U"]
        for video in videos:
            rel_posix = video.relative_to(self.share_root).as_posix()
            encoded_rel = "/".join(quote(part) for part in rel_posix.split("/"))
            lines.append(f"#EXTINF:-1,{rel_posix}")
            lines.append(f"{base_url}/{encoded_rel}")
        body = ("\n".join(lines) + "\n").encode("utf-8")
        return self._send_bytes(body, "audio/x-mpegurl; charset=utf-8", head_only=head_only)

    def send_head(self):
        self._range_length = None
        req_path = urlsplit(self.path).path
        head_only = self.command == "HEAD"

        if req_path == "/dlna/device.xml":
            return self._send_bytes(
                _build_device_xml(self.device_uuid, self.friendly_name),
                'text/xml; charset="utf-8"',
                head_only=head_only,
            )
        if req_path == "/dlna/cds.xml":
            return self._send_bytes(CDS_SCPD_XML, 'text/xml; charset="utf-8"', head_only=head_only)
        if req_path == "/dlna/cms.xml":
            return self._send_bytes(CMS_SCPD_XML, 'text/xml; charset="utf-8"', head_only=head_only)
        if req_path == "/playlist.m3u":
            return self._serve_m3u_playlist(head_only=head_only)

        path = self._safe_file_path()
        if path is None:
            resolved = self._safe_target_path()
            if resolved is not None and resolved.is_dir():
                return super().send_head()
            self.send_error(404, "File not found")
            return None

        try:
            stat_result = path.stat()
            file_size = stat_result.st_size
            mtime = stat_result.st_mtime
            etag = self._file_etag(path, stat_result)

            if self._not_modified(etag, mtime):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", email.utils.formatdate(mtime, usegmt=True))
                self.end_headers()
                return None

            start = 0
            end = file_size - 1
            status = 200
            range_header = self.headers.get("Range")

            if range_header:
                if_range = self.headers.get("If-Range")
                if if_range and if_range != etag:
                    try:
                        date = email.utils.parsedate_to_datetime(if_range)
                        modified = email.utils.parsedate_to_datetime(
                            email.utils.formatdate(mtime, usegmt=True)
                        )
                        if modified > date:
                            range_header = None
                    except (TypeError, ValueError, OverflowError):
                        range_header = None

            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match or file_size == 0:
                    return self._send_range_error(file_size)

                first, last = match.groups()
                if first:
                    start = int(first)
                    end = int(last) if last else file_size - 1
                elif last:
                    suffix_length = int(last)
                    if suffix_length == 0:
                        return self._send_range_error(file_size)
                    start = max(0, file_size - suffix_length)
                else:
                    return self._send_range_error(file_size)

                if start >= file_size or start > end:
                    return self._send_range_error(file_size)

                end = min(end, file_size - 1)
                status = 206

            content_length = max(0, end - start + 1)
            ctype = self.guess_type(str(path))
            file_obj = path.open("rb")
            try:
                file_obj.seek(start)
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(content_length))
                self.send_header("ETag", etag)
                self.send_header("Last-Modified", email.utils.formatdate(mtime, usegmt=True))
                self.send_header("Cache-Control", "no-cache")
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.end_headers()
            except Exception:
                file_obj.close()
                raise

            self._range_length = content_length
            return file_obj

        except OSError:
            self.send_error(404, "File not found")
            return None

    def copyfile(self, source, outputfile):
        remaining = self._range_length
        try:
            while remaining is None or remaining > 0:
                amount = CHUNK_SIZE if remaining is None else min(CHUNK_SIZE, remaining)
                data = source.read(amount)
                if not data:
                    break
                outputfile.write(data)
                if remaining is not None:
                    remaining -= len(data)
        except (*CLIENT_DISCONNECT_ERRORS, OSError):
            self.close_connection = True

    def log_message(self, fmt, *args):
        logger.info("%s - %s", self._client_tag(), fmt % args)

    def log_error(self, fmt, *args):
        msg = fmt % args
        # Media players probe missing subtitle files (.srt/.vtt/.ass); log 404s at DEBUG only.
        if "404" in msg:
            logger.debug("%s - %s", self._client_tag(), msg)
        else:
            logger.warning("%s - ERROR: %s", self._client_tag(), msg)


class MovieHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        client_tag = f"{client_address[0]}:{client_address[1]}" if client_address else "unknown"
        if isinstance(exc, CLIENT_DISCONNECT_ERRORS):
            return
        logger.exception("%s - Unhandled exception while processing request", client_tag)


def _is_virtual_or_link_local(ip):
    return (
        ip.startswith("127.")
        or ip.startswith("169.254.")
        or ip.startswith("192.168.56.")
    )


def get_local_addresses():
    primary_ip = None
    for probe_target in (("8.8.8.8", 80), ("192.0.2.1", 80)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(probe_target)
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                primary_ip = ip
                break
        except OSError:
            pass
        finally:
            sock.close()

    other_ips = set()
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if not _is_virtual_or_link_local(ip) and ip != primary_ip:
                other_ips.add(ip)
    except OSError:
        pass

    ordered = []
    if primary_ip:
        ordered.append(primary_ip)
    ordered.extend(sorted(other_ips))
    return ordered


def print_startup_banner(root, port, addresses, friendly_name, log_path):
    lan_ip = addresses[0] if addresses else "<YOUR_PC_IP>"
    base_url = f"http://{lan_ip}:{port}"

    print()
    print(r"                              /##                            ")
    print(r"  /#######  #########         ###         /######  ########\ ")
    print(r" ###           ###    /####\  ###  /##/  ###        /#   ### ")
    print(r" ###  /###     ###   ###/##/  ###/###/   \######\  ###   ### ")
    print(r" ###    ##     ###   ###      ###   ##\       ###  ###   ### ")
    print(r" \#####/##     ###   \######  ###   ###  ######/   ##./####/ ")
    print(r"                                                             ")
    print(f"                    MOVIE STREAMER v{VERSION}")
    print("  Breaking things so you don't have to find out the hard way 🔓")
    print("=" * 78)
    print(f"[+] Shared folder      : {root}")
    print(f"[+] Server domain/ IP  : {lan_ip}")
    print(f"[+] Port               : {port}")
    print(f"[+] DLNA / UPnP Name   : {friendly_name}")
    print(f"[+] Debug log          : {log_path if log_path else 'Disabled'}")
    print("-" * 78)
    print("[+] Android / Android TV (UPnP — Password less):")
    print(f" |  VLC          : Browse > Local Network -> '{friendly_name}'")
    print(f" |  KMPlayer     : Network > Auto-discovered UPnP -> '{friendly_name}'")
    print(f" |  NOVA Player  : Network & Files > Network > Media server (UPnP) -> '{friendly_name}'")
    print()
    print("[+] iOS (iPhone / iPad):")
    print(f" |  KMPlayer     : Network > Add (+) > WEBDAV (IP: {lan_ip}, Port: {port})")
    print(f" |  KMPlayer     : URL Playback -> {base_url}/playlist.m3u")
    print(f" |  VLC          : Browse > Open Network Stream -> {base_url}/playlist.m3u")
    print()
    print("[+] Browser / Direct URL (Any Device):")
    print(f" |  Folder View  : {base_url}/")
    print(f" |  Single File  : {base_url}/(movie_name.mkv)")
    if not addresses:
        print()
        print("[!] Could not detect a LAN IP automatically. Run 'ipconfig' to find your IPv4 address.")
    print("-" * 78)
    print("[!] Only share folders you are comfortable exposing to your LAN.")
    print("[!] Keep this window open while streaming. Press CTRL+C to stop.")
    print("=" * 78)
    print()

def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="GTekSD Movie Streamer: stream local files to devices on your LAN."
    )
    parser.add_argument(
        "folder", nargs="?", default=".",
        help="Folder to share (default: current directory)."
    )
    parser.add_argument(
        "-p", "--port", type=int, default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})."
    )
    parser.add_argument(
        "--log-file", default=str(DEFAULT_LOG_FILE),
        help=f"Path to debug log file (default: {DEFAULT_LOG_FILE})."
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Also print verbose debug logs to the console."
    )
    parser.add_argument(
        "--no-log", action="store_true",
        help="Disable writing debug logs to a file."
    )
    args = parser.parse_args()

    log_path = setup_logging(
        log_file=args.log_file,
        console_debug=args.debug,
        disable_file=args.no_log,
    )

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Folder does not exist or is not a directory: {root}")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")

    hostname = socket.gethostname()
    friendly_name = f"GTekSD Movie Streamer ({hostname})"
    device_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"gteksd-movie-streamer:{hostname}:{root}"))

    handler = partial(
        MovieHandler,
        directory=str(root),
        device_uuid=device_uuid,
        friendly_name=friendly_name,
    )

    try:
        server = MovieHTTPServer(("0.0.0.0", args.port), handler)
    except OSError as exc:
        raise SystemExit(
            f"[!] Could not start server on port {args.port}: {exc}\n"
            "    Try another port or check whether the port is already in use."
        )

    addresses = get_local_addresses()
    ssdp = None
    if addresses:
        ssdp = SSDPAdvertiser(addresses[0], args.port, device_uuid)
        ssdp.start()

    print_startup_banner(root, args.port, addresses, friendly_name, log_path)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping GTekSD Movie Streamer...")
    finally:
        if ssdp:
            ssdp.stop()
        server.server_close()
        logger.info("Server stopped.")


if __name__ == "__main__":
    main()
