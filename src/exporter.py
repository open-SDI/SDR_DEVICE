#!/usr/bin/env python3
import os, json, time, socket
from urllib.parse import urlparse
import numpy as np  # pip install numpy 필요

import pika
import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy)

# 메시지 타입 import
from sensor_msgs.msg import BatteryState, Imu, LaserScan, JointState
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped

def required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"환경변수 {name} 가 설정돼 있지 않습니다.")
    return val

def build_rmq_params():
    uri = os.getenv("RABBITMQ_URI")
    if uri:
        p = urlparse(uri)
        user = p.username or required("RABBITMQ_USER")
        pw   = p.password or required("RABBITMQ_PASS")
        host = p.hostname or required("RABBITMQ_HOST")
        port = p.port or int(required("RABBITMQ_PORT"))
        vhost = p.path[1:] if p.path and p.path != "/" else "/"
    else:
        host  = required("RABBITMQ_HOST")
        port  = int(required("RABBITMQ_PORT"))
        user  = required("RABBITMQ_USER")
        pw    = required("RABBITMQ_PASS")
        vhost = os.getenv("RABBITMQ_VHOST", "/")

    creds = pika.PlainCredentials(user, pw)
    return pika.ConnectionParameters(
        host=host, port=port, virtual_host=vhost, credentials=creds,
        heartbeat=30, connection_attempts=5, retry_delay=5,
    ), {"host": host, "port": port, "user": user, "vhost": vhost}

class ExporterNode(Node):
    def __init__(self):
        super().__init__("exporter_node")

        # RabbitMQ 연결
        params, info = build_rmq_params()
        self.get_logger().info(
            f"[RabbitMQ] host={info['host']}  port={info['port']}  "
            f"user={info['user']}  vhost={info['vhost']}"
        )
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue="turtlebot.telemetry", durable=True)
        self.get_logger().info("RabbitMQ connected ✔")

        self.bot = (os.getenv("ROBOT_NAME") or socket.gethostname()).lower()
        self.spec_wh = float(os.getenv("BATTERY_SPEC_WH", "19.98"))
        self.get_logger().info(f"ROBOT_NAME = {self.bot}")

        # 데이터 저장 변수
        self.last_battery_msg = None
        self.last_pose_msg = None
        self.last_imu_msg = None
        self.last_scan_msg = None
        self.last_odom_msg = None

        # --- [요청하신 QoS 설정 원복] ---
        # 1. battery_qos: 실시간성 중요 (Best Effort, Volatile) 
        # -> 배터리, 라이다, IMU, Odom 등 대부분의 센서에 사용
        battery_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST, depth=10)

        # 2. pose_qos: 데이터 신뢰성 중요 (Reliable, Transient Local)
        # -> AMCL 위치 정보에 사용
        pose_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST, depth=10)

        # --- 구독 설정 (Subscribers) ---
        
        # (1) 배터리 -> battery_qos 사용
        self.create_subscription(BatteryState, "/battery_state", 
                                 self.battery_callback, battery_qos)
        
        # (2) AMCL 위치 -> pose_qos 사용
        self.create_subscription(PoseWithCovarianceStamped, "/amcl_pose", 
                                 self.pose_callback, pose_qos)
        
        # (3) [추가] IMU -> battery_qos 사용 (센서 데이터는 보통 Best Effort)
        self.create_subscription(Imu, "/imu", 
                                 self.imu_callback, battery_qos)
        
        # (4) [추가] Lidar -> battery_qos 사용
        self.create_subscription(LaserScan, "/scan", 
                                 self.scan_callback, battery_qos)
        
        # (5) [추가] Odom -> battery_qos 사용
        self.create_subscription(Odometry, "/odom", 
                                 self.odom_callback, battery_qos)

        # 5초마다 전송
        self.create_timer(5.0, self.publish_telemetry_callback)

    # --- 콜백 함수들 ---
    def battery_callback(self, msg): self.last_battery_msg = msg
    def pose_callback(self, msg):    self.last_pose_msg = msg
    def imu_callback(self, msg):     self.last_imu_msg = msg
    def scan_callback(self, msg):    self.last_scan_msg = msg
    def odom_callback(self, msg):    self.last_odom_msg = msg

    # --- 전송 로직 ---
    def publish_telemetry_callback(self):
        # 1. 배터리 처리
        if self.last_battery_msg:
            raw_pct = self.last_battery_msg.percentage
            # 값 보정 (0~1.0 사이면 *100, 아니면 그대로)
            if raw_pct <= 1.0: 
                ratio = raw_pct
                pct_disp = raw_pct * 100
            else:
                ratio = raw_pct / 100.0
                pct_disp = raw_pct
            
            wh = ratio * self.spec_wh
            volt = self.last_battery_msg.voltage
        else:
            # 데이터 없으면 0 처리
            ratio = pct_disp = wh = volt = 0.0

        # 2. 위치 처리 (AMCL)
        if self.last_pose_msg:
            pos = self.last_pose_msg.pose.pose.position
            x_pos, y_pos = pos.x, pos.y
        else:
            x_pos = y_pos = 0.0

        # 3. 모션 처리 (Odom, IMU)
        linear_v = angular_v = accel_x = 0.0
        
        if self.last_odom_msg:
            linear_v = self.last_odom_msg.twist.twist.linear.x
            angular_v = self.last_odom_msg.twist.twist.angular.z
        
        if self.last_imu_msg:
            accel_x = self.last_imu_msg.linear_acceleration.x

        # 4. 라이다 요약 (가장 가까운 거리 / 정면 거리)
        scan_summary = {"min_dist": -1.0, "front_dist": -1.0}
        if self.last_scan_msg:
            try:
                ranges = np.array(self.last_scan_msg.ranges)
                # 유효 데이터 필터링 (0.01m ~ 3.5m)
                valid_indices = (ranges > 0.01) & (ranges < 3.5)
                valid_ranges = ranges[valid_indices]

                if len(valid_ranges) > 0:
                    scan_summary["min_dist"] = float(np.min(valid_ranges))
                
                # 정면(인덱스 0 주변) 데이터 평균
                if len(ranges) > 20:
                    front_cone = np.concatenate((ranges[:10], ranges[-10:]))
                    front_valid = front_cone[front_cone > 0.01]
                    if len(front_valid) > 0:
                        scan_summary["front_dist"] = float(np.mean(front_valid))
            except:
                pass

        # 로그 출력
        self.get_logger().info(
            f"\n--- [{self.bot}] Telemetry Report ---\n"
            f" [Power]  Batt: {int(pct_disp)}% ({volt}V)\n"
            f" [Pose]   (x={x_pos:.2f}, y={y_pos:.2f})\n"
            f" [Motion] Linear: {linear_v:.2f} m/s | Angular: {angular_v:.2f} rad/s | Accel X: {accel_x:.2f}\n"
            f" [Lidar]  Front: {scan_summary['front_dist']:.2f}m | Min(Risk): {scan_summary['min_dist']:.2f}m\n"
            f"----------------------------------------"
        )
        # JSON 패키징
        data = {
            "ts": time.time_ns(),
            "bot": self.bot,
            "type": "telemetry",
            "battery": {
                "percentage": round(ratio, 4),
                "voltage": round(volt, 2),
                "wh": round(wh, 2),
            },
            "pose": {
                "x": round(x_pos, 3), 
                "y": round(y_pos, 3)
            },
            "motion": {
                "linear_velocity": round(linear_v, 3),
                "angular_velocity": round(angular_v, 3),
                "acceleration_x": round(accel_x, 3)
            },
            "env": {
                "obstacle_min": round(scan_summary["min_dist"], 3),
                "obstacle_front": round(scan_summary["front_dist"], 3)
            }
        }

        # 발행
        try:
            self.channel.basic_publish(
                exchange="", routing_key="turtlebot.telemetry",
                body=json.dumps(data),
                properties=pika.BasicProperties(delivery_mode=2),
            )
        except Exception as e:
            self.get_logger().error(f"Publish Error: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = ExporterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.connection and not node.connection.is_closed:
            node.connection.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
