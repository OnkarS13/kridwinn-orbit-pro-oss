# ⚡ Quick Start Guide - Multi-Server Print Restructuring

## 📖 Reading Order

**Start here if you're new to this project!**

### 1️⃣ **Read This First** (5 minutes)
- ✅ **QUICK_START_GUIDE.md** ← You are here!
- Purpose: Get oriented and understand what to read next

### 2️⃣ **Understand the Big Picture** (15 minutes)
- 📘 **PROJECT_SUMMARY.md**
- Purpose: Understand what you're building and why
- Key sections:
  - Current vs Desired State
  - Key Requirements
  - Folder Structure
  - Collation Types Explained

### 3️⃣ **Learn the Architecture** (30 minutes)
- 🏛️ **ARCHITECTURE_DIAGRAM.md**
- Purpose: Visualize how components connect
- Key sections:
  - Component Hierarchy
  - Navigation Flow
  - Data Flow Diagrams
  - Signal/Slot Flow

### 4️⃣ **Understand Requirements** (1 hour)
- 🏗️ **RESTRUCTURING_PLAN.md**
- Purpose: Detailed specifications for every feature
- Key sections:
  - Proposed Architecture
  - UI/UX Design
  - Technical Implementation
  - Feature Requirements Tables

### 5️⃣ **Follow the Implementation Plan** (Daily reference)
- 🗺️ **IMPLEMENTATION_ROADMAP.md**
- Purpose: Step-by-step task list for 6 weeks
- Key sections:
  - Phase-by-phase breakdown
  - Daily tasks with checkboxes
  - Testing checklists
  - Progress tracking

---

## 🎯 What You're Building

### **In One Sentence:**
A hierarchical multi-mode print system that supports **RIP2PRINT** (with single/dual server options), **IMG2PRINT** (future), and **PDF2PRINT** (future) in a clean, modular architecture.

### **The User Experience:**

```
User Journey:
1. Click "MULTI-SERVER PRINT" tab
2. See three mode buttons: [RIP2PRINT] [IMG2PRINT] [PDF2PRINT]
3. Click [RIP2PRINT]
4. See two job buttons: [Single Server] [Dual Server]
5. Click [Single Server]
6. Fill configuration form:
   - Select server
   - Browse RIP folder
   - Choose BMP or TIFF
   - Set copies and collation type
   - Set page range
   - Choose reverse or continuous mode
7. Click "START PRINTING"
8. Watch progress in real-time
9. Job completes successfully!
```

---

## 🗂️ Folder Structure at a Glance

```
multi_server_print/
├── 📋 Documentation (read these!)
│   ├── PROJECT_SUMMARY.md
│   ├── ARCHITECTURE_DIAGRAM.md
│   ├── RESTRUCTURING_PLAN.md
│   ├── IMPLEMENTATION_ROADMAP.md
│   └── QUICK_START_GUIDE.md (you are here)
│
├── 🔧 Main Files
│   ├── multi_server_section.py      # Main orchestrator
│   └── __init__.py
│
├── 📁 shared/                        # Shared components
│   ├── server_manager.py
│   ├── server_config.py
│   ├── add_server_dialog.py
│   ├── edit_server_dialog.py
│   └── base_worker.py
│
├── 📁 mode_selector/                 # Top-level modes
│   └── mode_selector_widget.py
│
├── 📁 rip2print/                     # RIP2PRINT mode (Phase 1)
│   ├── rip2print_section.py
│   ├── job_type_selector.py
│   ├── single_server/               # Single server job
│   │   ├── single_server_widget.py
│   │   ├── single_server_worker.py
│   │   └── single_server_config.py
│   └── dual_server/                 # Dual server job
│       ├── dual_server_widget.py
│       ├── dual_server_worker.py
│       └── dual_server_config.py
│
├── 📁 img2print/                     # Future
└── 📁 pdf2print/                     # Future
```

**Key Principle:** Each button in the UI has its own folder!

---

## 🚀 Getting Started

### **Option A: Just Start Coding**
If you want to dive in immediately:

1. **Read:** `PROJECT_SUMMARY.md` (15 min)
2. **Skim:** `IMPLEMENTATION_ROADMAP.md` → Phase 1 tasks
3. **Start:** Create folder structure
4. **Test:** After each change

### **Option B: Understand Everything First** (Recommended)
If you want to understand the full scope:

1. **Read:** All 4 planning documents (2-3 hours)
2. **Visualize:** Draw your own diagram if it helps
3. **Plan:** Mark which tasks you'll do when
4. **Start:** Phase 1 with confidence

### **Option C: Learn by Doing**
If you learn best by building:

1. **Read:** `PROJECT_SUMMARY.md` (big picture)
2. **Start:** Phase 1, Task 1
3. **Reference:** Other docs as needed
4. **Iterate:** Build → Test → Refine

---

## 📋 Phase 1 Quick Checklist

**Goal:** Create infrastructure without breaking existing functionality

### **Day 1: Setup**
- [ ] Create all new folders
- [ ] Create all `__init__.py` files
- [ ] Test: App still runs

### **Day 2-3: Move Code**
- [ ] Move `server_manager.py` to `shared/`
- [ ] Move `server_config.py` to `shared/`
- [ ] Move `add_server_dialog.py` to `shared/`
- [ ] Move `edit_server_dialog.py` to `shared/`
- [ ] Update all imports
- [ ] Test: App still runs, server list works

### **Day 4: Base Classes**
- [ ] Create `shared/base_worker.py`
- [ ] Document base classes
- [ ] Test: No errors

### **Day 5: Placeholders**
- [ ] Create `img2print/img2print_placeholder.py`
- [ ] Create `pdf2print/pdf2print_placeholder.py`
- [ ] Style placeholders
- [ ] Test: Placeholders display "Coming Soon"

**End of Phase 1:** Everything still works, new structure in place!

---

## 🎓 Key Concepts You Need to Know

### **1. Collation Types**

**Type 1: Range × Copies**
```python
# Print all pages, then repeat
files = [1, 2, 3]
copies = 2
result = [1, 2, 3, 1, 2, 3]
```

**Type 2: Copies per Page**
```python
# Print each page N times, then next page
files = [1, 2, 3]
copies = 2
result = [1, 1, 2, 2, 3, 3]
```

### **2. Dual Server Odd/Even Split**

```python
# Same folder mode
files = [1, 2, 3, 4, 5, 6]
server1_files = [1, 3, 5]  # Odd pages
server2_files = [2, 4, 6]  # Even pages
```

### **3. Qt Threading Pattern**

```python
# Create worker
worker = SingleServerWorker(config)

# Create thread
thread = QThread()

# Move worker to thread
worker.moveToThread(thread)

# Connect signals
thread.started.connect(worker.run)
worker.progress.connect(self.update_progress)
worker.finished.connect(self.on_finished)

# Start thread
thread.start()
```

### **4. Signal/Slot Pattern**

```python
# Widget emits signal
class ModeSelectorWidget(QWidget):
    mode_selected = Signal(str)
    
    def on_button_click(self):
        self.mode_selected.emit("rip2print")

# Main section receives signal
class MultiServerPrintSection(QWidget):
    def __init__(self):
        self.mode_selector.mode_selected.connect(self._switch_mode)
    
    def _switch_mode(self, mode: str):
        # Handle mode switch
        pass
```

---

## 🧪 Testing Strategy

### **After Every Change:**
```python
# 1. Run the app
python app.py

# 2. Navigate to Multi-Server Print section

# 3. Check console for errors

# 4. Test basic functionality:
#    - Server list displays
#    - Refresh button works
#    - No crashes
```

### **After Each Phase:**
Refer to the acceptance criteria and testing checklist in `IMPLEMENTATION_ROADMAP.md`.

---

## 🛠️ Development Workflow

### **Daily Routine:**

**Morning:**
1. Review `IMPLEMENTATION_ROADMAP.md` for today's tasks
2. Check off completed tasks from yesterday
3. Plan today's work (3-5 tasks)

**During Development:**
1. Pick one task from the roadmap
2. Read relevant section in planning docs
3. Implement the feature
4. Test immediately
5. Commit to git
6. Move to next task

**End of Day:**
1. Update progress in roadmap
2. Note any blockers or questions
3. Plan tomorrow's tasks

---

## 📚 Document Reference Guide

### **When You Need To...**

| Task | Document | Section |
|------|----------|---------|
| Understand overall goals | PROJECT_SUMMARY.md | "What You Want to Achieve" |
| See folder structure | PROJECT_SUMMARY.md | "New Folder Structure" |
| Understand requirements | RESTRUCTURING_PLAN.md | "Feature Requirements" |
| Visualize architecture | ARCHITECTURE_DIAGRAM.md | Any diagram |
| Know what to do today | IMPLEMENTATION_ROADMAP.md | Current phase |
| Understand collation | PROJECT_SUMMARY.md | "Understanding Collation Types" |
| See UI mockups | RESTRUCTURING_PLAN.md | "UI/UX Design" |
| Check testing criteria | IMPLEMENTATION_ROADMAP.md | "Testing Checklist" |
| Understand signals/slots | ARCHITECTURE_DIAGRAM.md | "Signal/Slot Flow" |
| See code examples | RESTRUCTURING_PLAN.md | "Technical Implementation" |

---

## 🎯 Success Milestones

### **Week 1:** Infrastructure Ready ✅
- New folder structure exists
- Mode selector working
- Placeholders showing

### **Week 3:** Single Server Complete ✅
- Can select server and folder
- Both collation types work
- Page filtering works
- Printing works end-to-end

### **Week 5:** Dual Server Complete ✅
- Odd/even split works
- Both servers print in parallel
- All features functional

### **Week 6:** Production Ready ✅
- All documentation complete
- UI polished
- All tests passing
- Ready for users!

---

## 🔧 Useful Code Snippets

### **Create a New Widget**
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class MyWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        label = QLabel("Hello World")
        layout.addWidget(label)
```

### **Natural Sort Files**
```python
import re

def natural_sort_key(path):
    """Sort files naturally: 1, 2, 10 (not 1, 10, 2)"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(path))]

files = sorted(files, key=natural_sort_key)
```

### **File Discovery**
```python
from pathlib import Path

def discover_files(folder, pattern="*.bmp"):
    """Discover files in folder matching pattern"""
    path = Path(folder)
    if not path.exists():
        return []
    files = list(path.glob(pattern))
    return sorted(files, key=natural_sort_key)
```

### **Progress Update**
```python
# In worker
def run(self):
    total = len(files)
    for idx, file in enumerate(files):
        # Do work
        self.progress.emit(idx + 1, total, f"Processing {file.name}")

# In UI
def update_progress(self, current, total, message):
    percent = int((current / total) * 100)
    self.progress_bar.setValue(percent)
    self.status_label.setText(message)
```

---

## 🚨 Common Pitfalls to Avoid

### **1. Don't Move Everything at Once**
❌ Bad: Move all files to new structure in one go  
✅ Good: Move one file, update imports, test, commit

### **2. Don't Skip Testing**
❌ Bad: Implement 5 features, then test  
✅ Good: Implement 1 feature, test immediately

### **3. Don't Hardcode Paths**
❌ Bad: `"/home/user/rip/folder"`  
✅ Good: `Path(user_selected_folder)`

### **4. Don't Block UI Thread**
❌ Bad: Long operations in UI code  
✅ Good: Use QThread and workers

### **5. Don't Forget Error Handling**
❌ Bad: Assume everything works  
✅ Good: Try/except with user-friendly messages

---

## 🆘 Getting Help

### **Stuck on a Task?**
1. Re-read the relevant section in planning docs
2. Look at similar existing code
3. Check architecture diagrams for understanding
4. Break the task into smaller pieces
5. Ask specific questions with code examples

### **Something Not Clear?**
- Check `PROJECT_SUMMARY.md` for high-level explanation
- Check `ARCHITECTURE_DIAGRAM.md` for visual understanding
- Check `RESTRUCTURING_PLAN.md` for detailed specs

### **Need to Change Requirements?**
- Update `RESTRUCTURING_PLAN.md` with new requirements
- Update `IMPLEMENTATION_ROADMAP.md` with new tasks
- Continue development with updated plan

---

## ✅ Pre-Flight Checklist

**Before you start coding:**

- [ ] I have read `PROJECT_SUMMARY.md`
- [ ] I understand the overall goals
- [ ] I understand the folder structure
- [ ] I know what collation types are
- [ ] I know what odd/even split means
- [ ] I have reviewed Phase 1 tasks
- [ ] I have my development environment ready
- [ ] I have committed current code to git
- [ ] I am ready to start!

---

## 🎉 You're Ready!

You now have:
- ✅ Clear understanding of what to build
- ✅ Detailed plans and specifications
- ✅ Step-by-step implementation guide
- ✅ Visual diagrams for reference
- ✅ Testing strategies
- ✅ Code examples

**Next Action:** 
1. Read `PROJECT_SUMMARY.md` (if you haven't)
2. Review Phase 1 in `IMPLEMENTATION_ROADMAP.md`
3. Start Task 1.1: Create folder structure
4. Test after each change
5. Check off completed tasks
6. Keep building! 💪

---

## 📊 Time Estimates

| Document | Reading Time |
|----------|--------------|
| QUICK_START_GUIDE.md | 5 min |
| PROJECT_SUMMARY.md | 15 min |
| ARCHITECTURE_DIAGRAM.md | 30 min |
| RESTRUCTURING_PLAN.md | 60 min |
| IMPLEMENTATION_ROADMAP.md | 45 min |
| **Total** | **~2.5 hours** |

**But you don't need to read everything at once!**

Start with `PROJECT_SUMMARY.md` and reference others as needed.

---

## 🎓 Learning Resources

### **Qt/PySide6:**
- Official docs: https://doc.qt.io/qtforpython/
- Threading guide: https://doc.qt.io/qt-6/thread-basics.html

### **Python:**
- Pathlib: https://docs.python.org/3/library/pathlib.html
- Threading: https://docs.python.org/3/library/threading.html
- Dataclasses: https://docs.python.org/3/library/dataclasses.html

### **Design Patterns:**
- Refactoring Guru: https://refactoring.guru/design-patterns

---

**Good luck with your implementation! You've got this! 🚀**

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-16  
**Status:** Ready to Use  
**Next Step:** Read PROJECT_SUMMARY.md

