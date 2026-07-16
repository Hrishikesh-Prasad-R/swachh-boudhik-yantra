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
ros2_control, Stage 2 complete) and produce a complete architecture graph.

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
Mermaid flowchart (graph TD) of the 6 vacuum_* packages and their dependencies.
Internal packages as solid nodes. External deps shown only on edge labels.

## [SECTION: DATAFLOW_GRAPH]
Mermaid flowchart showing full ROS2 topic data-flow.
Nodes (executables) = rectangles. Topics = rounded rectangles.
Arrow direction = data flow direction. Include all known topics.

## [SECTION: TF_TREE]
Mermaid graph of the complete TF tree from odom to all leaf links.

## [SECTION: LAUNCH_SEQUENCE]
Mermaid sequenceDiagram showing sim.launch.py startup (t=0 to t=10s).
Participants: User, sim.launch.py, Gazebo, gz_ros2_control, JSB_spawner, DDC_spawner.

## [SECTION: CONTROLLER_ARCH]
Mermaid flowchart: keyboard/nav2 → /cmd_vel → diff_drive_controller →
ros2_control hardware interface → Gazebo joints → encoders → /odom → /tf.

## [SECTION: SUMMARY]
Structured markdown:
- Stage completed (Stage 1 + Stage 2)
- Package table (name, purpose, key topics)
- Key design decisions (3–5 bullet points)
- What is NOT yet implemented (future stages 3–10)
- Critical path to Stage 3 (D435i + EKF)
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
        'vacuum_gazebo', 'vacuum_interfaces', 'vacuum_slam', 'vacuum_utils'
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
        lines.append('    %% Swachh Boudhik Yantra — Package Dependencies')
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
        # Styling
        lines.append('    style vacuum_bringup   fill:#4A90D9,color:#fff')
        lines.append('    style vacuum_controller fill:#7ED321,color:#fff')
        lines.append('    style vacuum_description fill:#9B59B6,color:#fff')
        lines.append('    style vacuum_gazebo     fill:#E67E22,color:#fff')
        lines.append('    style vacuum_interfaces fill:#1ABC9C,color:#fff')
        lines.append('    style vacuum_slam       fill:#F39C12,color:#fff')
        lines.append('    style vacuum_utils      fill:#E74C3C,color:#fff')
        lines.append('```')
        return '\n'.join(lines)

    def _dataflow_graph(self, data: dict) -> str:
        return '''```mermaid
graph LR
    %% ROS2 Topic Data-Flow — Stage 3 & 4A

    subgraph UserI ["User Input & Teleop"]
        KB(["🎹 Keyboard Teleop"])
    end

    subgraph Simulation ["Gazebo Harmonic Simulation"]
        GZ_CLK["Gazebo Clock"]
        GZ_CAM["D435i RGBD Sensor Plugin"]
        GZ_CTRL["gz_ros2_control Plugin"]
    end

    subgraph Bridge ["ros_gz_bridge (parameter_bridge)"]
        CLK_B["/clock Bridge"]
        CAM_B["Camera Bridges\n(5 topics)"]
        GT_B["/ground_truth/poses Bridge"]
    end

    subgraph Controllers ["vacuum_controller Package"]
        DDC["diff_drive_controller"]
        JSB["joint_state_broadcaster"]
        NOISE["odometry_noise_node"]
        M_DIAG["motion_diagnostics_node"]
        C_DIAG["camera_diagnostics_node"]
    end

    subgraph SLAM ["vacuum_slam Package"]
        RTAB["rtabmap Node"]
    end

    %% Clock connections
    GZ_CLK -->|gz.msgs.Clock| CLK_B
    CLK_B -->|/clock| DDC
    CLK_B -->|/clock| RTAB
    CLK_B -->|/clock| C_DIAG

    %% Teleop
    KB -->|/cmd_vel| DDC

    %% ros2_control loop
    DDC -->|joint velocities| GZ_CTRL
    GZ_CTRL -->|joint states| JSB
    JSB -->|/joint_states| M_DIAG

    %% Camera dataflow (Stage 3)
    GZ_CAM -->|gz.msgs.Image / PointCloudPacked| CAM_B
    CAM_B -->|/camera/color/image_raw| RTAB
    CAM_B -->|/camera/color/image_raw| C_DIAG
    CAM_B -->|/camera/depth/image_rect_raw| RTAB
    CAM_B -->|/camera/depth/image_rect_raw| C_DIAG
    CAM_B -->|/camera/depth/points| RTAB
    CAM_B -->|/camera/depth/points| C_DIAG
    CAM_B -->|/camera/color/camera_info| RTAB
    CAM_B -->|/camera/depth/camera_info| RTAB

    %% Odometry / TF
    DDC -->|/odom| NOISE
    DDC -->|/odom| RTAB
    DDC -->|/odom| M_DIAG
    DDC -->|/tf (odom->base_footprint)| RTAB
    NOISE -->|/odom_noisy| NOISY_ODOM(["📊 /odom_noisy"])

    %% Diagnostics
    M_DIAG -->|/motion_diagnostics| DIAG_TOPIC(["🔍 /diagnostics"])
    C_DIAG -->|/camera/diagnostics| DIAG_TOPIC

    %% SLAM Outputs (Stage 4A)
    RTAB -->|/rtabmap/map| MAP_2D(["🗺️  /rtabmap/map\n(OccupancyGrid)"])
    RTAB -->|/rtabmap/cloud_map| MAP_3D(["☁️  /rtabmap/cloud_map\n(PointCloud2)"])
    RTAB -->|/rtabmap/odom| EVAL(["evaluate_trajectory.py\n(evo benchmark)"])

    %% Ground Truth Pose (Stage 4A)
    GZ_CTRL -->|gz.msgs.Pose_V| GT_B
    GT_B -->|/ground_truth/poses| EVAL
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
    participant U  as User
    participant SL as sim.launch.py
    participant RSP as robot_state_publisher
    participant GZ as Gazebo Harmonic
    participant BR as ros_gz_bridge
    participant GZC as gz_ros2_control
    participant CTRL as controllers.launch.py
    participant DIAG as camera_diagnostics_node
    participant SLAM as slam.launch.py
    participant RTAB as rtabmap Node

    U->>SL: ros2 launch vacuum_bringup sim.launch.py world:=apartment
    SL->>RSP: start (parse URDF with camera link, publish /robot_description)
    SL->>GZ: start Gazebo (loads apartment.sdf world)
    SL->>BR: start bridge (/clock + 5 camera topics)
    note over GZ: t=0s physics & Ogre2 renderer active

    note over SL: TimerAction delay 3s
    SL->>GZ: spawn vacuum_robot (loads rgbd_camera sensor)
    GZ->>GZC: init gz_ros2_control plugin
    note over GZ,GZC: t=3s robot spawned, camera rendering active

    note over SL: Include controllers launch
    SL->>CTRL: load controllers.launch.py

    note over CTRL: TimerAction delay 5s
    CTRL->>GZC: spawn joint_state_broadcaster → /joint_states active (t=5s)

    note over CTRL: TimerAction delay 6s
    CTRL->>GZC: spawn diff_drive_controller → /odom, /tf active (t=6s)

    note over CTRL: TimerAction delay 8s
    CTRL->>CTRL: start odometry_noise_node + motion_diagnostics_node (t=8s)

    note over CTRL: TimerAction delay 10s
    CTRL->>DIAG: start camera_diagnostics_node (t=10s)
    note over DIAG: Monitors camera FPS & latency

    %% SLAM activation (Stage 4A)
    U->>SLAM: ros2 launch vacuum_slam slam.launch.py environment:=apartment
    SLAM->>RTAB: start rtabmap node (loads rtabmap.yaml parameters)
    RTAB->>RTAB: Wipes old database, begins mapping
    note over RTAB: Mapping & loop closures active
```'''

    def _controller_arch(self) -> str:
        return '''```mermaid
graph TD
    %% ros2_control & SLAM Integration Architecture — Stage 3 & 4A

    KB(["Keyboard Teleop"])
    CMD(["📨 /cmd_vel\ngeometry_msgs/Twist"])
    DDC["diff_drive_controller\n(velocity limiters + wheel odom)"]
    HW["Hardware Interface\ngz_ros2_control/GazeboSimSystem"]
    SIM["Gazebo Physics\n(differential joint drive)"]
    ENC["Joint Encoder Feedback\n(angular pos/vel)"]
    JSB["joint_state_broadcaster"]
    JS(["📊 /joint_states"])
    RSP["robot_state_publisher"]
    ODOM(["📍 /odom\nnav_msgs/Odometry"])
    TF_ODOM(["🌐 TF: odom → base_footprint"])

    CAM_GZ["D435i Sensor Plugin\n(ideal/realistic depth model)"]
    CAM_DATA(["📷 RGBD Streams & TF\ncolor/image, depth/image, points"])
    RTAB["rtabmap Node\n(visual loop-closure mapping)"]
    TF_MAP(["🌐 TF: map → odom"])

    KB --> CMD
    CMD --> DDC
    DDC -->|"wheel velocity commands"| HW
    HW --> SIM
    SIM --> ENC
    ENC --> HW
    HW --> JSB
    JSB --> JS
    JS --> RSP

    HW -->|odom integration| DDC
    DDC --> ODOM
    DDC --> TF_ODOM

    %% Perception-Mapping data flow
    SIM -->|visual renderer| CAM_GZ
    CAM_GZ --> CAM_DATA
    CAM_DATA --> RTAB
    ODOM --> RTAB
    TF_ODOM --> RTAB
    RTAB --> TF_MAP

    style DDC fill:#4A90D9,color:#fff
    style HW fill:#E67E22,color:#fff
    style RTAB fill:#F39C12,color:#fff
    style SIM fill:#7ED321,color:#fff
```'''

    def _summary(self, data: dict) -> str:
        pkgs = data['packages']
        purpose = {
            'vacuum_bringup':     'Master launch orchestration (sim.launch.py + RViz)',
            'vacuum_controller':  'ros2_control config, diff drive, noise & diagnostics nodes',
            'vacuum_description': 'Xacro URDF robot model (13 links, 12 joints including D435i camera)',
            'vacuum_gazebo':      'Gazebo world, SDF, /clock and D435i bridge config',
            'vacuum_interfaces':  'Future custom msgs/srvs/actions (empty Stage 4)',
            'vacuum_slam':        'RTAB-Map SLAM node, map_saver configuration, and slam_rviz settings',
            'vacuum_utils':       'Validation scripts, TF checker, graphify, metrics logger, and trajectory/SLAM benchmark tools',
        }
        lines = []
        lines.append('### Stages Complete')
        lines.append('| Stage | Status | Description |')
        lines.append('|-------|--------|-------------|')
        lines.append('| Stage 1 | ✅ `v0.1-stage1-foundation` | Robot URDF, Gazebo world, TF tree |')
        lines.append('| Stage 2 | ✅ `v0.2-stage2-ros2control` | ros2_control, diff_drive, odometry |')
        lines.append('| Stage 3 | ✅ `v0.3-stage3-perception` | D435i RGB-D Integration, Diagnostics, Validation |')
        lines.append('| Stage 4A | 🛠️  Active | Manual RTAB-Map Mapping, Evaluation & Benchmarks |')
        lines.append('| Stage 4B | ⏳ Pending | Autonomous Frontier Exploration |')
        lines.append('| Stage 5 | ⏳ Pending | Nav2 navigation |')
        lines.append('| Stages 6–10 | ⏳ Pending | Coverage, Arm, Transfer, Deploy |')
        lines.append('')
        lines.append('### Package Summary')
        lines.append('| Package | Purpose |')
        lines.append('|---------|---------|')
        for p in pkgs:
            lines.append(f'| `{p["name"]}` | {purpose.get(p["name"], p["description"][:60])} |')
        lines.append('')
        lines.append('### Key Design Decisions')
        lines.append('- **gz_ros2_control**: inserts ros2_control abstraction layer, easing transition to Orin hardware.')
        lines.append('- **D435i RealSense Frame Convention**: links & joints follow REP-103 and RealSense SDK standards.')
        lines.append('- **Delayed Camera Diagnostics Node**: starts 10 seconds after simulation to allow Gazebo camera bridge stabilization.')
        lines.append('- **Dual Noise Modes**: supports both ideal (clean mapping) and realistic (noise validation) modes inside camera.yaml.')
        lines.append('- **unprivileged bwrap/python3.12 overrides**: launch python nodes via python3.12 explicitly to prevent python3.14 import errors.')
        lines.append('')
        lines.append('### Not Yet Implemented (Stages 4B–10)')
        lines.append('- Autonomous frontier exploration planning')
        lines.append('- Nav2 stack (costmaps, planners, recovery behaviors)')
        lines.append('- Coverage planner algorithm')
        lines.append('- MoveIt2 robotic arm manipulation')
        lines.append('- Jetson Orin Nano hardware deployment')
        lines.append('- Real-world to simulation transfer validation')
        lines.append('')
        lines.append('### Stage 4B Critical Path')
        lines.append('1. Complete manual mapping evaluation across Room, Office, Corridor, Apartment worlds.')
        lines.append('2. Record bags and verify ATE/RPE trajectory error metrics using `evo`.')
        lines.append('3. Implement Frontier Exploration algorithm node and Behavior Trees.')
        lines.append('4. Integrate Frontier planner with Nav2 local/global navigation.')
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
