# 🗺️ Implementation Roadmap - Multi-Server Print Restructuring

## 📅 Project Timeline Overview

**Total Duration:** 6 weeks  
**Start Date:** TBD  
**Target Completion:** RIP2PRINT fully functional

---

## 🎯 Phase-by-Phase Breakdown

## **PHASE 1: Infrastructure Setup** (Week 1 - Days 1-5)

### 🎯 Goal
Create the new folder structure and reorganize existing code without breaking functionality.

### 📋 Tasks

#### Day 1: Folder Structure Creation
- [ ] **Task 1.1:** Create new folder structure
  ```bash
  mkdir -p shared mode_selector rip2print/{single_server,dual_server} img2print pdf2print
  ```
- [ ] **Task 1.2:** Create all `__init__.py` files
- [ ] **Task 1.3:** Update `.gitignore` if needed

#### Day 2-3: Move Existing Code to `shared/`
- [ ] **Task 1.4:** Move `server_manager.py` → `shared/server_manager.py`
- [ ] **Task 1.5:** Move `server_config.py` → `shared/server_config.py`
- [ ] **Task 1.6:** Move `add_server_dialog.py` → `shared/add_server_dialog.py`
- [ ] **Task 1.7:** Move `edit_server_dialog.py` → `shared/edit_server_dialog.py`
- [ ] **Task 1.8:** Update all imports in moved files
- [ ] **Task 1.9:** Update imports in `multi_server_section.py`
- [ ] **Task 1.10:** Test that application still runs

#### Day 4: Create Base Classes
- [ ] **Task 1.11:** Create `shared/base_worker.py` with `BaseWorker` class
  - Define common signals (progress, finished, error)
  - Define common methods (cancel, connect_server)
- [ ] **Task 1.12:** Create `shared/base_config.py` with base configuration
- [ ] **Task 1.13:** Document base classes

#### Day 5: Create Placeholder Widgets
- [ ] **Task 1.14:** Create `img2print/img2print_placeholder.py`
  ```python
  class IMG2PrintPlaceholder(QWidget):
      def __init__(self):
          # Show "Coming Soon" message with icon
  ```
- [ ] **Task 1.15:** Create `pdf2print/pdf2print_placeholder.py`
- [ ] **Task 1.16:** Style placeholder widgets nicely

### ✅ Acceptance Criteria
- ✅ New folder structure exists
- ✅ Existing code moved to `shared/`
- ✅ All imports updated and working
- ✅ Application runs without errors
- ✅ Base classes documented
- ✅ Placeholder widgets created

### 🧪 Testing Checklist
- [ ] Application launches successfully
- [ ] Server list displays correctly
- [ ] Can refresh server list
- [ ] No console errors

---

## **PHASE 2: Mode Selector Widget** (Week 1 - Days 6-7)

### 🎯 Goal
Implement the top-level mode selector (RIP2PRINT | IMG2PRINT | PDF2PRINT).

### 📋 Tasks

#### Day 6: Create Mode Selector Widget
- [ ] **Task 2.1:** Create `mode_selector/mode_selector_widget.py`
  ```python
  class ModeSelectorWidget(QWidget):
      mode_selected = Signal(str)  # "rip2print", "img2print", "pdf2print"
  ```
- [ ] **Task 2.2:** Design button layout (horizontal, prominent)
- [ ] **Task 2.3:** Add icons to buttons (🖨️ 🖼️ 📄)
- [ ] **Task 2.4:** Implement button styling
  - Normal state
  - Hover state
  - Active/selected state
- [ ] **Task 2.5:** Connect button signals

#### Day 7: Integrate Mode Selector
- [ ] **Task 2.6:** Update `multi_server_section.py`
  - Add mode selector as first widget in right panel
  - Add placeholders to stack
- [ ] **Task 2.7:** Implement `_switch_mode()` method
  ```python
  def _switch_mode(self, mode: str):
      if mode == "rip2print":
          self.right_stack.setCurrentWidget(self.rip2print_section)
      elif mode == "img2print":
          self.right_stack.setCurrentWidget(self.img2print_placeholder)
      # ...
  ```
- [ ] **Task 2.8:** Add "Back to Mode Selection" button (optional)
- [ ] **Task 2.9:** Test mode switching

### ✅ Acceptance Criteria
- ✅ Three mode buttons visible and styled
- ✅ Clicking buttons switches views
- ✅ Selected button shows active state
- ✅ Smooth transitions between modes
- ✅ Placeholders show "Coming Soon" message

### 🧪 Testing Checklist
- [ ] Mode selector appears on right panel
- [ ] All three buttons are clickable
- [ ] RIP2PRINT shows placeholder (for now)
- [ ] IMG2PRINT shows placeholder
- [ ] PDF2PRINT shows placeholder
- [ ] Active button styling works
- [ ] No console errors

---

## **PHASE 3: RIP2PRINT - Single Server** (Week 2-3)

### 🎯 Goal
Complete single server job submission with all features.

### 📋 Tasks

#### Week 2, Day 1-2: Create RIP2PRINT Structure
- [ ] **Task 3.1:** Create `rip2print/rip2print_section.py`
  ```python
  class RIP2PrintSection(QWidget):
      def __init__(self, server_manager):
          self.job_type_selector = JobTypeSelector()
          self.content_stack = QStackedWidget()
  ```
- [ ] **Task 3.2:** Create `rip2print/job_type_selector.py`
  ```python
  class JobTypeSelector(QWidget):
      job_type_selected = Signal(str)  # "single", "dual"
  ```
- [ ] **Task 3.3:** Design job type selector layout
- [ ] **Task 3.4:** Connect signals for job type switching

#### Week 2, Day 3-5: Single Server UI
- [ ] **Task 3.5:** Create `rip2print/single_server/single_server_widget.py`
- [ ] **Task 3.6:** Implement server selection dropdown
  ```python
  self.server_combo = QComboBox()
  # Populate from server_manager.get_all_servers()
  ```
- [ ] **Task 3.7:** Implement folder selection
  ```python
  self.folder_edit = QLineEdit()
  self.browse_btn = QPushButton("Browse")
  ```
- [ ] **Task 3.8:** Implement file pattern selection
  ```python
  self.pattern_combo = QComboBox()
  self.pattern_combo.addItems(["*.bmp", "*.tiff", "*.BMP", "*.TIFF"])
  ```
- [ ] **Task 3.9:** Implement file count display
  ```python
  self.file_count_label = QLabel("Files detected: 0")
  # Update on folder change
  ```
- [ ] **Task 3.10:** Implement collation type selector
  ```python
  self.collation_group = QButtonGroup()
  self.collate_type1 = QRadioButton("Type 1: Range × Copies")
  self.collate_type2 = QRadioButton("Type 2: Copies per Page × Range")
  ```
- [ ] **Task 3.11:** Implement copies spinbox
- [ ] **Task 3.12:** Implement page range selector
  ```python
  self.range_all_radio = QRadioButton("All pages")
  self.range_specify_radio = QRadioButton("Specify range")
  self.range_from_spin = QSpinBox()
  self.range_to_spin = QSpinBox()
  ```
- [ ] **Task 3.13:** Implement order/mode selector (mutual exclusion)
  ```python
  self.order_mode_group = QButtonGroup()
  self.reverse_order_radio = QRadioButton("Reverse Order")
  self.continuous_mode_radio = QRadioButton("Continuous Mode")
  ```
- [ ] **Task 3.14:** Add action buttons
  ```python
  self.start_btn = QPushButton("START PRINTING")
  self.stop_btn = QPushButton("STOP")
  ```
- [ ] **Task 3.15:** Add progress bar and status log
- [ ] **Task 3.16:** Style all components

#### Week 3, Day 1-2: Single Server Configuration
- [ ] **Task 3.17:** Create `rip2print/single_server/single_server_config.py`
  ```python
  @dataclass
  class SingleServerConfig:
      server_id: str
      server_name: str
      server_ip: str
      server_port: int
      rip_folder: str
      file_pattern: str
      num_copies: int
      collation_type: int  # 1 or 2
      page_range_mode: str  # "all" or "specify"
      page_range_from: int
      page_range_to: int
      order_mode: str  # "normal", "reverse", "continuous"
      max_wait_time: int
  ```
- [ ] **Task 3.18:** Add validation methods to config
- [ ] **Task 3.19:** Add to_dict() and from_dict() methods

#### Week 3, Day 3-5: Single Server Worker
- [ ] **Task 3.20:** Create `rip2print/single_server/single_server_worker.py`
- [ ] **Task 3.21:** Implement file discovery
  ```python
  def discover_files(self):
      files = list(Path(self.config.rip_folder).glob(self.config.file_pattern))
      files = sorted(files, key=natural_sort_key)
      return files
  ```
- [ ] **Task 3.22:** Implement page range filtering
  ```python
  def apply_page_range(self, files):
      if self.config.page_range_mode == "all":
          return files
      else:
          return files[from_idx:to_idx]
  ```
- [ ] **Task 3.23:** Implement Collation Type 1 sequence builder
  ```python
  def build_collation_type1_sequence(self, files):
      sequence = []
      for copy in range(self.config.num_copies):
          sequence.extend(files)
      return sequence
  ```
- [ ] **Task 3.24:** Implement Collation Type 2 sequence builder
  ```python
  def build_collation_type2_sequence(self, files):
      sequence = []
      for file in files:
          for copy in range(self.config.num_copies):
              sequence.append(file)
      return sequence
  ```
- [ ] **Task 3.25:** Implement reverse order logic
- [ ] **Task 3.26:** Implement continuous mode logic
  ```python
  def continuous_mode_loop(self):
      while not self._cancelled:
          new_files = discover_new_files()
          if new_files:
              print_files(new_files)
          time.sleep(5)  # Poll every 5 seconds
  ```
- [ ] **Task 3.27:** Implement server connection
  ```python
  def connect_to_server(self):
      from pages.rip_to_print.rip_to_print import GISPrintServerClient
      self.client = GISPrintServerClient(self.config.server_ip, self.config.server_port)
      return self.client.connect()
  ```
- [ ] **Task 3.28:** Implement print loop with progress
  ```python
  def run(self):
      # Connect
      # Discover files
      # Build sequence
      total = len(sequence)
      for idx, file in enumerate(sequence):
          if self._cancelled:
              break
          self.print_file(file)
          self.progress.emit(idx + 1, total, f"Printed {file.name}")
      self.finished.emit(True)
  ```
- [ ] **Task 3.29:** Add error handling and logging
- [ ] **Task 3.30:** Add cancel/abort logic

#### Week 3, Day 6-7: Integration and Testing
- [ ] **Task 3.31:** Connect UI signals to worker
- [ ] **Task 3.32:** Implement start_printing() method
  ```python
  def start_printing(self):
      config = self.build_config_from_ui()
      self.worker = SingleServerWorker(config)
      self.thread = QThread()
      self.worker.moveToThread(self.thread)
      # Connect signals
      self.thread.started.connect(self.worker.run)
      self.worker.progress.connect(self.update_progress)
      self.worker.finished.connect(self.on_finished)
      self.thread.start()
  ```
- [ ] **Task 3.33:** Implement stop_printing() method
- [ ] **Task 3.34:** Test with real BMP files
- [ ] **Task 3.35:** Test all collation types
- [ ] **Task 3.36:** Test all page range options
- [ ] **Task 3.37:** Test reverse order
- [ ] **Task 3.38:** Test continuous mode
- [ ] **Task 3.39:** Test error scenarios
- [ ] **Task 3.40:** Fix bugs

### ✅ Acceptance Criteria
- ✅ Job type selector shows Single/Dual buttons
- ✅ Single server UI complete and styled
- ✅ Can select server from dropdown
- ✅ Can browse and select RIP folder
- ✅ File count updates automatically
- ✅ Both collation types work correctly
- ✅ Page range filtering works
- ✅ Reverse order works
- ✅ Continuous mode works
- ✅ Progress tracking works
- ✅ Can stop printing mid-job
- ✅ Error handling works

### 🧪 Testing Checklist
- [ ] Select server → Folder → Start → Print completes
- [ ] Collation Type 1: Files print in correct order
- [ ] Collation Type 2: Each file repeats N times
- [ ] Page range 1-10: Only first 10 files print
- [ ] Reverse order: Files print in reverse
- [ ] Continuous mode: New files detected and printed
- [ ] Stop button: Printing stops immediately
- [ ] Error handling: Invalid folder shows error
- [ ] Progress bar: Updates in real-time
- [ ] Status log: Shows detailed messages

---

## **PHASE 4: RIP2PRINT - Dual Server** (Week 4-5)

### 🎯 Goal
Complete dual server job submission with odd/even splitting and parallel printing.

### 📋 Tasks

#### Week 4, Day 1-3: Dual Server UI
- [ ] **Task 4.1:** Create `rip2print/dual_server/dual_server_widget.py`
- [ ] **Task 4.2:** Implement dual server selection
  ```python
  self.server1_combo = QComboBox()  # Server 1 selection
  self.server2_combo = QComboBox()  # Server 2 selection
  ```
- [ ] **Task 4.3:** Implement same folder checkbox
  ```python
  self.same_folder_checkbox = QCheckBox("Use same folder for both servers")
  self.same_folder_checkbox.toggled.connect(self._toggle_folder_mode)
  ```
- [ ] **Task 4.4:** Implement dual folder selection
  ```python
  self.folder1_edit = QLineEdit()
  self.folder2_edit = QLineEdit()
  self.browse1_btn = QPushButton("Browse Server 1 Folder")
  self.browse2_btn = QPushButton("Browse Server 2 Folder")
  ```
- [ ] **Task 4.5:** Implement folder mode toggle logic
  ```python
  def _toggle_folder_mode(self, same_folder):
      if same_folder:
          self.folder2_edit.hide()
          self.browse2_btn.hide()
      else:
          self.folder2_edit.show()
          self.browse2_btn.show()
  ```
- [ ] **Task 4.6:** Implement file count display (separate for each server)
  ```python
  self.file_count1_label = QLabel("Server 1 files: 0")
  self.file_count2_label = QLabel("Server 2 files: 0")
  self.total_count_label = QLabel("Total files: 0")
  ```
- [ ] **Task 4.7:** Reuse collation, copies, page range components
- [ ] **Task 4.8:** Implement reverse order (NO continuous mode)
- [ ] **Task 4.9:** Add dual progress bars
  ```python
  self.progress1_bar = QProgressBar()  # Server 1
  self.progress2_bar = QProgressBar()  # Server 2
  ```
- [ ] **Task 4.10:** Add dual status logs
- [ ] **Task 4.11:** Style all components

#### Week 4, Day 4-5: Dual Server Configuration
- [ ] **Task 4.12:** Create `rip2print/dual_server/dual_server_config.py`
  ```python
  @dataclass
  class DualServerConfig:
      server1_id: str
      server2_id: str
      same_folder: bool
      folder1: str
      folder2: str
      file_pattern: str
      num_copies: int
      collation_type: int
      page_range_mode: str
      page_range_from: int
      page_range_to: int
      reverse_order: bool
  ```
- [ ] **Task 4.13:** Add validation (ensure servers are different)
- [ ] **Task 4.14:** Add serialization methods

#### Week 5, Day 1-4: Dual Server Worker
- [ ] **Task 4.15:** Create `rip2print/dual_server/dual_server_worker.py`
- [ ] **Task 4.16:** Implement file discovery (same or separate folders)
  ```python
  def discover_files(self):
      if self.config.same_folder:
          all_files = glob(self.config.folder1, pattern)
          odd_files, even_files = self.split_odd_even(all_files)
      else:
          odd_files = glob(self.config.folder1, pattern)
          even_files = glob(self.config.folder2, pattern)
      return odd_files, even_files
  ```
- [ ] **Task 4.17:** Implement odd/even split logic
  ```python
  def split_odd_even(self, files):
      odd = [f for idx, f in enumerate(files, 1) if idx % 2 == 1]
      even = [f for idx, f in enumerate(files, 1) if idx % 2 == 0]
      return odd, even
  ```
- [ ] **Task 4.18:** Implement collation for dual servers
  - Type 1: Odd pages all copies, Even pages all copies
  - Type 2: Each odd page N times, Each even page N times
  ```python
  def build_sequences(self, odd_files, even_files):
      if self.config.collation_type == 1:
          seq1 = odd_files * self.config.num_copies
          seq2 = even_files * self.config.num_copies
      else:  # Type 2
          seq1 = [f for f in odd_files for _ in range(num_copies)]
          seq2 = [f for f in even_files for _ in range(num_copies)]
      return seq1, seq2
  ```
- [ ] **Task 4.19:** Implement parallel worker coordination
  ```python
  def run(self):
      # Discover and split files
      seq1, seq2 = self.build_sequences(odd_files, even_files)
      
      # Create two workers
      self.worker1 = ServerPrintWorker(server1, seq1)
      self.worker2 = ServerPrintWorker(server2, seq2)
      
      # Start both in threads
      self.thread1.start()
      self.thread2.start()
      
      # Monitor both
      self.thread1.wait()
      self.thread2.wait()
  ```
- [ ] **Task 4.20:** Implement progress aggregation
  ```python
  def on_worker1_progress(self, current, total):
      self.progress.emit("server1", current, total, "Printing...")
  
  def on_worker2_progress(self, current, total):
      self.progress.emit("server2", current, total, "Printing...")
  ```
- [ ] **Task 4.21:** Implement reverse order for both servers
- [ ] **Task 4.22:** Add comprehensive error handling
- [ ] **Task 4.23:** Add cancel logic (stop both servers)

#### Week 5, Day 5-7: Integration and Testing
- [ ] **Task 4.24:** Connect UI to dual server worker
- [ ] **Task 4.25:** Implement start_printing() for dual server
- [ ] **Task 4.26:** Implement stop_printing() for dual server
- [ ] **Task 4.27:** Test same folder mode (odd/even split)
- [ ] **Task 4.28:** Test separate folder mode
- [ ] **Task 4.29:** Test both collation types
- [ ] **Task 4.30:** Test page range filtering
- [ ] **Task 4.31:** Test reverse order
- [ ] **Task 4.32:** Test parallel printing (both servers active)
- [ ] **Task 4.33:** Test error scenarios (one server fails)
- [ ] **Task 4.34:** Performance testing
- [ ] **Task 4.35:** Fix bugs

### ✅ Acceptance Criteria
- ✅ Dual server UI complete
- ✅ Can select two different servers
- ✅ Same folder mode works (odd/even split)
- ✅ Separate folder mode works
- ✅ Both collation types work
- ✅ Parallel printing works
- ✅ Both progress bars update independently
- ✅ Can stop both servers
- ✅ Error handling works (one server fails, other continues)

### 🧪 Testing Checklist
- [ ] Same folder: Odd pages on Server 1, Even on Server 2
- [ ] Separate folders: Each server gets its own folder
- [ ] Collation Type 1: Correct sequence on both servers
- [ ] Collation Type 2: Correct sequence on both servers
- [ ] Reverse order: Both servers print in reverse
- [ ] Parallel: Both servers print simultaneously
- [ ] Stop: Both servers stop when clicked
- [ ] Server 1 offline: Error shown, Server 2 continues (or stops?)
- [ ] Progress bars: Independent updates

---

## **PHASE 5: Polish & Documentation** (Week 6)

### 🎯 Goal
Production readiness - polish UI, add validation, write documentation.

### 📋 Tasks

#### Day 1-2: UI/UX Polish
- [ ] **Task 5.1:** Add tooltips to all controls
- [ ] **Task 5.2:** Improve button styling and hover effects
- [ ] **Task 5.3:** Add loading spinners for long operations
- [ ] **Task 5.4:** Add confirmation dialogs for important actions
- [ ] **Task 5.5:** Improve error message formatting
- [ ] **Task 5.6:** Add success notifications
- [ ] **Task 5.7:** Optimize layout spacing and alignment
- [ ] **Task 5.8:** Test on different screen sizes
- [ ] **Task 5.9:** Add keyboard shortcuts (e.g., Ctrl+S to start)

#### Day 3: Validation and Error Handling
- [ ] **Task 5.10:** Add folder validation (exists, readable)
- [ ] **Task 5.11:** Add server selection validation (not the same)
- [ ] **Task 5.12:** Add file pattern validation
- [ ] **Task 5.13:** Add range validation (from < to)
- [ ] **Task 5.14:** Add network error handling
- [ ] **Task 5.15:** Add file system error handling
- [ ] **Task 5.16:** Add user-friendly error messages
- [ ] **Task 5.17:** Add retry logic for transient errors

#### Day 4-5: Documentation
- [ ] **Task 5.18:** Update main README.md
- [ ] **Task 5.19:** Create USER_GUIDE.md with screenshots
- [ ] **Task 5.20:** Create API_REFERENCE.md
- [ ] **Task 5.21:** Create TROUBLESHOOTING.md
- [ ] **Task 5.22:** Add inline code comments
- [ ] **Task 5.23:** Add docstrings to all classes/methods
- [ ] **Task 5.24:** Create example configurations
- [ ] **Task 5.25:** Create video tutorial (optional)

#### Day 6: Testing and Bug Fixes
- [ ] **Task 5.26:** Perform end-to-end testing
- [ ] **Task 5.27:** Test edge cases
- [ ] **Task 5.28:** Performance testing (large file counts)
- [ ] **Task 5.29:** Memory leak testing
- [ ] **Task 5.30:** Create test suite (unit tests)
- [ ] **Task 5.31:** Fix all identified bugs
- [ ] **Task 5.32:** Code review and refactoring

#### Day 7: Final Review
- [ ] **Task 5.33:** Code cleanup (remove debug prints)
- [ ] **Task 5.34:** Optimize imports
- [ ] **Task 5.35:** Check code style consistency
- [ ] **Task 5.36:** Final testing pass
- [ ] **Task 5.37:** Create release notes
- [ ] **Task 5.38:** Tag version in git
- [ ] **Task 5.39:** Deploy to production
- [ ] **Task 5.40:** User training (if needed)

### ✅ Acceptance Criteria
- ✅ All UI elements polished
- ✅ Comprehensive validation in place
- ✅ All documentation complete
- ✅ All tests passing
- ✅ No known bugs
- ✅ Production ready

### 🧪 Final Testing Checklist
- [ ] All features work end-to-end
- [ ] No console errors or warnings
- [ ] No memory leaks
- [ ] Performance acceptable (< 2s startup)
- [ ] All error scenarios handled gracefully
- [ ] Documentation accurate and complete
- [ ] User feedback incorporated

---

## 📊 Progress Tracking

### Overall Progress

| Phase | Status | Start Date | End Date | Progress |
|-------|--------|------------|----------|----------|
| Phase 1: Infrastructure | 🔴 Not Started | - | - | 0% |
| Phase 2: Mode Selector | 🔴 Not Started | - | - | 0% |
| Phase 3: Single Server | 🔴 Not Started | - | - | 0% |
| Phase 4: Dual Server | 🔴 Not Started | - | - | 0% |
| Phase 5: Polish | 🔴 Not Started | - | - | 0% |

**Legend:**
- 🔴 Not Started
- 🟡 In Progress
- 🟢 Completed

---

## 🚧 Risk Management

### Identified Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing server list functionality | Medium | High | Thorough testing after each change |
| Odd/even split logic errors | Medium | High | Comprehensive unit tests |
| Thread synchronization issues | High | High | Use Qt signals/slots correctly |
| Performance issues with large file counts | Low | Medium | Test with 10,000+ files |
| Network connection failures | Medium | Medium | Robust error handling and retry logic |
| UI not scaling well | Low | Low | Test on different resolutions |

---

## 🎯 Definition of Done

A task is considered "done" when:
- ✅ Code is written and follows style guidelines
- ✅ Code is tested (manual or automated)
- ✅ No linter errors or warnings
- ✅ Documentation is updated
- ✅ Code is reviewed (self-review or peer)
- ✅ Committed to version control
- ✅ Integrated with main codebase
- ✅ Acceptance criteria met

---

## 📝 Daily Standup Questions

At the end of each day, answer:
1. **What did I complete today?**
2. **What will I work on tomorrow?**
3. **Are there any blockers?**
4. **Do I need help from anyone?**

---

## 🎉 Milestones

### Milestone 1: Infrastructure Ready (End of Week 1)
- ✅ New folder structure in place
- ✅ Mode selector working
- ✅ Placeholders functional

### Milestone 2: Single Server Complete (End of Week 3)
- ✅ All single server features working
- ✅ Both collation types functional
- ✅ Thoroughly tested

### Milestone 3: Dual Server Complete (End of Week 5)
- ✅ Dual server fully functional
- ✅ Parallel printing working
- ✅ Odd/even split working

### Milestone 4: Production Ready (End of Week 6)
- ✅ All documentation complete
- ✅ All tests passing
- ✅ UI polished
- ✅ Ready for users

---

## 📞 Support and Resources

### Documentation
- Qt Documentation: https://doc.qt.io/qtforpython/
- Python Threading: https://docs.python.org/3/library/threading.html

### Code Examples
- See `pages/rip_to_print/rip_to_print.py` for GIS client usage
- See `pages/pdf_img_rip_print/section.py` for worker patterns

### Help Channels
- Internal team chat
- Code review sessions
- Pair programming sessions

---

## 🔄 Change Log

| Date | Change | Reason |
|------|--------|--------|
| 2025-10-16 | Initial roadmap created | Project kickoff |

---

**This roadmap is a living document and will be updated as the project progresses.**

**Next Action:** Review and approve this roadmap, then begin Phase 1!

