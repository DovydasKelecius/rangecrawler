# RangePhantom – Project Requirements

**Modern, headless user simulation framework for cyber ranges and training**

### Core Purpose

Build a realistic, automated agent that behaves like a real human user inside any target environment (workstation, server, VM, container) for use in cyber ranges, red-team exercises, purple-team testing, training labs, and detection engineering.

### Non-Negotiable Requirements

| ID  | Requirement                               | Details / Rationale                                                                                                                                                                                           | Status  |
| --- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| R01 | **Realistic user simulation**             | Agent must perform believable sequences: browsing, Office/docs usage, email, file ops, chat, etc.                                                                                                             | Planned |
| R02 | **Fully headless operation**              | Zero GUI/X11/Wayland dependency on Linux, no RDP/WinForms on Windows. Runs as background service/daemon.                                                                                                      | Planned |
| R03 | **Single-binary or container deployment** | Preferred delivery: one static binary or official Docker/Podman image (multi-arch amd64 + arm64)                                                                                                              | Planned |
| R04 | **Easy-to-use configuration interface**   | Modern web dashboard (responsive, mobile-friendly) for:<br>• Creating/editing timelines<br>• Managing agents<br>• Viewing live activity                                                                       | Planned |
| R05 | **Scenario timeline editor**              | Drag-and-drop or YAML/JSON editor to define exact user behavior over time (e.g., “9:05 open Outlook → 9:15 browse SharePoint → 9:30 create Word doc”)                                                         | Planned |
| R06 | **Environment usability & health checks** | Before and during execution, the system must validate:<br>• Agent can reach C2/dashboard<br>• Required apps exist (browser, Office, etc.)<br>• Disk/space/network sane<br>• Clear error if preconditions fail | Planned |

### Non-Goals (explicitly out of scope)

- Real malware / exploit delivery
- Active defense or counter-detection
- Commercial support or SLA
