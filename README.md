# 🤖 TurtleBot3 데이터 수집 프로세스 가이드

> 만약 오케스트레이션 구성을 안하셨으면 오케스트레이션 구성부터 해주시길 바랍니다!

[오케스크레이션 구성] => https://github.com/KopenSDI/SDI-Orchestration

## 📚 목차
1. [리포지터리 구조](#리포지터리-구조)
2. [환경 설정 및 버전](#환경-설정-및-버전)
3. [프로세스 역할](#프로세스-역할)
4. [프로세스 설치](#프로세스-설치)
   1. [의존성 설치](#의존성-설치)
   2. [초기 환경 세팅](#초기-환경-세팅)
5. [프로세스 실행](#프로세스-실행)
   1. [데이터 추출 전 준비](#데이터-추출-전-준비)
   2. [배터리·위치 정보 추출](#배터리위치-정보-추출)
6. [참고 문서](#참고-문서)

## 🗂️ 1. 리포지터리 구조

```text
KETI_TURTLEBOT/                 # TurtleBot Raspberry Pi 측 전용 디렉터리
├── exporter.py                   # ↳ ROS ✕ metric-collector 브릿지 (Python 3 Node)
├── run_exporter.py               # ↳ 실행 래퍼: ENV 주입 + ROS setup + exporter 호출
└── README.md                     # ↳ (현재) 사용자 가이드
```

## 🛠️2. 환경 설정 및 버전


| 항목                  | 버전 / 세부 정보                             |
| --------------------- | ------------------------------------------- |
| **ROS 2**             | ros2-jazzy                                  |
| **Operating System**  | Ubuntu 24.04.2 LTS                           |
| **Kernel**            | Linux 6.8.0-1028-raspi                    |
| **Architecture**      | arm64                                       |
| **k3s**               | v1.32.5+k3s1                                |
| **Container Runtime** | containerd://2.0.5-k3s1.32                  |


| 경로                                 | 유형       | 핵심 기능                                                                                                  |
| ---------------------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| **exporter.py**                    | Python 3 | `/battery_state`·`/amcl_pose` 구독 → 5 초마다 metric-collector 발행  (큐: `turtlebot.telemetry`)|
| **run\_exporter.py**               | Bash     | metric-collector·Robot 식별 ENV를 설정하고 `python3 exporter.py` 실행                          |
| **README.md**                      | Markdown | 기존 간단 가이드를 포함.    

## 3. 프로세스 역할
- 📡 **run_exporter**: 터틀봇의 배터리 상태와 위치 정보를 실시간으로 수집해 Metric-Collector에 전송하는 익스포터 프로세스

```
ROS 2 토픽 (/battery_state & /amcl_pose)
        │ (QoS 설정 BEST_EFFORT / RELIABLE)
        ▼
            ExporterNode (rclpy)
                ├ battery_callback       ——  전압·퍼센트 실시간 저장
                ├ pose_callback         ——  X·Y 좌표 저장
                └ publish_telemetry()   ——  5 초마다 metric-collector 발행
        ▼
metric-collector Queue  ── "turtlebot.telemetry" (durable)
```

- 메시지 예시(JSON)\*

```jsonc
{
  "ts": 1719123456789012345,  // epoch‑ns
  "bot": "tb3-alpha",
  "type": "telemetry",
  "battery": { "percentage": 0.83, "voltage": 11.8, "wh": 16.583 },
  "pose":    { "x": 4.16,      "y": -1.92 }
}
```

---
## 4. 프로세스 설치 <a id="프로세스-설치"></a>

### 의존성 설치 <a id="의존성-설치"></a>

```bash
git clone https://github.com/sungmin306/SDI-Turtlebot-Setting.git
cd SDI-Turtlebot-Setting/KETI_TURTLEBOT
sudo apt install -y python3-pika  # 터틀봇 메트릭 데이터 관련 의존성 라이브러리 설치
```

### 초기 환경 세팅 <a id="초기-환경-세팅"></a>

```bash
vi run_exporter.py  # 주석 처리된 부분을 본인 환경에 맞게 수정(주석 설명 참고고)
```


---
## 5. 프로세스 실행 <a id="프로세스-실행"></a>

### 데이터 추출 전 준비 <a id="데이터-추출-전-준비"></a>

⚠️ **TurtleBot3에서 2D Pose Estimate를 설정해야 `/tf`·`/amcl_pose` 등 위치 관련 ROS 토픽을 정상 수신할 수 있다.**
<img src="https://github.com/user-attachments/assets/2c3cbdc2-4001-448c-bcc9-4ebeb48377a6" width="600" height="376"/>




> 위와 같이 RViz에서 Initial Pose 할당 후 SLAM 맵을 완성하면 `/amcl_pose` 토픽에 좌표가 들어오기 시작한다.

결과 예시:

<img src="https://github.com/user-attachments/assets/d4d36a0c-2e0a-4367-afcc-348d2e74a3f3" width="600" height="376"/>

---
### 6. 배터리·위치 정보 추출 <a id="배터리위치-정보-추출"></a>

```bash
# 1) 터틀봇 bringup(터틀봇에서 실행)
ros2 launch turtlebot3_bringup robot.launch.py

# 2) SLAM 맵 획득(터틀봇-Remote-PC에서 실행)
ros2 launch turtlebot3_cartographer cartographer.launch.py  # 공식 가이드 참고

# 3) Navigation 활성화(터틀봇-Remote-PC 에서 실행)
ros2 launch turtlebot3_navigation2 navigation2.launch.py   # 공식 가이드 참고

# 4) 데이터 수집 프로세스 실행(터틀봇에서 실행)
./run_exporter.py # SDI-스케줄러 사용시 꼭 필요합니다.
```

실행 결과

![Image](https://github.com/user-attachments/assets/a9cebf17-2d5f-4f56-a9f9-5f15f6ef1c07)

> **중요** SLAM 단계에서 생성한 맵(.pgm & .yaml)을 저장한 뒤 Navigation을 실행해야 위치 토픽이 정상적으로 게시된다.

---
## 참고 문서 <a id="참고-문서"></a>

| 주제 | 링크 |
|------|------|
| SLAM 설정 | <https://emanual.robotis.com/docs/en/platform/turtlebot3/slam/#run-slam-node> |
| Navigation 설정 | <https://emanual.robotis.com/docs/en/platform/turtlebot3/navigation/#run-navigation-nodes> |

---


