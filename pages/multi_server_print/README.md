# Multi-Server Print Module

## Overview

The Multi-Server Print module enables **parallel printing to multiple GIS Print Servers simultaneously**. Each server can have its own IP address, port, settings, and operate independently.

## Features

✅ **Multiple Print Servers** - Add, configure, and manage multiple printer servers  
✅ **Independent Operation** - Each server runs in its own thread with isolated state  
✅ **Parallel Printing** - Print to multiple servers simultaneously  
✅ **Per-Server Settings** - Each server has its own RIP folder, copies, filters, etc.  
✅ **Real-time Status** - Live connection status and progress for each server  
✅ **Persistent Configuration** - Server configurations saved and restored  
✅ **Easy Management** - Add/remove servers via intuitive UI  

## Architecture

```
MultiServerPrintSection (Main Widget)
├── PrintServerManager (Config Management)
│   └── PrinterServerConfig (Per-Server Data)
├── ServerControlWidget (Individual Server UI)
│   ├── Connection Status
│   ├── RIP Folder Selection
│   ├── Print Settings
│   ├── Page Selection
│   ├── Progress Display
│   └── Action Buttons
└── MultiServerPrintWorker (Print Thread)
    └── GUIRipPrinter (Print Engine)
```

## Usage

### 1. Add a New Server

1. Click the **"🖨️ MULTI-SERVER PRINT"** tab
2. Click **"+ Add"** button in the server list
3. Enter:
   - **Server Name**: e.g., "Production Printer"
   - **IP Address**: e.g., "192.168.1.100" or "localhost"
   - **Port**: e.g., 2000
4. Click **"Add Server"**

### 2. Configure Server Settings

For each server, configure:

- **RIP Folder**: Folder containing .bmp files to print
- **Number of Copies**: How many copies of each file (1-100)
- **File Pattern**: `*.bmp`, `*.BMP`, or `*.*`
- **Include Subdirectories**: Recursive folder search
- **Continuous Mode**: Monitor folder for new files
- **Max Wait Time**: Timeout for continuous mode (30-3600 sec)

### 3. Page Selection

Choose one of:
- **Print all pages**: All files in folder
- **Print range**: Specific range (from X to Y)
- **Odd only**: Only odd-numbered files (1, 3, 5, ...)
- **Even only**: Only even-numbered files (2, 4, 6, ...)
- **Reverse order**: ✓ Print in reverse (independent of mode)

### 4. Start Printing

1. Select a server from the list
2. Configure its settings
3. Click **"Start Printing"**
4. Monitor progress in real-time
5. Repeat for other servers (parallel operation!)

### 5. Stop Printing

- Click **"🛑 STOP PRINT SERVER"** to abort
- Sends immediate ABORT command to server
- Safe to stop and restart

## Configuration File

Servers are saved in `config/printer_servers.json`:

```json
{
  "server_uuid": {
    "id": "server_uuid",
    "name": "Production Printer",
    "ip": "192.168.1.100",
    "port": 2000,
    "rip_folder": "C:/rip_output/server1",
    "num_copies": 1,
    "pattern": "*.bmp",
    "recursive": false,
    "continuous_mode": false,
    "max_wait_time": 300,
    "page_filter": {
      "mode": "all",
      "from": 1,
      "to": 1000000,
      "reverse": false,
      "odd": false,
      "even": false
    }
  }
}
```

## Parallel Printing Example

**Scenario**: Print 10,000 files across 2 servers in half the time

```
Server 1 (192.168.1.100:2000)
├── RIP Folder: C:/jobs/batch1
├── Files: 5,000 .bmp files
└── Status: Printing... 2,500/5,000 (50%)

Server 2 (192.168.1.101:2000)
├── RIP Folder: C:/jobs/batch2
├── Files: 5,000 .bmp files
└── Status: Printing... 3,200/5,000 (64%)

Total Time: ~50% faster than sequential!
```

## Technical Details

### Threading Model

- Each server runs in a **separate QThread**
- **No blocking** - UI remains responsive
- **Signal/Slot** communication for thread safety
- **Isolated state** - One server crash doesn't affect others

### Network Communication

- **Independent TCP connections** per server
- **Dual-socket architecture** (main + abort)
- **Async pipelined queuing** for high throughput
- **Automatic reconnection** on failure

### Error Handling

- **Connection errors**: Displayed in server info panel
- **Print errors**: Stop current job, others continue
- **Validation**: Folder paths, file patterns checked
- **Graceful degradation**: Failed servers don't crash app

## Files Created

```
pages/multi_server_print/
├── __init__.py                  # Module exports
├── server_config.py             # PrinterServerConfig class
├── server_manager.py            # PrintServerManager class
├── add_server_dialog.py         # Add server dialog
├── server_control_widget.py     # Per-server UI widget
├── multi_server_section.py      # Main section widget
├── multi_server_worker.py       # Worker thread class
└── README.md                    # This file
```

## Integration

Added to `app.py`:
- New tab: **"🖨️ MULTI-SERVER PRINT"**
- Import: `from pages.multi_server_print.multi_server_section import MultiServerPrintSection`
- Stacked widget index: 8

## Future Enhancements

Potential improvements:
- Load balancing across servers
- Server groups for batch jobs
- Performance metrics dashboard
- Email notifications on completion
- Cloud server support
- Job queue management

## Troubleshooting

**Q: Server shows "Not Connected"**  
A: Check that GIS Print Server is running at the specified IP:port

**Q: Can I use different ports on the same IP?**  
A: Yes! e.g., 192.168.1.100:2000 and 192.168.1.100:2001

**Q: How many servers can I run simultaneously?**  
A: No hard limit, but 2-10 servers is practical for most systems

**Q: What if I remove a server while it's printing?**  
A: The UI prevents removal of active servers

**Q: Can I edit server settings while printing?**  
A: Settings are disabled during printing to prevent conflicts

## Support

For issues or questions:
1. Check connection status indicator
2. Review server info panel for error messages
3. Check logs in `logs/YYYY-MM-DD/{session_id}/`
4. Verify GIS Print Server is accessible

---

**Version**: 1.0  
**Last Updated**: 2024  
**License**: See project root

