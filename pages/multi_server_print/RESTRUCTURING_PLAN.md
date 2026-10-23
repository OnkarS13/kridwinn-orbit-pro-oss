# 🏗️ Multi-Server Print Section - Restructuring Plan

## 📋 Executive Summary

This document outlines the complete restructuring of the **Multi-Server Print Section** to create a hierarchical, modular, and scalable architecture that supports multiple print modes (RIP2PRINT, IMG2PRINT, PDF2PRINT) with different job submission strategies.

---

## 🎯 Project Goals

### Primary Objectives
1. ✅ **Modular Architecture** - Button-wise subfolder structure
2. ✅ **Hierarchical Navigation** - Multi-level button navigation (Mode → Job Type → Configuration)
3. ✅ **Scalability** - Easy to add new modes and job types
4. ✅ **Maintainability** - Clean separation of concerns
5. ✅ **Production Ready** - Robust error handling and user experience
6. ✅ **Backward Compatible** - Preserve existing server management

### Phase 1 Focus
- Implement **RIP2PRINT** mode completely
- Create infrastructure for IMG2PRINT and PDF2PRINT (placeholder buttons)
- Focus on both **Single Server** and **Dual Server** job submissions

---

## 📐 Current State Analysis

### Existing Structure
```
pages/multi_server_print/
├── __init__.py
├── multi_server_section.py          # Main section widget (LEFT: servers, RIGHT: controls)
├── server_manager.py                # Server configuration management
├── server_config.py                 # Data models
├── server_control_widget.py         # Individual server UI
├── multi_server_worker.py           # Threaded printing
├── add_server_dialog.py             # Add server dialog
├── edit_server_dialog.py            # Edit server dialog
└── README.md
```

### Current Functionality
- ✅ Left panel: Server list with Add/Edit/Remove (hidden) + Refresh
- ✅ Right panel: Per-server control widget
- ✅ Per-server settings: RIP folder, copies, pattern, recursive, continuous mode
- ✅ Page filtering: all/range/odd/even/reverse
- ✅ Progress tracking and status monitoring
- ✅ Multi-threaded printing per server

### Current Limitations
- ❌ No mode selection (RIP/IMG/PDF)
- ❌ No job submission type (Single/Dual server)
- ❌ No collation type options
- ❌ Limited to single folder per server
- ❌ Odd/Even logic not optimized for dual server
- ❌ No TIFF support (only BMP)

---

## 🏛️ Proposed Architecture

### New Folder Structure
```
pages/multi_server_print/
├── __init__.py                           # Module exports
├── multi_server_section.py               # MAIN WIDGET (orchestrator)
│
├── shared/                               # Shared components
│   ├── __init__.py
│   ├── server_manager.py                 # Server configuration (existing)
│   ├── server_config.py                  # Data models (existing)
│   ├── add_server_dialog.py             # Add server dialog (existing)
│   ├── edit_server_dialog.py            # Edit server dialog (existing)
│   └── base_worker.py                    # Base worker class for printing
│
├── mode_selector/                        # Mode selection widget
│   ├── __init__.py
│   └── mode_selector_widget.py          # RIP2PRINT | IMG2PRINT | PDF2PRINT buttons
│
├── rip2print/                            # RIP2PRINT MODE (Phase 1)
│   ├── __init__.py
│   ├── rip2print_section.py             # Main RIP2PRINT widget
│   ├── job_type_selector.py             # Single/Dual server button selector
│   │
│   ├── single_server/                    # SINGLE SERVER job submission
│   │   ├── __init__.py
│   │   ├── single_server_widget.py      # UI for single server job
│   │   ├── single_server_worker.py      # Worker thread for single server
│   │   └── single_server_config.py      # Configuration data model
│   │
│   └── dual_server/                      # DUAL SERVER job submission
│       ├── __init__.py
│       ├── dual_server_widget.py        # UI for dual server job
│       ├── dual_server_worker.py        # Worker thread for dual server (odd/even)
│       └── dual_server_config.py        # Configuration data model
│
├── img2print/                            # IMG2PRINT MODE (Phase 2 - placeholder)
│   ├── __init__.py
│   └── img2print_placeholder.py         # "Coming Soon" widget
│
├── pdf2print/                            # PDF2PRINT MODE (Phase 3 - placeholder)
│   ├── __init__.py
│   └── pdf2print_placeholder.py         # "Coming Soon" widget
│
└── README.md                             # Updated documentation
```

---

## 🎨 UI/UX Design

### Overall Layout Structure

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  MULTI-SERVER PRINT                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────────┐ ┌────────────────────────────────────────────────┐ │
│ │  SERVER LIST         │ │  CONTENT AREA (Dynamic)                        │ │
│ │                      │ │                                                │ │
│ │  🟢 Production       │ │  ┌──────────────────────────────────────────┐ │ │
│ │  📡 192.168.1.100    │ │  │  MODE SELECTOR                           │ │ │
│ │                      │ │  │  [RIP2PRINT] [IMG2PRINT] [PDF2PRINT]    │ │ │
│ │  🟢 Backup           │ │  └──────────────────────────────────────────┘ │ │
│ │  📡 192.168.1.101    │ │                                                │ │
│ │                      │ │  ┌──────────────────────────────────────────┐ │ │
│ │  [🔄 Refresh]        │ │  │  JOB TYPE SELECTOR (RIP2PRINT)           │ │ │
│ │                      │ │  │  [Single Server] [Dual Server]           │ │ │
│ └──────────────────────┘ │  └──────────────────────────────────────────┘ │ │
│                          │                                                │ │
│                          │  ┌──────────────────────────────────────────┐ │ │
│                          │  │  JOB CONFIGURATION                        │ │ │
│                          │  │  (Based on selected job type)             │ │ │
│                          │  │                                           │ │ │
│                          │  │  • Browse RIP Folder(s)                   │ │ │
│                          │  │  • File Pattern (BMP/TIFF)                │ │ │
│                          │  │  • Files Detected: 1,234                  │ │ │
│                          │  │  • Number of Copies                       │ │ │
│                          │  │  • Collation Type                         │ │ │
│                          │  │  • Page Range                             │ │ │
│                          │  │  • Reverse/Continuous                     │ │ │
│                          │  │                                           │ │ │
│                          │  │  [START PRINTING] [STOP]                  │ │ │
│                          │  └──────────────────────────────────────────┘ │ │
│                          │                                                │ │
│                          │  ┌──────────────────────────────────────────┐ │ │
│                          │  │  PROGRESS & STATUS                        │ │ │
│                          │  │  ████████████░░░░░░░░░░░░░ 55%            │ │ │
│                          │  │  Printing: Page 123/234                   │ │ │
│                          │  └──────────────────────────────────────────┘ │ │
│                          └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Navigation Flow

```
MULTI-SERVER PRINT SECTION
    │
    ├─→ LEFT: Server List (persistent across all modes)
    │   ├─ Server 1 (IP:Port) 🟢/🔴
    │   ├─ Server 2 (IP:Port) 🟢/🔴
    │   └─ [Refresh Button]
    │
    └─→ RIGHT: Dynamic Content Area
        │
        ├─→ LEVEL 1: Mode Selector
        │   ├─ [RIP2PRINT] ← Active
        │   ├─ [IMG2PRINT] ← Coming Soon
        │   └─ [PDF2PRINT] ← Coming Soon
        │
        └─→ LEVEL 2: Job Type Selector (for RIP2PRINT)
            ├─ [Single Server] ← Shows Single Server Widget
            └─ [Dual Server] ← Shows Dual Server Widget
                │
                ├─→ Single Server Widget
                │   ├─ Server Selection (dropdown from left list)
                │   ├─ Browse RIP Folder
                │   ├─ File Pattern: BMP/TIFF
                │   ├─ Total Files: N
                │   ├─ Collation Type 1/2
                │   ├─ Page Range: All/Specify
                │   ├─ Reverse Order / Continuous Mode (radio)
                │   └─ [Start] [Stop]
                │
                └─→ Dual Server Widget
                    ├─ Server 1 Selection + Folder
                    ├─ Server 2 Selection + Folder
                    ├─ Same Folder Mode (checkbox)
                    ├─ File Pattern: BMP/TIFF
                    ├─ Total Files: N (Server 1: X, Server 2: Y)
                    ├─ Collation Type 1/2
                    ├─ Page Range: All/Specify
                    ├─ Reverse Order (only)
                    └─ [Start] [Stop]
```

---

## 🔧 Technical Implementation

### 1. Main Widget Orchestration

**File:** `multi_server_section.py`

```python
class MultiServerPrintSection(QWidget):
    """
    Main orchestrator for Multi-Server Print Section
    Maintains LEFT panel (server list) + RIGHT panel (dynamic content)
    """
    
    def __init__(self):
        self.server_manager = PrintServerManager()
        self.left_panel = self._create_server_list_panel()  # Persistent
        self.right_stack = QStackedWidget()  # Dynamic content
        
        # Add mode selector as first page
        self.mode_selector = ModeSelectorWidget()
        self.right_stack.addWidget(self.mode_selector)
        
        # Add mode-specific sections
        self.rip2print_section = RIP2PrintSection(self.server_manager)
        self.right_stack.addWidget(self.rip2print_section)
        
        # Placeholders
        self.img2print_placeholder = IMG2PrintPlaceholder()
        self.pdf2print_placeholder = PDF2PrintPlaceholder()
        self.right_stack.addWidget(self.img2print_placeholder)
        self.right_stack.addWidget(self.pdf2print_placeholder)
        
        # Connect mode selector
        self.mode_selector.mode_selected.connect(self._switch_mode)
```

### 2. Mode Selector Widget

**File:** `mode_selector/mode_selector_widget.py`

```python
class ModeSelectorWidget(QWidget):
    """
    Top-level mode selector: RIP2PRINT | IMG2PRINT | PDF2PRINT
    """
    mode_selected = Signal(str)  # "rip2print", "img2print", "pdf2print"
    
    def __init__(self):
        # Create three prominent buttons
        self.rip2print_btn = QPushButton("🖨️ RIP2PRINT")
        self.img2print_btn = QPushButton("🖼️ IMG2PRINT")
        self.pdf2print_btn = QPushButton("📄 PDF2PRINT")
        
        # Style and layout
        # Connect signals
```

### 3. RIP2PRINT Section

**File:** `rip2print/rip2print_section.py`

```python
class RIP2PrintSection(QWidget):
    """
    RIP2PRINT mode - shows job type selector + content
    """
    
    def __init__(self, server_manager):
        self.server_manager = server_manager
        
        # Job type selector
        self.job_type_selector = JobTypeSelector()
        
        # Content stack
        self.content_stack = QStackedWidget()
        self.single_server_widget = SingleServerWidget(server_manager)
        self.dual_server_widget = DualServerWidget(server_manager)
        
        self.content_stack.addWidget(self.single_server_widget)
        self.content_stack.addWidget(self.dual_server_widget)
        
        # Connect selector
        self.job_type_selector.job_type_selected.connect(self._switch_job_type)
```

### 4. Single Server Widget

**File:** `rip2print/single_server/single_server_widget.py`

```python
class SingleServerWidget(QWidget):
    """
    Single Server Job Submission UI
    """
    
    def __init__(self, server_manager):
        self.server_manager = server_manager
        self.worker = None
        self.thread = None
        
        # UI Components
        self.server_combo = QComboBox()  # Select from available servers
        self.folder_edit = QLineEdit()
        self.browse_btn = QPushButton("Browse")
        self.pattern_combo = QComboBox()  # BMP / TIFF
        self.file_count_label = QLabel("Files detected: 0")
        
        # Collation type
        self.collation_group = QButtonGroup()
        self.collate_type1_radio = QRadioButton("Type 1: Range × Copies")
        self.collate_type2_radio = QRadioButton("Type 2: Copies per Page × Range")
        
        # Number of copies
        self.copies_spin = QSpinBox()
        
        # Page range
        self.range_all_radio = QRadioButton("All pages")
        self.range_specify_radio = QRadioButton("Specify range")
        self.range_from_spin = QSpinBox()
        self.range_to_spin = QSpinBox()
        
        # Order/Mode selection (mutually exclusive)
        self.order_mode_group = QButtonGroup()
        self.reverse_order_radio = QRadioButton("Reverse Order")
        self.continuous_mode_radio = QRadioButton("Continuous Mode")
        
        # Actions
        self.start_btn = QPushButton("START PRINTING")
        self.stop_btn = QPushButton("STOP")
        
        # Progress
        self.progress_bar = QProgressBar()
        self.status_log = QTextEdit()
```

**File:** `rip2print/single_server/single_server_worker.py`

```python
class SingleServerWorker(QObject):
    """
    Worker for single server printing with collation support
    """
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(bool)
    error = Signal(str)
    
    def __init__(self, config: SingleServerConfig):
        self.config = config
        self.printer = None
        self._cancelled = False
        
    def run(self):
        # Connect to server
        # Discover files
        # Apply page range filter
        # Build print sequence based on collation type
        # Print with progress callbacks
        pass
    
    def _build_collation_type1_sequence(self, files):
        """
        Type 1: 1 to page_range × num_copies
        Example: [1,2,3,4,5] × 3 copies = [1,2,3,4,5, 1,2,3,4,5, 1,2,3,4,5]
        """
        pass
    
    def _build_collation_type2_sequence(self, files):
        """
        Type 2: num_copies per page × range
        Example: [1,2,3,4,5] × 3 copies = [1,1,1, 2,2,2, 3,3,3, 4,4,4, 5,5,5]
        """
        pass
```

### 5. Dual Server Widget

**File:** `rip2print/dual_server/dual_server_widget.py`

```python
class DualServerWidget(QWidget):
    """
    Dual Server Job Submission UI
    Supports:
    - Same folder (odd/even split)
    - Different folders (server 1 folder, server 2 folder)
    """
    
    def __init__(self, server_manager):
        self.server_manager = server_manager
        self.worker1 = None
        self.worker2 = None
        self.threads = []
        
        # Server selection
        self.server1_combo = QComboBox()
        self.server2_combo = QComboBox()
        
        # Folder selection
        self.same_folder_checkbox = QCheckBox("Use same folder for both servers")
        self.folder1_edit = QLineEdit()
        self.folder2_edit = QLineEdit()
        self.browse1_btn = QPushButton("Browse Server 1 Folder")
        self.browse2_btn = QPushButton("Browse Server 2 Folder")
        
        # When same_folder is checked, folder2 is hidden
        self.same_folder_checkbox.toggled.connect(self._toggle_folder_mode)
        
        # Rest similar to single server but NO continuous mode
        # Only Reverse Order option
```

**File:** `rip2print/dual_server/dual_server_worker.py`

```python
class DualServerWorker(QObject):
    """
    Coordinator for dual server printing
    Manages two separate workers for Server 1 and Server 2
    """
    
    def __init__(self, config: DualServerConfig):
        self.config = config
        self.worker1 = None
        self.worker2 = None
        
    def run(self):
        # Discover files from folder(s)
        # Split files into odd/even
        # Build sequences based on collation type
        # Start both workers in parallel
        # Monitor progress from both
        pass
    
    def _split_odd_even(self, files):
        """
        Split files into odd and even sequences
        Odd: [1, 3, 5, 7, ...]
        Even: [2, 4, 6, 8, ...]
        """
        pass
```

---

## 📊 Data Models

### Single Server Configuration

```python
@dataclass
class SingleServerConfig:
    server_id: str
    server_name: str
    server_ip: str
    server_port: int
    rip_folder: str
    file_pattern: str  # "*.bmp" or "*.tiff"
    num_copies: int
    collation_type: int  # 1 or 2
    page_range_mode: str  # "all" or "specify"
    page_range_from: int
    page_range_to: int
    order_mode: str  # "normal", "reverse", "continuous"
    max_wait_time: int  # For continuous mode only
```

### Dual Server Configuration

```python
@dataclass
class DualServerConfig:
    server1_id: str
    server2_id: str
    same_folder: bool
    folder1: str
    folder2: str  # Empty if same_folder is True
    file_pattern: str
    num_copies: int
    collation_type: int
    page_range_mode: str
    page_range_from: int
    page_range_to: int
    reverse_order: bool
```

---

## 🎯 Feature Requirements (Detailed)

### RIP2PRINT - Single Server

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 1 | Browse RIP Folder | Select folder containing BMP/TIFF files | ✅ Required |
| 2 | Sort Files | Natural sort (1, 2, 10, not 1, 10, 2) | ✅ Required |
| 3 | File Pattern | BMP / TIFF selection | ✅ Required |
| 4 | No Subdirectories | Flat folder only (recursive disabled) | ✅ Required |
| 5 | File Count Display | Show total files detected | ✅ Required |
| 6 | Collation Type 1 | Range × Copies [1,2,3] × 2 = [1,2,3,1,2,3] | ✅ Required |
| 7 | Collation Type 2 | Copies per Page [1,2,3] × 2 = [1,1,2,2,3,3] | ✅ Required |
| 8 | Page Range - All | Print all files | ✅ Required |
| 9 | Page Range - Specify | From X to Y | ✅ Required |
| 10 | Reverse Order | Print in reverse sequence | ✅ Required |
| 11 | Continuous Mode | Monitor folder for new files | ✅ Required |
| 12 | Mutual Exclusion | Reverse OR Continuous (not both) | ✅ Required |
| 13 | Live Status - Files Sent | Display files sent to server | ✅ Required |
| 14 | Live Status - Files Printed | Display files confirmed printed | ✅ Required |
| 15 | Live Status - Speed (MPM) | Display meters per minute (future) | ⏳ Future |

### RIP2PRINT - Dual Server

| # | Feature | Description | Status |
|---|---------|-------------|--------|
| 1 | Two Server Selection | Select Server 1 and Server 2 | ✅ Required |
| 2 | Same Folder Mode | Checkbox: Use one folder for both | ✅ Required |
| 3 | Separate Folder Mode | Browse folder for each server | ✅ Required |
| 4 | Odd/Even Split | Server 1 gets odd pages, Server 2 gets even | ✅ Required |
| 5 | Sort Files | Natural sort in both folders | ✅ Required |
| 6 | File Pattern | BMP / TIFF selection | ✅ Required |
| 7 | File Count Display | Total files in both folders | ✅ Required |
| 8 | Collation Type 1 | Same logic, but odd pages always Server 1 | ✅ Required |
| 9 | Collation Type 2 | Same logic, but copies stay on same server | ✅ Required |
| 10 | Page Range - All | Print all files | ✅ Required |
| 11 | Page Range - Specify | From X to Y | ✅ Required |
| 12 | Reverse Order Only | Only reverse, NO continuous mode | ✅ Required |
| 13 | Parallel Printing | Both servers print simultaneously | ✅ Required |
| 14 | Live Status - Dual Display | Status for both servers independently | ✅ Required |
| 15 | Live Status - Files Sent | Display for Server 1 and Server 2 | ✅ Required |
| 16 | Live Status - Files Printed | Display for Server 1 and Server 2 | ✅ Required |
| 17 | Live Status - Speed (MPM) | Display for both servers (future) | ⏳ Future |

---

## 🔄 Workflow Diagrams

### Single Server - Collation Type 1
```
Input: Files [1, 2, 3, 4, 5], Copies = 3, Range = All

Processing:
Step 1: Discover files → [1, 2, 3, 4, 5]
Step 2: Apply range → [1, 2, 3, 4, 5] (all)
Step 3: Build sequence (Type 1) → [1,2,3,4,5, 1,2,3,4,5, 1,2,3,4,5]
Step 4: Print to Server → 15 print commands

Result: All pages printed 3 times in sequence
```

### Single Server - Collation Type 2
```
Input: Files [1, 2, 3, 4, 5], Copies = 3, Range = All

Processing:
Step 1: Discover files → [1, 2, 3, 4, 5]
Step 2: Apply range → [1, 2, 3, 4, 5] (all)
Step 3: Build sequence (Type 2) → [1,1,1, 2,2,2, 3,3,3, 4,4,4, 5,5,5]
Step 4: Print to Server → 15 print commands

Result: Each page printed 3 times before moving to next
```

### Dual Server - Same Folder
```
Input: Folder [1, 2, 3, 4, 5, 6], Copies = 2, Range = All, Same Folder = True

Processing:
Step 1: Discover files → [1, 2, 3, 4, 5, 6]
Step 2: Split odd/even → Odd: [1,3,5] | Even: [2,4,6]
Step 3: Build sequences (Type 1)
        Server 1: [1,3,5, 1,3,5]
        Server 2: [2,4,6, 2,4,6]
Step 4: Print in parallel → Server 1: 6 commands | Server 2: 6 commands

Result: Odd pages on Server 1, Even pages on Server 2, printed in parallel
```

### Dual Server - Separate Folders
```
Input: 
  Folder 1 [A1, A2, A3, A4]
  Folder 2 [B1, B2, B3, B4]
  Copies = 1, Range = All

Processing:
Step 1: Discover files
        Folder 1 → [A1, A2, A3, A4]
        Folder 2 → [B1, B2, B3, B4]
Step 2: Interleave odd/even
        Server 1 (odd from Folder 1): [A1, A3]
        Server 2 (even from Folder 2): [B2, B4]
        OR
        Server 1: All from Folder 1 [A1, A2, A3, A4]
        Server 2: All from Folder 2 [B1, B2, B3, B4]
Step 3: Print in parallel

Result: Each server prints its assigned files
```

---

## 🛠️ Implementation Phases

### Phase 1: Infrastructure Setup (Week 1)
**Goal:** Create folder structure and base classes

**Tasks:**
1. ✅ Create new folder structure
2. ✅ Move existing shared components to `shared/` folder
3. ✅ Create base classes and interfaces
4. ✅ Update imports and exports
5. ✅ Create placeholder widgets for IMG2PRINT and PDF2PRINT
6. ✅ Update main section to use new structure

**Deliverables:**
- New folder structure
- Updated imports
- Placeholders working
- No functionality broken

### Phase 2: Mode Selector (Week 1)
**Goal:** Implement top-level mode selection

**Tasks:**
1. ✅ Create `ModeSelectorWidget`
2. ✅ Implement three prominent buttons
3. ✅ Connect to main section orchestrator
4. ✅ Show/hide appropriate content
5. ✅ Style buttons (active state, hover, etc.)

**Deliverables:**
- Working mode selector
- Smooth transitions
- Visual feedback

### Phase 3: RIP2PRINT - Single Server (Week 2-3)
**Goal:** Complete single server functionality

**Tasks:**
1. ✅ Create `JobTypeSelector` widget
2. ✅ Implement `SingleServerWidget` UI
3. ✅ Create `SingleServerConfig` data model
4. ✅ Implement `SingleServerWorker` with:
   - File discovery and natural sort
   - BMP/TIFF pattern support
   - Collation Type 1 logic
   - Collation Type 2 logic
   - Page range filtering
   - Reverse order support
   - Continuous mode support
5. ✅ Connect signals and slots
6. ✅ Add progress tracking
7. ✅ Add error handling
8. ✅ Test thoroughly

**Deliverables:**
- Fully working single server printing
- All collation types working
- All page range options working
- Reverse and continuous modes working

### Phase 4: RIP2PRINT - Dual Server (Week 4-5)
**Goal:** Complete dual server functionality

**Tasks:**
1. ✅ Implement `DualServerWidget` UI
2. ✅ Create `DualServerConfig` data model
3. ✅ Implement `DualServerWorker` with:
   - Two server coordination
   - Same folder mode (odd/even split)
   - Separate folder mode
   - Collation Type 1 for dual servers
   - Collation Type 2 for dual servers
   - Parallel printing logic
   - Progress tracking for both servers
4. ✅ Handle server selection conflicts
5. ✅ Test edge cases
6. ✅ Add comprehensive error handling

**Deliverables:**
- Fully working dual server printing
- Odd/even split working correctly
- Both collation types working
- Parallel execution stable

### Phase 5: Polish & Documentation (Week 6)
**Goal:** Production readiness

**Tasks:**
1. ✅ Add validation and error messages
2. ✅ Improve UI/UX feedback
3. ✅ Add tooltips and help text
4. ✅ Write comprehensive tests
5. ✅ Update README.md
6. ✅ Create user documentation
7. ✅ Performance optimization
8. ✅ Code review and refactoring

**Deliverables:**
- Production-ready code
- Complete documentation
- User guide
- Test coverage

### Phase 6: IMG2PRINT (Future)
**Goal:** Implement image-to-print workflow

### Phase 7: PDF2PRINT (Future)
**Goal:** Implement PDF-to-print workflow

---

## 🏗️ Design Patterns

### 1. Strategy Pattern
- Different job submission strategies (Single/Dual)
- Different collation strategies (Type 1/Type 2)
- Different file patterns (BMP/TIFF)

### 2. Observer Pattern
- Progress updates from workers
- Server status changes
- UI state synchronization

### 3. Factory Pattern
- Worker creation based on job type
- Configuration creation based on mode

### 4. State Pattern
- UI state management (idle, configuring, printing, paused, error)
- Button enable/disable logic

### 5. Command Pattern
- Print commands queued to GIS servers
- Undo/cancel operations

---

## 🎨 UI/UX Best Practices

### Visual Hierarchy
1. **Level 1:** Mode buttons (large, prominent)
2. **Level 2:** Job type buttons (medium)
3. **Level 3:** Configuration forms (standard)
4. **Level 4:** Status and progress (subtle)

### Color Scheme
- **Primary Action:** Blue (#007bff)
- **Success:** Green (#28a745)
- **Warning:** Orange (#ffc107)
- **Danger/Stop:** Red (#dc3545)
- **Neutral:** Gray (#6c757d)

### Feedback
- ✅ Immediate visual feedback on button clicks
- ✅ Loading states for long operations
- ✅ Progress bars for printing
- ✅ Status messages in real-time
- ✅ Error messages with actionable guidance

### Accessibility
- ✅ Clear labels and tooltips
- ✅ Keyboard navigation support
- ✅ Logical tab order
- ✅ Proper contrast ratios
- ✅ Error messages that are easy to understand

---

## 🧪 Testing Strategy

### Unit Tests
- Configuration data models
- File sorting logic
- Collation sequence builders
- Page range filters
- Odd/even split logic

### Integration Tests
- Worker to UI communication
- Multi-threaded printing
- Server connection handling
- File discovery in folders

### End-to-End Tests
- Complete single server workflows
- Complete dual server workflows
- Error scenarios
- Edge cases (empty folders, network errors, etc.)

### Manual Testing Checklist
- [ ] Single server - Type 1 collation - All pages
- [ ] Single server - Type 1 collation - Range
- [ ] Single server - Type 2 collation - All pages
- [ ] Single server - Type 2 collation - Range
- [ ] Single server - Reverse order
- [ ] Single server - Continuous mode
- [ ] Dual server - Same folder - Type 1
- [ ] Dual server - Same folder - Type 2
- [ ] Dual server - Separate folders - Type 1
- [ ] Dual server - Separate folders - Type 2
- [ ] Dual server - Reverse order
- [ ] Error handling - Server offline
- [ ] Error handling - Folder not found
- [ ] Error handling - No files in folder
- [ ] Mode switching without errors
- [ ] Server list refresh

---

## 🔐 Error Handling

### Expected Errors
1. **Server Connection Failed**
   - Action: Show error message, suggest checking server status
   - UI: Keep form enabled, allow retry

2. **Folder Not Found**
   - Action: Show error message, highlight folder field
   - UI: Keep form enabled, allow re-browse

3. **No Files Detected**
   - Action: Show warning, list possible reasons
   - UI: Keep form enabled, allow configuration change

4. **Print Job Failed**
   - Action: Show detailed error from GIS server
   - UI: Enable retry or cancel

5. **Server Already Busy**
   - Action: Show message, suggest waiting
   - UI: Disable start button temporarily

### Error Recovery
- ✅ Graceful degradation
- ✅ Clear error messages
- ✅ Actionable suggestions
- ✅ Easy retry mechanisms
- ✅ State preservation where possible

---

## 📝 Code Style Guidelines

### Naming Conventions
- **Classes:** PascalCase (e.g., `SingleServerWidget`)
- **Functions:** snake_case (e.g., `build_collation_sequence`)
- **Constants:** UPPER_SNAKE_CASE (e.g., `MAX_COPIES`)
- **Private methods:** _snake_case (e.g., `_on_button_clicked`)

### Documentation
- Docstrings for all classes and public methods
- Inline comments for complex logic
- Type hints for function parameters and returns

### File Organization
```python
# 1. Imports (stdlib, third-party, local)
# 2. Constants
# 3. Helper functions
# 4. Main class
# 5. Helper classes
```

---

## 🚀 Performance Considerations

### Optimization Strategies
1. **Lazy Loading:** Only load components when needed
2. **Caching:** Cache file lists, server status
3. **Threading:** Keep UI responsive during operations
4. **Batch Processing:** Group operations where possible
5. **Memory Management:** Clear resources after use

### Bottlenecks to Avoid
- ❌ Blocking UI thread with long operations
- ❌ Loading all files into memory at once
- ❌ Redundant file system scans
- ❌ Excessive signal emissions

---

## 📚 Documentation Deliverables

1. **README.md** - Overview and quick start
2. **API_REFERENCE.md** - Class and method documentation
3. **USER_GUIDE.md** - Step-by-step usage instructions
4. **ARCHITECTURE.md** - Technical architecture details
5. **TROUBLESHOOTING.md** - Common issues and solutions

---

## ✅ Acceptance Criteria

### Must Have (MVP)
- ✅ Three mode buttons visible (RIP2PRINT functional, others placeholder)
- ✅ Single server job submission fully working
- ✅ Dual server job submission fully working
- ✅ Both collation types working correctly
- ✅ Page range filtering working
- ✅ Reverse order and continuous mode working
- ✅ BMP and TIFF file pattern support
- ✅ Progress tracking and status updates
- ✅ Error handling for common scenarios
- ✅ Server list integration maintained

### Should Have
- ✅ Smooth animations and transitions
- ✅ Comprehensive tooltips
- ✅ Detailed status messages
- ✅ Performance optimization
- ✅ Comprehensive documentation

### Could Have (Future)
- ⏳ Job history and logging
- ⏳ Job templates/presets
- ⏳ Print queue management
- ⏳ Advanced statistics
- ⏳ Email notifications on completion

---

## 🎯 Success Metrics

1. **Functionality:** 100% of requirements implemented
2. **Stability:** Zero crashes during normal operation
3. **Performance:** UI remains responsive (<100ms response)
4. **Code Quality:** Clean, modular, well-documented
5. **User Experience:** Intuitive navigation, clear feedback
6. **Maintainability:** Easy to add new modes/features

---

## 📞 Support & Maintenance

### Future Enhancements
- Add IMG2PRINT mode
- Add PDF2PRINT mode
- Add job scheduling
- Add print queue management
- Add advanced statistics dashboard

### Known Limitations
- Maximum file count: Limited by system memory
- Continuous mode: Polls filesystem (not event-driven)
- Network: No automatic server discovery

---

## 📋 Appendix

### A. File Pattern Support
- **BMP:** Standard bitmap format (current support)
- **TIFF:** Tagged Image File Format (to be added)
- **Future:** PNG, JPEG support in IMG2PRINT mode

### B. Collation Examples

**Type 1 Example:**
```
Input: [1, 2, 3], Copies = 2
Output: [1, 2, 3, 1, 2, 3]
```

**Type 2 Example:**
```
Input: [1, 2, 3], Copies = 2
Output: [1, 1, 2, 2, 3, 3]
```

### C. Dual Server Logic

**Same Folder Mode:**
```
Folder: [1, 2, 3, 4, 5, 6]
Server 1 (odd): [1, 3, 5]
Server 2 (even): [2, 4, 6]
```

**Separate Folder Mode:**
```
Folder 1: [A, B, C, D]
Folder 2: [W, X, Y, Z]
Server 1: [A, B, C, D]
Server 2: [W, X, Y, Z]
```

---

## 🎉 Conclusion

This restructuring plan provides a **solid foundation** for building a scalable, maintainable, and user-friendly multi-server print system. The modular architecture allows for easy addition of new modes and features while maintaining code quality and performance.

**Next Steps:**
1. Review and approve this plan
2. Begin Phase 1: Infrastructure setup
3. Iterative development with regular testing
4. User feedback and refinement

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-16  
**Status:** Ready for Implementation  
**Estimated Timeline:** 6 weeks for RIP2PRINT complete implementation

