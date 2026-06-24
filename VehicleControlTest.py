import os
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
import time
import threading
import RPi.GPIO as GPIO
import can

# ==========================================
# Gear 설정
# ==========================================

BUTTON_P = 0
BUTTON_D = 1
BUTTON_R = 3
BUTTON_PCA = 4

GEAR_P = 0
GEAR_D = 1
GEAR_R = 2

gear_state = GEAR_P

# ==========================================
# 장애물 단계
# ==========================================

LEVEL_NO_OBSTACLE = 0
LEVEL_SAFE        = 1
LEVEL_CAUTION     = 2
LEVEL_CLOSE       = 3
LEVEL_DANGER      = 4

obstacle_level = LEVEL_NO_OBSTACLE

# ==========================================
# PCA 상태
# ==========================================

pca_enabled = True

pca_button_prev = False

# ==========================================
# Buzzer 설정
# ==========================================

BUZZER_PIN = 18

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

buzzer = GPIO.PWM(BUZZER_PIN, 2000)
buzzer.start(0)

# ==========================================
# CAN 초기화
# ==========================================

can_bus = can.interface.Bus(
    channel="can0",
    interface="socketcan"
)

# ==========================================
# CAN TX 0x100
# VehicleControlCmd
#
# B0 : DriveCmd
# B1 : SteeringCmd
# ==========================================

def send_vehicle_control(speed_cmd, steer_cmd):

    msg = can.Message(
        arbitration_id=0x100,
        data=bytes([
            speed_cmd,
            steer_cmd
        ]),
        is_extended_id=False
    )

    can_bus.send(msg)

# ==========================================
# pygame 초기화
# ==========================================

pygame.init()
pygame.joystick.init()

# ==========================================
# 게임패드 연결 대기
# ==========================================

while pygame.joystick.get_count() == 0:

    print("게임패드 연결 대기중...")

    time.sleep(1)

    pygame.joystick.quit()
    pygame.joystick.init()

# ==========================================
# 게임패드 연결
# ==========================================

js = pygame.joystick.Joystick(0)
js.init()

print("게임패드 연결됨 :", js.get_name())

# ==========================================
# Axis 값을 0~255 변환
# ==========================================

def axis_to_byte(axis_value):

    value = int((axis_value + 1.0) * 127.5)

    if value < 0:
        value = 0

    if value > 255:
        value = 255

    return value

# ==========================================
# 비프음 스레드
# ==========================================

def beep_worker():

    global obstacle_level

    while True:

        level = obstacle_level

        # 없음
        if level == LEVEL_NO_OBSTACLE:

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.1)

        # 안전
        elif level == LEVEL_SAFE:

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.1)

        # 주의
        elif level == LEVEL_CAUTION:

            buzzer.ChangeDutyCycle(50)
            time.sleep(0.08)

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.7)

        # 근접
        elif level == LEVEL_CLOSE:

            buzzer.ChangeDutyCycle(50)
            time.sleep(0.08)

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.15)

        # 위험
        elif level == LEVEL_DANGER:

            buzzer.ChangeDutyCycle(50)
            time.sleep(0.1)

        else:

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.1)

# ==========================================
# 비프음 스레드 시작
# ==========================================

beep_thread = threading.Thread(
    target=beep_worker,
    daemon=True
)

beep_thread.start()

# ==========================================
# CAN TX TIMER
# ==========================================

last_can_tx = 0

# ==========================================
# 메인 루프
# ==========================================

try:

    while True:

        pygame.event.pump()

        # ==============================
        # Axis 읽기
        # ==============================

        axis_speed = js.get_axis(1)
        axis_steer = js.get_axis(2)

        # ==============================
        # 기어 입력
        # ==============================

        if js.get_button(BUTTON_P):
            gear_state = GEAR_P

        if js.get_button(BUTTON_D):
            gear_state = GEAR_D

        if js.get_button(BUTTON_R):
            gear_state = GEAR_R

        # ==============================
        # PCA On / Off (Edge Trigger)
        # ==============================

        current_pca_button = js.get_button(BUTTON_PCA)

        if current_pca_button and not pca_button_prev:

            pca_enabled = not pca_enabled

            print(
                f"PCA {'ON' if pca_enabled else 'OFF'}"
            )

        pca_button_prev = current_pca_button

        # ==============================
        # 장애물 단계 테스트
        # ==============================

        if js.get_button(11):
            obstacle_level = LEVEL_NO_OBSTACLE

        if js.get_button(6):
            obstacle_level = LEVEL_SAFE

        if js.get_button(7):
            obstacle_level = LEVEL_CAUTION

        if js.get_button(8):
            obstacle_level = LEVEL_CLOSE

        if js.get_button(9):
            obstacle_level = LEVEL_DANGER

        # ==============================
        # Byte 변환
        # ==============================

        speed_byte = axis_to_byte(axis_speed)
        steer_byte = axis_to_byte(axis_steer)

        # ==============================
        # 기어별 제한
        # ==============================

        if gear_state == GEAR_P:

            speed_byte = 127
            steer_byte = 127

        elif gear_state == GEAR_D:

            # 후진 금지
            if speed_byte > 127:
                speed_byte = 127

        elif gear_state == GEAR_R:

            # 전진 금지
            if speed_byte < 127:
                speed_byte = 127

        # ==============================
        # CAN 송신 (0x100)
        # VehicleControlCmd
        # B0 = DriveCmd
        # B1 = SteeringCmd
        # ==============================

        now = time.time()

        if now - last_can_tx >= 0.012:

            send_vehicle_control(
                speed_byte,
                steer_byte
            )

            last_can_tx = now

        # ==============================
        # 기어 표시
        # ==============================

        gear_text = "P"

        if gear_state == GEAR_D:
            gear_text = "D"

        elif gear_state == GEAR_R:
            gear_text = "R"

        # ==============================
        # 장애물 단계 표시
        # ==============================

        level_text = {
            LEVEL_NO_OBSTACLE: "NO_OBSTACLE",
            LEVEL_SAFE: "SAFE",
            LEVEL_CAUTION: "CAUTION",
            LEVEL_CLOSE: "CLOSE",
            LEVEL_DANGER: "DANGER"
        }

        print(
            f"Speed Axis : {axis_speed:.3f} -> {speed_byte}"
        )

        print(
            f"Steer Axis : {axis_steer:.3f} -> {steer_byte}"
        )

        print(
            f"Gear : {gear_text}"
        )

        print(
            f"PCA : {'ON' if pca_enabled else 'OFF'}"
        )

        print(
            f"Obstacle : {level_text[obstacle_level]}"
        )

        print("--------------------------------")

        time.sleep(0.1)

except KeyboardInterrupt:

    print("종료")

finally:

    buzzer.stop()
    GPIO.cleanup()
    pygame.quit()