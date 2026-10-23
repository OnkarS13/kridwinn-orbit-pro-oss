import socket
import os
import time
from pathlib import Path
from collections import deque
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import queue
import threading

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Error code definitions
ERROR_CODES = {
    0: "Success",
    -1: "Unknown command",
    -5: "Incorrect parameters",
    -8: "Print Server suspended",
    -100: "General Render Engine failure",
    -101: "Render Engine busy",
    -102: "Failed to load Render Engine configuration",
    -201: "Print Controller busy",
    -202: "General Print Controller failure",
    -210: "Print failed",
    -216: "Print Controller not initialized",
    -220: "Failed to add item to queue",
    -225: "Failed to wait for print to initialize",
}

class GISPrintServerClient:
    """Thread-safe client for GIS Print Server with retry logic"""
    
    def __init__(self, host='localhost', port=2000):
        self.host = host
        self.port = port
        self.main_socket = None
        self.connected = False
        self.message_buffer = deque()
        self.socket_lock = Lock()  # Thread safety for socket operations

    def connect(self):
        """Connect to Print Server"""
        try:
            self.main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.main_socket.connect((self.host, self.port))
            
            response = self._receive_single_message(self.main_socket)
            logger.info(f"Connection response: {response}")
            
            if "N,C" in response:
                self.connected = True
                logger.info("Connected successfully")
                return True
            else:
                logger.error("Connection failed")
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def _receive_single_message(self, sock):
        """Receive a single message"""
        response = b""
        while b'\n' not in response:
            chunk = sock.recv(1024)
            if not chunk:
                break
            response += chunk
        return response.decode().strip()

    def _receive_messages(self):
        """Receive and handle multiple messages"""
        if not self.main_socket:
            raise Exception("Not connected to server")

        # Check for buffered messages first
        buffered_messages = []
        while self.message_buffer:
            buffered_messages.append(self.message_buffer.popleft())

        if buffered_messages:
            return buffered_messages

        # Read new messages
        messages = []
        buffer = b""

        # Set a small timeout to avoid blocking indefinitely
        self.main_socket.settimeout(0.5)

        try:
            while True:
                try:
                    chunk = self.main_socket.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                except socket.timeout:
                    break

            # Split by newlines
            if buffer:
                lines = buffer.decode().split('\n')
                for line in lines:
                    line = line.strip()
                    if line:
                        messages.append(line)
                        logger.debug(f"Received: {line}")

        finally:
            self.main_socket.settimeout(None)

        return messages

    def _parse_info_message(self, message):
        """Parse information messages"""
        parts = message.split(',')
        if len(parts) < 3:
            return

        msg_type = parts[2]

        # Status message
        if msg_type == 'S' and len(parts) >= 5:
            status_text = parts[3]
            status_code = int(parts[4])
            logger.debug(f"Status: {status_text} (code: {status_code})")

        # Current label
        elif msg_type == 'L' and len(parts) >= 4:
            label_num = int(parts[3])
            logger.debug(f"Processing page {label_num}")

    def _send_message(self, message):
        """Send message to server (thread-safe)"""
        with self.socket_lock:
            message_with_newline = message + '\n'
            self.main_socket.send(message_with_newline.encode())
            logger.debug(f"Sent: {message}")

    def _wait_for_complete_with_info(self):
        """Wait for completion with proper message handling"""
        ack_id = None

        while True:
            with self.socket_lock:
                messages = self._receive_messages()

            for message in messages:
                # Acknowledgement
                if message.startswith("A,"):
                    parts = message.split(',')
                    ack_id = parts[1]
                    logger.debug(f"Got acknowledgement ID: {ack_id}")

                # Information message
                elif message.startswith("I,"):
                    self._parse_info_message(message)

                # Complete message
                elif message.startswith("C,"):
                    parts = message.split(',')
                    cmd_id = parts[1]
                    error_code = int(parts[2])

                    if error_code == 0:
                        logger.debug(f"Command {cmd_id} completed successfully")
                        return True, error_code
                    else:
                        error_msg = ERROR_CODES.get(error_code, f"Unknown error: {error_code}")
                        logger.warning(f"Command {cmd_id} failed: {error_msg}")
                        return False, error_code

    def render_image_with_retry(self, input_image_path, output_rip_path, max_retries=5):
        """Render an image to RIP format with retry logic for busy errors"""
        input_path = os.path.abspath(input_image_path)
        output_path = os.path.abspath(output_rip_path)

        if output_path.endswith('.bmp'):
            output_path = output_path[:-4]

        retry_delay = 2.0  # Starting delay in seconds
        
        for attempt in range(max_retries):
            command = f"R,B,{input_path},{output_path}.bmp"
            self._send_message(command)
            success, error_code = self._wait_for_complete_with_info()
            
            if success:
                return True
            elif error_code == -101:  # Render Engine busy
                if attempt < max_retries - 1:
                    logger.info(f"Render Engine busy, waiting {retry_delay}s before retry {attempt + 2}/{max_retries}...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30.0)  # Cap at 30 seconds
                else:
                    logger.error(f"Render Engine still busy after {max_retries} attempts")
                    return False
            else:
                # For other errors, don't retry
                logger.error(f"Render failed with error code {error_code}")
                return False
        
        return False

    def close(self):
        """Close connection"""
        if self.main_socket:
            with self.socket_lock:
                self.main_socket.close()
        self.connected = False
        logger.info("Connection closed")


class ClientPool:
    """Manages a pool of GIS Print Server clients for parallel processing (single server)"""
    
    def __init__(self, host='localhost', port=2000, pool_size=4):
        self.host = host
        self.port = port
        self.pool_size = pool_size
        self.clients = queue.Queue()
        self.all_clients = []
        
    def initialize(self):
        """Create and connect all clients in the pool"""
        logger.info(f"Initializing client pool with {self.pool_size} connections...")
        
        for i in range(self.pool_size):
            client = GISPrintServerClient(self.host, self.port)
            if client.connect():
                self.clients.put(client)
                self.all_clients.append(client)
                logger.info(f"Client {i+1}/{self.pool_size} connected")
                # Add small delay between connections
                time.sleep(0.1)
            else:
                logger.error(f"Failed to connect client {i+1}")
                # Close any connected clients and fail
                self.close_all()
                return False
        
        logger.info(f"Client pool initialized with {len(self.all_clients)} connections")
        return len(self.all_clients) > 0
    
    def get_client(self, timeout=None):
        """Get an available client from the pool"""
        return self.clients.get(timeout=timeout)
    
    def return_client(self, client):
        """Return a client to the pool"""
        self.clients.put(client)
    
    def close_all(self):
        """Close all client connections"""
        for client in self.all_clients:
            try:
                client.close()
            except:
                pass
        logger.info("All client connections closed")


class MultiServerClientPool:
    """Manages multiple server connections with distributed client pools"""
    
    def __init__(self, server_configs, connections_per_server=4):
        """
        Initialize multi-server client pool
        
        Args:
            server_configs: List of dicts with 'host', 'port', 'name' keys
            connections_per_server: Number of connections per server
        """
        self.server_configs = server_configs
        self.connections_per_server = connections_per_server
        self.server_pools = {}  # {server_id: ClientPool}
        self.server_queues = {}  # {server_id: queue of clients}
        self.all_clients = []
        self.server_index = 0  # For round-robin distribution
        self.server_ids = []
        self.distribution_lock = Lock()
        
    def initialize(self):
        """Initialize all server pools"""
        logger.info(f"Initializing multi-server pool with {len(self.server_configs)} servers...")
        
        for i, config in enumerate(self.server_configs):
            server_id = config.get('id', f"server_{i}")
            host = config['host']
            port = config['port']
            name = config.get('name', f"{host}:{port}")
            
            logger.info(f"Connecting to {name} ({host}:{port}) with {self.connections_per_server} connections...")
            
            pool = ClientPool(host, port, pool_size=self.connections_per_server)
            if not pool.initialize():
                logger.error(f"Failed to initialize pool for {name}")
                self.close_all()
                return False
            
            self.server_pools[server_id] = pool
            self.server_queues[server_id] = pool.clients
            self.server_ids.append(server_id)
            self.all_clients.extend(pool.all_clients)
            
            logger.info(f"✅ Server '{name}' connected with {self.connections_per_server} connections")
        
        total_connections = len(self.all_clients)
        logger.info(f"Multi-server pool initialized: {len(self.server_pools)} servers, {total_connections} total connections")
        return len(self.server_pools) > 0
    
    def get_next_server_id(self):
        """Get next server ID using round-robin"""
        with self.distribution_lock:
            if not self.server_ids:
                return None
            server_id = self.server_ids[self.server_index]
            self.server_index = (self.server_index + 1) % len(self.server_ids)
            return server_id
    
    def get_client_from_server(self, server_id, timeout=None):
        """Get client from specific server"""
        if server_id not in self.server_queues:
            raise ValueError(f"Unknown server ID: {server_id}")
        return self.server_queues[server_id].get(timeout=timeout)
    
    def return_client_to_server(self, server_id, client):
        """Return client to specific server"""
        if server_id in self.server_queues:
            self.server_queues[server_id].put(client)
    
    def get_client(self, timeout=None):
        """Get client from any available server (round-robin)"""
        server_id = self.get_next_server_id()
        if server_id:
            return self.get_client_from_server(server_id, timeout), server_id
        return None, None
    
    def return_client(self, client, server_id):
        """Return client to its server"""
        self.return_client_to_server(server_id, client)
    
    def close_all(self):
        """Close all server connections"""
        for server_id, pool in self.server_pools.items():
            try:
                pool.close_all()
                logger.info(f"Closed connections for server: {server_id}")
            except Exception as e:
                logger.error(f"Error closing pool for {server_id}: {e}")
        logger.info("All multi-server connections closed")
    
    def get_total_connections(self):
        """Get total number of connections across all servers"""
        return len(self.all_clients)
    
    def get_server_count(self):
        """Get number of servers"""
        return len(self.server_pools)


class ServerDistributor:
    """Handles distribution of work items across multiple servers"""
    
    def __init__(self, server_configs, distribution_mode='alternate'):
        """
        Initialize distributor
        
        Args:
            server_configs: List of server configuration dicts
            distribution_mode: 'alternate' (round-robin) or 'chunks'
        """
        self.server_configs = server_configs
        self.distribution_mode = distribution_mode
        self.server_ids = [cfg.get('id', f"server_{i}") for i, cfg in enumerate(server_configs)]
        self.current_index = 0
        self.lock = Lock()
    
    def distribute_items(self, items):
        """
        Distribute items across servers based on distribution mode
        
        Args:
            items: List of items to distribute
        
        Returns:
            Dict mapping server_id to list of items
        """
        if not items or not self.server_ids:
            return {}
        
        distribution = {sid: [] for sid in self.server_ids}
        
        if self.distribution_mode == 'alternate':
            # Round-robin: alternate items across servers
            for i, item in enumerate(items):
                server_id = self.server_ids[i % len(self.server_ids)]
                distribution[server_id].append(item)
        
        elif self.distribution_mode == 'chunks':
            # Divide into chunks
            num_servers = len(self.server_ids)
            chunk_size = len(items) // num_servers
            remainder = len(items) % num_servers
            
            start_idx = 0
            for i, server_id in enumerate(self.server_ids):
                # Add 1 extra item to first 'remainder' servers
                size = chunk_size + (1 if i < remainder else 0)
                end_idx = start_idx + size
                distribution[server_id] = items[start_idx:end_idx]
                start_idx = end_idx
        
        return distribution
    
    def get_next_server_id(self):
        """Get next server ID for round-robin allocation"""
        with self.lock:
            if not self.server_ids:
                return None
            server_id = self.server_ids[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.server_ids)
            return server_id


class ParallelImageRipProcessor:
    """Processes images from a folder to RIP files using parallel processing with error handling.
    Supports cancellation and optional progress callbacks.
    """
    
    # Supported image extensions
    SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    
    def __init__(self, client_pool, output_dir="rip_output", max_workers=4):
        self.client_pool = client_pool
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.progress_lock = Lock()
        self.processed_count = 0
        self.failed_images = []
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10
        
        # Serial number counter for file naming
        self.serial_counter = 0
        self.serial_lock = Lock()
        
        # Cancellation support
        self.cancellation_callback = None
        self.cancelled = False
        
        # Adaptive concurrency control
        self.busy_error_count = 0
        self.success_count = 0
        self.max_busy_errors = 1  # React immediately on first error
        self.success_threshold = 5  # Fewer successes needed to recover (was 10)
        self.current_workers = max_workers
        self.min_workers = 2
        self.max_workers_limit = max_workers + 4  # Can grow beyond initial
        self.worker_adjustment_lock = Lock()
        self.last_adjustment_time = time.time()
        self.adjustment_cooldown = 2.0  # Fast response: only 2 seconds between adjustments
        
        # Adaptive delay control with learning
        self.base_delay = 0.20  # Base delay in seconds (will adapt)
        self.original_base_delay = 0.20  # Store original for reference
        self.current_delay = self.base_delay
        self.delay_increment = 0.01  # 10ms increment
        self.min_delay = 0.10  # Minimum 100ms
        self.max_delay = 0.50  # Maximum 500ms
        
        # Learning mechanism for optimal delay
        self.stable_delay_count = 0  # Count consecutive successes at current delay
        self.stability_threshold = 15  # Need 15 successes to learn new base
        self.learned_base = False  # Track if we've learned optimal delay
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        logger.info(f"Output directory: {self.output_dir}")
    
    def set_cancellation_callback(self, callback):
        """Set callback function to check if processing should be cancelled"""
        self.cancellation_callback = callback
    
    def cancel_processing(self):
        """Cancel ongoing processing"""
        self.cancelled = True
    
    def _is_cancelled(self):
        """Check if processing should be cancelled"""
        if self.cancelled:
            return True
        if self.cancellation_callback and self.cancellation_callback():
            self.cancelled = True
            return True
        return False
    
    def _adjust_concurrency_on_busy_error(self):
        """Reduce concurrency and increase delay immediately on busy error"""
        with self.worker_adjustment_lock:
            current_time = time.time()
            
            # Reset stability counter on error - we're not stable anymore
            self.stable_delay_count = 0
            
            # Only adjust if cooldown period has passed
            if current_time - self.last_adjustment_time < self.adjustment_cooldown:
                return
            
            self.busy_error_count += 1
            
            if self.busy_error_count >= self.max_busy_errors:
                # Reduce workers aggressively
                if self.current_workers > self.min_workers:
                    old_workers = self.current_workers
                    # Reduce by 3 workers for faster response (was 2)
                    self.current_workers = max(self.min_workers, self.current_workers - 3)
                    
                    # Increase delay by 20ms for more breathing room (was 10ms)
                    old_delay = self.current_delay
                    self.current_delay = min(self.max_delay, self.current_delay + (self.delay_increment * 2))
                    
                    logger.warning(f"⚠️  Render engine BUSY! Immediate action: Workers {old_workers} → {self.current_workers}, "
                                 f"Delay {old_delay:.3f}s → {self.current_delay:.3f}s")
                    self.last_adjustment_time = current_time
                    self.busy_error_count = 0  # Reset counter
                    self.success_count = 0     # Reset success counter

    def _on_successful_render(self):
        """Track successful renders and potentially increase concurrency and reduce delay"""
        with self.worker_adjustment_lock:
            current_time = time.time()
            
            # Track stability for learning optimal delay
            self.stable_delay_count += 1
            
            # Learning mechanism: If stable at a higher delay, learn it as new base
            if (not self.learned_base and 
                self.stable_delay_count >= self.stability_threshold and 
                self.current_delay > self.base_delay):
                # We've been stable at this higher delay - learn it!
                old_base = self.base_delay
                self.base_delay = self.current_delay
                self.learned_base = True
                logger.info(f"🎓 LEARNED optimal delay: {old_base:.3f}s → {self.base_delay:.3f}s "
                          f"(stable for {self.stability_threshold} successes)")
                logger.info(f"   This PDF needs {self.base_delay:.3f}s minimum - won't try to go lower")
            
            # Only adjust if cooldown period has passed
            if current_time - self.last_adjustment_time < self.adjustment_cooldown:
                return
            
            self.busy_error_count = max(0, self.busy_error_count - 1)
            self.success_count += 1
            
            # Increase workers and decrease delay if we have successes and no recent busy errors
            if (self.success_count >= self.success_threshold and 
                self.busy_error_count == 0 and 
                self.current_workers < self.max_workers_limit):
                
                old_workers = self.current_workers
                # Increase by 2 workers for faster recovery (was 1)
                self.current_workers = min(self.max_workers_limit, self.current_workers + 2)
                
                # Decrease delay by 20ms for faster recovery, but NOT below learned base
                old_delay = self.current_delay
                self.current_delay = max(self.base_delay, self.current_delay - (self.delay_increment * 2))
                
                logger.info(f"✅ Stable performance! Increasing workers: {old_workers} → {self.current_workers}, "
                          f"Decreasing delay: {old_delay:.3f}s → {self.current_delay:.3f}s (base: {self.base_delay:.3f}s)")
                self.last_adjustment_time = current_time
                self.success_count = 0  # Reset counter

    def get_current_worker_count(self):
        """Get current optimal worker count"""
        with self.worker_adjustment_lock:
            return self.current_workers
    
    def get_current_delay(self):
        """Get current adaptive delay"""
        with self.worker_adjustment_lock:
            return self.current_delay
    
    def _get_next_serial_number(self):
        """Get next serial number for file naming (thread-safe)"""
        with self.serial_lock:
            self.serial_counter += 1
            return self.serial_counter

    def process_folder(self, folder_path, keep_structure=False, delay_between_submissions=0.1):
        """
        Process all images in a folder to RIP files using parallel processing with adaptive delay
        
        Args:
            folder_path: Path to folder containing images
            keep_structure: If True, maintains subdirectory structure in output
            delay_between_submissions: Initial delay in seconds between job submissions (will adapt)
        
        Returns:
            True if all images processed successfully
        """
        folder_path = Path(folder_path)
        if not folder_path.exists() or not folder_path.is_dir():
            logger.error(f"Invalid folder path: {folder_path}")
            return False
        
        # Set initial base delay from parameter (reset learning for new batch)
        self.base_delay = delay_between_submissions
        self.original_base_delay = delay_between_submissions
        self.current_delay = self.base_delay
        self.learned_base = False
        self.stable_delay_count = 0
            
        logger.info(f"Processing image folder: {folder_path}")
        
        # Collect all image files
        image_files = self._collect_images(folder_path)
        
        if not image_files:
            logger.warning(f"No supported images found in {folder_path}")
            return False
        
        total_images = len(image_files)
        logger.info(f"Found {total_images} images to process")
        logger.info(f"Using {self.max_workers} worker threads")
        
        # Reset counters
        self.processed_count = 0
        self.failed_images = []
        
        # Process images in parallel with controlled submission
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks with delays
            futures = {}
            for i, image_path in enumerate(image_files):
                # Add adaptive delay between submissions to avoid overwhelming the server
                if i > 0:
                    time.sleep(self.get_current_delay())
                    
                future = executor.submit(
                    self._process_single_image_with_retry,
                    image_path,
                    folder_path,
                    keep_structure,
                    total_images
                )
                futures[future] = image_path
            
            # Wait for completion and collect results
            for future in as_completed(futures):
                image_path = futures[future]
                try:
                    success = future.result()
                    if not success:
                        with self.progress_lock:
                            self.failed_images.append(image_path)
                except Exception as e:
                    logger.error(f"Exception processing {image_path}: {e}")
                    with self.progress_lock:
                        self.failed_images.append(image_path)
        
        # Report results
        successful_count = total_images - len(self.failed_images)
        logger.info(f"Processing completed: {successful_count}/{total_images} images RIPped successfully")
        
        if self.failed_images:
            logger.error(f"Failed to process {len(self.failed_images)} images:")
            for img in self.failed_images:
                logger.error(f"  - {img}")
        
        return len(self.failed_images) == 0

    def process_folder_with_cancellation(self, folder_path, keep_structure=False, 
                                       delay_between_submissions=0.1, cancellation_check=None, rotation_deg=0):
        """Process folder with cancellation support and adaptive delay"""
        # Store the cancellation check
        if cancellation_check:
            self.cancellation_callback = cancellation_check
        
        # Set initial base delay from parameter (reset learning for new batch)
        self.base_delay = delay_between_submissions
        self.original_base_delay = delay_between_submissions
        self.current_delay = self.base_delay
        self.learned_base = False
        self.stable_delay_count = 0
        
        folder_path = Path(folder_path)
        if not folder_path.exists() or not folder_path.is_dir():
            logger.error(f"Invalid folder path: {folder_path}")
            return False
            
        logger.info(f"Processing image folder with cancellation support: {folder_path}")
        logger.info(f"Starting with: Workers={self.current_workers}, Delay={self.current_delay:.3f}s (will learn optimal)")
        
        # Collect all image files
        image_files = self._collect_images(folder_path)
        
        if not image_files:
            logger.warning(f"No supported images found in {folder_path}")
            return False
        
        total_images = len(image_files)
        logger.info(f"Found {total_images} images to process")
        logger.info(f"Using {self.max_workers} worker threads")
        
        # Reset counters
        self.processed_count = 0
        self.failed_images = []
        self.cancelled = False
        
        # Process images with cancellation checks
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            for i, image_path in enumerate(image_files):
                # Check cancellation before submitting new work
                if self._is_cancelled():
                    logger.info("Processing cancelled by user")
                    break
                
                if i > 0:
                    # Use adaptive delay that adjusts based on server load
                    time.sleep(self.get_current_delay())
                    
                future = executor.submit(
                    self._process_single_image_with_cancellation,
                    image_path, folder_path, keep_structure, total_images, rotation_deg
                )
                futures[future] = image_path
            
            # Wait for completion with cancellation checks
            for future in as_completed(futures):
                if self._is_cancelled():
                    logger.info("Cancelling remaining tasks...")
                    # Cancel remaining futures
                    for remaining_future in futures:
                        if not remaining_future.done():
                            remaining_future.cancel()
                    break
                
                image_path = futures[future]
                try:
                    success = future.result()
                    if not success:
                        with self.progress_lock:
                            self.failed_images.append(image_path)
                except Exception as e:
                    logger.error(f"Exception processing {image_path}: {e}")
                    with self.progress_lock:
                        self.failed_images.append(image_path)
        
        # Report results
        successful_count = total_images - len(self.failed_images)
        if self._is_cancelled():
            logger.info(f"Processing cancelled: {successful_count}/{total_images} images RIPped before cancellation")
        else:
            logger.info(f"Processing completed: {successful_count}/{total_images} images RIPped successfully")
        
        if self.failed_images:
            logger.error(f"Failed to process {len(self.failed_images)} images:")
            for img in self.failed_images:
                logger.error(f"  - {img}")
        
        return not self._is_cancelled() and len(self.failed_images) == 0

    def process_specific_images_with_cancellation(self, image_list, base_folder, keep_structure=False, 
                                                   delay_between_submissions=0.1, cancellation_check=None, rotation_deg=0):
        """
        Process a specific list of images (for retry logic).
        
        Args:
            image_list: List of Path objects for images to process
            base_folder: Base folder path for structure reference
            keep_structure: If True, maintains subdirectory structure in output
            delay_between_submissions: Delay in seconds between job submissions
            cancellation_check: Function to check if processing should be cancelled
        
        Returns:
            True if all images processed successfully
        """
        # Store the cancellation check
        if cancellation_check:
            self.cancellation_callback = cancellation_check
        
        # KEEP learned base delay for retries (don't reset learning)
        # Only update current_delay if it's lower than what we need
        if self.current_delay < delay_between_submissions:
            self.current_delay = delay_between_submissions
        # Keep base_delay as learned value
        
        base_folder = Path(base_folder)
        total_images = len(image_list)
        
        if total_images == 0:
            logger.info("No images to process")
            return True
        
        logger.info(f"Processing {total_images} specific images (retry)")
        if self.learned_base:
            logger.info(f"Using learned optimal delay: {self.base_delay:.3f}s (current: {self.current_delay:.3f}s)")
        
        # Reset counters for this batch
        with self.progress_lock:
            self.failed_images = []
        self.cancelled = False
        
        # Process images with cancellation checks
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            for i, image_path in enumerate(image_list):
                # Check cancellation before submitting new work
                if self._is_cancelled():
                    logger.info("Processing cancelled by user")
                    break
                
                if i > 0:
                    # Use adaptive delay that adjusts based on server load
                    time.sleep(self.get_current_delay())
                    
                future = executor.submit(
                    self._process_single_image_with_cancellation,
                    image_path, base_folder, keep_structure, total_images, rotation_deg
                )
                futures[future] = image_path
            
            # Wait for completion with cancellation checks
            for future in as_completed(futures):
                if self._is_cancelled():
                    logger.info("Cancelling remaining tasks...")
                    break
                
                image_path = futures[future]
                try:
                    success = future.result()
                    if not success:
                        with self.progress_lock:
                            self.failed_images.append(image_path)
                except Exception as e:
                    logger.error(f"Exception processing {image_path}: {e}")
                    with self.progress_lock:
                        self.failed_images.append(image_path)
        
        # Report results
        successful_count = total_images - len(self.failed_images)
        if self._is_cancelled():
            logger.info(f"Retry cancelled: {successful_count}/{total_images} images RIPped before cancellation")
        else:
            logger.info(f"Retry completed: {successful_count}/{total_images} images RIPped successfully")
        
        if self.failed_images:
            logger.warning(f"Still failed: {len(self.failed_images)} images after retry")
        
        return not self._is_cancelled() and len(self.failed_images) == 0

    def _process_single_image_with_cancellation(self, image_path, base_folder, keep_structure, total_images, rotation_deg=0):
        """Process single image with cancellation check and optional rotation"""
        # Check cancellation before starting
        if self._is_cancelled():
            return False
        
        # Apply rotation if needed (for retry logic)
        if rotation_deg != 0:
            return self._process_single_image_with_rotation_and_retry(image_path, base_folder, keep_structure, total_images, rotation_deg)
        else:
            # The actual processing continues as before
            return self._process_single_image_with_retry(image_path, base_folder, keep_structure, total_images)

    def _process_single_image_with_retry(self, image_path, base_folder, keep_structure, total_images):
        """Process a single image using a client from the pool with retry logic"""
        # Check if we should pause due to too many failures
        with self.progress_lock:
            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.warning(f"Too many consecutive failures ({self.consecutive_failures}), pausing for 10 seconds...")
                time.sleep(10)
                self.consecutive_failures = 0

        # Get a client from the pool (wait up to 60 seconds)
        client = None
        try:
            client = self.client_pool.get_client(timeout=60)
        except queue.Empty:
            logger.error(f"Timeout waiting for available client for {image_path.name}")
            return False
        
        try:
            # Determine output path with serial number
            serial_number = self._get_next_serial_number()

            if keep_structure:
                relative_path = image_path.relative_to(base_folder)
                output_subdir = self.output_dir / relative_path.parent
                output_subdir.mkdir(parents=True, exist_ok=True)
                rip_filename = f"{image_path.stem}_rip_{serial_number}.bmp"
                rip_path = output_subdir / rip_filename
            else:
                rip_filename = f"{image_path.stem}_rip_{serial_number}.bmp"
                rip_path = self.output_dir / rip_filename
            
            # RIP the image with retry logic
            success = client.render_image_with_retry(str(image_path), str(rip_path), max_retries=3)
            
            # Provide feedback to adaptive system
            if success:
                self._on_successful_render()
            else:
                # Check if it was a busy error by attempting to get the last error
                # This is a simplified approach - you might want to enhance error tracking
                self._adjust_concurrency_on_busy_error()
            
            # Update progress
            with self.progress_lock:
                self.processed_count += 1
                current_count = self.processed_count
            
            if success:
                logger.info(f"[{current_count}/{total_images}] RIPped: {image_path.name}")
                with self.progress_lock:
                    self.consecutive_failures = 0  # Reset on success
            else:
                logger.error(f"[{current_count}/{total_images}] Failed: {image_path.name}")
                with self.progress_lock:
                    self.consecutive_failures += 1
            
            return success
            
        finally:
            # Always return the client to the pool
            if client:
                self.client_pool.return_client(client)

    def _process_single_image_with_rotation_and_retry(self, image_path, base_folder, keep_structure, total_images, rotation_deg):
        """Process a single image with rotation applied during retry"""
        from PIL import Image
        import tempfile
        import os
        
        # Check if we should pause due to too many failures
        with self.progress_lock:
            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.warning(f"Too many consecutive failures ({self.consecutive_failures}), pausing for 10 seconds...")
                time.sleep(10)
                self.consecutive_failures = 0

        # Get a client from the pool (wait up to 60 seconds)
        client = None
        rotated_image_path = None
        
        try:
            client = self.client_pool.get_client(timeout=60)
        except queue.Empty:
            logger.error(f"Timeout waiting for available client for {image_path.name}")
            return False
        
        try:
            # Apply rotation to the image
            logger.info(f"Applying {rotation_deg}° rotation to {image_path.name} for retry")
            
            # Open and rotate the image
            with Image.open(image_path) as img:
                # Convert to RGB if necessary (for JPEG compatibility)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Apply rotation
                rotated_img = img.rotate(rotation_deg, expand=True)
                
                # Save rotated image to temporary file
                temp_dir = tempfile.mkdtemp()
                rotated_image_path = Path(temp_dir) / f"rotated_{image_path.name}"
                rotated_img.save(rotated_image_path, 'PNG')
            
            # Determine output path with serial number
            serial_number = self._get_next_serial_number()

            if keep_structure:
                relative_path = image_path.relative_to(base_folder)
                output_subdir = self.output_dir / relative_path.parent
                output_subdir.mkdir(parents=True, exist_ok=True)
                rip_filename = f"{image_path.stem}_rip_{serial_number}.bmp"
                rip_path = output_subdir / rip_filename
            else:
                rip_filename = f"{image_path.stem}_rip_{serial_number}.bmp"
                rip_path = self.output_dir / rip_filename
            
            # RIP the rotated image with retry logic
            success = client.render_image_with_retry(str(rotated_image_path), str(rip_path), max_retries=3)
            
            # Provide feedback to adaptive system
            if success:
                self._on_successful_render()
            else:
                self._adjust_concurrency_on_busy_error()
            
            # Update progress
            with self.progress_lock:
                self.processed_count += 1
                current_count = self.processed_count
                
            if success:
                logger.info(f"[{current_count}/{total_images}] ✅ RIPped (with {rotation_deg}° rotation): {image_path.name}")
                with self.progress_lock:
                    self.consecutive_failures = 0  # Reset on success
            else:
                logger.error(f"[{current_count}/{total_images}] ❌ Failed (with {rotation_deg}° rotation): {image_path.name}")
                with self.progress_lock:
                    self.consecutive_failures += 1
            
            return success
            
        finally:
            # Always return the client to the pool
            if client:
                self.client_pool.return_client(client)
            
            # Clean up temporary rotated image
            if rotated_image_path and rotated_image_path.exists():
                try:
                    rotated_image_path.unlink()
                    # Also remove temp directory if empty
                    temp_dir = rotated_image_path.parent
                    if temp_dir.exists() and not any(temp_dir.iterdir()):
                        temp_dir.rmdir()
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary file {rotated_image_path}: {e}")

    def _collect_images(self, folder_path):
        """Collect all supported image files from folder"""
        image_files = [] 
        
        for file_path in folder_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                image_files.append(file_path)
        
        # Sort for consistent processing order
        image_files.sort()
        return image_files

    def list_rip_files(self):
        """List all RIP files created"""
        rip_files = list(self.output_dir.rglob("*.bmp"))
        logger.info(f"Found {len(rip_files)} RIP files in {self.output_dir}:")
        for rip_file in sorted(rip_files):
            logger.info(f"  - {rip_file.relative_to(self.output_dir)}")
        return rip_files


class MultiServerImageRipProcessor:
    """
    Multi-server RIP processor that distributes work across multiple GIS servers.
    Maintains sequential file numbering regardless of which server processes each image.
    """
    
    SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
    
    def __init__(self, multi_server_pool, output_dir="rip_output", max_workers=12, distribution_mode='alternate'):
        """
        Initialize multi-server RIP processor
        
        Args:
            multi_server_pool: MultiServerClientPool instance
            output_dir: Output directory for RIP files
            max_workers: Maximum worker threads
            distribution_mode: 'alternate' or 'chunks'
        """
        self.multi_server_pool = multi_server_pool
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.distribution_mode = distribution_mode
        
        # Progress tracking
        self.progress_lock = Lock()
        self.processed_count = 0
        self.failed_images = []
        
        # Serial number counter (shared across all servers)
        self.serial_counter = 0
        self.serial_lock = Lock()
        
        # Cancellation support
        self.cancellation_callback = None
        self.cancelled = False
        
        # Adaptive concurrency (simplified for multi-server)
        self.base_delay = 0.20
        self.current_delay = self.base_delay
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        logger.info(f"Multi-server RIP output directory: {self.output_dir}")
        logger.info(f"Distribution mode: {distribution_mode}")
        logger.info(f"Servers: {multi_server_pool.get_server_count()}, Total connections: {multi_server_pool.get_total_connections()}")
    
    def set_cancellation_callback(self, callback):
        """Set callback function to check if processing should be cancelled"""
        self.cancellation_callback = callback
    
    def cancel_processing(self):
        """Cancel ongoing processing"""
        self.cancelled = True
    
    def _is_cancelled(self):
        """Check if processing should be cancelled"""
        if self.cancelled:
            return True
        if self.cancellation_callback and self.cancellation_callback():
            self.cancelled = True
            return True
        return False
    
    def _get_next_serial_number(self):
        """Get next serial number for file naming (thread-safe across all servers)"""
        with self.serial_lock:
            self.serial_counter += 1
            return self.serial_counter
    
    def get_current_worker_count(self):
        """Get current worker count"""
        return self.max_workers
    
    def get_current_delay(self):
        """Get current delay"""
        return self.current_delay
    
    def _collect_images(self, folder_path):
        """Collect all supported image files from folder"""
        image_files = []
        
        for file_path in folder_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                image_files.append(file_path)
        
        # Sort for consistent processing order
        image_files.sort()
        return image_files
    
    def process_folder_with_cancellation(self, folder_path, keep_structure=False, 
                                       delay_between_submissions=0.1, cancellation_check=None, rotation_deg=0):
        """Process folder with multi-server distribution and cancellation support"""
        if cancellation_check:
            self.cancellation_callback = cancellation_check
        
        self.current_delay = delay_between_submissions
        
        folder_path = Path(folder_path)
        if not folder_path.exists() or not folder_path.is_dir():
            logger.error(f"Invalid folder path: {folder_path}")
            return False
        
        logger.info(f"Multi-server processing: {folder_path}")
        
        # Collect all image files
        image_files = self._collect_images(folder_path)
        
        if not image_files:
            logger.warning(f"No supported images found in {folder_path}")
            return False
        
        total_images = len(image_files)
        logger.info(f"Found {total_images} images to process across {self.multi_server_pool.get_server_count()} servers")
        
        # Reset counters
        self.processed_count = 0
        self.failed_images = []
        self.cancelled = False
        
        # Distribute images across servers based on mode
        if self.distribution_mode == 'alternate':
            # Round-robin distribution
            return self._process_with_round_robin(image_files, folder_path, keep_structure, total_images, rotation_deg)
        else:
            # Chunk-based distribution
            return self._process_with_chunks(image_files, folder_path, keep_structure, total_images, rotation_deg)
    
    def _process_with_round_robin(self, image_files, base_folder, keep_structure, total_images, rotation_deg):
        """Process images using round-robin (alternate) distribution with parallel per-server submission"""
        logger.info("Using ROUND-ROBIN distribution (alternate pages across servers)")
        
        # Step 1: Distribute images across servers in round-robin fashion
        distributor = ServerDistributor(
            self.multi_server_pool.server_configs,
            distribution_mode='alternate'
        )
        distribution = distributor.distribute_items(image_files)
        
        # Log distribution
        for server_id, items in distribution.items():
            logger.info(f"  Server {server_id}: {len(items)} images assigned")
        
        # Step 2: Create one ThreadPoolExecutor per server for parallel submission
        # Each server gets its own submission thread to maintain 0.2s delay independently
        server_executors = {}
        all_futures = {}
        submission_threads = []
        
        def submit_for_server(server_id, server_images):
            """Submit images for a specific server with delays between submissions"""
            # Create dedicated executor for this server's workers
            with ThreadPoolExecutor(max_workers=self.max_workers // len(distribution)) as executor:
                for idx, image_path in enumerate(server_images):
                    if self._is_cancelled():
                        break
                    
                    # Apply delay between submissions for this server (0.2s per image)
                    if idx > 0:
                        time.sleep(self.current_delay)
                    
                    future = executor.submit(
                        self._process_single_image_multi_server,
                        image_path, base_folder, keep_structure, total_images, rotation_deg, server_id
                    )
                    
                    with self.progress_lock:
                        all_futures[future] = (image_path, server_id)
        
        # Step 3: Launch parallel submission threads (one per server)
        import threading
        for server_id, server_images in distribution.items():
            if server_images:  # Only if server has images assigned
                thread = threading.Thread(
                    target=submit_for_server,
                    args=(server_id, server_images),
                    name=f"Submitter-{server_id}"
                )
                thread.start()
                submission_threads.append(thread)
        
        # Wait for all submission threads to complete
        for thread in submission_threads:
            thread.join()
        
        # Step 4: Wait for all futures to complete
        logger.info(f"All submissions complete. Waiting for {len(all_futures)} jobs to finish...")
        
        for future in as_completed(all_futures):
            if self._is_cancelled():
                logger.info("Cancelling remaining tasks...")
                for remaining_future in all_futures:
                    if not remaining_future.done():
                        remaining_future.cancel()
                break
            
            image_path, server_id = all_futures[future]
            try:
                success = future.result()
                if not success:
                    with self.progress_lock:
                        self.failed_images.append(image_path)
            except Exception as e:
                logger.error(f"Exception processing {image_path} on {server_id}: {e}")
                with self.progress_lock:
                    self.failed_images.append(image_path)
        
        # Report results
        successful_count = total_images - len(self.failed_images)
        if self._is_cancelled():
            logger.info(f"Processing cancelled: {successful_count}/{total_images} images RIPped before cancellation")
        else:
            logger.info(f"Multi-server processing completed: {successful_count}/{total_images} images RIPped successfully")
        
        if self.failed_images:
            logger.error(f"Failed to process {len(self.failed_images)} images")
        
        return not self._is_cancelled() and len(self.failed_images) == 0
    
    def _process_with_chunks(self, image_files, base_folder, keep_structure, total_images, rotation_deg):
        """Process images using chunk-based distribution with parallel per-server submission"""
        logger.info("Using CHUNK-BASED distribution")
        
        # Distribute images into chunks per server
        distributor = ServerDistributor(
            self.multi_server_pool.server_configs,
            distribution_mode='chunks'
        )
        distribution = distributor.distribute_items(image_files)
        
        # Log distribution
        for server_id, items in distribution.items():
            logger.info(f"  Server {server_id}: {len(items)} images")
        
        # Create parallel submission threads (one per server)
        all_futures = {}
        submission_threads = []
        
        def submit_for_server(server_id, server_images):
            """Submit images for a specific server with delays between submissions"""
            # Create dedicated executor for this server's workers
            with ThreadPoolExecutor(max_workers=self.max_workers // len(distribution)) as executor:
                for idx, image_path in enumerate(server_images):
                    if self._is_cancelled():
                        break
                    
                    # Apply delay between submissions for this server (0.2s per image)
                    if idx > 0:
                        time.sleep(self.current_delay)
                    
                    future = executor.submit(
                        self._process_single_image_multi_server,
                        image_path, base_folder, keep_structure, total_images, rotation_deg, server_id
                    )
                    
                    with self.progress_lock:
                        all_futures[future] = (image_path, server_id)
        
        # Launch parallel submission threads (one per server)
        import threading
        for server_id, server_images in distribution.items():
            if server_images:  # Only if server has images assigned
                thread = threading.Thread(
                    target=submit_for_server,
                    args=(server_id, server_images),
                    name=f"Submitter-{server_id}"
                )
                thread.start()
                submission_threads.append(thread)
        
        # Wait for all submission threads to complete
        for thread in submission_threads:
            thread.join()
        
        # Wait for all futures to complete
        logger.info(f"All submissions complete. Waiting for {len(all_futures)} jobs to finish...")
        
        for future in as_completed(all_futures):
            if self._is_cancelled():
                logger.info("Cancelling remaining tasks...")
                break
            
            image_path, server_id = all_futures[future]
            try:
                success = future.result()
                if not success:
                    with self.progress_lock:
                        self.failed_images.append(image_path)
            except Exception as e:
                logger.error(f"Exception processing {image_path} on {server_id}: {e}")
                with self.progress_lock:
                    self.failed_images.append(image_path)
        
        # Report results
        successful_count = total_images - len(self.failed_images)
        logger.info(f"Multi-server processing completed: {successful_count}/{total_images} images RIPped")
        
        return not self._is_cancelled() and len(self.failed_images) == 0
    
    def process_specific_images_with_cancellation(self, image_list, base_folder, keep_structure=False, 
                                                   delay_between_submissions=0.1, cancellation_check=None, rotation_deg=0):
        """
        Process a specific list of images (for retry logic) in multi-server mode.
        
        Args:
            image_list: List of Path objects for images to process
            base_folder: Base folder path for structure reference
            keep_structure: If True, maintains subdirectory structure in output
            delay_between_submissions: Delay in seconds between job submissions
            cancellation_check: Function to check if processing should be cancelled
            rotation_deg: Rotation to apply (if needed for retry)
        
        Returns:
            True if all images processed successfully
        """
        if cancellation_check:
            self.cancellation_callback = cancellation_check
        
        self.current_delay = delay_between_submissions
        
        base_folder = Path(base_folder)
        total_images = len(image_list)
        
        if total_images == 0:
            logger.info("No images to process")
            return True
        
        logger.info(f"Multi-server retry: Processing {total_images} specific images")
        
        # Reset counters for this batch
        with self.progress_lock:
            self.failed_images = []
        self.cancelled = False
        
        # Distribute retry images across servers
        distributor = ServerDistributor(
            self.multi_server_pool.server_configs,
            distribution_mode=self.distribution_mode
        )
        distribution = distributor.distribute_items(image_list)
        
        # Process with parallel submission per server
        all_futures = {}
        submission_threads = []
        
        def submit_for_server(server_id, server_images):
            """Submit retry images for a specific server"""
            with ThreadPoolExecutor(max_workers=self.max_workers // len(distribution)) as executor:
                for idx, image_path in enumerate(server_images):
                    if self._is_cancelled():
                        break
                    
                    if idx > 0:
                        time.sleep(self.current_delay)
                    
                    future = executor.submit(
                        self._process_single_image_multi_server,
                        image_path, base_folder, keep_structure, total_images, rotation_deg, server_id
                    )
                    
                    with self.progress_lock:
                        all_futures[future] = (image_path, server_id)
        
        # Launch submission threads
        import threading
        for server_id, server_images in distribution.items():
            if server_images:
                thread = threading.Thread(
                    target=submit_for_server,
                    args=(server_id, server_images),
                    name=f"RetrySubmitter-{server_id}"
                )
                thread.start()
                submission_threads.append(thread)
        
        # Wait for all submissions
        for thread in submission_threads:
            thread.join()
        
        # Wait for all futures to complete
        logger.info(f"Retry: Waiting for {len(all_futures)} jobs to finish...")
        
        for future in as_completed(all_futures):
            if self._is_cancelled():
                logger.info("Retry cancelled...")
                break
            
            image_path, server_id = all_futures[future]
            try:
                success = future.result()
                if not success:
                    with self.progress_lock:
                        self.failed_images.append(image_path)
            except Exception as e:
                logger.error(f"Exception during retry for {image_path} on {server_id}: {e}")
                with self.progress_lock:
                    self.failed_images.append(image_path)
        
        # Report results
        successful_count = total_images - len(self.failed_images)
        if self._is_cancelled():
            logger.info(f"Retry cancelled: {successful_count}/{total_images} images RIPped before cancellation")
        else:
            logger.info(f"Retry completed: {successful_count}/{total_images} images RIPped successfully")
        
        if self.failed_images:
            logger.warning(f"Still failed: {len(self.failed_images)} images after retry")
        
        return not self._is_cancelled() and len(self.failed_images) == 0
    
    def _process_single_image_multi_server(self, image_path, base_folder, keep_structure, total_images, rotation_deg, server_id):
        """Process single image using specified server"""
        if self._is_cancelled():
            return False
        
        # Get client from specific server
        client = None
        try:
            client = self.multi_server_pool.get_client_from_server(server_id, timeout=60)
        except queue.Empty:
            logger.error(f"Timeout waiting for client from server {server_id} for {image_path.name}")
            return False
        
        try:
            # Get sequential serial number
            serial_number = self._get_next_serial_number()
            
            if keep_structure:
                relative_path = image_path.relative_to(base_folder)
                output_subdir = self.output_dir / relative_path.parent
                output_subdir.mkdir(parents=True, exist_ok=True)
                rip_filename = f"{image_path.stem}_rip_{serial_number:04d}.bmp"
                rip_path = output_subdir / rip_filename
            else:
                rip_filename = f"{image_path.stem}_rip_{serial_number:04d}.bmp"
                rip_path = self.output_dir / rip_filename
            
            # RIP the image
            success = client.render_image_with_retry(str(image_path), str(rip_path), max_retries=3)
            
            # Update progress
            with self.progress_lock:
                self.processed_count += 1
                current_count = self.processed_count
            
            if success:
                logger.info(f"[{current_count}/{total_images}] ✅ RIPped on {server_id}: {image_path.name} → {rip_filename}")
            else:
                logger.error(f"[{current_count}/{total_images}] ❌ Failed on {server_id}: {image_path.name}")
            
            return success
        
        finally:
            if client:
                self.multi_server_pool.return_client_to_server(server_id, client)
    
    def list_rip_files(self):
        """List all RIP files created"""
        rip_files = list(self.output_dir.rglob("*.bmp"))
        logger.info(f"Found {len(rip_files)} RIP files in {self.output_dir}")
        return rip_files


def main():
    """Main function for parallel processing of image folders"""
    # Configuration
    SERVER_HOST = 'localhost'
    SERVER_PORT = 2000
    
    # Processing configuration
    IMAGE_FOLDER = r"C:\Users\Kridwinn\Music\pdf_images_2\TEST_File_1909-001"  # Change this to your image folder path
    OUTPUT_FOLDER = "rip_output_6800_test_10"  # Output folder for RIP files
    KEEP_FOLDER_STRUCTURE = False  # Set to True to maintain subdirectory structure
    
    # Parallel processing configuration (reduced for stability)
    NUM_CONNECTIONS = 12  # Number of parallel connections to the server
    MAX_WORKERS = 12  # Number of worker threads
    DELAY_BETWEEN_SUBMISSIONS = 0.2  # Delay in seconds between job submissions
    
    # Create client pool
    client_pool = ClientPool(SERVER_HOST, SERVER_PORT, pool_size=NUM_CONNECTIONS)

    start = time.time()
    
    try:
        # Initialize client pool
        logger.info(f"Initializing {NUM_CONNECTIONS} connections to Print Server...")
        if not client_pool.initialize():
            logger.error("Failed to initialize client pool")
            return
        
        # Create processor
        processor = ParallelImageRipProcessor(
            client_pool, 
            output_dir=OUTPUT_FOLDER,
            max_workers=MAX_WORKERS
        )
        
        # Start processing
        start_time = time.time()
        logger.info("Starting parallel image folder to RIP conversion...")
        
        # Process with controlled submission rate
        success = processor.process_folder(
            IMAGE_FOLDER,
            keep_structure=KEEP_FOLDER_STRUCTURE,
            delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS
        )
        
        # Calculate processing time
        elapsed_time = time.time() - start_time
        
        if success:
            logger.info(f"Image folder processing completed successfully in {elapsed_time:.2f} seconds!")
            processor.list_rip_files()
        else:
            logger.warning(f"Some images failed to process (completed in {elapsed_time:.2f} seconds)")
        
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        client_pool.close_all()

    end = time.time()
    time_2 = end - start
    print(time_2)


if __name__ == "__main__":
    main()