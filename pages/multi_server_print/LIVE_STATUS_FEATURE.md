# 📊 Live Status Monitoring Feature - Design Specification

## 🎯 Feature Overview

**Feature Name:** Live Status Monitoring  
**Priority:** High  
**Phase:** Phase 3 (Single Server) & Phase 4 (Dual Server)  
**Status:** To be implemented

### **Purpose**
Provide real-time monitoring of the printing process showing:
1. **Files Sent for Printing** - Total files queued/sent to server
2. **Files Actually Printed** - Confirmed printed files (from server feedback)
3. **Speed (MPM)** - Meters per minute (to be added later, fetched from server)

---

## 📐 Design Specification

### **Where to Display**

The live status should be displayed in **two locations** for optimal visibility:

#### **Location 1: Progress Section (Primary)**
In the widget where printing is active (SingleServerWidget / DualServerWidget)

```
┌─────────────────────────────────────────────────────┐
│  LIVE STATUS                                        │
├─────────────────────────────────────────────────────┤
│  📤 Files Sent:     125 / 150    (83%)              │
│  ✅ Files Printed:  118 / 150    (79%)              │
│  ⏱️  Speed (MPM):    15.3 m/min  (Coming Soon)      │
│                                                     │
│  Progress: ████████████████░░░░░░ 79%              │
│  Status: Printing page_0119.bmp...                 │
└─────────────────────────────────────────────────────┘
```

#### **Location 2: Status Log Section (Secondary)**
Real-time updates appended to the log

```
[14:23:15] ✅ Printed: page_0118.bmp (118/150) - 79%
[14:23:16] 📤 Sent: page_0119.bmp (119/150)
[14:23:17] ✅ Printed: page_0119.bmp (119/150) - 79%
[14:23:17] 📤 Sent: page_0120.bmp (120/150)
```

---

## 🎨 UI Design

### **Single Server - Live Status Widget**

```python
class LiveStatusWidget(QWidget):
    """
    Live status display for printing progress
    Shows files sent, printed, and speed metrics
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("<b>📊 Live Status</b>")
        title.setStyleSheet("font-size: 14pt; color: #212529;")
        layout.addWidget(title)
        
        # Status grid
        grid = QGridLayout()
        
        # Files Sent
        sent_icon = QLabel("📤")
        sent_icon.setStyleSheet("font-size: 16pt;")
        self.sent_label = QLabel("Files Sent:")
        self.sent_value = QLabel("0 / 0 (0%)")
        self.sent_value.setStyleSheet("font-weight: bold; color: #007bff;")
        grid.addWidget(sent_icon, 0, 0)
        grid.addWidget(self.sent_label, 0, 1)
        grid.addWidget(self.sent_value, 0, 2)
        
        # Files Printed
        printed_icon = QLabel("✅")
        printed_icon.setStyleSheet("font-size: 16pt;")
        self.printed_label = QLabel("Files Printed:")
        self.printed_value = QLabel("0 / 0 (0%)")
        self.printed_value.setStyleSheet("font-weight: bold; color: #28a745;")
        grid.addWidget(printed_icon, 1, 0)
        grid.addWidget(self.printed_label, 1, 1)
        grid.addWidget(self.printed_value, 1, 2)
        
        # Speed (MPM) - Coming Soon
        speed_icon = QLabel("⏱️")
        speed_icon.setStyleSheet("font-size: 16pt;")
        self.speed_label = QLabel("Speed (MPM):")
        self.speed_value = QLabel("-- m/min (Coming Soon)")
        self.speed_value.setStyleSheet("font-weight: bold; color: #6c757d; font-style: italic;")
        grid.addWidget(speed_icon, 2, 0)
        grid.addWidget(self.speed_label, 2, 1)
        grid.addWidget(self.speed_value, 2, 2)
        
        layout.addLayout(grid)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # Style the group
        self.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                padding: 10px;
            }
        """)
    
    def update_status(self, sent: int, printed: int, total: int, speed: float = None):
        """Update live status display"""
        # Calculate percentages
        sent_pct = int((sent / total) * 100) if total > 0 else 0
        printed_pct = int((printed / total) * 100) if total > 0 else 0
        
        # Update labels
        self.sent_value.setText(f"{sent} / {total} ({sent_pct}%)")
        self.printed_value.setText(f"{printed} / {total} ({printed_pct}%)")
        
        # Update speed (if available)
        if speed is not None:
            self.speed_value.setText(f"{speed:.1f} m/min")
            self.speed_value.setStyleSheet("font-weight: bold; color: #17a2b8;")
        
        # Color coding based on progress
        if printed_pct < 25:
            color = "#dc3545"  # Red - Just started
        elif printed_pct < 75:
            color = "#ffc107"  # Orange - In progress
        else:
            color = "#28a745"  # Green - Almost done
        
        self.printed_value.setStyleSheet(f"font-weight: bold; color: {color};")
```

### **Dual Server - Live Status Widget**

For dual server, show status for **both servers side by side**:

```
┌──────────────────────────────────────────────────────────────┐
│  📊 LIVE STATUS                                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  SERVER 1 (Odd Pages)          │  SERVER 2 (Even Pages)     │
│  ─────────────────────────────────────────────────────────  │
│  📤 Sent:     62 / 75  (83%)   │  📤 Sent:     63 / 75  (84%)│
│  ✅ Printed:  59 / 75  (79%)   │  ✅ Printed:  60 / 75  (80%)│
│  ⏱️  Speed:    15.3 m/min       │  ⏱️  Speed:    15.1 m/min   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 Technical Implementation

### **1. Data Model - Live Status Config**

**File:** `rip2print/shared/live_status.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class LiveStatusData:
    """
    Real-time status data for printing operations
    """
    # Counters
    files_sent: int = 0
    files_printed: int = 0
    total_files: int = 0
    
    # Speed metrics
    speed_mpm: Optional[float] = None  # Meters per minute
    
    # Timestamps
    start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None
    
    # Current file
    current_file: str = ""
    
    # Calculated properties
    @property
    def sent_percentage(self) -> int:
        return int((self.files_sent / self.total_files) * 100) if self.total_files > 0 else 0
    
    @property
    def printed_percentage(self) -> int:
        return int((self.files_printed / self.total_files) * 100) if self.total_files > 0 else 0
    
    @property
    def lag(self) -> int:
        """Number of files sent but not yet printed"""
        return self.files_sent - self.files_printed
    
    @property
    def elapsed_time(self) -> float:
        """Elapsed time in seconds"""
        if self.start_time and self.last_update:
            return (self.last_update - self.start_time).total_seconds()
        return 0.0
    
    def reset(self):
        """Reset all counters"""
        self.files_sent = 0
        self.files_printed = 0
        self.total_files = 0
        self.speed_mpm = None
        self.start_time = None
        self.last_update = None
        self.current_file = ""
```

### **2. Worker Integration - Tracking Status**

**File:** `rip2print/single_server/single_server_worker.py`

```python
class SingleServerWorker(QObject):
    """
    Worker for single server printing with live status tracking
    """
    
    # Signals
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(bool)
    error = Signal(str)
    
    # NEW: Live status signals
    status_update = Signal(dict)  # {sent, printed, total, speed, current_file}
    file_sent = Signal(str)       # file_path
    file_printed = Signal(str)    # file_path
    
    def __init__(self, config: SingleServerConfig):
        super().__init__()
        self.config = config
        self.printer = None
        self._cancelled = False
        
        # Live status tracking
        self.status = LiveStatusData()
    
    def run(self):
        """Execute printing with live status tracking"""
        try:
            # Connect to server
            self.printer = GUIRipPrinter(
                self.config.server_ip, 
                self.config.server_port
            )
            
            if not self.printer.connect():
                self.error.emit("Failed to connect to server")
                self.finished.emit(False)
                return
            
            # Discover files
            files = self.discover_files()
            sequence = self.build_sequence(files)
            
            # Initialize status
            self.status.total_files = len(sequence)
            self.status.start_time = datetime.now()
            
            # Print each file
            for idx, file_path in enumerate(sequence):
                if self._cancelled:
                    break
                
                # Send file to server
                self.send_file_to_server(file_path)
                self.status.files_sent += 1
                self.status.current_file = file_path.name
                self.status.last_update = datetime.now()
                
                # Emit file sent signal
                self.file_sent.emit(str(file_path))
                
                # Wait for print confirmation from server
                print_confirmed = self.wait_for_print_confirmation(file_path)
                
                if print_confirmed:
                    self.status.files_printed += 1
                    self.file_printed.emit(str(file_path))
                
                # Fetch speed from server (if available)
                speed = self.fetch_speed_from_server()
                if speed:
                    self.status.speed_mpm = speed
                
                # Emit status update
                self.emit_status_update()
                
                # Emit progress
                self.progress.emit(
                    self.status.files_printed,
                    self.status.total_files,
                    f"Printed: {file_path.name}"
                )
            
            self.finished.emit(True)
        
        except Exception as e:
            logger.error(f"Printing failed: {e}")
            self.error.emit(str(e))
            self.finished.emit(False)
    
    def send_file_to_server(self, file_path: Path):
        """Send file to print server"""
        # Use existing GUIRipPrinter method
        # This adds file to server queue
        self.printer.print_file(str(file_path))
    
    def wait_for_print_confirmation(self, file_path: Path, timeout: int = 30) -> bool:
        """
        Wait for server to confirm file has been printed
        This can be done by:
        1. Monitoring server status messages
        2. Checking print queue
        3. Listening for completion events
        """
        # Method 1: Check if server sent print completion event
        # The GISPrintServerClient has event listeners
        # We can check for PRINT_COMPLETE events
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self._cancelled:
                return False
            
            # Check server status
            status = self.printer.client.get_current_status()
            
            # If server indicates print complete for this file
            if self.is_print_complete(status, file_path):
                return True
            
            time.sleep(0.1)  # Poll every 100ms
        
        # Assume printed if timeout (fallback)
        return True
    
    def is_print_complete(self, status: dict, file_path: Path) -> bool:
        """Check if server confirms this file is printed"""
        # Parse server status to check if file completed
        # This depends on GIS server protocol
        # For now, simplified logic:
        return True  # Placeholder - implement based on server protocol
    
    def fetch_speed_from_server(self) -> Optional[float]:
        """
        Fetch current print speed from server (MPM - meters per minute)
        This will be implemented later based on server API
        """
        # TODO: Implement server API call to fetch speed
        # Example:
        # speed_data = self.printer.client.get_speed_metrics()
        # return speed_data.get('mpm')
        return None  # Placeholder for now
    
    def emit_status_update(self):
        """Emit live status update"""
        status_dict = {
            'sent': self.status.files_sent,
            'printed': self.status.files_printed,
            'total': self.status.total_files,
            'speed': self.status.speed_mpm,
            'current_file': self.status.current_file,
            'lag': self.status.lag,
            'elapsed': self.status.elapsed_time
        }
        self.status_update.emit(status_dict)
```

### **3. UI Integration - SingleServerWidget**

**File:** `rip2print/single_server/single_server_widget.py`

```python
class SingleServerWidget(QWidget):
    """
    Single Server Job Submission UI with Live Status
    """
    
    def __init__(self, server_manager):
        super().__init__()
        self.server_manager = server_manager
        self.worker = None
        self.thread = None
        
        # ... existing UI components ...
        
        # NEW: Live Status Widget
        self.live_status = LiveStatusWidget()
        self.live_status.setVisible(False)  # Hidden until printing starts
        
        # Add to layout (after progress bar)
        # layout.addWidget(self.live_status)
    
    def start_printing(self):
        """Start printing with live status tracking"""
        # ... existing validation ...
        
        # Create config
        config = self.build_config_from_ui()
        
        # Create worker
        self.worker = SingleServerWorker(config)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        
        # NEW: Connect live status signals
        self.worker.status_update.connect(self.update_live_status)
        self.worker.file_sent.connect(self.on_file_sent)
        self.worker.file_printed.connect(self.on_file_printed)
        
        # Show live status widget
        self.live_status.setVisible(True)
        
        # Start thread
        self.thread.start()
        
        # Update UI state
        self.set_printing_active(True)
    
    def update_live_status(self, status: dict):
        """Update live status display"""
        self.live_status.update_status(
            sent=status['sent'],
            printed=status['printed'],
            total=status['total'],
            speed=status.get('speed')
        )
    
    def on_file_sent(self, file_path: str):
        """Handle file sent event"""
        timestamp = time.strftime("%H:%M:%S")
        filename = Path(file_path).name
        self.status_log.append(f"[{timestamp}] 📤 Sent: {filename}")
    
    def on_file_printed(self, file_path: str):
        """Handle file printed event"""
        timestamp = time.strftime("%H:%M:%S")
        filename = Path(file_path).name
        self.status_log.append(f"[{timestamp}] ✅ Printed: {filename}")
    
    def on_finished(self, success: bool):
        """Handle printing completion"""
        # ... existing cleanup ...
        
        # Keep live status visible to show final counts
        # Don't hide it immediately
        
        if success:
            self.status_log.append("[COMPLETE] All files printed successfully! ✅")
```

### **4. Dual Server Implementation**

**File:** `rip2print/dual_server/dual_server_widget.py`

```python
class DualServerWidget(QWidget):
    """
    Dual Server Job Submission UI with Live Status for Both Servers
    """
    
    def __init__(self, server_manager):
        super().__init__()
        self.server_manager = server_manager
        self.worker1 = None
        self.worker2 = None
        self.threads = []
        
        # ... existing UI components ...
        
        # NEW: Live Status Widgets (one for each server)
        self.live_status1 = LiveStatusWidget()
        self.live_status1.setVisible(False)
        
        self.live_status2 = LiveStatusWidget()
        self.live_status2.setVisible(False)
        
        # Layout: Side by side
        status_layout = QHBoxLayout()
        
        # Server 1 status
        server1_container = QVBoxLayout()
        server1_label = QLabel("<b>SERVER 1 (Odd Pages)</b>")
        server1_container.addWidget(server1_label)
        server1_container.addWidget(self.live_status1)
        
        # Server 2 status
        server2_container = QVBoxLayout()
        server2_label = QLabel("<b>SERVER 2 (Even Pages)</b>")
        server2_container.addWidget(server2_label)
        server2_container.addWidget(self.live_status2)
        
        status_layout.addLayout(server1_container)
        status_layout.addLayout(server2_container)
        
        # Add to main layout
        # layout.addLayout(status_layout)
    
    def start_printing(self):
        """Start dual server printing with live status"""
        # ... create workers for both servers ...
        
        # Connect status signals for Server 1
        self.worker1.status_update.connect(
            lambda status: self.live_status1.update_status(
                status['sent'], status['printed'], status['total'], status.get('speed')
            )
        )
        
        # Connect status signals for Server 2
        self.worker2.status_update.connect(
            lambda status: self.live_status2.update_status(
                status['sent'], status['printed'], status['total'], status.get('speed')
            )
        )
        
        # Show both status widgets
        self.live_status1.setVisible(True)
        self.live_status2.setVisible(True)
        
        # Start both threads
        self.thread1.start()
        self.thread2.start()
```

---

## 📊 Data Flow for Live Status

```
┌──────────────────────────────────────────────────────┐
│  SingleServerWorker (in QThread)                     │
│                                                      │
│  1. Send file to server                             │
│     ├─ files_sent += 1                              │
│     └─ emit file_sent(path)                         │
│                                                      │
│  2. Wait for print confirmation                     │
│     ├─ Poll server status                           │
│     └─ Check print complete event                   │
│                                                      │
│  3. File confirmed printed                          │
│     ├─ files_printed += 1                           │
│     └─ emit file_printed(path)                      │
│                                                      │
│  4. Fetch speed (optional)                          │
│     ├─ Call server API                              │
│     └─ Update speed_mpm                             │
│                                                      │
│  5. Emit status update                              │
│     └─ emit status_update({sent, printed, ...})    │
│                                                      │
└────────────────┬─────────────────────────────────────┘
                 │
                 │ Signal
                 │
┌────────────────▼─────────────────────────────────────┐
│  SingleServerWidget (UI Thread)                      │
│                                                      │
│  on_status_update(status):                          │
│     ├─ Update LiveStatusWidget                      │
│     │  ├─ sent_value.setText(...)                   │
│     │  ├─ printed_value.setText(...)                │
│     │  └─ speed_value.setText(...)                  │
│     │                                                │
│     └─ Update progress bar                          │
│        └─ progress_bar.setValue(printed_pct)        │
│                                                      │
│  on_file_sent(path):                                │
│     └─ status_log.append("📤 Sent: ...")            │
│                                                      │
│  on_file_printed(path):                             │
│     └─ status_log.append("✅ Printed: ...")          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## 🎯 Implementation Plan

### **Phase 3.5: Add Live Status to Single Server** (3 days)

#### Day 1: Data Model & Widget
- [ ] Create `LiveStatusData` class in `shared/live_status.py`
- [ ] Create `LiveStatusWidget` class
- [ ] Style the widget
- [ ] Test widget standalone

#### Day 2: Worker Integration
- [ ] Add status tracking to `SingleServerWorker`
- [ ] Implement file sent/printed signals
- [ ] Add print confirmation logic
- [ ] Test worker signals

#### Day 3: UI Integration & Testing
- [ ] Integrate `LiveStatusWidget` into `SingleServerWidget`
- [ ] Connect all signals
- [ ] Test with real printing
- [ ] Fix bugs

### **Phase 4.5: Add Live Status to Dual Server** (2 days)

#### Day 1: Dual Status Widgets
- [ ] Add two `LiveStatusWidget` instances
- [ ] Layout side by side
- [ ] Connect to both workers

#### Day 2: Testing & Polish
- [ ] Test with dual server printing
- [ ] Ensure both update independently
- [ ] Fix any synchronization issues

### **Future: Add Speed (MPM)** (1-2 days)
- [ ] Research GIS server API for speed metrics
- [ ] Implement `fetch_speed_from_server()` method
- [ ] Update UI to show real speed
- [ ] Test with various print speeds

---

## 🧪 Testing Checklist

### **Unit Tests:**
- [ ] `LiveStatusData` calculations correct
- [ ] Percentage calculations accurate
- [ ] Lag calculation correct
- [ ] Elapsed time tracking works

### **Integration Tests:**
- [ ] Worker emits correct status updates
- [ ] UI receives and displays updates
- [ ] File sent/printed events trigger
- [ ] Multiple files tracked correctly

### **End-to-End Tests:**
- [ ] Single server: Status updates during printing
- [ ] Dual server: Both statuses update independently
- [ ] Status persists after completion
- [ ] Final counts are accurate

### **Edge Cases:**
- [ ] Zero files (empty folder)
- [ ] One file (edge case)
- [ ] Large file count (1000+ files)
- [ ] Print failure mid-job
- [ ] Server disconnect during printing

---

## 📝 User Stories

### **Story 1: Monitor Print Progress**
**As a** user  
**I want to** see how many files have been sent and actually printed  
**So that** I can track the actual print progress

**Acceptance Criteria:**
- ✅ See files sent count
- ✅ See files printed count
- ✅ See percentages for both
- ✅ Updates in real-time

### **Story 2: Identify Print Lag**
**As a** user  
**I want to** see the difference between sent and printed  
**So that** I can identify if the server is lagging behind

**Acceptance Criteria:**
- ✅ Lag is automatically calculated
- ✅ Large lag shows warning color
- ✅ User understands server processing speed

### **Story 3: Monitor Speed (Future)**
**As a** user  
**I want to** see the print speed in meters per minute  
**So that** I can estimate completion time

**Acceptance Criteria:**
- ✅ Speed fetched from server
- ✅ Displayed in MPM format
- ✅ Updates periodically

---

## 🎨 Visual Design

### **Color Coding:**
- **Files Sent:** Blue (#007bff) - Information
- **Files Printed:** 
  - Red (#dc3545) if < 25% - Just started
  - Orange (#ffc107) if 25-75% - In progress
  - Green (#28a745) if > 75% - Almost done
- **Speed:** Cyan (#17a2b8) when available, Gray (#6c757d) when pending

### **Icons:**
- 📤 Files Sent (upload icon)
- ✅ Files Printed (checkmark)
- ⏱️ Speed (timer/clock)

---

## 🚀 Future Enhancements

### **Phase 2: Advanced Metrics**
1. **Estimated Time Remaining** - Based on current speed
2. **Average Speed** - Over the entire job
3. **Peak Speed** - Fastest MPM recorded
4. **Print Quality Indicators** - From server feedback

### **Phase 3: Alerts**
1. **Slow Print Warning** - If speed drops below threshold
2. **High Lag Alert** - If sent/printed gap too large
3. **Completion Notification** - Desktop notification

### **Phase 4: Analytics**
1. **Print History** - Store all print jobs
2. **Performance Graphs** - Speed over time
3. **Server Comparison** - Compare dual server performance
4. **Export Reports** - CSV/PDF reports

---

## 📚 API Reference (for Speed Fetch)

### **GIS Server Speed API (To be implemented)**

```python
# Pseudo-code for future implementation
def fetch_speed_from_server(self) -> Optional[float]:
    """
    Fetch current print speed from GIS server
    
    Returns:
        float: Speed in meters per minute (MPM)
        None: If speed not available
    """
    try:
        # Method 1: Use existing status message
        status = self.printer.client.get_current_status()
        if 'speed_mpm' in status:
            return float(status['speed_mpm'])
        
        # Method 2: Query specific speed metric
        speed_data = self.printer.client.send_command("GET_SPEED")
        if speed_data and 'mpm' in speed_data:
            return float(speed_data['mpm'])
        
        # Method 3: Calculate from server metrics
        # pages_per_min = ...
        # meters_per_page = ...
        # return pages_per_min * meters_per_page
        
        return None
    except Exception as e:
        logger.error(f"Failed to fetch speed: {e}")
        return None
```

---

## ✅ Acceptance Criteria Summary

### **Must Have:**
- ✅ Display files sent count
- ✅ Display files printed count
- ✅ Display percentages
- ✅ Real-time updates during printing
- ✅ Works for single server
- ✅ Works for dual server (both independently)
- ✅ Color-coded progress indicators

### **Should Have:**
- ✅ Log entries for sent/printed events
- ✅ Visual separation between sent and printed
- ✅ Lag calculation visible
- ✅ Final status persists after completion

### **Nice to Have (Future):**
- ⏳ Speed (MPM) display
- ⏳ Estimated time remaining
- ⏳ Performance graphs
- ⏳ Desktop notifications

---

**This feature will significantly improve user experience by providing transparent, real-time feedback on the printing process!** 📊✨

---

**Document Version:** 1.0  
**Created:** 2025-10-16  
**Status:** Design Complete, Ready for Implementation  
**Next Step:** Implement in Phase 3.5 (after basic single server works)

