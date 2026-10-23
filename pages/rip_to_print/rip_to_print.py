import socket
import os
import time
import threading
from pathlib import Path
from queue import Queue, Empty
from collections import deque
import logging
import re
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Simple timing context for consistent step duration logging
class StepTimer:
    def __init__(self, label: str):
        self.label = label
        self._start = None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = time.perf_counter() - self._start
        logger.info(f"[TIMING] {self.label}: {elapsed:.3f} s")


def show_batch_size_recommendation_dialog(parent, analysis):
    """
    Show batch size recommendation dialog based on folder analysis

    Args:
        parent: Parent widget for the dialog
        analysis: Dictionary from analyze_folder_and_recommend_batch_size()

    Returns:
        str: 'recommended', 'continue', or 'cancel'
    """
    from PySide6.QtWidgets import QMessageBox, QPushButton
    from PySide6.QtCore import Qt

    if not analysis or analysis.get('total_pages', 0) == 0:
        return 'continue'  # No analysis available, proceed

    # Extract data
    total_pages = analysis.get('total_pages', 0)
    total_size_mb = analysis.get('total_size_mb', 0)
    avg_page_mb = analysis.get('avg_page_size_mb', 0)
    min_page_mb = analysis.get('min_page_size_mb', 0)
    max_page_mb = analysis.get('max_page_size_mb', 0)
    min_planes = analysis.get('min_planes', 0)
    max_planes = analysis.get('max_planes', 0)
    current_batch = analysis.get('current_batch_size', 0)
    recommended_batch = analysis.get('recommended_batch_size', 0)
    risk_level = analysis.get('risk_level', 'Low')
    risk_message = analysis.get('risk_message', '')
    pmb_capacity = analysis.get('pmb_capacity_mb', 95)

    # Safety check: Don't show dialog if there's no current batch size to compare
    if current_batch is None or current_batch == 0:
        return 'continue'  # No meaningful current batch to compare against

    # Determine if we should show the dialog
    # Only show if there's a significant difference or risk
    if risk_level == 'Low' and abs(current_batch - recommended_batch) < 10:
        return 'continue'  # Settings are fine, no need to bother user

    # Create custom message box
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("📊 Batch Size Recommendation")
    msg_box.setIcon(QMessageBox.Information)

    # Risk level emoji
    risk_emoji = {
        'Low': '✅',
        'Medium': '⚠️',
        'High': '🚨'
    }.get(risk_level, '❓')

    # Build detailed message
    message = f"""
<h3>Folder Analysis Complete</h3>

<b>📁 Folder Statistics:</b>
<table>
<tr><td>• Total pages:</td><td><b>{total_pages}</b></td></tr>
<tr><td>• Total size:</td><td><b>{total_size_mb:.1f} MB</b></td></tr>
<tr><td>• Average page size:</td><td><b>{avg_page_mb:.2f} MB</b></td></tr>
<tr><td>• Page size range:</td><td><b>{min_page_mb:.2f} - {max_page_mb:.2f} MB</b></td></tr>
<tr><td>• Color planes:</td><td><b>{min_planes} - {max_planes} planes per page</b></td></tr>
</table>

<b>⚙️ Current Settings:</b>
<table>
<tr><td>• Your batch size:</td><td><b>{current_batch} pages</b></td></tr>
<tr><td>• Pipeline size:</td><td><b>{current_batch * 2} pages (2× batch)</b></td></tr>
<tr><td>• PMB capacity:</td><td><b>{pmb_capacity:.0f} MB</b></td></tr>
<tr><td>• Risk level:</td><td><b>{risk_emoji} {risk_level}</b></td></tr>
<tr><td>• Risk:</td><td><b>{risk_message}</b></td></tr>
</table>

<b>💡 Recommendation:</b>
<table>
<tr><td>• Optimal batch size:</td><td><b style='color: #28a745;'>{recommended_batch} pages</b></td></tr>
<tr><td>• Benefit:</td><td><b>Safe, fast printing - prevents buffer overflow</b></td></tr>
</table>
"""

    msg_box.setText(message)
    msg_box.setTextFormat(Qt.RichText)

    # Add custom buttons
    use_recommended_btn = msg_box.addButton(f"Use Recommended ({recommended_batch})", QMessageBox.AcceptRole)
    continue_btn = msg_box.addButton(f"Continue with {current_batch}", QMessageBox.RejectRole)
    cancel_btn = msg_box.addButton("Cancel", QMessageBox.DestructiveRole)

    # Set default button based on risk
    if risk_level == 'High':
        msg_box.setDefaultButton(use_recommended_btn)
    else:
        msg_box.setDefaultButton(continue_btn)

    # Show dialog
    msg_box.exec()

    # Determine which button was clicked
    clicked_button = msg_box.clickedButton()
    if clicked_button == use_recommended_btn:
        return 'recommended'
    elif clicked_button == continue_btn:
        return 'continue'
    else:
        return 'cancel'

# Error code definitions based on GIS documentation
ERROR_CODES = {
    0: "Success",
    -1: "Unknown command",
    -5: "Incorrect parameters",
    -8: "Print Server suspended",
    -201: "Print Controller busy",
    -202: "General Print Controller failure",
    -210: "Print failed",
    -216: "Print Controller not initialized",
    -220: "Failed to add item to queue",
    -225: "Failed to wait for print to initialize",
    -100: "General Render Engine failure",
    -101: "Render Engine busy",
    -102: "Failed to load Render Engine configuration",
}

class GISPrintServerClient:
    def __init__(self, host='localhost', port=2000):
        """
        Initialize GIS Print Server client with dual socket architecture

        Args:
            host: IP address or hostname of the Print Server
            port: Port number (default 2000)
        """
        self.host = host
        self.port = port
        self.main_socket = None      # For normal operations
        self.abort_socket = None     # For abort commands
        self.listener_socket = None  # For status monitoring
        self.command_id = 0
        self.connected = False
        self.message_buffer = deque()  # Buffer for multi-message handling
        self.status_listeners = []
        self.current_status = {"code": 0, "text": "Unknown"}
        self.current_speed_mpm = None  # Track latest reported speed (meters per minute)
        self.is_initialized = False
        self.pmb_memory_size = None  # Store PMB memory size
        self.pmb_memory_used = 0     # Track used memory
        self.expected_pages = None   # Expected total pages/labels to print
        self.printed_pages = 0       # Observed printed pages from events
        self.last_traffic_code = None  # Last traffic light code
        
        # Pipeline tracking
        self.pending_commands = {}  # Track commands awaiting acknowledgment
        self.command_lock = threading.Lock()
        self.next_cmd_id = 0
        
        # Background message reading thread
        self._message_reader_thread = None
        self._message_reader_stop = threading.Event()
        # FIX 1 & 3: Limit deque size to prevent memory overflow (max 1000 messages)
        # When full, old messages are automatically dropped (FIFO)
        self._incoming_messages = deque(maxlen=1000)
        self._incoming_lock = threading.Lock()
        self._incoming_messages_dropped = 0  # Track dropped messages
        self._last_position_mm = None
        self._last_position_time = None

    def add_status_listener(self, listener):
        """Register a callback that receives parsed info events."""
        if callable(listener) and listener not in self.status_listeners:
            self.status_listeners.append(listener)

    def remove_status_listener(self, listener):
        """Remove a previously registered status listener."""
        if listener in self.status_listeners:
            self.status_listeners.remove(listener)

    def _message_reader_worker(self):
        """Background thread continuously reading messages from the server"""
        buffer = b""
        while not self._message_reader_stop.is_set():
            try:
                if not self.main_socket:
                    break
                self.main_socket.settimeout(0.5)
                try:
                    chunk = self.main_socket.recv(16384)
                    if not chunk:
                        break
                    buffer += chunk
                    
                    # Process complete messages
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        message = line.decode().strip()
                        if message:
                            with self._incoming_lock:
                                self._incoming_messages.append(message)
                except socket.timeout:
                    continue
            except Exception as e:
                if not self._message_reader_stop.is_set():
                    logger.debug(f"Message reader error: {e}")
                break
    
    def connect(self):
        """Establish dual TCP/IP connections to the Print Server"""
        try:
            # Main connection
            with StepTimer("Connect main socket"):
                self.main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    self.main_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
                try:
                    self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
                    self.main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
                except Exception:
                    pass
                self.main_socket.connect((self.host, self.port))

            # Handle connection handshake
            with StepTimer("Handshake main socket"):
                response = self._receive_single_message(self.main_socket)
            logger.info(f"Main connection response: {response}")

            with StepTimer("Authenticate main socket"):
                auth_ok = self._handle_authentication(self.main_socket, response)
            if not auth_ok:
                return False

            # Abort connection
            logger.info("Establishing abort socket connection...")
            with StepTimer("Connect abort socket"):
                self.abort_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    self.abort_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
                try:
                    self.abort_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
                    self.abort_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
                except Exception:
                    pass
                self.abort_socket.connect((self.host, self.port))

            with StepTimer("Handshake abort socket"):
                abort_response = self._receive_single_message(self.abort_socket)
            with StepTimer("Authenticate abort socket"):
                abort_ok = self._handle_authentication(self.abort_socket, abort_response)
            if not abort_ok:
                logger.error("Failed to establish abort socket")
                return False

            logger.info("Successfully connected with dual socket architecture")
            self.connected = True
            
            # Start background message reader thread
            self._message_reader_stop.clear()
            self._message_reader_thread = threading.Thread(
                target=self._message_reader_worker, 
                daemon=True,
                name="GIS-MessageReader"
            )
            self._message_reader_thread.start()

            # Initialize server
            with StepTimer("Initialize server"):
                initialized = self._initialize_server()
            if not initialized:
                logger.error("Failed to initialize server")
                return False

            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def _handle_authentication(self, sock, response):
        """Handle authentication for a socket connection"""
        if response.startswith("N,A"):
            # Authentication required
            auth_key = response.split(',')[2].strip()
            response_key = self._transform_auth_key(auth_key)
            self._send_message_on_socket(sock, f"N,R,{response_key}")
            response = self._receive_single_message(sock)

        if "N,C" in response:
            return True
        elif "N,F" in response:
            logger.error("Authentication failed")
            return False
        else:
            logger.error("Unexpected connection response")
            return False

    def _transform_auth_key(self, auth_key):
        """Transform authentication key - placeholder"""
        return auth_key

    def _initialize_server(self):
        """Initialize server and set appropriate modes"""
        try:
            # Wait for server to be fully initialized
            logger.info("Waiting for server initialization...")
            with StepTimer("Server wait init S,I,W"):
                self._send_message("S,I,W")
                if not self._wait_for_complete_with_info():
                    return False

            # Get available system modes
            logger.info("Getting system modes...")
            with StepTimer("Get system modes S,T,N"):
                self._send_message("S,T,N")
                response = self._wait_for_complete_with_return()
            if response:
                modes = response.split(';') if isinstance(response, str) else []
                logger.info(f"Available modes: {modes}")

            # Get PMB memory information
            with StepTimer("Get PMB memory info"):
                self.get_pmb_memory_info()

            self.is_initialized = True
            return True

        except Exception as e:
            logger.error(f"Initialization error: {e}")
            return False

    def get_pmb_memory_info(self):
        """Get PMB memory size from the server"""
        try:
            logger.info("Getting PMB memory information...")
            self._send_message("P,M,I")
            response = self._wait_for_complete_with_return()
            
            if response and isinstance(response, str):
                try:
                    memory_parts = response.split(',')
                    if memory_parts:
                        self.pmb_memory_size = int(memory_parts[0]) * 1024 * 1024
                        logger.info(f"PMB memory size: {self.pmb_memory_size / (1024*1024):.2f} MB")
                except:
                    self.pmb_memory_size = 256 * 1024 * 1024
                    logger.warning(f"Could not parse memory size, using default: {self.pmb_memory_size / (1024*1024):.2f} MB")
            else:
                self.pmb_memory_size = 256 * 1024 * 1024
                logger.info(f"Using default PMB memory size: {self.pmb_memory_size / (1024*1024):.2f} MB")
                
        except Exception as e:
            logger.warning(f"Could not get PMB memory info: {e}")
            self.pmb_memory_size = 256 * 1024 * 1024
    
    def get_queue_status(self):
        """Get current queue status including memory usage"""
        try:
            self._send_message("P,Q,S")
            response = self._wait_for_complete_with_return()
            
            if response and isinstance(response, str):
                parts = response.split(',')
                if len(parts) >= 2:
                    items_in_queue = int(parts[0])
                    memory_used = int(parts[1])
                    return {'items': items_in_queue, 'memory_used': memory_used}
            
            return {'items': 0, 'memory_used': self.pmb_memory_used}
            
        except Exception as e:
            logger.debug(f"Could not get queue status: {e}")
            return {'items': 0, 'memory_used': self.pmb_memory_used}

    def get_current_status(self):
        """Return the latest cached controller status information."""
        status = dict(self.current_status) if isinstance(self.current_status, dict) else {}
        if self.current_speed_mpm is not None:
            status['speed_mpm'] = self.current_speed_mpm
        status['printed_pages'] = self.printed_pages
        return status

    def get_current_speed(self):
        """Get the latest reported speed in meters per minute (if available)."""
        return self.current_speed_mpm

    @staticmethod
    def _normalize_speed_value(raw_value):
        """Convert raw speed values from controller into meters per minute."""
        if raw_value is None:
            return None
        try:
            if isinstance(raw_value, str):
                match = re.search(r'-?\d+(?:\.\d+)?', raw_value)
                if not match:
                    return None
                value = float(match.group(0))
                unit_section = raw_value[match.end():].strip().lower()
            else:
                value = float(raw_value)
                unit_section = ""
        except (TypeError, ValueError):
            return None

        # Ignore impossible values
        if value < 0:
            return None

        if 'mm/s' in unit_section:
            # millimetres per second → metres per minute
            return (value / 1000.0) * 60.0
        if 'mm/min' in unit_section or 'mm per min' in unit_section:
            # millimetres per minute → metres per minute
            return value / 1000.0
        if 'm/s' in unit_section:
            # metres per second → metres per minute
            return value * 60.0

        # Heuristic: large numbers are likely mm/min
        if value > 500:
            return value / 1000.0

        return value

    def _update_speed_mpm(self, raw_value):
        """Update cached speed and notify listeners."""
        speed_value = self._normalize_speed_value(raw_value)
        if speed_value is None:
            return None

        # Only log when value changes meaningfully to avoid chatter
        if self.current_speed_mpm is None or abs(self.current_speed_mpm - speed_value) > 0.05:
            logger.debug(f"Print speed updated: {speed_value:.2f} m/min")

        self.current_speed_mpm = speed_value
        self._notify_status_listeners({
            'category': 'print',
            'event': 'speed',
            'speed_mpm': speed_value
        })
        return speed_value

    def query_print_count(self):
        """Query the print controller for the cumulative printed count (Images Printed field)."""
        try:
            with self.command_lock:
                self._send_message("P,1")
                response = self._wait_for_complete_with_return()
            if not response or not isinstance(response, str):
                return None
            fields = response.split(',')
            if len(fields) < 17:
                return None
            try:
                # Field 'm' (Images Printed) is at index 16 based on protocol documentation
                return int(fields[16])
            except (ValueError, IndexError):
                return None
        except Exception as e:
            logger.debug(f"Print count query failed: {e}")
            return None

    def _notify_status_listeners(self, event):
        """Notify registered listeners of a parsed event."""
        for listener in list(self.status_listeners):
            try:
                listener(event)
            except Exception as e:
                logger.debug(f"Status listener error: {e}")

    def _get_next_cmd_id(self):
        """Get next command ID for tracking"""
        with self.command_lock:
            self.next_cmd_id += 1
            return str(self.next_cmd_id)

    def _send_message(self, message):
        """Send a message to the Print Server on main socket"""
        return self._send_message_on_socket(self.main_socket, message)

    def _send_message_on_socket(self, sock, message):
        """Send a message on a specific socket"""
        if not sock:
            raise Exception("Socket not connected")

        message_with_newline = message + '\n'
        sock.send(message_with_newline.encode())
        logger.debug(f"Sent: {message}")
        return True

    def _send_message_async(self, message):
        """Send a message without waiting for response - for pipelining"""
        if not self.main_socket:
            raise Exception("Socket not connected")
        
        message_with_newline = message + '\n'
        self.main_socket.send(message_with_newline.encode())
        logger.debug(f"Sent (async): {message}")
        return True

    def _receive_single_message(self, sock):
        """Receive a single message from a socket"""
        if not sock:
            raise Exception("Socket not connected")

        response = b""
        while b'\n' not in response:
            chunk = sock.recv(1024)
            if not chunk:
                break
            response += chunk

        return response.decode().strip()

    def _receive_messages(self):
        """Get messages from the background reader thread"""
        if not self.main_socket:
            raise Exception("Not connected to server")

        # Check old buffer first
        buffered_messages = []
        while self.message_buffer:
            buffered_messages.append(self.message_buffer.popleft())

        if buffered_messages:
            return buffered_messages

        # Get messages from background thread
        messages = []
        with self._incoming_lock:
            while self._incoming_messages:
                messages.append(self._incoming_messages.popleft())

        return messages

    def _parse_info_message(self, message):
        """Parse information messages"""
        parts = message.split(',')
        if len(parts) < 3:
            return

        msg_id = parts[1]
        msg_type = parts[2]

        event = None

        # Status message
        if msg_type == 'S' and len(parts) >= 5:
            status_text = parts[3]
            status_code = int(parts[4])
            self.current_status = {"code": status_code, "text": status_text}
            logger.info(f"Status: {status_text} (code: {status_code})")
            event = {'category': 'print', 'event': 'status', 'code': status_code, 'text': status_text}

            # Try to extract speed embedded within the status text
            speed_match = re.search(r'(-?\d+(?:\.\d+)?)\s*(?:m/?min|mpm)', status_text, re.IGNORECASE)
            if speed_match:
                self._update_speed_mpm(speed_match.group(0))

        # Current label
        elif msg_type == 'L' and len(parts) >= 4:
            label_num = int(parts[3])
            logger.info(f"Printing label/page {label_num}")
            if label_num > self.printed_pages:
                self.printed_pages = label_num
            event = {'category': 'print', 'event': 'label', 'label': label_num}

        # End of printing
        elif msg_type == 'EP':
            logger.info("End of printing")
            event = {'category': 'print', 'event': 'end_print'}
            self._last_position_mm = None
            self._last_position_time = None

        # Speed update (varies by firmware)
        elif msg_type.upper() in {'SPD', 'SPEED', 'V', 'VEL', 'SP', 'MPM'} and len(parts) >= 4:
            self._update_speed_mpm(parts[3])
            return
        elif msg_type.upper() == 'X' and len(parts) >= 5:
            # Positional telemetry: I,<id>,X,<x>,Y,<y>,...
            # Extract the primary travel axis (typically Y)
            y_value = None
            try:
                for idx in range(3, len(parts), 2):
                    axis = parts[idx].upper()
                    if idx + 1 >= len(parts):
                        break
                    value = float(parts[idx + 1])
                    if axis == 'Y':
                        y_value = value
                        break
                if y_value is not None:
                    now = time.monotonic()
                    if self._last_position_mm is not None and self._last_position_time is not None:
                        delta_mm = y_value - self._last_position_mm
                        delta_t = now - self._last_position_time
                        if delta_t > 0:
                            speed_m_per_min = (abs(delta_mm) / delta_t) / 1000.0 * 60.0
                            # Ignore tiny, noisy speeds
                            if speed_m_per_min >= 0.01:
                                self._update_speed_mpm(speed_m_per_min)
                    self._last_position_mm = y_value
                    self._last_position_time = now
            except Exception as pos_err:
                logger.debug(f"Failed to process position telemetry: {pos_err}")
            return

        # Traffic light
        elif msg_type == 'T' and len(parts) >= 4:
            traffic_code = int(parts[3])
            traffic_states = {0: "Ready", 1: "Preparing", 2: "Printing", 3: "Error"}
            logger.info(f"Traffic light: {traffic_states.get(traffic_code, 'Unknown')}")
            self.last_traffic_code = traffic_code
            event = {'category': 'print', 'event': 'traffic', 'code': traffic_code}

        # Memory status
        elif msg_type == 'M' and len(parts) >= 4:
            memory_used = int(parts[3])
            logger.info(f"PMB memory used: {memory_used / (1024*1024):.2f} MB")
            self.pmb_memory_used = memory_used
            event = {'category': 'print', 'event': 'memory', 'memory_used': memory_used}

        # RTP (Ready To Print) - server is ready to receive more data
        elif msg_type == 'RTP' and len(parts) >= 4:
            rtp_count = int(parts[3])
            logger.debug(f"RTP (Ready To Print): {rtp_count}")
            event = {'category': 'print', 'event': 'rtp', 'count': rtp_count}

        # SP (Swathe Processed) - buffer level monitoring
        elif msg_type == 'SP' and len(parts) >= 4:
            swathe_num = int(parts[3])
            logger.debug(f"SP (Swathe Processed): {swathe_num}")
            event = {'category': 'print', 'event': 'swathe', 'swathe': swathe_num}

        if event:
            self._notify_status_listeners(event)

    def _wait_for_complete_with_info(self):
        """Wait for completion while processing info messages"""
        ack_id = None

        while True:
            messages = self._receive_messages()

            for message in messages:
                if message.startswith("A,"):
                    parts = message.split(',')
                    ack_id = parts[1]
                    logger.debug(f"Got acknowledgement ID: {ack_id}")

                elif message.startswith("I,"):
                    self._parse_info_message(message)

                elif message.startswith("C,"):
                    parts = message.split(',')
                    cmd_id = parts[1]
                    error_code = int(parts[2])

                    if error_code == 0:
                        logger.debug(f"Command {cmd_id} completed successfully")
                        return True
                    else:
                        error_msg = ERROR_CODES.get(error_code, f"Unknown error: {error_code}")
                        logger.error(f"Command {cmd_id} failed: {error_msg}")
                        return False

    def _wait_for_complete_with_return(self):
        """Wait for completion and return any data"""
        ack_id = None

        while True:
            messages = self._receive_messages()

            for message in messages:
                if message.startswith("A,"):
                    parts = message.split(',')
                    ack_id = parts[1]

                elif message.startswith("I,"):
                    self._parse_info_message(message)

                elif message.startswith("C,"):
                    parts = message.split(',')
                    error_code = int(parts[2])

                    if error_code == 0:
                        if len(parts) > 3:
                            return ','.join(parts[3:])
                        return True
                    else:
                        return None

    def _process_messages_async(self, timeout=0.01):
        """Process incoming messages asynchronously - returns counts of different message types"""
        if not self.main_socket:
            return {'acks': 0, 'completes': 0, 'errors': 0}

        acks = 0
        completes = 0
        errors = 0

        # FIX 2: Monitor queue size to detect buildup
        # Get messages from background thread
        messages = []
        queue_size = 0
        with self._incoming_lock:
            queue_size = len(self._incoming_messages)
            while self._incoming_messages:
                messages.append(self._incoming_messages.popleft())

        # Warn if queue is getting large (potential buildup)
        if queue_size > 500:
            logger.warning(f"⚠️ Message queue size: {queue_size}/1000 (50% full - potential buildup)")
        elif queue_size > 800:
            logger.error(f"❌ Message queue size: {queue_size}/1000 (80% full - near overflow!)")
        elif queue_size > 100:
            logger.debug(f"Queue size: {queue_size}/1000")
        
        # Process messages
        for line in messages:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("A,"):
                acks += 1
                logger.debug(f"ACK received: {line}")
            
            elif line.startswith("C,"):
                parts = line.split(',')
                if len(parts) >= 3:
                    error_code = int(parts[2])
                    if error_code == 0:
                        completes += 1
                    else:
                        errors += 1
                        if errors <= 3:  # Only log first few errors
                            logger.debug(f"Error in completion: {ERROR_CODES.get(error_code, error_code)}")
            
            elif line.startswith("I,"):
                self._parse_info_message(line)
        
        return {'acks': acks, 'completes': completes, 'errors': errors}

    def abort_print(self):
        """Send abort command on abort socket"""
        if not self.abort_socket:
            logger.error("Abort socket not connected")
            return False

        logger.warning("Sending abort command...")
        self._send_message_on_socket(self.abort_socket, "P,A")

        response = self._receive_single_message(self.abort_socket)
        if response.startswith("A,"):
            logger.info("Abort acknowledged")
            return True
        return False

    def register_listener(self, engine_type='P'):
        """Register as listener for real-time updates"""
        command = f"{engine_type},L"
        self._send_message(command)
        return self._wait_for_complete_with_info()

    def set_expected_pages(self, expected: int):
        """Set expected total pages/labels to print and reset counters."""
        try:
            self.expected_pages = int(expected) if expected is not None else None
        except Exception:
            self.expected_pages = None
        self.printed_pages = 0
        self.last_traffic_code = None

    def wait_for_print_completion(self, timeout_s: float = 600.0, poll_interval_s: float = 0.5, cancellation_check=None):
        """Wait until printing is actually finished.
        
        Args:
            timeout_s: Maximum time to wait in seconds
            poll_interval_s: How often to check status
            cancellation_check: Optional callable that returns True if operation should be cancelled
        """
        start = time.perf_counter()
        ep_seen = False
        last_items = None

        while True:
            # Check for cancellation first
            if cancellation_check and callable(cancellation_check):
                if cancellation_check():
                    logger.info("Print completion wait cancelled by user")
                    return False
            
            messages = self._receive_messages()
            for message in messages:
                if message.startswith("I,"):
                    parts = message.split(',')
                    if len(parts) >= 3 and parts[2] == 'EP':
                        logger.info("End of printing (EP) received")
                        ep_seen = True
                    self._parse_info_message(message)

            # Removed get_queue_status() call to avoid "Unknown TCP/IP message: P,Q,S" warnings
            # The queue completion is detected via EP message and traffic light status instead
            
            pages_ok = (self.expected_pages is None) or (self.printed_pages >= self.expected_pages)
            ready_ok = (self.last_traffic_code == 0)
            if pages_ok and (ep_seen or ready_ok):
                return True

            if time.perf_counter() - start > timeout_s:
                logger.error("Timed out waiting for print completion")
                return False

            time.sleep(poll_interval_s)

    def print_queue_mode_start(self):
        """Start print queue mode for continuous printing"""
        logger.info("Starting print queue mode...")
        self.pmb_memory_used = 0
        command = "P,Q,P"
        self._send_message(command)
        return self._wait_for_complete_with_info()

    def print_queue_add_item_async(self, rip_file_path, num_copies=1):
        """Add item to print queue asynchronously (no wait)"""
        rip_path = os.path.abspath(rip_file_path)
        
        # Detect extension (case-insensitive) and strip plane suffix (_0, _1, etc.)
        path_lower = rip_path.lower()
        if path_lower.endswith('.bmp'):
            extension = rip_path[-4:]  # Preserve original case
            base = rip_path[:-4]
            # Strip _0, _1, _2, _3 suffix if present
            if len(base) >= 2 and base[-2] == '_' and base[-1].isdigit():
                base = base[:-2]
            command = f"P,Q,A,{base}{extension},{num_copies}"
        elif path_lower.endswith('.tif') or path_lower.endswith('.tiff'):
            extension = rip_path[-4:] if path_lower.endswith('.tif') else rip_path[-5:]
            base = rip_path[:-4] if path_lower.endswith('.tif') else rip_path[:-5]
            # Strip _0, _1, _2, _3 suffix if present
            if len(base) >= 2 and base[-2] == '_' and base[-1].isdigit():
                base = base[:-2]
            command = f"P,Q,A,{base}{extension},{num_copies}"
        else:
            # Fallback: no known extension, send as-is
            command = f"P,Q,A,{rip_path},{num_copies}"
        
        self._send_message_async(command)
        return True

    def print_queue_add_item(self, rip_file_path, num_copies=1):
        """Add item to print queue with acknowledgment wait (fallback)"""
        rip_path = os.path.abspath(rip_file_path)
        
        # Detect extension (case-insensitive) and strip plane suffix (_0, _1, etc.)
        path_lower = rip_path.lower()
        if path_lower.endswith('.bmp'):
            extension = rip_path[-4:]  # Preserve original case
            base = rip_path[:-4]
            # Strip _0, _1, _2, _3 suffix if present
            if len(base) >= 2 and base[-2] == '_' and base[-1].isdigit():
                base = base[:-2]
            command = f"P,Q,A,{base}{extension},{num_copies}"
        elif path_lower.endswith('.tif') or path_lower.endswith('.tiff'):
            extension = rip_path[-4:] if path_lower.endswith('.tif') else rip_path[-5:]
            base = rip_path[:-4] if path_lower.endswith('.tif') else rip_path[:-5]
            # Strip _0, _1, _2, _3 suffix if present
            if len(base) >= 2 and base[-2] == '_' and base[-1].isdigit():
                base = base[:-2]
            command = f"P,Q,A,{base}{extension},{num_copies}"
        else:
            # Fallback: no known extension, send as-is
            command = f"P,Q,A,{rip_path},{num_copies}"
        
        logger.debug(f"Queue add command: {command}")
        self._send_message(command)
        return self._wait_for_complete_with_info()

    def print_queue_mode_end(self):
        """End print queue mode and wait for completion"""
        logger.info("Ending print queue mode...")
        command = "P,Q,E"
        self._send_message(command)
        return self._wait_for_complete_with_info()

    def close(self):
        """Close all connections"""
        # Stop background message reader
        if self._message_reader_thread and self._message_reader_thread.is_alive():
            self._message_reader_stop.set()
            self._message_reader_thread.join(timeout=2.0)
        
        for sock in [self.main_socket, self.abort_socket, self.listener_socket]:
            if sock:
                try:
                    sock.close()
                except:
                    pass
        self.connected = False
        logger.info("All connections closed")


def natural_sort_key(text):
    """Natural sorting key function for filenames"""
    def atoi(text):
        return int(text) if text.isdigit() else text.lower()
    return [atoi(c) for c in re.split('([0-9]+)', str(text))]


def get_file_size(file_path):
    """Get file size in bytes"""
    try:
        return os.path.getsize(file_path)
    except:
        return 0

def _get_base_filename_without_color_plane(file_path):
    """
    Extract base filename without color plane suffix (_0, _1, _2, _3).
    
    Examples:
        TEST_File_1709_page_0001_rip_0001_0.bmp -> TEST_File_1709_page_0001_rip_0001.bmp
        TEST_File_1709_page_0001_rip_0001_1.bmp -> TEST_File_1709_page_0001_rip_0001.bmp
    """
    path = Path(file_path)
    stem = path.stem  # filename without extension
    extension = path.suffix
    
    # Check if filename ends with _0, _1, _2, or _3
    if len(stem) >= 2 and stem[-2] == '_' and stem[-1].isdigit():
        # Remove the _X suffix
        base_stem = stem[:-2]
        return str(path.parent / f"{base_stem}{extension}")
    
    # No color plane suffix, return as-is
    return str(file_path)


class RIPFolderPrinter:
    """Handles printing of already-ripped BMP files from a folder with async queue management"""
    
    def __init__(self, client, progress_callback=None, batch_size=10):
        """Initialize RIP folder printer
        
        Args:
            client: GISPrintServerClient instance
            progress_callback: Optional callback function for progress updates
                              Signature: progress_callback(processed, total, message)
            batch_size: Number of files to send to printer queue at once (default: 10)
        """
        self.client = client
        self.total_files_printed = 0
        self.total_files_sent = 0  # Track files sent to server
        self.total_files_acked = 0  # Track files acknowledged by server
        self.failed_files = []
        self.skipped_files = []
        self.memory_safety_factor = 0.95
        self.max_queue_items = 500
        self.progress_callback = progress_callback
        self._cancelled = False

        # Async pipeline configuration with SCALABLE design (no arbitrary caps)
        # Validate batch_size: allow unlimited but ensure it's positive integer
        self.batch_size_requested = int(batch_size) if batch_size > 0 else 10
        self.batch_size = max(1, self.batch_size_requested)  # Minimum 1

        # SCALABLE PIPELINE: Use 2× batch_size for double-buffering (proactive sending)
        # This ensures we maintain 2× batch_size in server buffer at all times
        # Formula: pipeline_window = batch_size * 2
        # No arbitrary caps - scales with ANY batch size (10, 500, 2500, 10000+)
        self.pipeline_window = self.batch_size * 2  # Double-buffering strategy

        # Minimum pipeline window for very small batches
        self.pipeline_window = max(20, self.pipeline_window)

        # Adaptive ACK timeout based on batch size - IMPROVED SCALING
        # Larger batches need more time for server processing
        if self.batch_size >= 5000:
            self.ack_wait_timeout = 1.0  # 1s for extreme batches (5000+)
        elif self.batch_size >= 2000:
            self.ack_wait_timeout = 0.5  # 500ms for very large batches (2000-5000)
        elif self.batch_size >= 1000:
            self.ack_wait_timeout = 0.3  # 300ms for large batches (1000-2000)
        elif self.batch_size >= 500:
            self.ack_wait_timeout = 0.2  # 200ms for medium-large batches (500-1000)
        elif self.batch_size >= 200:
            self.ack_wait_timeout = 0.15  # 150ms for medium batches (200-500)
        elif self.batch_size >= 100:
            self.ack_wait_timeout = 0.1  # 100ms for small-medium batches (100-200)
        else:
            self.ack_wait_timeout = 0.05  # 50ms for small batches (<100)

        # RTP (Ready To Print) waiting configuration
        self.rtp_enabled = True  # Enable RTP waiting for buffer synchronization
        self.rtp_timeout = 5.0  # Max wait time for RTP signal (5s) - reduced from 30s for faster startup
        self.rtp_received = False  # Flag: has RTP been received?
        self.rtp_count = 0  # Last RTP count received
        self.buffer_level = 0  # Track current buffer level (SP - L)
        self.swathes_processed = 0  # Track SP messages
        self.labels_printed = 0  # Track L messages

        # Double-buffering threshold: when to send next batch
        # Send next batch when buffer drops below 1× batch_size (maintain 2× buffer)
        self.buffer_threshold = self.batch_size

        # Log configuration for debugging
        logger.info(f"RIPFolderPrinter initialized with SCALABLE pipeline:")
        logger.info(f"  Batch size requested: {self.batch_size_requested}")
        logger.info(f"  Batch size actual: {self.batch_size}")
        logger.info(f"  Pipeline window (2× batch): {self.pipeline_window}")
        logger.info(f"  ACK wait timeout: {self.ack_wait_timeout}s")
        logger.info(f"  RTP waiting: {self.rtp_enabled}")
        logger.info(f"  Buffer threshold: {self.buffer_threshold}")

        # Info message for large batches
        if self.batch_size >= 1000:
            logger.info(f"Large batch mode: {self.batch_size} files per batch, "
                       f"pipeline window: {self.pipeline_window} (no caps applied)")
        
        # Continuous printing configuration
        self.monitor_interval = 2.0  # Check for new files every 2 seconds
        self.processed_files = set()  # Track processed files to avoid duplicates
        self.continuous_mode = False  # Flag for continuous mode
        self.last_scan_time = 0  # Track last folder scan time
    
    def cancel(self):
        """Cancel the printing process"""
        self._cancelled = True

    def _buffer_status_listener(self, event):
        """Listen for buffer-related events (RTP, SP, L) to track buffer level"""
        try:
            event_type = event.get('event')

            if event_type == 'rtp':
                # RTP (Ready To Print) signal received - SERVER IS READY!
                rtp_count = event.get('count', 0)
                self.rtp_received = True  # Set flag
                self.rtp_count = rtp_count
                logger.info(f"✓ RTP (Ready To Print) received: count={rtp_count} - Server ready for data")

            elif event_type == 'swathe':
                # SP (Swathe Processed) message
                swathe_num = event.get('swathe', 0)
                self.swathes_processed = swathe_num
                self.buffer_level = self.swathes_processed - self.labels_printed
                logger.debug(f"Buffer monitor: SP={swathe_num}, L={self.labels_printed}, buffer={self.buffer_level}")

            elif event_type == 'label':
                # L (Label) message - page printed
                label_num = event.get('label', 0)
                self.labels_printed = label_num
                self.buffer_level = self.swathes_processed - self.labels_printed
                logger.debug(f"Buffer monitor: L={label_num}, SP={self.swathes_processed}, buffer={self.buffer_level}")

        except Exception as e:
            logger.debug(f"Buffer status listener error: {e}")

    def _wait_for_rtp(self, timeout=5.0):
        """
        Wait for RTP (Ready To Print) signal from server before sending data

        This is CRITICAL for preventing underrun:
        - Server sends RTP when buffer is ready to receive data
        - Must wait for RTP before first batch
        - Should check RTP periodically for subsequent batches

        Args:
            timeout: Maximum time to wait for RTP (seconds)

        Returns:
            bool: True if RTP received, False if timeout
        """
        if not self.rtp_enabled:
            return True  # RTP waiting disabled, proceed

        if self.rtp_received:
            logger.debug("RTP already received, proceeding")
            return True

        logger.info(f"Waiting for RTP (Ready To Print) signal... (timeout: {timeout}s)")
        start_time = time.perf_counter()

        while not self.rtp_received:
            # Check for cancellation
            if self._cancelled:
                logger.info("RTP wait cancelled")
                return False

            # Process messages to receive RTP
            if self.client:
                try:
                    self.client._process_messages_async(timeout=0.1)
                except Exception as e:
                    logger.debug(f"Error processing messages during RTP wait: {e}")

            # Check timeout
            elapsed = time.perf_counter() - start_time
            if elapsed > timeout:
                logger.warning(f"RTP timeout after {elapsed:.1f}s - proceeding anyway (may cause underrun)")
                return False

            # Small sleep to avoid busy-waiting
            time.sleep(0.05)

        elapsed = time.perf_counter() - start_time
        logger.info(f"✓ RTP received after {elapsed:.2f}s - server ready!")
        return True

    def analyze_folder_and_recommend_batch_size(self, folder_path, pattern="*.bmp", recursive=False, current_batch_size=None):
        """
        Analyze folder and recommend optimal batch size

        Returns dict with:
        - analysis: folder statistics
        - recommendation: optimal batch size
        - risk_level: Low/Medium/High
        - message: detailed explanation
        """
        from pathlib import Path

        logger.info("=" * 60)
        logger.info("ANALYZING FOLDER FOR BATCH SIZE RECOMMENDATION")
        logger.info("=" * 60)

        # Get all RIP files (INCLUDING all color planes for accurate size calculation)
        rip_files = self.discover_rip_files(folder_path, pattern, recursive, deduplicate_color_planes=False)

        if not rip_files:
            return {
                'analysis': None,
                'recommendation': None,
                'risk_level': 'Low',
                'message': 'No files found in folder'
            }

        # Analyze each page (group files by base name to detect color planes)
        page_groups = {}
        for file_path, file_size in rip_files:
            # Get base name (without _0, _1, _2, _3 suffix) using existing helper
            base_name = _get_base_filename_without_color_plane(file_path)

            if base_name not in page_groups:
                page_groups[base_name] = []
            page_groups[base_name].append((file_path, file_size))

        # Calculate statistics
        page_sizes = []
        total_size = 0
        max_planes = 0
        min_planes = float('inf')

        for base_name, planes in page_groups.items():
            page_size = sum(size for _, size in planes)
            page_sizes.append(page_size)
            total_size += page_size
            max_planes = max(max_planes, len(planes))
            min_planes = min(min_planes, len(planes))

        num_pages = len(page_groups)
        avg_page_size = total_size / num_pages if num_pages > 0 else 0
        max_page_size = max(page_sizes) if page_sizes else 0
        min_page_size = min(page_sizes) if page_sizes else 0

        # PMB configuration (from customer's specs)
        PMB_TOTAL_BUFFER = 95 * 1024 * 1024  # 95 MB total buffer
        PMB_PRE_BUFFER = 45 * 1024 * 1024  # 45 MB pre-buffer
        SAFETY_FACTOR = 0.90  # Use 90% of capacity for safety (10% margin)

        # Calculate optimal batch size based on different criteria

        # Method 1: Based on total PMB buffer capacity
        safe_buffer_capacity = PMB_TOTAL_BUFFER * SAFETY_FACTOR
        optimal_pipeline_pages = int(safe_buffer_capacity / avg_page_size) if avg_page_size > 0 else 100
        optimal_batch_method1 = max(1, optimal_pipeline_pages // 2)  # Pipeline = 2× batch

        # Method 2: Based on max page size (safest for variable sizes)
        if max_page_size > 0:
            safe_pipeline_pages = int(safe_buffer_capacity / max_page_size)
            optimal_batch_method2 = max(1, safe_pipeline_pages // 2)
        else:
            optimal_batch_method2 = optimal_batch_method1

        # Method 3: Ensure first batch fills pre-buffer (for RTP signal)
        # Use max_page_size for safety (worst-case scenario)
        pages_for_prebuffer = int(PMB_PRE_BUFFER / max_page_size) if max_page_size > 0 else 10
        min_batch_for_rtp = max(1, pages_for_prebuffer)

        # Final recommendation: balance all criteria
        recommended_batch = max(
            min(optimal_batch_method1, optimal_batch_method2),  # Use safer of the two
            min_batch_for_rtp  # But ensure pre-buffer can be filled
        )

        # Cap at reasonable maximum
        recommended_batch = min(recommended_batch, 100)  # Max 100 per batch for practical reasons

        # Analyze current batch size (if provided)
        risk_level = 'Low'
        risk_message = ''

        if current_batch_size:
            current_pipeline = current_batch_size * 2
            current_memory = current_pipeline * avg_page_size
            capacity_usage = (current_memory / PMB_TOTAL_BUFFER) * 100

            if capacity_usage > 100:
                risk_level = 'High'
                risk_message = f'Pipeline exceeds PMB capacity by {capacity_usage - 100:.0f}%'
            elif capacity_usage > 85:
                risk_level = 'Medium'
                risk_message = f'Pipeline uses {capacity_usage:.0f}% of PMB capacity'
            else:
                risk_level = 'Low'
                risk_message = f'Pipeline uses {capacity_usage:.0f}% of PMB capacity'

        # Build analysis result
        analysis = {
            'total_pages': num_pages,
            'total_size_mb': total_size / (1024 * 1024),
            'avg_page_size_mb': avg_page_size / (1024 * 1024),
            'min_page_size_mb': min_page_size / (1024 * 1024),
            'max_page_size_mb': max_page_size / (1024 * 1024),
            'min_planes': min_planes if min_planes != float('inf') else 0,
            'max_planes': max_planes,
            'current_batch_size': current_batch_size,
            'recommended_batch_size': recommended_batch,
            'risk_level': risk_level,
            'risk_message': risk_message,
            'pmb_capacity_mb': PMB_TOTAL_BUFFER / (1024 * 1024),
            'prebuffer_mb': PMB_PRE_BUFFER / (1024 * 1024)
        }

        logger.info(f"Folder Analysis Complete:")
        logger.info(f"  Total pages: {num_pages}")
        logger.info(f"  Total size: {total_size / (1024 * 1024):.2f} MB")
        logger.info(f"  Avg page size: {avg_page_size / (1024 * 1024):.2f} MB")
        logger.info(f"  Page size range: {min_page_size / (1024 * 1024):.2f} - {max_page_size / (1024 * 1024):.2f} MB")
        logger.info(f"  Color planes range: {min_planes if min_planes != float('inf') else 0} - {max_planes}")
        logger.info(f"  Current batch size: {current_batch_size}")
        logger.info(f"  Recommended batch size: {recommended_batch}")
        logger.info(f"  Risk level: {risk_level}")
        logger.info("=" * 60)

        return analysis

    def _get_server_queue_capacity(self):
        """
        Query server's actual queue capacity from PMB memory size
        Returns None if unable to determine, otherwise returns max queue items
        """
        try:
            if not self.client or not hasattr(self.client, 'pmb_memory_size'):
                return None

            pmb_size = self.client.pmb_memory_size
            if pmb_size is None or pmb_size <= 0:
                logger.debug("PMB memory size not available, using default limits")
                return None

            # Estimate queue capacity based on PMB memory
            # Assume average file ~500KB, use 80% of PMB for safety
            avg_file_size_kb = 500
            usable_memory_kb = int(pmb_size * 0.8)
            estimated_capacity = max(20, usable_memory_kb // avg_file_size_kb)

            # Cap at reasonable maximum (don't exceed hardcoded max_queue_items)
            server_capacity = min(estimated_capacity, self.max_queue_items)

            logger.info(f"Server queue capacity estimated: {server_capacity} items (PMB: {pmb_size} KB)")
            return server_capacity

        except Exception as e:
            logger.warning(f"Failed to query server queue capacity: {e}")
            return None

    def discover_rip_files(self, folder_path, pattern="*.bmp", recursive=False, deduplicate_color_planes=True):
        """Discover all RIP files (.bmp, .tif, .tiff - case insensitive) in a folder

        Args:
            folder_path: Path to folder containing RIP files
            pattern: File pattern to match (default: "*.bmp")
            recursive: If True, search recursively in subfolders
            deduplicate_color_planes: If True (default), return only one file per page (for printing).
                                     If False, return all color plane files (for analysis).
        """
        folder_path = Path(folder_path)
        
        if not folder_path.exists():
            logger.error(f"Folder does not exist: {folder_path}")
            return []
            
        if not folder_path.is_dir():
            logger.error(f"Path is not a directory: {folder_path}")
            return []
        
        # Use a dict to deduplicate files (Windows is case-insensitive)
        rip_files_dict = {}
        
        # Search for all supported RIP file extensions (case-insensitive)
        patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
        
        if recursive:
            for pat in patterns:
                for rip_file in folder_path.rglob(pat):
                    if rip_file.is_file():
                        # Use normalized path as key to avoid duplicates
                        key = str(rip_file).lower()
                        if key not in rip_files_dict:
                            file_size = get_file_size(rip_file)
                            rip_files_dict[key] = (str(rip_file), file_size)
        else:
            for pat in patterns:
                for rip_file in folder_path.glob(pat):
                    if rip_file.is_file():
                        # Use normalized path as key to avoid duplicates
                        key = str(rip_file).lower()
                        if key not in rip_files_dict:
                            file_size = get_file_size(rip_file)
                            rip_files_dict[key] = (str(rip_file), file_size)
        
        # Convert dict values to list and sort
        rip_files = list(rip_files_dict.values())
        rip_files.sort(key=lambda x: natural_sort_key(x[0]))

        # Deduplicate color plane files (prefer _0 plane) - ONLY if requested
        if deduplicate_color_planes:
            base_name_to_file = {}

            for file_path, file_size in rip_files:
                # Get base name without color plane suffix
                base_name = _get_base_filename_without_color_plane(file_path).lower()

                if base_name not in base_name_to_file:
                    # First occurrence - add it
                    base_name_to_file[base_name] = (file_path, file_size)
                else:
                    # Already have this base - prefer _0 plane
                    current_file = str(file_path).lower()
                    if '_0.bmp' in current_file or '_0.tif' in current_file or '_0.tiff' in current_file:
                        # Replace with _0 plane
                        base_name_to_file[base_name] = (file_path, file_size)

            # Use deduplicated list
            rip_files = list(base_name_to_file.values())
            rip_files.sort(key=lambda x: natural_sort_key(x[0]))

            total_size = sum(size for _, size in rip_files)

            logger.info(f"Found {len(rip_files)} unique RIP files (color planes deduplicated) in {folder_path}")
            logger.info(f"Total size: {total_size / (1024*1024):.2f} MB")
        else:
            # Return all files including all color planes (for analysis)
            total_size = sum(size for _, size in rip_files)

            logger.info(f"Found {len(rip_files)} RIP files (including all color planes) in {folder_path}")
            logger.info(f"Total size: {total_size / (1024*1024):.2f} MB")
        
        return rip_files
    
    def print_rip_folder(self, folder_path, pattern="*.bmp", recursive=False, num_copies=1, files_override=None):
        """Print all RIP files from a folder with async queue management"""
        self._cancelled = False
        # Reset RTP and buffer tracking for new job
        self.rtp_received = False
        self.buffer_level = 0
        self.swathes_processed = 0
        self.labels_printed = 0
        
        if self.progress_callback:
            self.progress_callback(0, 0, "Starting RIP folder print process...")
        
        logger.info("=" * 60)
        logger.info("STARTING RIP FOLDER PRINT PROCESS (ASYNC)")
        logger.info("=" * 60)
        logger.info(f"Folder: {folder_path}")
        logger.info(f"Pattern: {pattern}")
        logger.info(f"Recursive: {recursive}")
        logger.info(f"Copies per file: {num_copies}")
        
        # Discover RIP files (or use provided list)
        if files_override is None:
            if self.progress_callback:
                self.progress_callback(5, 0, "Discovering RIP files...")
            with StepTimer("Discover RIP files"):
                files_with_sizes = self.discover_rip_files(folder_path, pattern, recursive)
        else:
            files_with_sizes = list(files_override)
        
        if not files_with_sizes:
            error_msg = "No RIP files found to print"
            logger.error(error_msg)
            if self.progress_callback:
                self.progress_callback(0, 0, error_msg)
            return False
        
        # Filter files within memory limit
        if self.progress_callback:
            self.progress_callback(10, len(files_with_sizes), f"Found {len(files_with_sizes)} RIP files, filtering by memory...")
            
        with StepTimer("Filter files within memory limit"):
            max_memory = self.client.pmb_memory_size * self.memory_safety_factor
            files_to_process = []
            
            for file_path, file_size in files_with_sizes:
                if self._cancelled:
                    return False
                    
                if file_size > max_memory:
                    logger.warning(f"File too large: {Path(file_path).name}")
                    self.skipped_files.append(file_path)
                else:
                    files_to_process.append((file_path, file_size))
        
        if not files_to_process:
            error_msg = "No files could fit within memory constraints"
            logger.error(error_msg)
            if self.progress_callback:
                self.progress_callback(0, len(files_with_sizes), error_msg)
            return False
        
        # Start queue mode
        if self.progress_callback:
            self.progress_callback(15, len(files_to_process), f"Starting print queue mode for {len(files_to_process)} files...")
            
        logger.info(f"\nStarting async queue mode for {len(files_to_process)} files...")

        with StepTimer("Register listener P,L"):
            self.client.register_listener('P')

        # Register buffer monitoring listener for RTP, SP, L messages
        logger.info("Registering buffer status listener for RTP/SP/L monitoring...")
        self.client.add_status_listener(self._buffer_status_listener)

        self.client.set_expected_pages(len(files_to_process) * num_copies)

        with StepTimer("Start queue mode P,Q,P"):
            start_ok = self.client.print_queue_mode_start()
        if not start_ok:
            error_msg = "Failed to start print queue mode"
            logger.error(error_msg)
            if self.progress_callback:
                self.progress_callback(0, len(files_to_process), error_msg)
            return False
        
        # Use async pipelined processing
        if self.progress_callback:
            self.progress_callback(20, len(files_to_process), "Queuing files for printing...")
            
        with StepTimer("Queue files async"):
            success = self._queue_files_async_pipeline(files_to_process, num_copies, max_memory)
        
        if success and not self._cancelled:
            if self.progress_callback:
                self.progress_callback(90, len(files_to_process), "Finalizing print job...")
                
            logger.info("\nFinalizing print job...")
            with StepTimer("End queue mode P,Q,E"):
                end_ok = self.client.print_queue_mode_end()
            if end_ok:
                if self.progress_callback:
                    self.progress_callback(95, len(files_to_process), "Waiting for print completion...")
                    
                with StepTimer("Wait for print completion"):
                    done = self.client.wait_for_print_completion(
                        timeout_s=3600.0,
                        cancellation_check=lambda: self._cancelled
                    )
                
                # Check if cancelled during wait
                if self._cancelled:
                    logger.info("Print job cancelled during completion wait")
                    if self.progress_callback:
                        self.progress_callback(0, len(files_to_process), "Printing cancelled by user")
                    return False
                
                if not done:
                    logger.warning("Print completion wait timed out")
                    if self.progress_callback:
                        self.progress_callback(100, len(files_to_process), "Print completion timed out")
                    return False
                else:
                    if self.progress_callback:
                        self.progress_callback(100, len(files_to_process), "Printing completed successfully!")
                        
                logger.info("=" * 60)
                logger.info("PRINTING COMPLETED!")
                logger.info(f"Total files printed: {self.total_files_printed}")
                logger.info("=" * 60)
                return True
            else:
                error_msg = "Print queue execution failed"
                logger.error(error_msg)
                if self.progress_callback:
                    self.progress_callback(0, len(files_to_process), error_msg)
                return False
        else:
            if self._cancelled:
                error_msg = "Printing cancelled by user"
                logger.info(error_msg)
                if self.progress_callback:
                    self.progress_callback(0, len(files_to_process), error_msg)
            else:
                error_msg = "Failed to queue files"
                logger.error(error_msg)
                if self.progress_callback:
                    self.progress_callback(0, len(files_to_process), error_msg)
            return False
    
    def _queue_files_async_pipeline(self, files_to_process, num_copies, max_memory):
        """
        SCALABLE async pipelined queuing with proactive double-buffering

        Strategy:
        1. Maintain 2× batch_size in pipeline (double-buffering)
        2. Send batches proactively when buffer drops below threshold
        3. No arbitrary caps - scales with ANY batch size
        4. True batch boundaries for accurate reporting
        """
        total_files = len(files_to_process)
        files_sent = 0  # Track files actually sent
        files_acked = 0  # Track files acknowledged
        file_index = 0
        in_flight = 0  # Current files in pipeline
        errors_seen = 0
        max_errors = 10
        last_progress_report = 0
        batch_number = 0  # Track batch count

        # Use configured pipeline window (2× batch_size, no caps)
        max_in_flight = self.pipeline_window

        # Adaptive pipeline: only limit by total files if very small job
        if total_files < max_in_flight:
            max_in_flight = total_files
            logger.info(f"Small job: limiting pipeline to {max_in_flight} (total files)")

        logger.info(f"SCALABLE async pipeline mode: {total_files} files")
        logger.info(f"Pipeline window: {max_in_flight} files (2× batch_size, NO CAPS)")
        logger.info(f"Batch size: {self.batch_size} files per batch")
        logger.info(f"Buffer threshold: {self.buffer_threshold} files (send next batch when below)")
        logger.info(f"Proactive double-buffering: maintaining 2× batch in server buffer")

        print(f"[RIP_PRINT] ═══════════════════════════════════════════════")
        print(f"[RIP_PRINT] SCALABLE PIPELINE MODE")
        print(f"[RIP_PRINT] Total files: {total_files}")
        print(f"[RIP_PRINT] Batch size: {self.batch_size} files")
        print(f"[RIP_PRINT] Pipeline window: {max_in_flight} files (2× batch)")
        print(f"[RIP_PRINT] No arbitrary caps applied")
        print(f"[RIP_PRINT] ═══════════════════════════════════════════════")

        if self.progress_callback:
            self.progress_callback(15, total_files, f"Scalable pipeline: {self.batch_size} per batch, {max_in_flight} window")

        queue_start_time = time.perf_counter()

        # Track batches for TRUE batch reporting
        current_batch_sent = 0  # Files sent in current batch
        batches_sent = 0  # Number of complete batches sent

        # PROACTIVE DOUBLE-BUFFERING LOOP
        while file_index < total_files or in_flight > 0:

            # Check for cancellation
            if self._cancelled:
                logger.info("Printing cancelled during file queuing")
                return False

            # CRITICAL: Wait for RTP before first batch (prevents underrun)
            if batch_number == 0 and file_index == 0 and self.rtp_enabled:
                logger.info("═" * 60)
                logger.info("CRITICAL: Waiting for RTP before first batch...")
                logger.info("This ensures server buffer is ready to receive data")
                logger.info("═" * 60)

                rtp_ok = self._wait_for_rtp(timeout=self.rtp_timeout)
                if not rtp_ok:
                    logger.error("RTP not received - server may not be ready!")
                    logger.warning("Proceeding anyway, but underrun risk is HIGH")
                    if self.progress_callback:
                        self.progress_callback(10, total_files, "⚠️ RTP timeout - proceeding with caution")

            # PROACTIVE SENDING: Send next batch when pipeline has space
            # Conditions:
            # 1. Files remaining to send
            # 2. Pipeline has space (in_flight < buffer_threshold for double-buffering)
            can_send_batch = (file_index < total_files and in_flight < self.buffer_threshold)

            # FIX 4: Buffer level monitoring (warn only, don't block)
            # Blocking here can cause deadlocks if SP/L tracking is inaccurate
            # Changed from blocking to warning only
            if can_send_batch and self.buffer_level < -self.batch_size:
                logger.warning(f"⚠️ Buffer level negative ({self.buffer_level}), but continuing to send (non-blocking)")
                # Don't block - just warn and proceed

            if can_send_batch:
                # Calculate how many files to send in this batch
                files_remaining = total_files - file_index
                batch_to_send = min(self.batch_size, files_remaining)

                # Also ensure we don't overflow the pipeline window
                space_available = max_in_flight - in_flight
                batch_to_send = min(batch_to_send, space_available)

                if batch_to_send > 0:
                    logger.info(f"PROACTIVE: Sending batch #{batch_number + 1} ({batch_to_send} files), "
                               f"in_flight={in_flight}, threshold={self.buffer_threshold}")

                    batch_start_index = file_index
                    batch_sent_count = 0
                    batch_errors = 0
                    max_batch_errors = 5

                    # Send the entire batch at once
                    for i in range(batch_to_send):
                        if file_index >= total_files:
                            break

                        file_path, file_size = files_to_process[file_index]

                        # Ensure file_path is a Path object
                        if not isinstance(file_path, Path):
                            file_path = Path(file_path)

                        try:
                            # Verify file exists
                            if not file_path.exists():
                                logger.warning(f"File missing: {file_path.name}")
                                file_index += 1
                                batch_errors += 1
                                if batch_errors >= max_batch_errors:
                                    logger.error("Too many file errors in batch")
                                    break
                                continue

                            # Send file asynchronously
                            self.client.print_queue_add_item_async(file_path, num_copies)
                            in_flight += 1
                            batch_sent_count += 1
                            files_sent += 1
                            current_batch_sent += 1
                            self.total_files_sent = files_sent

                            file_index += 1

                            # Small delay every 10 files to avoid TCP buffer overflow
                            if batch_sent_count % 10 == 0:
                                time.sleep(0.001)

                        except Exception as e:
                            logger.error(f"Send error: {file_path.name} - {e}")
                            file_index += 1
                            batch_errors += 1
                            if batch_errors >= max_batch_errors:
                                logger.error("Too many send errors in batch")
                                break

                    # Report batch completion
                    if batch_sent_count > 0:
                        batch_number += 1
                        batches_sent += 1

                        elapsed = time.perf_counter() - queue_start_time
                        rate = files_sent / elapsed if elapsed > 0 else 0

                        logger.info(f"✓ Batch #{batch_number} sent: {batch_sent_count} files "
                                   f"({files_sent}/{total_files} total, {in_flight} in-flight, "
                                   f"{rate:.1f} files/sec)")

                        print(f"[RIP_PRINT] ✓ Batch #{batch_number}: {batch_sent_count} files → "
                             f"{files_sent}/{total_files} total ({files_sent * 100 // total_files}%)")

                        if self.progress_callback:
                            progress_percent = int(20 + (files_sent / total_files) * 70)
                            self.progress_callback(progress_percent, total_files,
                                                 f"Batch #{batch_number}: {batch_sent_count} files → {files_sent}/{total_files} queued")

                        current_batch_sent = 0  # Reset for next batch

            # ASYNC ACK PROCESSING: Process responses without blocking
            # This frees up pipeline slots for proactive sending
            if in_flight > 0:
                # Adaptive timeout based on state
                if file_index >= total_files:
                    # All files sent - use longer timeout to drain pipeline
                    timeout = 0.5
                elif in_flight >= max_in_flight:
                    # Pipeline full - wait a bit for ACKs
                    timeout = self.ack_wait_timeout
                else:
                    # Normal operation - quick check
                    timeout = 0.01

                msg_counts = self.client._process_messages_async(timeout)

                # Update in-flight counter
                acks = msg_counts['acks']
                completes = msg_counts['completes']
                errors = msg_counts['errors']

                freed = acks + completes
                if freed > 0:
                    in_flight = max(0, in_flight - freed)
                    files_acked += freed
                    self.total_files_acked = files_acked
                    logger.debug(f"ACKs: freed {freed} slots, {in_flight} in-flight, buffer_level={self.buffer_level}")

                # Error handling with adaptive throttling
                if errors > 0:
                    errors_seen += errors
                    error_rate = errors_seen / max(1, files_sent) if files_sent > 0 else 0

                    if errors_seen <= 3:
                        logger.warning(f"Errors: {errors} (total: {errors_seen}, rate: {error_rate:.1%})")

                    # Adaptive throttling for high error rates
                    if error_rate > 0.05:
                        logger.warning(f"High error rate ({error_rate:.1%}), throttling")
                        time.sleep(0.1)

                    # Stop if too many errors
                    if errors_seen > max_errors:
                        logger.error(f"Too many errors ({errors_seen}), aborting")
                        if self.progress_callback:
                            self.progress_callback(0, total_files, f"❌ Errors: {errors_seen}")
                        break

            # Periodic progress reporting (every 100 files or at end)
            if files_sent > last_progress_report:
                if files_sent % 100 == 0 or files_sent == total_files:
                    elapsed = time.perf_counter() - queue_start_time
                    rate = files_sent / elapsed if elapsed > 0 else 0
                    logger.info(f"Progress: {files_sent}/{total_files} "
                               f"({files_sent * 100 // total_files}%), "
                               f"rate: {rate:.1f} files/sec, in-flight: {in_flight}, "
                               f"buffer: {self.buffer_level}")
                    last_progress_report = files_sent

            # EXIT CONDITIONS

            # Success: all files sent and acknowledged
            if file_index >= total_files and in_flight == 0:
                logger.info("✓ All files sent and acknowledged")
                break

            # Safety timeouts
            elapsed_total = time.perf_counter() - queue_start_time

            # Timeout waiting for final ACKs (after all files sent)
            if file_index >= total_files and in_flight > 0:
                # Adaptive timeout based on batch size (larger batches need more time)
                ack_drain_timeout = min(300.0, max(60.0, self.batch_size / 10.0))

                if elapsed_total > ack_drain_timeout:
                    logger.warning(f"ACK drain timeout: {in_flight} pending after {elapsed_total:.1f}s, proceeding")
                    if self.progress_callback:
                        self.progress_callback(90, total_files, f"⚠️ {in_flight} files pending")
                    break

            # Ultimate safety: prevent infinite loop
            # Scale max time with job size (larger jobs need more time)
            max_total_time = min(3600.0, max(600.0, total_files / 10.0))

            if elapsed_total > max_total_time:
                logger.error(f"Maximum time exceeded ({elapsed_total:.1f}s), aborting")
                if self.progress_callback:
                    self.progress_callback(0, total_files, f"❌ Timeout: {int(elapsed_total)}s")
                return False

            # Prevent busy-waiting: sleep if can't send and waiting for ACKs
            if file_index >= total_files or in_flight >= max_in_flight:
                time.sleep(0.01)
        
        # FINAL SUMMARY
        self.total_files_printed = files_sent
        queue_elapsed = time.perf_counter() - queue_start_time

        logger.info(f"\n" + "=" * 60)
        logger.info(f"SCALABLE PIPELINE COMPLETE!")
        logger.info(f"=" * 60)
        logger.info(f"Files sent: {files_sent}/{total_files}")
        logger.info(f"Files acknowledged: {files_acked}")
        logger.info(f"Batches sent: {batches_sent}")
        logger.info(f"Avg batch size: {files_sent / max(1, batches_sent):.1f} files")
        if in_flight > 0:
            logger.warning(f"Files still in-flight: {in_flight} (proceeding)")
        logger.info(f"Time taken: {queue_elapsed:.1f} seconds")
        logger.info(f"Throughput: {files_sent / max(0.001, queue_elapsed):.1f} files/second")
        logger.info(f"Pipeline window: {self.pipeline_window} (2× batch, no caps)")
        logger.info(f"Buffer level at end: {self.buffer_level}")

        if errors_seen > 0:
            logger.warning(f"Total errors: {errors_seen}")

        print(f"\n[RIP_PRINT] ═══════════════════════════════════════════════")
        print(f"[RIP_PRINT] COMPLETE: {files_sent}/{total_files} files")
        print(f"[RIP_PRINT] Batches: {batches_sent} × ~{files_sent // max(1, batches_sent)} files")
        print(f"[RIP_PRINT] Throughput: {files_sent / max(0.001, queue_elapsed):.1f} files/sec")
        print(f"[RIP_PRINT] ═══════════════════════════════════════════════\n")

        return files_sent > 0
    
    def print_rip_folder_continuous(self, folder_path, pattern="*.bmp", recursive=False, num_copies=1, max_wait_time=300):
        """
        Print all RIP files from a folder with continuous monitoring for new files
        
        Args:
            folder_path: Path to folder containing RIP files
            pattern: File pattern to match (default "*.bmp")
            recursive: Whether to search subdirectories
            num_copies: Number of copies per file
            max_wait_time: Maximum time to wait for new files (seconds) before ending
            
        Returns:
            bool: True if successful
        """
        self._cancelled = False
        # Reset RTP and buffer tracking for new job
        self.rtp_received = False
        self.buffer_level = 0
        self.swathes_processed = 0
        self.labels_printed = 0
        self.continuous_mode = True
        self.processed_files.clear()
        self.last_scan_time = 0
        
        if self.progress_callback:
            self.progress_callback(0, 0, "Starting CONTINUOUS RIP folder print process...")
        
        logger.info("=" * 60)
        logger.info("STARTING CONTINUOUS RIP FOLDER PRINT PROCESS")
        logger.info("=" * 60)
        logger.info(f"Folder: {folder_path}")
        logger.info(f"Pattern: {pattern}")
        logger.info(f"Recursive: {recursive}")
        logger.info(f"Copies per file: {num_copies}")
        logger.info(f"Monitor interval: {self.monitor_interval}s")
        logger.info(f"Max wait time: {max_wait_time}s")
        
        # Start print queue mode once
        if self.progress_callback:
            self.progress_callback(5, 0, "Starting print queue mode...")
            
        with StepTimer("Register listener P,L"):
            self.client.register_listener('P')

        # Register buffer monitoring listener for RTP, SP, L messages
        logger.info("Registering buffer status listener for continuous mode...")
        self.client.add_status_listener(self._buffer_status_listener)

        with StepTimer("Start queue mode P,Q,P"):
            start_ok = self.client.print_queue_mode_start()
        if not start_ok:
            error_msg = "Failed to start print queue mode"
            logger.error(error_msg)
            if self.progress_callback:
                self.progress_callback(0, 0, error_msg)
            return False
        
        # Continuous monitoring loop
        total_files_processed = 0
        batch_number = 1
        last_activity_time = time.time()
        max_memory = self.client.pmb_memory_size * self.memory_safety_factor
        
        try:
            while not self._cancelled:
                # Discover new files
                current_files = self.discover_rip_files(folder_path, pattern, recursive)
                
                # Filter out already processed files
                new_files = []
                for file_path, file_size in current_files:
                    if file_path not in self.processed_files:
                        if file_size <= max_memory:
                            new_files.append((file_path, file_size))
                        else:
                            logger.warning(f"File too large, skipping: {Path(file_path).name}")
                            self.skipped_files.append(file_path)
                
                if new_files:
                    # Sort new files by natural order
                    new_files.sort(key=lambda x: natural_sort_key(x[0]))
                    
                    logger.info(f"Batch {batch_number}: Found {len(new_files)} new files to print")
                    
                    if self.progress_callback:
                        self.progress_callback(10, len(new_files), 
                                             f"Batch {batch_number}: Processing {len(new_files)} new files...")
                    
                    # Add new files to queue
                    files_added = self._add_files_to_queue_continuous(new_files, num_copies)
                    
                    if files_added > 0:
                        total_files_processed += files_added
                        batch_number += 1
                        last_activity_time = time.time()
                        
                        # Mark files as processed
                        for file_path, _ in new_files:
                            self.processed_files.add(file_path)
                        
                        logger.info(f"Batch {batch_number-1} complete: {files_added} files added to queue")
                        
                        if self.progress_callback:
                            self.progress_callback(20, total_files_processed, 
                                                 f"Total processed: {total_files_processed} files in {batch_number-1} batches")
                    else:
                        logger.warning(f"Batch {batch_number}: Failed to add files to queue")
                else:
                    # No new files found
                    if self.progress_callback:
                        self.progress_callback(20, total_files_processed, 
                                             f"Monitoring... (processed {total_files_processed} files, waiting for new files)")
                    
                    # Check if we should timeout
                    idle_time = time.time() - last_activity_time
                    if idle_time > max_wait_time:
                        logger.info(f"No new files for {max_wait_time}s, ending continuous mode")
                        break
                
                # Wait before next scan
                time.sleep(self.monitor_interval)
            
            # End print queue mode
            if not self._cancelled:
                logger.info("Ending continuous print queue mode...")
                with StepTimer("End queue mode P,Q,E"):
                    end_ok = self.client.print_queue_mode_end()
                
                if end_ok:
                    if self.progress_callback:
                        self.progress_callback(90, total_files_processed, "Waiting for final print completion...")
                    
                    with StepTimer("Wait for final print completion"):
                        done = self.client.wait_for_print_completion(
                            timeout_s=3600.0,
                            cancellation_check=lambda: self._cancelled
                        )
                    
                    # Check if cancelled during wait
                    if self._cancelled:
                        logger.info("Continuous print job cancelled during completion wait")
                        if self.progress_callback:
                            self.progress_callback(0, total_files_processed, "Continuous printing cancelled by user")
                        return False
                    
                    if done:
                        if self.progress_callback:
                            self.progress_callback(100, total_files_processed, 
                                                 f"Continuous printing completed! Total: {total_files_processed} files")
                        
                        logger.info("=" * 60)
                        logger.info("CONTINUOUS PRINTING COMPLETED!")
                        logger.info(f"Total files processed: {total_files_processed}")
                        logger.info(f"Total batches: {batch_number-1}")
                        logger.info("=" * 60)
                        
                        self.total_files_printed = total_files_processed
                        return True
                    else:
                        logger.warning("Final print completion wait timed out")
                        return False
                else:
                    logger.error("Failed to end print queue mode")
                    return False
            else:
                logger.info("Continuous printing cancelled by user")
                return False
                
        except Exception as e:
            logger.error(f"Continuous printing error: {e}")
            return False
        finally:
            self.continuous_mode = False
    
    def _add_files_to_queue_continuous(self, new_files, num_copies):
        """
        Add new files to the print queue in continuous mode
        Returns number of files successfully added
        """
        files_added = 0
        max_memory = self.client.pmb_memory_size * self.memory_safety_factor
        
        try:
            for file_path, file_size in new_files:
                if self._cancelled:
                    break
                
                # Check memory constraints
                if file_size > max_memory:
                    logger.warning(f"File too large for continuous mode: {Path(file_path).name}")
                    self.skipped_files.append(file_path)
                    continue
                
                # Add to queue
                try:
                    self.client.print_queue_add_item_async(file_path, num_copies)
                    files_added += 1
                    
                    # Small delay to avoid overwhelming the server
                    if files_added % 10 == 0:
                        time.sleep(0.01)
                        
                except Exception as e:
                    logger.error(f"Failed to add file to queue: {file_path} - {e}")
                    self.failed_files.append(file_path)
            
            # Process any pending acknowledgments
            if files_added > 0:
                time.sleep(0.1)  # Brief pause for acknowledgments
                msg_counts = self.client._process_messages_async(0.1)
                logger.debug(f"Continuous mode: {msg_counts}")
            
            return files_added
            
        except Exception as e:
            logger.error(f"Error in continuous file queuing: {e}")
            return files_added
    
    def get_summary(self):
        """Get summary of the print job"""
        return {
            'total_files_printed': self.total_files_printed,
            'failed_files': len(self.failed_files),
            'skipped_files': len(self.skipped_files),
            'failed_file_list': [Path(f).name for f in self.failed_files],
            'skipped_file_list': [Path(f).name for f in self.skipped_files]
        }


def main():
    """Main function for printing RIP folder"""
    
    # Configuration
    SERVER_HOST = 'localhost'
    SERVER_PORT = 2000
    
    # RIP folder configuration
    RIP_FOLDER = r"C:\Users\Kridwinn\Music\new_2"
    
    # Printing configuration
    config = {
        'pattern': "*.bmp",
        'recursive': False,
        'num_copies': 1,
    }
    
    # Create client
    client = GISPrintServerClient(SERVER_HOST, SERVER_PORT)
    
    try:
        # Connect to Print Server
        logger.info("Connecting to Print Server...")
        if not client.connect():
            logger.error("Failed to connect to Print Server")
            return
        
        # Create RIP folder printer
        printer = RIPFolderPrinter(client)
        
        # Print the RIP folder
        success = printer.print_rip_folder(
            RIP_FOLDER,
            pattern=config['pattern'],
            recursive=config['recursive'],
            num_copies=config['num_copies']
        )
        
        # Show summary
        summary = printer.get_summary()
        logger.info("\n" + "=" * 60)
        logger.info("PRINT JOB SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Files printed: {summary['total_files_printed']}")
        logger.info(f"Failed files: {summary['failed_files']}")
        logger.info(f"Skipped files: {summary['skipped_files']}")
        
        if summary['failed_file_list']:
            logger.info("\nFailed files list:")
            for fname in summary['failed_file_list']:
                logger.info(f"  - {fname}")
        
        if summary['skipped_file_list']:
            logger.info("\nSkipped files list (exceeded memory):")
            for fname in summary['skipped_file_list']:
                logger.info(f"  - {fname}")
        
        if not success:
            logger.warning("Some operations failed")
            
    except KeyboardInterrupt:
        logger.warning("Interrupted by user, aborting...")
        client.abort_print()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        client.abort_print()
    finally:
        client.close()


class GUIRipPrinter:
    """GUI-friendly wrapper for RIP printing with Qt signals"""
    
    def __init__(self, host='localhost', port=2000):
        self.host = host
        self.port = port
        self.client = None
        self.printer = None
        
    def connect(self):
        """Connect to the print server"""
        try:
            self.client = GISPrintServerClient(self.host, self.port)
            return self.client.connect()
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def print_rip_folder_with_callback(self, folder_path, progress_callback, 
                                     pattern="*.bmp", recursive=False, num_copies=1, files_override=None, batch_size=10):
        """Print RIP folder with progress callback"""
        if not self.client:
            if not self.connect():
                return False
        
        # Create printer with progress callback
        self.printer = RIPFolderPrinter(self.client, progress_callback, batch_size=batch_size)
        
        try:
            return self.printer.print_rip_folder(folder_path, pattern, recursive, num_copies, files_override=files_override)
        except Exception as e:
            logger.error(f"Print error: {e}")
            return False
    
    def print_rip_folder_continuous_with_callback(self, folder_path, progress_callback, 
                                                pattern="*.bmp", recursive=False, num_copies=1, max_wait_time=300, batch_size=10):
        """Print RIP folder continuously with progress callback"""
        if not self.client:
            if not self.connect():
                return False
        
        # Create printer with progress callback
        self.printer = RIPFolderPrinter(self.client, progress_callback, batch_size=batch_size)
        
        try:
            return self.printer.print_rip_folder_continuous(folder_path, pattern, recursive, num_copies, max_wait_time)
        except Exception as e:
            logger.error(f"Continuous print error: {e}")
            return False
    
    def cancel(self):
        """Cancel the printing process"""
        if self.printer:
            self.printer.cancel()
    
    def close(self):
        """Close the connection"""
        if self.client:
            self.client.close()


if __name__ == "__main__":
    main()