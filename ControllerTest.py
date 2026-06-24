import pygame
import time

pygame.init()
pygame.joystick.init()

while pygame.joystick.get_count() == 0:
    print("게임패드 연결 대기중...")
    time.sleep(1)
    pygame.joystick.quit()
    pygame.joystick.init()

js = pygame.joystick.Joystick(0)
js.init()

print("=================================")
print("게임패드 :", js.get_name())
print("버튼 수 :", js.get_numbuttons())
print("축 수   :", js.get_numaxes())
print("Hat 수  :", js.get_numhats())
print("=================================")

while True:

    pygame.event.pump()

    # 버튼 확인
    for i in range(js.get_numbuttons()):

        if js.get_button(i):
            print(f"BUTTON {i} PRESSED")

    # 축 확인
    for i in range(js.get_numaxes()):

        value = js.get_axis(i)

        if abs(value) > 0.2:
            print(f"AXIS {i} = {value:.3f}")

    # D-Pad 확인
    for i in range(js.get_numhats()):

        hat = js.get_hat(i)

        if hat != (0, 0):
            print(f"HAT {i} = {hat}")

    time.sleep(0.05)