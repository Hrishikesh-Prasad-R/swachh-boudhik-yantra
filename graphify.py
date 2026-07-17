#!/usr/bin/env python3.12
"""
graphify.py — Swachh Boudhik Yantra Workspace Graph Generator
──────────────────────────────────────────────────────────────
Uses the Gemini REST API to analyse the entire vacuum_ws workspace
and generate a comprehensive architecture map:

  • Package dependency graph (Mermaid)
  • ROS2 topic data-flow: node → topic → node (Mermaid)
  • TF tree (Mermaid)
  • Launch file startup sequence (Mermaid sequenceDiagram)
  • ros2_control architecture (Mermaid)
  • Human-readable summary

Outputs (in graphify_output/):
  workspace_graph.md   — Full report (open in VS Code with Mermaid plugin)
  summary.md           — Gemini summary only
  *.mmd                — Individual Mermaid diagram sources

Uses only stdlib + requests + python-dotenv — no gRPC needed.
Runs without an API key using --no-ai flag (static generation only).

Usage:
  python3.12 graphify.py                  # Gemini-enhanced (needs API key in .env)
  python3.12 graphify.py --no-ai          # Static mode (no API key needed)
  python3.12 graphify.py --workspace /path/to/vacuum_ws
  python3.12 graphify.py --model gemini-2.0-flash-lite
"""

import os
import sys
import json
import re
import textwrap
import argparse
from pathlib import Path
from datetime import datetime

# ── Minimal dependencies ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
except ImportError:
    print('[ERROR] python-dotenv missing: python3.12 -m pip install python-dotenv')
    sys.exit(1)

try:
    import requests
except ImportError:
    print('[ERROR] requests missing: python3.12 -m pip install requests')
    sys.exit(1)


# ── Gemini REST client (no gRPC / google-auth needed) ────────────────────────

class GeminiClient:
    """Thin wrapper around the Gemini generateContent REST endpoint."""

    BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models'

    def __init__(self, api_key: str, model: str = 'gemini-2.0-flash'):
        self.api_key = api_key
        self.model   = model
        self.url     = f'{self.BASE_URL}/{model}:generateContent?key={api_key}'

    def generate(self, prompt: str, max_tokens: int = 8192) -> str:
        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature':     0.2,
                'maxOutputTokens': max_tokens,
            },
        }
        print(f'[gemini] POST → {self.model} ({len(prompt):,} chars)...')
        resp = requests.post(
            self.url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=120,
        )
        if resp.status_code == 429:
            print(f'[warn] Gemini API quota exceeded (429). Falling back to static generation.')
            print('[warn] Get a new API key at: https://aistudio.google.com/apikey')
            return ''
        if resp.status_code != 200:
            print(f'[ERROR] Gemini API returned {resp.status_code}: {resp.text[:300]}')
            return ''

        data = resp.json()
        text = data['candidates'][0]['content']['parts'][0]['text']
        print(f'[gemini] Received {len(text):,} chars')
        return text


# ── Workspace Scanner ────────────────────────────────────────────────────────

class WorkspaceScanner:
    """Static analysis of the ROS2 workspace source tree."""

    def __init__(self, ws_root: Path):
        self.ws_root = ws_root
        self.src     = ws_root / 'src'

    def scan(self) -> dict:
        print(f'[scan] Workspace: {self.ws_root}')
        data = {
            'workspace_root': str(self.ws_root),
            'packages':     self._scan_packages(),
            'launch_files': self._scan_launch_files(),
            'node_files':   self._scan_node_files(),
            'xacro_files':  self._scan_xacro_files(),
            'config_files': self._scan_config_files(),
            'file_tree':    self._file_tree(),
        }
        return data

    def _scan_packages(self) -> list:
        packages = []
        for pkg_xml in sorted(self.src.rglob('package.xml')):
            try:
                import xml.etree.ElementTree as ET
                root = ET.parse(pkg_xml).getroot()
                name = root.findtext('name', '')
                deps = sorted(set(
                    d.text for tag in ('depend','build_depend','exec_depend')
                    for d in root.findall(tag) if d.text
                ))
                packages.append({
                    'name':        name,
                    'version':     root.findtext('version', ''),
                    'description': (root.findtext('description') or '').strip(),
                    'dependencies': deps,
                    'path':        str(pkg_xml.parent.relative_to(self.src)),
                })
                print(f'  [pkg] {name}  ({len(deps)} deps)')
            except Exception as e:
                print(f'  [warn] {pkg_xml}: {e}')
        return packages

    def _scan_launch_files(self) -> list:
        result = []
        for f in sorted(self.src.rglob('*.launch.py')):
            content = f.read_text(errors='ignore')
            result.append({
                'file': str(f.relative_to(self.src)),
                'nodes': re.findall(r"executable=['\"]([^'\"]+)['\"]", content),
                'packages': re.findall(
                    r"get_package_share_directory\(['\"]([^'\"]+)['\"]\)", content),
                'snippet': content[:3500],
            })
        return result

    def _scan_node_files(self) -> list:
        result = []
        for f in sorted(self.src.rglob('*.py')):
            if 'test' in f.parts:
                continue
            content = f.read_text(errors='ignore')
            if 'rclpy' not in content:
                continue
            result.append({
                'file': str(f.relative_to(self.src)),
                'publishers':  re.findall(
                    r"create_publisher\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", content),
                'subscribers': re.findall(
                    r"create_subscription\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", content),
                'services':    re.findall(
                    r"create_service\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", content),
                'snippet': content[:3500],
            })
        return result

    def _scan_xacro_files(self) -> list:
        result = []
        for f in sorted(self.src.rglob('*.xacro')):
            content = f.read_text(errors='ignore')
            result.append({
                'file': str(f.relative_to(self.src)),
                'includes': re.findall(r'xacro:include[^/]*/([^"\']+)', content),
                'snippet': content[:2000],
            })
        return result

    def _scan_config_files(self) -> list:
        result = []
        for f in sorted(self.src.rglob('*.yaml')):
            result.append({
                'file':    str(f.relative_to(self.src)),
                'content': f.read_text(errors='ignore')[:1500],
            })
        return result

    def _file_tree(self) -> str:
        lines = []
        for p in sorted(self.src.rglob('*')):
            rel   = p.relative_to(self.src)
            depth = len(rel.parts) - 1
            icon  = '📁 ' if p.is_dir() else '📄 '
            lines.append('  ' * depth + icon + p.name)
        return '\n'.join(lines[:250])


# ── Prompt Builder ───────────────────────────────────────────────────────────

def build_prompt(data: dict) -> str:
    # Compact serialisation — strip large snippets from lists
    def compact(lst, skip=('snippet',), max_content=600):
        out = []
        for item in lst:
            d = {}
            for k, v in item.items():
                if k in skip:
                    continue
                if k == 'content' and len(str(v)) > max_content:
                    d[k] = str(v)[:max_content] + '...'
                else:
                    d[k] = v
            out.append(d)
        return json.dumps(out, indent=2)

    return textwrap.dedent(f"""
You are a senior ROS2 robotics architect. Analyse the following workspace for the
"Swachh Boudhik Yantra" autonomous vacuum robot (ROS2 Jazzy, Gazebo Harmonic,
ros2_control, Stage 4B complete) and produce a complete architecture graph.

Current stage: Stage 4B — Autonomous Exploration (Nav2 + Frontier Exploration).
Packages present: vacuum_bringup, vacuum_controller, vacuum_description,
vacuum_gazebo, vacuum_interfaces, vacuum_slam, vacuum_utils,
vacuum_nav2 (NEW — Nav2 config), vacuum_exploration (NEW — WFD frontier exploration).

=== FILE TREE ===
{data['file_tree']}

=== PACKAGES ===
{compact(data['packages'])}

=== NODE FILES (publishers/subscribers) ===
{compact(data['node_files'])}

=== LAUNCH FILES ===
{compact(data['launch_files'])}

=== XACRO FILES ===
{compact(data['xacro_files'])}

=== CONFIG / YAML ===
{compact(data['config_files'])}

---
Generate ALL of the following sections. Use EXACT names from the data.
Each section MUST start with the exact header shown.

## [SECTION: PACKAGE_GRAPH]
Mermaid flowchart (graph TD) of all 9 vacuum_* packages and their dependencies.
Internal packages as solid nodes. External deps shown only on edge labels.
Include vacuum_nav2 and vacuum_exploration as new nodes.

## [SECTION: DATAFLOW_GRAPH]
Mermaid flowchart showing full ROS2 topic data-flow.
Nodes (executables) = rectangles. Topics = rounded rectangles.
Arrow direction = data flow direction. Include all known topics.
Must include: frontier_detector → /frontiers → exploration_manager → Nav2 → /cmd_vel → robot.

## [SECTION: TF_TREE]
Mermaid graph of the complete TF tree from odom to all leaf links.

## [SECTION: LAUNCH_SEQUENCE]
Mermaid sequenceDiagram showing exploration.launch.py startup sequence.
Participants: User, exploration.launch.py, Gazebo, RTAB-Map, Nav2, FrontierDetector, ExplorationManager.
Show TimerAction delays (T+0, T+12, T+20, T+28).

## [SECTION: CONTROLLER_ARCH]
Mermaid flowchart showing the full Stage 4B autonomous loop:
Unknown Environment → FrontierDetector → GoalSelector → ExplorationManager
→ Nav2 NavigateToPose → MPPI Controller → /cmd_vel → Robot → RTAB-Map
→ /rtabmap/map → FrontierDetector (cycle).

## [SECTION: SUMMARY]
Structured markdown:
- Stages completed (1 through 4B)
- Package table (name, purpose, key topics) — all 9 packages
- Key design decisions for Stage 4B (blacklist expiry, composite scoring, 3-condition completion)
- What is NOT yet implemented (stages 5–10)
- Critical path to Stage 5 (Localisation + Goal-Based Navigation)
""").strip()


# ── Static Graph Generator (no AI needed) ────────────────────────────────────

class StaticGraphGenerator:
    """
    Generates Mermaid diagrams from scanned workspace data alone.
    Produces deterministic, accurate graphs without API calls.
    Used as fallback when Gemini is unavailable or quota is exceeded.
    """

    INTERNAL_PKGS = {
        'vacuum_bringup', 'vacuum_controller', 'vacuum_description',
        'vacuum_gazebo', 'vacuum_interfaces', 'vacuum_slam', 'vacuum_utils',
        'vacuum_nav2', 'vacuum_exploration',
    }

    def generate_all(self, data: dict) -> dict:
        return {
            'PACKAGE_GRAPH':   self._package_graph(data),
            'DATAFLOW_GRAPH':  self._dataflow_graph(data),
            'TF_TREE':         self._tf_tree(),
            'LAUNCH_SEQUENCE': self._launch_sequence(),
            'CONTROLLER_ARCH': self._controller_arch(),
            'SUMMARY':         self._summary(data),
        }

    def _package_graph(self, data: dict) -> str:
        lines = ['```mermaid', 'graph TD']
        lines.append('    %% Swachh Boudhik Yantra — Package Dependencies (Stage 4B)')
        # Style internal packages
        for p in data['packages']:
            n = p['name']
            lines.append(f'    {n}["{n}\n{p["version"]}"]')
        lines.append('')
        # Edges
        for p in data['packages']:
            n = p['name']
            for dep in p['dependencies']:
                if dep in self.INTERNAL_PKGS:
                    lines.append(f'    {n} --> {dep}')
        lines.append('')
        # Styling — original packages
        lines.append('    style vacuum_bringup     fill:#4A90D9,color:#fff')
        lines.append('    style vacuum_controller  fill:#7ED321,color:#fff')
        lines.append('    style vacuum_description fill:#9B59B6,color:#fff')
        lines.append('    style vacuum_gazebo      fill:#E67E22,color:#fff')
        lines.append('    style vacuum_interfaces  fill:#1ABC9C,color:#fff')
        lines.append('    style vacuum_slam        fill:#F39C12,color:#fff')
        lines.append('    style vacuum_utils       fill:#E74C3C,color:#fff')
        # Styling — Stage 4B new packages (highlighted)
        lines.append('    style vacuum_nav2        fill:#C0392B,color:#fff,stroke:#922B21,stroke-width:2px')
        lines.append('    style vacuum_exploration fill:#8E44AD,color:#fff,stroke:#6C3483,stroke-width:2px')
        lines.append('```')
        return '\n'.join(lines)

    def _dataflow_graph(self, data: dict) -> str:
        return '''```mermaid
graph LR
    %% ROS2 Topic Data-Flow — Stage 4B (Autonomous Exploration)

    subgraph Simulation ["Gazebo Harmonic Simulation"]
        GZ_CLK["Gazebo Clock"]
        GZ_CAM["D435i RGBD Sensor Plugin"]
        GZ_CTRL["gz_ros2_control Plugin"]
    end

    subgraph Bridge ["ros_gz_bridge"]
        CLK_B["/clock Bridge"]
        CAM_B["Camera Bridges (5 topics)"]
        D2L["depthimage_to_laserscan"]
    end

    subgraph Controllers ["vacuum_controller"]
        DDC["diff_drive_controller"]
        JSB["joint_state_broadcaster"]
        NOISE["odometry_noise_node"]
    end

    subgraph SLAM ["vacuum_slam"]
        RTAB["rtabmap Node"]
    end

    subgraph Nav2Stack ["vacuum_nav2 — Nav2 Stack"]
        BT["bt_navigator\nNavigateToPose action"]
        PLAN["planner_server\nSmacPlannerHybrid"]
        CTRL["controller_server\nMPPIController"]
        BEH["behavior_server\nspin / backup / wait"]
        VEL["velocity_smoother"]
    end

    subgraph Exploration ["vacuum_exploration — Stage 4B"]
        FD["frontier_detector\nWavefront Frontier Detection"]
        EM["exploration_manager\n9-state FSM"]
        FV["frontier_visualizer"]
        MET["exploration_metrics\n1Hz CSV logging"]
    end

    %% Clock
    GZ_CLK -->|gz.msgs.Clock| CLK_B
    CLK_B -->|/clock| DDC & RTAB & BT & FD & EM

    %% Camera bridge
    GZ_CAM -->|gz image streams| CAM_B
    CAM_B -->|/camera/color/image_raw| RTAB
    CAM_B -->|/camera/depth/image_rect_raw| RTAB & D2L
    CAM_B -->|/camera/color/camera_info| RTAB & D2L
    D2L -->|/scan_from_depth| PLAN & CTRL

    %% ros2_control loop
    DDC -->|joint velocities| GZ_CTRL
    GZ_CTRL -->|joint states| JSB
    DDC -->|/odom| RTAB & EM & MET
    DDC -->|/tf odom→base_footprint| RTAB & BT

    %% SLAM outputs
    RTAB -->|/rtabmap/map| MAP_2D(["🗺️ /rtabmap/map\nOccupancyGrid"])
    RTAB -->|map→odom TF| BT
    MAP_2D -->|static layer| PLAN
    MAP_2D -->|subscribe| FD
    MAP_2D -->|subscribe| MET

    %% Frontier detection
    FD -->|/frontiers/markers| FV
    FD -->|/frontiers/centroids| EM

    %% Exploration manager → Nav2
    EM -->|NavigateToPose action goal| BT
    BT -->|plan request| PLAN
    PLAN -->|global path| CTRL
    CTRL -->|/diff_drive_controller/cmd_vel_unstamped| VEL
    VEL -->|smoothed cmd_vel| DDC
    BT -->|action result| EM

    %% Visualisation
    EM -->|/exploration/status JSON| MET & FV
    EM -->|/exploration/current_goal| FV
    FV -->|/exploration/trajectory| RVIZ(["🖥️ RViz2"])
    FV -->|/exploration/status_text| RVIZ
    MAP_2D --> RVIZ
```'''

    def _tf_tree(self) -> str:
        return '''```mermaid
graph TD
    %% TF Tree — Swachh Boudhik Yantra (Stage 3 & 4A)
    MAP(["map\npublished by rtabmap"])
    ODOM["odom\npublished by diff_drive_controller"]
    BF["base_footprint\nground contact plane"]
    BL["base_link\nrobot chassis CoM"]
    LW["left_wheel_link"]
    RW["right_wheel_link"]
    CW["caster_wheel_link"]

    CAM_M["camera_mount_link\nchassis bracket"]
    CAM_L["camera_link\nD435i physical centre"]
    CAM_CF["camera_color_frame"]
    CAM_CO["camera_color_optical_frame\n(z-forward, x-right, y-down)"]
    CAM_DF["camera_depth_frame"]
    CAM_DO["camera_depth_optical_frame\n(z-forward, x-right, y-down)"]

    ARM["arm_mount_link\nArm placeholder"]
    VAC["vacuum_mount_link\nVacuum placeholder"]

    MAP -->|dynamic| ODOM
    ODOM -->|dynamic| BF
    BF -->|fixed| BL
    BL -->|continuous| LW
    BL -->|continuous| RW
    BL -->|fixed| CW
    BL -->|fixed| CAM_M
    BL -->|fixed| ARM
    BL -->|fixed| VAC

    %% D435i Camera TF Chain (Stage 3)
    CAM_M -->|fixed| CAM_L
    CAM_L -->|fixed| CAM_CF
    CAM_CF -->|fixed (rpy=-pi/2,0,-pi/2)| CAM_CO
    CAM_L -->|fixed| CAM_DF
    CAM_DF -->|fixed (rpy=-pi/2,0,-pi/2)| CAM_DO

    style MAP fill:#F39C12,color:#fff
    style ODOM fill:#4A90D9,color:#fff
    style BF fill:#7ED321,color:#fff
    style BL fill:#9B59B6,color:#fff
```'''

    def _launch_sequence(self) -> str:
        return '''```mermaid
sequenceDiagram
    participant U   as User
    participant EL  as exploration.launch.py
    participant GZ  as Gazebo Harmonic
    participant GZC as gz_ros2_control
    participant RTAB as RTAB-Map
    participant NAV2 as Nav2 Stack
    participant FD  as frontier_detector
    participant EM  as exploration_manager
    participant MET as exploration_metrics

    U->>EL: ./start.sh explore apartment
    note over EL: T+0s — Launch Gazebo simulation
    EL->>GZ: ros2 launch vacuum_bringup sim.launch.py
    GZ->>GZC: init gz_ros2_control plugin
    note over GZ,GZC: T+3s robot spawned, /odom & /tf active

    note over EL: T+12s — Launch SLAM
    EL->>RTAB: ros2 launch vacuum_slam slam.launch.py delete_db:=true
    RTAB->>RTAB: Wipe old DB, begin mapping
    note over RTAB: /rtabmap/map publishing, map→odom TF active

    note over EL: T+20s — Launch Nav2
    EL->>NAV2: ros2 launch vacuum_nav2 nav2.launch.py
    NAV2->>NAV2: lifecycle_manager activates all Nav2 nodes
    note over NAV2: NavigateToPose action server ready

    note over EL: T+28s — Launch exploration nodes
    EL->>FD: start frontier_detector (WFD, 2 Hz)
    EL->>EM: start exploration_manager (FSM, 10 Hz)
    EL->>MET: start exploration_metrics (1 Hz CSV)
    note over FD,EM: IDLE → WAITING_FOR_MAP → DETECT → SELECT → NAVIGATING

    EM->>NAV2: NavigateToPose goal (frontier centroid)
    NAV2->>GZC: MPPI cmd_vel → robot moves
    GZC->>RTAB: new depth frames → map grows
    RTAB->>FD: /rtabmap/map updated
    FD->>EM: /frontiers/centroids (new frontiers)
    note over EM: Repeat until FINISHED
```'''

    def _controller_arch(self) -> str:
        return '''```mermaid
graph TD
    %% Stage 4B — Full Autonomous Exploration Loop

    ENV(["🏠 Unknown Environment"])
    CAM["D435i RealSense\nRGB-D Camera"]
    RTAB["RTAB-Map\n(maps free & unknown cells)"]
    MAP(["📦 /rtabmap/map\nOccupancyGrid — live"])

    FD["frontier_detector\nWavefront Frontier Detection\n2 Hz"]
    FRONTS(["📍 /frontiers/centroids\nPoseArray"])

    EM["exploration_manager\n9-state FSM\nblacklist + 3-condition completion"]
    GS["goal_selector\n(embedded in manager)\ninfo_gain − dist − obs_penalty"]

    BT["Nav2 bt_navigator\nexplore.xml BT\nNavigateToPose action"]
    PLAN["planner_server\nSmacPlannerHybrid\nallow_unknown=true"]
    MPPI["controller_server\nMPPIController\nDiffDrive model"]

    DDC["diff_drive_controller\nvelocity → wheel joints"]
    HW["gz_ros2_control\nGazebo Physics"]

    STATUS(["📊 /exploration/status\nJSON: state, coverage%, goals"])
    VIZ["frontier_visualizer\n🟢 frontiers 🔴 selected\n🟡 goal 🔵 trajectory"]
    MET["exploration_metrics\n1Hz CSV\nmetadata.yaml + summary.txt"]

    ENV --> CAM
    CAM --> RTAB
    RTAB --> MAP
    MAP --> FD
    FD --> FRONTS
    FRONTS --> EM
    EM --> GS
    GS --> BT
    BT --> PLAN
    PLAN --> MPPI
    MPPI --> DDC
    DDC --> HW
    HW --> ENV
    HW -->|/odom| RTAB
    EM --> STATUS
    STATUS --> VIZ
    STATUS --> MET
    MAP --> MET

    style FD fill:#8E44AD,color:#fff
    style EM fill:#8E44AD,color:#fff
    style BT fill:#C0392B,color:#fff
    style PLAN fill:#C0392B,color:#fff
    style MPPI fill:#C0392B,color:#fff
    style RTAB fill:#F39C12,color:#fff
    style DDC fill:#4A90D9,color:#fff
    style HW fill:#E67E22,color:#fff
```'''

    def _summary(self, data: dict) -> str:
        pkgs = data['packages']
        purpose = {
            'vacuum_bringup':     'Master launch orchestration (sim.launch.py + RViz)',
            'vacuum_controller':  'ros2_control config, diff drive, noise & diagnostics nodes',
            'vacuum_description': 'Xacro URDF robot model (13 links, 12 joints including D435i camera)',
            'vacuum_gazebo':      'Gazebo world, SDF, /clock and D435i bridge config',
            'vacuum_interfaces':  'Custom msgs/srvs/actions placeholder',
            'vacuum_slam':        'RTAB-Map SLAM node, map_saver, slam_rviz config',
            'vacuum_utils':       'Validation scripts, TF checker, graphify, metrics, benchmark tools',
            'vacuum_nav2':        'Stage 4B — Nav2 config: MPPI + SmacHybrid + explore.xml BT + costmaps',
            'vacuum_exploration': 'Stage 4B — WFD frontier detection, 9-state FSM manager, metrics CSV',
        }
        lines = []
        lines.append('### Stages Complete')
        lines.append('| Stage | Status | Description |')
        lines.append('|-------|--------|-------------|')
        lines.append('| Stage 1 | ✅ Complete | Robot URDF, Gazebo world, TF tree |')
        lines.append('| Stage 2 | ✅ Complete | ros2_control, diff_drive, odometry |')
        lines.append('| Stage 3 | ✅ Complete | D435i RGB-D Integration, Diagnostics, Validation |')
        lines.append('| Stage 4A | ✅ Complete | Manual RTAB-Map Mapping, Map Export |')
        lines.append('| Stage 4B | ✅ Complete | Autonomous Exploration (Nav2 + Frontier WFD) |')
        lines.append('| Stage 5 | ⏳ Next | Localisation & Goal-Based Navigation (AMCL + pre-built map) |')
        lines.append('| Stage 6 | ⏳ Pending | Coverage Planning & Autonomous Vacuuming |')
        lines.append('| Stage 7 | ⏳ Pending | Robotic Arm & Manipulation |')
        lines.append('| Stage 8 | ⏳ Pending | Mission Manager (Manual/Semi/Auto) |')
        lines.append('| Stage 9 | ⏳ Pending | Benchmarking & Research Evaluation |')
        lines.append('| Stage 10 | ⏳ Pending | Jetson Deployment & Sim-to-Real |')
        lines.append('')
        lines.append('### Package Summary')
        lines.append('| Package | Stage | Purpose |')
        lines.append('|---------|-------|---------|')
        for p in pkgs:
            stage = '4B 🆕' if p['name'] in ('vacuum_nav2', 'vacuum_exploration') else '1–4A'
            lines.append(f'| `{p["name"]}` | {stage} | {purpose.get(p["name"], p["description"][:60])} |')
        lines.append('')
        lines.append('### Key Design Decisions (Stage 4B)')
        lines.append('- **Nav2 in Stage 4B**: Frontier exploration requires NavigateToPose — Nav2 introduced here, not Stage 5.')
        lines.append('- **MPPI + SmacHybrid**: Non-holonomic trajectory optimisation (MPPI) with Hybrid A* global planning.')
        lines.append('- **Custom explore.xml BT**: adds BackUp recovery for tight-corner frontier situations.')
        lines.append('- **Blacklist with 60s expiry**: failed frontiers are excluded but re-enabled after map updates.')
        lines.append('- **3-condition completion**: requires no-frontier count + map growth stall + robot stationary (prevents premature stop).')
        lines.append('- **Coverage metric**: free_cells / (free_cells + unknown_cells) × 100, logged every second.')
        lines.append('- **Metadata YAML per run**: git commit hash, config filenames, rtabmap.db path for full reproducibility.')
        lines.append('')
        lines.append('### Not Yet Implemented (Stages 5–10)')
        lines.append('- Stage 5: AMCL localisation on pre-built map + click-to-goal navigation')
        lines.append('- Stage 6: Coverage planning algorithm (boustrophedon / spiral)')
        lines.append('- Stage 7: MoveIt2 robotic arm manipulation')
        lines.append('- Stage 8: Mission manager (manual / semi-auto / fully-auto modes)')
        lines.append('- Stage 9: Q1 paper benchmarking — ATE/RPE, coverage %, comparative table')
        lines.append('- Stage 10: Jetson Orin Nano hardware deployment & sim-to-real transfer')
        lines.append('')
        lines.append('### Stage 5 Critical Path')
        lines.append('1. Run Stage 4B exploration on apartment world — collect rosbag + metrics CSV.')
        lines.append('2. Save map with ./save_map.sh — verify full apartment coverage.')
        lines.append('3. Create vacuum_nav2/config/amcl_params.yaml for AMCL localisation.')
        lines.append('4. Write nav2_localization.launch.py: load saved map + AMCL + NavigateToPose.')
        lines.append('5. Test click-to-goal navigation in RViz on pre-built map.')
        return '\n'.join(lines)



# ── Section Parser ───────────────────────────────────────────────────────────

def parse_sections(raw: str) -> dict:
    sections: dict = {}
    current: str | None = None
    buf: list = []

    for line in raw.splitlines():
        m = re.match(r'^##\s*\[SECTION:\s*(\w+)\]', line)
        if m:
            if current:
                sections[current] = '\n'.join(buf).strip()
            current = m.group(1)
            buf = []
        else:
            buf.append(line)

    if current and buf:
        sections[current] = '\n'.join(buf).strip()

    return sections


# ── Report Writer ────────────────────────────────────────────────────────────

def write_reports(output_dir: Path, data: dict, sections: dict, raw: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ── Main consolidated report ─────────────────────────────────────
    report = output_dir / 'workspace_graph.md'
    with open(report, 'w') as f:
        f.write(f'# Swachh Boudhik Yantra — Workspace Architecture\n')
        f.write(f'*Generated {ts} by graphify.py (Gemini 2.0 Flash)*\n\n')
        f.write('> Open this file in VS Code with **Markdown Preview Mermaid Support** '
                'extension to see rendered diagrams.\n\n')
        f.write('---\n\n')

        section_titles = {
            'PACKAGE_GRAPH':    '📦 Package Dependency Graph',
            'DATAFLOW_GRAPH':   '🔄 ROS2 Topic Data-Flow',
            'TF_TREE':          '🌳 TF Tree',
            'LAUNCH_SEQUENCE':  '🚀 Launch Startup Sequence',
            'CONTROLLER_ARCH':  '⚙️  ros2_control Architecture',
            'SUMMARY':          '📋 Architecture Summary',
        }

        for key, title in section_titles.items():
            f.write(f'## {title}\n\n')
            if key in sections:
                f.write(sections[key] + '\n\n')
            else:
                f.write(f'*(Section {key} not generated)*\n\n')
            f.write('---\n\n')

        # Raw workspace stats
        f.write('## 📊 Workspace Statistics\n\n')
        f.write('| Metric | Count |\n|--------|-------|\n')
        f.write(f'| Packages | {len(data["packages"])} |\n')
        f.write(f'| ROS2 node files | {len(data["node_files"])} |\n')
        f.write(f'| Launch files | {len(data["launch_files"])} |\n')
        f.write(f'| Xacro files | {len(data["xacro_files"])} |\n')
        f.write(f'| Config YAML files | {len(data["config_files"])} |\n\n')

        f.write('| Package | Version | Description |\n|---------|---------|-------------|\n')
        for p in data['packages']:
            f.write(f'| `{p["name"]}` | {p["version"]} | {p["description"][:70]} |\n')

    print(f'\n[output] Report:   {report}')

    # ── Individual .mmd files ────────────────────────────────────────
    for key, content in sections.items():
        if key == 'SUMMARY':
            continue
        mmd = _extract_mermaid_block(content)
        out = output_dir / f'{key.lower()}.mmd'
        out.write_text(mmd)
        print(f'[output] {key}: {out}')

    # ── Summary standalone ───────────────────────────────────────────
    if 'SUMMARY' in sections:
        s = output_dir / 'summary.md'
        s.write_text(f'# Architecture Summary\n*{ts}*\n\n' + sections['SUMMARY'])
        print(f'[output] Summary:  {s}')

    return report


def _extract_mermaid_block(content: str) -> str:
    m = re.search(r'```mermaid\n(.*?)```', content, re.DOTALL)
    return m.group(1).strip() if m else content


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Graphify: ROS2 workspace mapper')
    parser.add_argument('--workspace', default='',
        help='vacuum_ws root (default: auto-detect from script location)')
    parser.add_argument('--output', default='',
        help='Output directory (default: <workspace>/graphify_output/)')
    parser.add_argument('--model', default='gemini-2.0-flash',
        help='Gemini model (default: gemini-2.0-flash)')
    parser.add_argument('--env', default='',
        help='.env file path (default: <workspace>/.env)')
    parser.add_argument('--no-ai', action='store_true',
        help='Generate static diagrams only — no API call needed')
    args = parser.parse_args()

    # Auto-detect workspace root (3 levels up from this script: src/vacuum_utils/scripts/)
    script_dir = Path(__file__).resolve().parent
    ws_root = Path(args.workspace).resolve() if args.workspace else script_dir.parent.parent.parent

    # Load API key
    env_path = Path(args.env).resolve() if args.env else ws_root / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f'[env] Loaded: {env_path}')
    else:
        print(f'[warn] .env not found at {env_path}')

    api_key = os.getenv('GEMINI_API_KEY', '')
    if not api_key:
        if args.no_ai:
            api_key = 'STATIC_MODE'
        else:
            print('[ERROR] GEMINI_API_KEY not set.')
            sys.exit(1)
    
    if api_key != 'STATIC_MODE':
        masked = api_key[:8] + '...' + '*' * 16
        print(f'[env] Key: {masked}')
    else:
        print('[env] Key: None (Static Mode)')

    output_dir = Path(args.output).resolve() if args.output else ws_root / 'graphify_output'

    print('\n' + '═' * 62)
    print('  Swachh Boudhik Yantra — Workspace Graphifier')
    mode_str = 'STATIC MODE (no API)' if args.no_ai else 'GEMINI AI MODE'
    print(f'  {mode_str}')
    print('═' * 62)

    # 1. Scan
    print('\n[1/3] Scanning workspace...')
    scanner = WorkspaceScanner(ws_root)
    data    = scanner.scan()
    print(f'      {len(data["packages"])} packages | '
          f'{len(data["node_files"])} nodes | '
          f'{len(data["launch_files"])} launches')

    # 2. Generate diagrams
    sections: dict = {}

    if not args.no_ai:
        print('\n[2/3] Calling Gemini API...')
        client   = GeminiClient(api_key=api_key, model=args.model)
        prompt   = build_prompt(data)
        raw      = client.generate(prompt)
        if raw:
            sections = parse_sections(raw)
            print(f'      Sections from Gemini: {list(sections.keys())}')
        else:
            print('[info] Gemini returned empty — using static generator for all sections')
    else:
        print('\n[2/3] Static generation (--no-ai flag set)...')

    # Fill any missing sections with static generator
    static_gen = StaticGraphGenerator()
    all_static = static_gen.generate_all(data)
    missing = [k for k in all_static if k not in sections]
    if missing:
        print(f'      Static fallback for: {missing}')
        for k in missing:
            sections[k] = all_static[k]

    # 3. Write reports
    print(f'\n[3/3] Writing to {output_dir}...')
    report = write_reports(output_dir, data, sections, '')

    print('\n' + '═' * 62)
    print('  ✅  Done!')
    print(f'  Open: {report}')
    print('═' * 62)
    print('\n  VS Code tip: Install "Markdown Preview Mermaid Support"')
    print('  to render the diagrams inline.\n')


if __name__ == '__main__':
    main()
