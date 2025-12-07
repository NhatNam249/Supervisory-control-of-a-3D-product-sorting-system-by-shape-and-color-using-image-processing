import sys
import cv2
import numpy as np
import snap7

from PyQt5 import QtCore, QtGui, QtWidgets
from util import get_limits  # HÀM GET_LIMITS Ở util.py

# ===================== CẤU HÌNH PLC =====================
PLC_IP = "192.168.0.1"   # ĐỔI thành IP PLC của bạn
RACK = 0
SLOT = 1

DB_NUMBER = 5            # DB chứa mã màu
COLOR_ADDR_BYTE = 0      # DBW0: lưu mã màu (INT)

# QUY ƯỚC MÃ MÀU GỬI XUỐNG PLC
COLOR_NONE = 0
COLOR_YELLOW = 1
COLOR_RED = 2
COLOR_BLUE = 3

# ===================== CẤU HÌNH CAMERA =====================
CAM_INDEX_1 = 1   # camera 1 (trên)
CAM_INDEX_2 = 2   # camera 2 (ngang)

FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ===================== CẤU HÌNH NGƯỠNG HSV =====================
YELLOW_BGR = [0, 255, 255]   # vàng
RED_BGR    = [0, 0, 255]     # đỏ

YELLOW_LOWER, YELLOW_UPPER = get_limits(YELLOW_BGR)
RED_LOWER, RED_UPPER       = get_limits(RED_BGR)

# XANH DƯƠNG: DẢI RỘNG CHO XANH ĐẬM
BLUE_LOWER = np.array([90, 50, 50], dtype=np.uint8)
BLUE_UPPER = np.array([140, 255, 255], dtype=np.uint8)


# ===================== NHẬN DẠNG MÀU + HÌNH TRONG VÙNG MÀU =====================
def detect_color_and_shape(frame):
    """
    - Lọc 3 màu: vàng, đỏ, xanh dương bằng HSV
    - Chỉ lấy contour trong vùng màu (mask)
    - Từ contour đó suy ra hình: tam giác / vuông / chữ nhật / tròn
    -> Không bị ảnh hưởng bởi nền xung quanh
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Tạo mask cho từng màu
    mask_yellow = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)
    mask_red    = cv2.inRange(hsv, RED_LOWER, RED_UPPER)
    mask_blue   = cv2.inRange(hsv, BLUE_LOWER, BLUE_UPPER)

    # Làm mượt mask để giảm nhiễu
    mask_yellow = cv2.medianBlur(mask_yellow, 5)
    mask_red    = cv2.medianBlur(mask_red, 5)
    mask_blue   = cv2.medianBlur(mask_blue, 5)

    def get_max_contour(mask):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0, None, None
        c = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(c)
        if area < 500:   # bỏ nhiễu nhỏ
            return 0, None, None
        x, y, w, h = cv2.boundingRect(c)
        return area, (x, y, w, h), c

    # Tìm contour lớn nhất cho mỗi màu
    area_yellow, bbox_yellow, cnt_yellow = get_max_contour(mask_yellow)
    area_red,    bbox_red,    cnt_red    = get_max_contour(mask_red)
    area_blue,   bbox_blue,   cnt_blue   = get_max_contour(mask_blue)

    candidates = [
        (area_yellow, COLOR_YELLOW, bbox_yellow, cnt_yellow, (0, 255, 255), "VANG"),
        (area_red,    COLOR_RED,    bbox_red,    cnt_red,    (0, 0, 255),   "DO"),
        (area_blue,   COLOR_BLUE,   bbox_blue,   cnt_blue,   (255, 0, 0),   "XANH DUONG"),
    ]

    best_area = 0
    best_color_code = COLOR_NONE
    best_bbox = None
    best_cnt = None
    best_color_bgr = None
    best_color_name = "NONE"

    for area, code, bbox, cnt, bgr, text in candidates:
        if area > best_area:
            best_area = area
            best_color_code = code
            best_bbox = bbox
            best_cnt = cnt
            best_color_bgr = bgr
            best_color_name = text

    shape_name = "NONE"

    if best_area > 0 and best_bbox is not None and best_cnt is not None:
        # Dùng contour của VÙNG MÀU để đoán hình dạng
        epsilon = 0.02 * cv2.arcLength(best_cnt, True)
        approx = cv2.approxPolyDP(best_cnt, epsilon, True)
        v = len(approx)

        x, y, w, h = best_bbox
        aspect_ratio = float(w) / h if h != 0 else 1.0

        if v == 3:
            shape_name = "TAM GIAC"
        elif v == 4:
            if 0.9 <= aspect_ratio <= 1.1:
                shape_name = "VUONG"
            else:
                shape_name = "CHU NHAT"
        else:
            shape_name = "TRON"

        # Vẽ khung + ghi cả màu + hình
        cv2.rectangle(frame, (x, y), (x + w, y + h), best_color_bgr, 3)
        cv2.putText(
            frame,
            f"{best_color_name} - {shape_name}",
            (x, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            best_color_bgr,
            2,
        )

    return frame, best_color_code, shape_name


def color_code_to_text(color_code: int):
    if color_code == COLOR_YELLOW:
        return "VANG (code = 1)", "orange"
    elif color_code == COLOR_RED:
        return "DO (code = 2)", "red"
    elif color_code == COLOR_BLUE:
        return "XANH DUONG (code = 3)", "blue"
    else:
        return "None (code = 0)", "gray"


# ===================== LỚP GIAO DIỆN CHÍNH =====================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("2 Camera + PLC - Quet MAU + HINH theo vung mau")
        self.resize(1400, 600)

        self.plc_connected = False
        self.last_color_code = COLOR_NONE

        # Kết nối PLC
        self.client = snap7.client.Client()
        self.connect_plc()

        # Mở camera
        self.cap1 = cv2.VideoCapture(CAM_INDEX_1)
        self.cap2 = cv2.VideoCapture(CAM_INDEX_2)

        self.cap1.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap1.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap2.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap2.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        # ========= GIAO DIỆN =========
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        cam_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(cam_layout)

        self.label_cam1 = QtWidgets.QLabel("Camera 1")
        self.label_cam2 = QtWidgets.QLabel("Camera 2")

        self.label_cam1.setFixedSize(640, 480)
        self.label_cam2.setFixedSize(640, 480)
        self.label_cam1.setStyleSheet("background-color: black;")
        self.label_cam2.setStyleSheet("background-color: black;")

        cam_layout.addWidget(self.label_cam1)
        cam_layout.addWidget(self.label_cam2)

        status_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(status_layout)

        self.label_plc_status = QtWidgets.QLabel("PLC: Chua ket noi")
        self.label_plc_status.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.label_color_status = QtWidgets.QLabel("Mau: None")
        self.label_color_status.setStyleSheet("font-size: 16px; font-weight: bold;")

        status_layout.addWidget(self.label_plc_status)
        status_layout.addWidget(self.label_color_status)

        self.btn_quit = QtWidgets.QPushButton("Thoat")
        self.btn_quit.clicked.connect(self.close)
        status_layout.addWidget(self.btn_quit)

        # Timer cập nhật hình
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frames)
        self.timer.start(30)

        self.update_plc_label()

    # ---------- PLC ----------
    def connect_plc(self):
        try:
            self.client.connect(PLC_IP, RACK, SLOT)
            if self.client.get_connected():
                self.plc_connected = True
            else:
                self.plc_connected = False
        except Exception as e:
            print("Loi ket noi PLC:", e)
            self.plc_connected = False

    def update_plc_label(self):
        if self.plc_connected:
            self.label_plc_status.setText(f"PLC: Da ket noi ({PLC_IP})")
            self.label_plc_status.setStyleSheet("color: green; font-size: 16px; font-weight: bold;")
        else:
            self.label_plc_status.setText("PLC: Khong ket noi")
            self.label_plc_status.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")

    def send_color_to_plc(self, color_code: int):
        if not self.plc_connected:
            return
        try:
            data = int(color_code).to_bytes(2, byteorder="big", signed=True)
            self.client.db_write(DB_NUMBER, COLOR_ADDR_BYTE, data)
        except Exception as e:
            print("Loi ghi PLC:", e)
            self.plc_connected = False
            self.update_plc_label()

    # ---------- CẬP NHẬT FRAME ----------
    def update_frames(self):
        ret1, frame1 = self.cap1.read()
        ret2, frame2 = self.cap2.read()

        if ret1:
            # Camera 1: QUÉT MÀU + HÌNH (theo vùng màu) + GỬI PLC
            frame1, color_code, shape_name = detect_color_and_shape(frame1)

            text, color_css = color_code_to_text(color_code)
            self.label_color_status.setText(f"Mau: {text} | Hinh: {shape_name}")
            self.label_color_status.setStyleSheet(
                f"color: {color_css}; font-size: 16px; font-weight: bold;"
            )

            if color_code != self.last_color_code:
                self.send_color_to_plc(color_code)
                self.last_color_code = color_code

            self.show_frame_on_label(frame1, self.label_cam1)

        if ret2:
            # Camera 2: CŨNG QUÉT MÀU + HÌNH (theo vùng màu) nhưng KHÔNG gửi PLC
            frame2, _, _ = detect_color_and_shape(frame2)
            self.show_frame_on_label(frame2, self.label_cam2)

    def show_frame_on_label(self, frame, label):
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        q_image = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(q_image)
        pixmap = pixmap.scaled(label.width(), label.height(), QtCore.Qt.KeepAspectRatio)
        label.setPixmap(pixmap)

    # ---------- ĐÓNG APP ----------
    def closeEvent(self, event):
        self.timer.stop()
        if self.cap1.isOpened():
            self.cap1.release()
        if self.cap2.isOpened():
            self.cap2.release()
        if self.plc_connected:
            self.client.disconnect()
        cv2.destroyAllWindows()
        event.accept()


# ===================== CHẠY CHƯƠNG TRÌNH =====================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
