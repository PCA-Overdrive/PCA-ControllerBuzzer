import os
os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
import time
import threading
import RPi.GPIO as GPIO
import can
import struct

# ==========================================
# CAN INIT
# ==========================================
can_bus = can.interface.Bus(
    channel="can0",
    interface="socketcan",
    fd=True
)

# ==========================================
# LOCK (RX safety)
# ==========================================
lock = threading.Lock()

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
prev_pca_button = 0

# ==========================================
# ECU STATE
# ==========================================
obstacle_levels = [0] * 10
pca_state = 0
vehicle_speed = 0
gear_status_from_ecu = 0
emergency_stop = 0
exit_status = 0

# ==========================================
# USER STATE
# ==========================================
pca_enabled = 0
auto_parking_cmd = 0
line_angle_cmd = 0

# ==========================================
# BUZZER
# ==========================================
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

buzzer = GPIO.PWM(BUZZER_PIN, 2000)
buzzer.start(0)

# ==========================================
# CAN RX THREAD
# ==========================================
def can_rx():
    global obstacle_levels, pca_state, vehicle_speed
    global gear_status_from_ecu, emergency_stop, exit_status

    print("RX THREAD ALIVE")

    while True:
        msg = can_bus.recv()
        if msg is None:
            continue

        d = msg.data

        if msg.arbitration_id == 0x400:
            if len(d) < 14:
                continue

            with lock:
                obstacle_levels[:] = list(d[0:10])
                pca_state = d[10]
                vehicle_speed = d[11]
                gear_status_from_ecu = d[12]
                emergency_stop = d[13]

        elif msg.arbitration_id == 0x401:
            if len(d) > 0:
                with lock:
                    exit_status = d[0]

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

threading.Thread(target=can_rx, daemon=True).start()

# ==========================================
# UTIL
# ==========================================
def axis_to_byte(v):
    x = int((v + 1.0) * 127.5)
    return max(0, min(255, x))

def get_max_level():
    return max(obstacle_levels)

# ==========================================
# CAN TX
# ==========================================
def send_vehicle_status(speed, steer, gear, pca_en, line_angle):
    line_bytes = struct.pack("<h", int(line_angle))

    msg = can.Message(
        arbitration_id=0x201,
        data=bytes([
            speed,
            steer,
            gear,
            pca_en,
            line_bytes[0],
            line_bytes[1]
        ]),
        is_extended_id=False,
    )

    can_bus.send(msg)

def send_auto_parking(cmd):
    msg = can.Message(
        arbitration_id=0x300,
        data=bytes([cmd]),
        is_extended_id=False
    )
    can_bus.send(msg)

# ==========================================
# BUZZER THREAD
# ==========================================
def beep_worker():
    while True:
        level = get_max_level()

        if level in [LEVEL_NO_OBSTACLE, LEVEL_SAFE]:
            buzzer.ChangeDutyCycle(0)

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

        time.sleep(0.05)

threading.Thread(target=beep_worker, daemon=True).start()

# ==========================================
# TIMERS
# ==========================================
last_201 = 0
last_300 = 0
last_print = 0

# ==========================================
# MAIN LOOP
# ==========================================
try:
    while True:

        pygame.event.pump()

        speed = axis_to_byte(js.get_axis(1))
        steer = axis_to_byte(js.get_axis(2))

        if js.get_button(BUTTON_P):
            gear_state = GEAR_P
        if js.get_button(BUTTON_D):
            gear_state = GEAR_D
        if js.get_button(BUTTON_R):
            gear_state = GEAR_R

        current_pca_button = js.get_button(BUTTON_PCA)

        if current_pca_button == 1 and prev_pca_button == 0:
            pca_enabled = 1 - pca_enabled

        prev_pca_button = current_pca_button

        if gear_state == GEAR_P:
            speed = 127
            steer = 127
        elif gear_state == GEAR_D and speed > 127:
            speed = 127
        elif gear_state == GEAR_R and speed < 127:
            speed = 127

        if emergency_stop == 1:
            speed = 127
            steer = 127

        now = time.time()

        if now - last_201 >= 0.012:
            send_vehicle_status(speed, steer, gear_state, pca_enabled, line_angle_cmd)
            last_201 = now

        if now - last_300 >= 0.1:
            send_auto_parking(auto_parking_cmd)
            last_300 = now

        # ==========================================
        # SIMPLE PRINT (REQUESTED FORMAT)
        # ==========================================
        if now - last_print >= 0.2:
            print(
                f"SPD:{speed}  "
                f"STR:{steer}  "
                f"GEAR:{gear_state}  "
                f"PCA:{pca_enabled}  "
                f"ECU_PCA:{pca_state}  "
                f"VSPD:{vehicle_speed}  "
                f"ESTOP:{emergency_stop}  "
                f"EXIT:{exit_status}  "
                f"OBS:{get_max_level()}"
            )
            last_print = now

        time.sleep(0.01)

except KeyboardInterrupt:
    print("EXIT")

finally:
    buzzer.stop()
    GPIO.cleanup()
    pygame.quit()
