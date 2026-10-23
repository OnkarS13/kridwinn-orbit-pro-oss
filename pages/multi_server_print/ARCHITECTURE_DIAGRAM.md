# 🏛️ Multi-Server Print Architecture - Visual Guide

## 📐 Component Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MULTI-SERVER PRINT SECTION                           │
│                      (main orchestrator widget)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  │                                   │
         ┌────────▼────────┐                 ┌───────▼────────┐
         │  LEFT PANEL     │                 │  RIGHT PANEL   │
         │  (Persistent)   │                 │  (Dynamic)     │
         │                 │                 │                │
         │  ┌───────────┐  │                 │  QStackedWidget│
         │  │ Server    │  │                 │                │
         │  │ List      │  │                 └────────┬───────┘
         │  │ Widget    │  │                          │
         │  └───────────┘  │              ┌───────────┴───────────────────┐
         │                 │              │                               │
         │  ┌───────────┐  │         ┌────▼────┐    ┌──────▼──────┐      │
         │  │ Refresh   │  │         │  Mode   │    │    Mode     │      │
         │  │ Button    │  │         │ Selector│    │   Content   │      │
         │  └───────────┘  │         │ Widget  │    │   Pages     │      │
         └─────────────────┘         └─────────┘    └─────────────┘
```

## 🔄 Navigation Flow Diagram

```
                        ┌──────────────────────┐
                        │  Application Starts  │
                        └──────────┬───────────┘
                                   │
                        ┌──────────▼───────────┐
                        │  Multi-Server Print  │
                        │    Section Loads     │
                        └──────────┬───────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
         ┌──────────▼──────────┐      ┌──────────▼──────────┐
         │   LEFT: Server List │      │  RIGHT: Mode Select │
         │   (Always Visible)  │      │   (Default View)    │
         └─────────────────────┘      └──────────┬──────────┘
                                                  │
                                      ┌───────────┼───────────┐
                                      │           │           │
                              ┌───────▼───┐  ┌───▼───┐  ┌───▼───┐
                              │RIP2PRINT  │  │IMG2   │  │PDF2   │
                              │ (Active)  │  │PRINT  │  │PRINT  │
                              └─────┬─────┘  │(Soon) │  │(Soon) │
                                    │        └───────┘  └───────┘
                        ┌───────────┴───────────┐
                        │                       │
                ┌───────▼────────┐    ┌────────▼────────┐
                │ Single Server  │    │  Dual Server    │
                │ Job Submission │    │  Job Submission │
                └───────┬────────┘    └────────┬────────┘
                        │                      │
                        │                      │
           ┌────────────┴────────┐   ┌─────────┴──────────┐
           │                     │   │                    │
      ┌────▼─────┐        ┌─────▼───▼──┐          ┌──────▼─────┐
      │Configure │        │   Start    │          │  Monitor   │
      │ Settings │        │  Printing  │          │  Progress  │
      └──────────┘        └────────────┘          └────────────┘
```

## 🗂️ Folder Structure Tree

```
pages/multi_server_print/
│
├── 📄 __init__.py                          # Module entry point
├── 📄 multi_server_section.py              # Main orchestrator
├── 📄 README.md                            # User documentation
├── 📄 RESTRUCTURING_PLAN.md               # This planning document
├── 📄 ARCHITECTURE_DIAGRAM.md             # Visual architecture
│
├── 📁 shared/                              # Shared components
│   ├── __init__.py
│   ├── server_manager.py                   # Server CRUD operations
│   ├── server_config.py                    # Server data models
│   ├── add_server_dialog.py               # Add server UI
│   ├── edit_server_dialog.py              # Edit server UI
│   └── base_worker.py                      # Base worker class
│
├── 📁 mode_selector/                       # Mode selection
│   ├── __init__.py
│   └── mode_selector_widget.py            # RIP/IMG/PDF buttons
│
├── 📁 rip2print/                           # RIP2PRINT mode
│   ├── __init__.py
│   ├── rip2print_section.py               # RIP2PRINT main widget
│   ├── job_type_selector.py               # Single/Dual selector
│   │
│   ├── 📁 single_server/                   # Single server mode
│   │   ├── __init__.py
│   │   ├── single_server_widget.py        # UI component
│   │   ├── single_server_worker.py        # Print worker
│   │   └── single_server_config.py        # Configuration
│   │
│   └── 📁 dual_server/                     # Dual server mode
│       ├── __init__.py
│       ├── dual_server_widget.py          # UI component
│       ├── dual_server_worker.py          # Print worker
│       └── dual_server_config.py          # Configuration
│
├── 📁 img2print/                           # IMG2PRINT mode (future)
│   ├── __init__.py
│   └── img2print_placeholder.py           # "Coming Soon"
│
└── 📁 pdf2print/                           # PDF2PRINT mode (future)
    ├── __init__.py
    └── pdf2print_placeholder.py           # "Coming Soon"
```

## 🎯 Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    MultiServerPrintSection                      │
│                         (QWidget)                               │
├─────────────────────────────────────────────────────────────────┤
│ - server_manager: PrintServerManager                            │
│ - left_panel: QWidget                                           │
│ - right_stack: QStackedWidget                                   │
│ - mode_selector: ModeSelectorWidget                             │
│ - rip2print_section: RIP2PrintSection                           │
├─────────────────────────────────────────────────────────────────┤
│ + __init__()                                                    │
│ + _create_server_list_panel() -> QWidget                        │
│ + _switch_mode(mode: str)                                       │
│ + _refresh_servers()                                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ contains
                ┌───────────────┴───────────────┐
                │                               │
┌───────────────▼──────────┐    ┌───────────────▼──────────┐
│   ModeSelectorWidget     │    │    RIP2PrintSection      │
│       (QWidget)          │    │       (QWidget)          │
├──────────────────────────┤    ├──────────────────────────┤
│                          │    │ - job_type_selector      │
├──────────────────────────┤    │ - content_stack          │
│ + rip2print_btn          │    │ - single_server_widget   │
│ + img2print_btn          │    │ - dual_server_widget     │
│ + pdf2print_btn          │    ├──────────────────────────┤
├──────────────────────────┤    │ + _switch_job_type()     │
│ mode_selected: Signal    │    └──────────────────────────┘
└──────────────────────────┘                │
                                            │ contains
                        ┌───────────────────┴───────────────┐
                        │                                   │
        ┌───────────────▼──────────┐        ┌───────────────▼──────────┐
        │  SingleServerWidget      │        │   DualServerWidget       │
        │      (QWidget)           │        │       (QWidget)          │
        ├──────────────────────────┤        ├──────────────────────────┤
        │ - config                 │        │ - config                 │
        │ - worker                 │        │ - worker1, worker2       │
        │ - thread                 │        │ - threads[]              │
        ├──────────────────────────┤        ├──────────────────────────┤
        │ + start_printing()       │        │ + start_printing()       │
        │ + stop_printing()        │        │ + stop_printing()        │
        │ + update_progress()      │        │ + update_progress()      │
        └──────────┬───────────────┘        └──────────┬───────────────┘
                   │ creates                           │ creates
                   │                                   │
        ┌──────────▼───────────┐          ┌───────────▼────────────┐
        │ SingleServerWorker   │          │  DualServerWorker      │
        │     (QObject)        │          │      (QObject)         │
        ├──────────────────────┤          ├────────────────────────┤
        │ - config             │          │ - config               │
        │ - printer            │          │ - worker1, worker2     │
        ├──────────────────────┤          ├────────────────────────┤
        │ + run()              │          │ + run()                │
        │ + cancel()           │          │ + cancel()             │
        │ + build_sequence()   │          │ + split_odd_even()     │
        └──────────────────────┘          └────────────────────────┘
```

## 🔌 Signal/Slot Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Actions                             │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Clicks "RIP2PRINT" button
         │
┌────────▼────────────────────────────────────────────────────────┐
│  ModeSelectorWidget.mode_selected.emit("rip2print")             │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Signal
         │
┌────────▼────────────────────────────────────────────────────────┐
│  MultiServerPrintSection._switch_mode("rip2print")              │
│  → Changes QStackedWidget to show RIP2PrintSection              │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Clicks "Single Server" button
         │
┌────────▼────────────────────────────────────────────────────────┐
│  JobTypeSelector.job_type_selected.emit("single")               │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Signal
         │
┌────────▼────────────────────────────────────────────────────────┐
│  RIP2PrintSection._switch_job_type("single")                    │
│  → Shows SingleServerWidget                                     │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Configures settings and clicks "Start Printing"
         │
┌────────▼────────────────────────────────────────────────────────┐
│  SingleServerWidget.start_printing()                            │
│  → Creates SingleServerWorker                                   │
│  → Moves worker to QThread                                      │
│  → Starts thread                                                │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Worker runs in background
         │
┌────────▼────────────────────────────────────────────────────────┐
│  SingleServerWorker.run()                                       │
│  → Connects to server                                           │
│  → Discovers files                                              │
│  → Builds print sequence                                        │
│  → Prints files                                                 │
│  → Emits progress signals                                       │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ Emits: progress(current, total, message)
         │
┌────────▼────────────────────────────────────────────────────────┐
│  SingleServerWidget.update_progress()                           │
│  → Updates progress bar                                         │
│  → Updates status label                                         │
│  → Appends to log                                               │
└────────┬────────────────────────────────────────────────────────┘
         │
         │ On completion: finished(success)
         │
┌────────▼────────────────────────────────────────────────────────┐
│  SingleServerWidget._on_finished()                              │
│  → Shows completion message                                     │
│  → Re-enables buttons                                           │
│  → Cleans up worker/thread                                      │
└─────────────────────────────────────────────────────────────────┘
```

## 🎭 State Machine Diagram

```
                    ┌──────────────┐
                    │    IDLE      │
                    │  (Initial)   │
                    └───────┬──────┘
                            │
                            │ User configures settings
                            │
                    ┌───────▼──────┐
                    │ CONFIGURING  │
                    │  (Form Edit) │
                    └───────┬──────┘
                            │
                            │ Clicks "Start Printing"
                            │
                    ┌───────▼──────┐
                    │ CONNECTING   │
                    │ (To Server)  │
                    └───────┬──────┘
                            │
                    ┌───────┴───────┐
                    │               │
            Connected       Connection Failed
                    │               │
            ┌───────▼──────┐  ┌────▼──────┐
            │  PRINTING    │  │   ERROR   │
            │  (Active)    │  │           │
            └───────┬──────┘  └────┬──────┘
                    │               │
        ┌───────────┼───────────┐   │
        │           │           │   │
   User Stops   Completes    Error │
        │           │           │   │
    ┌───▼───┐  ┌───▼───┐  ┌────▼───▼──┐
    │STOPPED│  │SUCCESS│  │   ERROR   │
    │       │  │       │  │  (Details) │
    └───┬───┘  └───┬───┘  └────┬──────┘
        │          │           │
        └──────────┴───────────┘
                   │
            ┌──────▼──────┐
            │    IDLE     │
            │  (Ready)    │
            └─────────────┘
```

## 🔁 Data Flow Diagram

```
┌─────────────┐
│    USER     │
└──────┬──────┘
       │ Selects RIP Folder
       │
┌──────▼──────────────────────────────────────────────┐
│              SingleServerWidget                     │
│  ┌────────────────────────────────────────────┐    │
│  │  folder_path = "/path/to/rip/folder"       │    │
│  │  file_pattern = "*.bmp"                    │    │
│  │  num_copies = 3                            │    │
│  │  collation_type = 1                        │    │
│  │  page_range = (1, 100)                     │    │
│  └────────────────┬───────────────────────────┘    │
└───────────────────┼────────────────────────────────┘
                    │ Creates config
                    │
       ┌────────────▼──────────────┐
       │  SingleServerConfig       │
       │  (Data Transfer Object)   │
       └────────────┬──────────────┘
                    │ Passed to worker
                    │
       ┌────────────▼──────────────────────────────┐
       │      SingleServerWorker                   │
       │  ┌──────────────────────────────────┐    │
       │  │ 1. Scan folder for files         │    │
       │  │    → files = [1.bmp, 2.bmp, ...] │    │
       │  ├──────────────────────────────────┤    │
       │  │ 2. Sort naturally                │    │
       │  │    → [1.bmp, 2.bmp, 10.bmp]      │    │
       │  ├──────────────────────────────────┤    │
       │  │ 3. Apply page range filter       │    │
       │  │    → [1.bmp...100.bmp]           │    │
       │  ├──────────────────────────────────┤    │
       │  │ 4. Build collation sequence      │    │
       │  │    Type 1: [1,2,3, 1,2,3, 1,2,3] │    │
       │  ├──────────────────────────────────┤    │
       │  │ 5. Connect to GIS server         │    │
       │  │    → GISPrintServerClient        │    │
       │  ├──────────────────────────────────┤    │
       │  │ 6. Send print commands           │    │
       │  │    For each file in sequence:    │    │
       │  │      → PRINT file_path           │    │
       │  │      → Emit progress signal      │    │
       │  └──────────────────────────────────┘    │
       └────────────┬──────────────────────────────┘
                    │ Emits signals
                    │
       ┌────────────▼──────────────┐
       │  progress(current, total) │
       │  finished(success)        │
       │  error(message)           │
       └────────────┬──────────────┘
                    │ Back to UI
                    │
┌───────────────────▼────────────────────────────────┐
│           SingleServerWidget                       │
│  ┌────────────────────────────────────────────┐   │
│  │  progress_bar.setValue(percentage)         │   │
│  │  status_label.setText(message)             │   │
│  │  log.append(message)                       │   │
│  └────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

## 🧩 Component Interaction Map

```
┌──────────────────────────────────────────────────────────────────┐
│                    MULTI-SERVER PRINT SYSTEM                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │  Server List    │◄────────┤ Server Manager  │               │
│  │  Widget         │         │ (CRUD)          │               │
│  └────────┬────────┘         └─────────────────┘               │
│           │                                                      │
│           │ Selected Server                                     │
│           │                                                      │
│  ┌────────▼────────────────────────────────────────┐            │
│  │           Mode Selector Widget                  │            │
│  │  [RIP2PRINT] [IMG2PRINT] [PDF2PRINT]           │            │
│  └────────┬────────────────────────────────────────┘            │
│           │                                                      │
│           │ Mode: "rip2print"                                   │
│           │                                                      │
│  ┌────────▼────────────────────────────────────────┐            │
│  │         RIP2PrintSection Widget                 │            │
│  │                                                  │            │
│  │  ┌──────────────────────────────────────────┐  │            │
│  │  │    Job Type Selector Widget              │  │            │
│  │  │    [Single Server] [Dual Server]         │  │            │
│  │  └───────┬──────────────────────────────────┘  │            │
│  │          │                                      │            │
│  │  ┌───────┴──────────┬────────────────────┐    │            │
│  │  │                  │                     │    │            │
│  │  ▼                  ▼                     │    │            │
│  │  Single Server    Dual Server             │    │            │
│  │  Widget           Widget                  │    │            │
│  │  │                │                       │    │            │
│  │  ├─Creates───────►├─Creates──────────────►│    │            │
│  │  │                │                       │    │            │
│  │  ▼                ▼                       │    │            │
│  │  Worker           Worker1 + Worker2      │    │            │
│  │  │                │                       │    │            │
│  │  └────Uses────────┴─Uses─────────────┐   │    │            │
│  │                                       │   │    │            │
│  │  ┌────────────────────────────────────▼───▼┐  │            │
│  │  │      GIS Print Server Client          │  │            │
│  │  │      (Network Communication)          │  │            │
│  │  │                                        │  │            │
│  │  │  • Connect to server                  │  │            │
│  │  │  • Send PRINT commands                │  │            │
│  │  │  • Receive status updates             │  │            │
│  │  │  • Handle errors                      │  │            │
│  │  └────────────────────────────────────────┘  │            │
│  └──────────────────────────────────────────────┘            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## 📊 Collation Logic Flowchart

### Type 1: Range × Copies

```
┌─────────────────┐
│  Input Files:   │
│  [1, 2, 3]      │
│  Copies: 3      │
└────────┬────────┘
         │
    ┌────▼────┐
    │ Iterate │
    │ Copies  │
    └────┬────┘
         │
    For copy 1, 2, 3:
         │
    ┌────▼────────────┐
    │ Append all files│
    │ to sequence     │
    └────┬────────────┘
         │
┌────────▼─────────┐
│  Output:         │
│  [1,2,3,1,2,3,   │
│   1,2,3]         │
└──────────────────┘
```

### Type 2: Copies per Page × Range

```
┌─────────────────┐
│  Input Files:   │
│  [1, 2, 3]      │
│  Copies: 3      │
└────────┬────────┘
         │
    ┌────▼────┐
    │ Iterate │
    │  Files  │
    └────┬────┘
         │
    For each file:
         │
    ┌────▼────────────┐
    │ Append file N   │
    │ times           │
    └────┬────────────┘
         │
┌────────▼─────────┐
│  Output:         │
│  [1,1,1,2,2,2,   │
│   3,3,3]         │
└──────────────────┘
```

## 🎯 Deployment Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    User's Computer                         │
│  ┌──────────────────────────────────────────────────────┐ │
│  │            Print Processing Application              │ │
│  │                                                      │ │
│  │  ┌────────────────────────────────────────────┐    │ │
│  │  │     Multi-Server Print Section             │    │ │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐│    │ │
│  │  │  │   Mode   │  │   Job    │  │  Worker  ││    │ │
│  │  │  │ Selector │  │   Type   │  │ Threads  ││    │ │
│  │  │  └──────────┘  └──────────┘  └────┬─────┘│    │ │
│  │  └─────────────────────────────────────┼──────┘    │ │
│  └────────────────────────────────────────┼───────────┘ │
└─────────────────────────────────────────────┼───────────┘
                                              │
                         Network (TCP/IP)     │
                                              │
                ┌─────────────────────────────┼─────────────────────┐
                │                             │                     │
                │                             │                     │
    ┌───────────▼───────────┐    ┌───────────▼───────────┐        │
    │  GIS Print Server 1   │    │  GIS Print Server 2   │        │
    │  192.168.1.100:2000   │    │  192.168.1.101:2000   │        │
    │                       │    │                       │        │
    │  ┌─────────────────┐ │    │  ┌─────────────────┐ │        │
    │  │ Print Controller│ │    │  │ Print Controller│ │        │
    │  └────────┬────────┘ │    │  └────────┬────────┘ │        │
    └───────────┼──────────┘    └───────────┼──────────┘        │
                │                            │                    │
    ┌───────────▼──────────┐    ┌───────────▼──────────┐        │
    │   Physical Printer 1  │    │   Physical Printer 2  │        │
    │   (Odd Pages)         │    │   (Even Pages)        │        │
    └───────────────────────┘    └───────────────────────┘        │
```

## 🎨 UI Component Styling Hierarchy

```
┌─────────────────────────────────────────────────────────┐
│              Global Application Style                   │
│              (Bootstrap-inspired colors)                │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
┌────────▼─────┐  ┌──────▼──────┐  ┌────▼──────┐
│  Primary     │  │  Secondary  │  │  Accent   │
│  #007bff     │  │  #6c757d    │  │  #28a745  │
│  (Actions)   │  │  (Text)     │  │  (Success)│
└──────────────┘  └─────────────┘  └───────────┘
         │
         │ Applied to
         │
┌────────▼─────────────────────────────────────────┐
│           Component-Level Styles                 │
├──────────────────────────────────────────────────┤
│                                                  │
│  Mode Buttons                                    │
│  ├─ Large (16pt font)                           │
│  ├─ Prominent (20px padding)                    │
│  └─ Active state (darker blue)                  │
│                                                  │
│  Job Type Buttons                                │
│  ├─ Medium (14pt font)                          │
│  ├─ Moderate (15px padding)                     │
│  └─ Active state (blue border)                  │
│                                                  │
│  Form Controls                                   │
│  ├─ Standard (12pt font)                        │
│  ├─ Minimal (8px padding)                       │
│  └─ Focus state (blue outline)                  │
│                                                  │
│  Status Indicators                               │
│  ├─ Connected: Green (#28a745)                  │
│  ├─ Disconnected: Red (#dc3545)                 │
│  └─ Warning: Orange (#ffc107)                   │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 📚 Quick Reference

### Key Files by Responsibility

| Responsibility | File Path | Description |
|---------------|-----------|-------------|
| **Main Orchestrator** | `multi_server_section.py` | Main widget, layout manager |
| **Server Management** | `shared/server_manager.py` | CRUD operations for servers |
| **Mode Selection** | `mode_selector/mode_selector_widget.py` | Top-level mode buttons |
| **RIP Main** | `rip2print/rip2print_section.py` | RIP2PRINT mode container |
| **Job Type Select** | `rip2print/job_type_selector.py` | Single/Dual selector |
| **Single Server UI** | `rip2print/single_server/single_server_widget.py` | UI for single server |
| **Single Server Logic** | `rip2print/single_server/single_server_worker.py` | Print logic |
| **Dual Server UI** | `rip2print/dual_server/dual_server_widget.py` | UI for dual server |
| **Dual Server Logic** | `rip2print/dual_server/dual_server_worker.py` | Print logic |

---

**This architecture ensures:**
- ✅ **Modularity** - Each component is self-contained
- ✅ **Scalability** - Easy to add new modes and features
- ✅ **Maintainability** - Clear separation of concerns
- ✅ **Testability** - Components can be tested independently
- ✅ **Reusability** - Shared components reduce duplication


