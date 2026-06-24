import os
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
import time
import threading
import RPi.GPIO as GPIO
import can

# ==========================================
# CAN INIT
# ==========================================

can_bus = can.interface.Bus(
    channel="can0",
    interface="socketcan"
)

# ==========================================
# LEVEL DEFINE
# ==========================================

LEVEL_NO_OBSTACLE = 0
LEVEL_SAFE = 1
LEVEL_CAUTION = 2
LEVEL_CLOSE = 3
LEVEL_DANGER = 4

# ==========================================
# GAMEPAD BUTTON
# ==========================================

BUTTON_P = 0
BUTTON_D = 1
BUTTON_R = 3
BUTTON_PCA = 4

# ==========================================
# GEAR
# ==========================================

GEAR_P = 0
GEAR_D = 1
GEAR_R = 2

gear_state = GEAR_P

# ==========================================
# PCA BUTTON EDGE DETECT
# ==========================================

prev_pca_button = 0

# ==========================================
# ECU STATE (FROM 0x400)
# ==========================================

# B0 ~ B9
obstacle_levels = [0] * 10

# B10
pca_state = 0

# B11
vehicle_speed = 0

# B12
gear_status_from_ecu = 0

# B13
emergency_stop = 0

# ==========================================
# EXIT STATUS (FROM 0x401)
# ==========================================

# 0 : Normal
# 1 : 출차 진행중
# 2 : 출차 완료
# 3 : 출차 중단
exit_status = 0

# ==========================================
# USER STATE
# ==========================================

# 0x201 B3
pca_enabled = 0

# ==========================================
# AUTO PARKING COMMAND
# 앱 연동 시 값 변경 예정
#
# 0 : Normal
# 1 : Start Straight Exit
# 2 : Start Left Exit
# 3 : Start Right Exit
# 4 : Stop Auto Exit
# ==========================================

auto_parking_cmd = 0

# ==========================================
# BUZZER
# ==========================================

BUZZER_PIN = 18

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

buzzer = GPIO.PWM(BUZZER_PIN, 2000)
buzzer.start(0)

# ==========================================
# PYGAME INIT
# ==========================================

pygame.init()
pygame.joystick.init()

while pygame.joystick.get_count() == 0:
    print("게임패드 대기중...")
    time.sleep(1)

    pygame.joystick.quit()
    pygame.joystick.init()

js = pygame.joystick.Joystick(0)
js.init()

print("Joystick connected:", js.get_name())

# ==========================================
# UTIL
# ==========================================

def axis_to_byte(v):
    x = int((v + 1.0) * 127.5)
    return max(0, min(255, x))


def get_max_level():
    return max(obstacle_levels)

# ==========================================
# CAN TX 0x201
#
# B0 DriveCmd
# B1 SteeringCmd
# B2 GearStatusCmd
# B3 PCAActivatedTF
# ==========================================

def send_vehicle_status(speed, steer, gear, pca_en):

    msg = can.Message(
        arbitration_id=0x201,
        data=bytes([
            speed,
            steer,
            gear,
            pca_en
        ]),
        is_extended_id=False
    )

    can_bus.send(msg)

# ==========================================
# CAN TX 0x300
#
# B0 AutoParkingStartCmd
#
# 0 : Normal
# 1 : Start Straight Exit
# 2 : Start Left Exit
# 3 : Start Right Exit
# 4 : Stop Auto Exit
# ==========================================

def send_auto_parking(cmd):

    msg = can.Message(
        arbitration_id=0x300,
        data=bytes([cmd]),
        is_extended_id=False
    )

    can_bus.send(msg)

# ==========================================
# CAN RX THREAD
# ==========================================

def can_rx():

    global obstacle_levels
    global pca_state
    global vehicle_speed
    global gear_status_from_ecu
    global emergency_stop
    global exit_status

    while True:

        msg = can_bus.recv()

        if msg is None:
            continue

        # ==================================
        # 0x400 DistanceLevelCmd
        # ==================================

        if msg.arbitration_id == 0x400:

            d = msg.data

            for i in range(10):
                obstacle_levels[i] = d[i]

            pca_state = d[10]
            vehicle_speed = d[11]
            gear_status_from_ecu = d[12]
            emergency_stop = d[13]

        # ==================================
        # 0x401 ExitCompleteCmd
        # ==================================

        elif msg.arbitration_id == 0x401:

            exit_status = msg.data[0]

threading.Thread(
    target=can_rx,
    daemon=True
).start()

# ==========================================
# BUZZER THREAD
#
# 가장 위험한 센서 레벨 기준
# ==========================================

def beep_worker():

    while True:

        level = get_max_level()

        if level == LEVEL_NO_OBSTACLE:

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.1)

        elif level == LEVEL_SAFE:

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.1)

        elif level == LEVEL_CAUTION:

            buzzer.ChangeDutyCycle(50)
            time.sleep(0.08)

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.7)

        elif level == LEVEL_CLOSE:

            buzzer.ChangeDutyCycle(50)
            time.sleep(0.08)

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.15)

        elif level == LEVEL_DANGER:

            buzzer.ChangeDutyCycle(50)
            time.sleep(0.1)

        else:

            buzzer.ChangeDutyCycle(0)
            time.sleep(0.1)

threading.Thread(
    target=beep_worker,
    daemon=True
).start()

# ==========================================
# TIMERS
# ==========================================

last_201 = 0
last_300 = 0

# ==========================================
# MAIN LOOP
# ==========================================

try:

    while True:

        pygame.event.pump()

        # ==================================
        # AXIS INPUT
        # ==================================

        speed = axis_to_byte(
            js.get_axis(1)
        )

        steer = axis_to_byte(
            js.get_axis(2)
        )

        # ==================================
        # GEAR SELECT
        # ==================================

        if js.get_button(BUTTON_P):
            gear_state = GEAR_P

        if js.get_button(BUTTON_D):
            gear_state = GEAR_D

        if js.get_button(BUTTON_R):
            gear_state = GEAR_R

        # ==================================
        # PCA ENABLE TOGGLE
        # Rising Edge
        # ==================================

        current_pca_button = js.get_button(
            BUTTON_PCA
        )

        if current_pca_button == 1 and prev_pca_button == 0:
            pca_enabled = 1 - pca_enabled

        prev_pca_button = current_pca_button

        # ==================================
        # GEAR LIMIT
        # ==================================

        if gear_state == GEAR_P:

            speed = 127
            steer = 127

        elif gear_state == GEAR_D:

            if speed > 127:
                speed = 127

        elif gear_state == GEAR_R:

            if speed < 127:
                speed = 127

        # ==================================
        # EMERGENCY STOP
        # ==================================

        if emergency_stop == 1:

            speed = 127
            steer = 127

        now = time.time()

        # ==================================
        # TX 0x201 (12ms)
        # ==================================

        if now - last_201 >= 0.012:

            send_vehicle_status(
                speed,
                steer,
                gear_state,
                pca_enabled
            )

            last_201 = now

        # ==================================
        # TX 0x300 (100ms)
        # ==================================

        if now - last_300 >= 0.1:

            send_auto_parking(
                auto_parking_cmd
            )

            last_300 = now

        # ==================================
        # STATUS PRINT
        # ==================================

        print("Speed:", speed)
        print("Steer:", steer)
        print("Gear:", gear_state)
        print("PCA Enabled:", pca_enabled)
        print("PCA ECU State:", pca_state)
        print("Vehicle Speed:", vehicle_speed)
        print("Gear From ECU:", gear_status_from_ecu)
        print("Emergency Stop:", emergency_stop)
        print("Exit Status:", exit_status)
        print("Max Obstacle Level:", get_max_level())
        print("--------------------------------")

        time.sleep(0.01)

except KeyboardInterrupt:

    print("EXIT")

finally:

    buzzer.stop()
    GPIO.cleanup()
    pygame.quit()