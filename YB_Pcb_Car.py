import math
import smbus


class YB_Pcb_Car:
    def __init__(self):
        self.address = 0x16
        self.bus = smbus.SMBus(1)

    def write_array(self, register, data):
        self.bus.write_i2c_block_data(
            self.address,
            register,
            data,
        )

    def Ctrl_Car(self, left_direction, left_speed,
                 right_direction, right_speed):
        left_speed = max(0, min(255, int(left_speed)))
        right_speed = max(0, min(255, int(right_speed)))

        self.write_array(
            0x01,
            [
                int(left_direction),
                left_speed,
                int(right_direction),
                right_speed,
            ],
        )

    def Car_Run(self, left_speed, right_speed):
        self.Ctrl_Car(1, left_speed, 1, right_speed)

    def Car_Back(self, left_speed, right_speed):
        self.Ctrl_Car(0, left_speed, 0, right_speed)

    def Car_Left(self, left_speed, right_speed):
        self.Ctrl_Car(0, left_speed, 1, right_speed)

    def Car_Right(self, left_speed, right_speed):
        self.Ctrl_Car(1, left_speed, 0, right_speed)

    def Car_Stop(self):
        self.bus.write_byte_data(self.address, 0x02, 0x00)

    def Control_Car(self, left_speed, right_speed):
        left_direction = 1 if left_speed >= 0 else 0
        right_direction = 1 if right_speed >= 0 else 0

        self.Ctrl_Car(
            left_direction,
            math.fabs(left_speed),
            right_direction,
            math.fabs(right_speed),
        )
