import sys
import math
import time
import cv2
import numpy as np
import snap7

from PyQt5 import QtCore, QtGui, QtWidgets
from snap7.util import set_bool   # dùng để ghi 1 bit trong DB

# ===================== CẤU HÌNH PLC =====================
PLC_IP = "192.168.0.1"  # ĐỔI thành IP PLC của bạn
RACK = 0
SLOT = 1

DB_NUMBER = 32  # DB chứa dữ liệu

# ĐỊA CHỈ DB (WORD)
COLOR_ADDR_BYTE = 0    # DBW0: lưu mã màu (INT)
SHAPE2D_ADDR_BYTE = 4  # DBW4: mã hình 2D
SHAPE3D_ADDR_BYTE = 6  # DBW6: mã hình 3D
LEN_CODE_ADDR_BYTE = 8   # DBW8: mã dài (1/2/3)
WID_CODE_ADDR_BYTE = 10  # DBW10: mã rộng (1/2/3)
HEI_CODE_ADDR_BYTE = 12  # DBW12: mã cao (1/2/3)

# 3 mã chọn theo ĐIỀU KIỆN
MATCH_COLOR_ADDR_BYTE = 14   # DBW14: mã theo MÀU
MATCH_2D_ADDR_BYTE = 16      # DBW16: mã theo HÌNH 2D
MATCH_3D_ADDR_BYTE = 18      # DBW18: mã theo HÌNH 3D

# BIT START/STOP CHƯƠNG TRÌNH PLC (KIỂU 1)
PLC_START_DB = 32      # DB chứa Start_From_PC
PLC_START_BYTE = 20    # DBX20.0 -> byte 20
PLC_START_BIT = 0      # bit 0  -> DBX20.0

# QUY ƯỚC MÃ MÀU
COLOR_NONE = 0
COLOR_YELLOW = 1
COLOR_RED = 2
COLOR_BLUE = 3

# MÃ HÌNH 2D
SHAPE2D_NONE = 0
SHAPE2D_TRIANGLE = 1
SHAPE2D_SQUARE = 2
SHAPE2D_RECT = 3
SHAPE2D_CIRCLE = 4

# MÃ HÌNH 3D
SHAPE3D_NONE = 0
SHAPE3D_CYLINDER = 1          # trụ tròn (từ mặt TRON)
SHAPE3D_TRI_PRISM = 2         # lăng trụ tam giác
SHAPE3D_CUBE = 3              # lập phương
SHAPE3D_RECT_BOX = 4          # khối hộp chữ nhật

# ===================== CẤU HÌNH CAMERA =====================
CAM_INDEX_1 = 1  # camera 1 (trên)
CAM_INDEX_2 = 2  # camera 2 (ngang)

FRAME_WIDTH = 350
FRAME_HEIGHT = 350

# ===================== HỆ SỐ QUY ĐỔI PIXEL -> CM =====================
CM_PER_PX_TOP = 0.017    # camera trên: dài & rộng
CM_PER_PX_SIDE = 0.01    # camera ngang: cao

# ===================== NGƯỠNG MẶC ĐỊNH CHO MÃ 1/2/3 (cm) =====================
LEN_TH1_CM = 3.0
LEN_TH2_CM = 6.0
WID_TH1_CM = 3.0
WID_TH2_CM = 6.0
HEI_TH1_CM = 3.0
HEI_TH2_CM = 6.0

# ===================== THAM SỐ ỔN ĐỊNH =====================
STABLE_TIME_SEC = 1.0          # cần đứng yên tối thiểu 1 giây
STABLE_MOVE_THRESH_PX = 8.0    # dịch chuyển tâm < 8px coi như đứng yên


# ===================== HÀM TẠO NGƯỠNG HSV (KHÔNG DÙNG CHO ĐỎ) =====================
def get_limits(color_bgr):
    """
    Tạo khoảng HSV cho các màu KHÔNG bị quấn vòng (vd: vàng).
    KHÔNG dùng cho màu đỏ (vì đỏ nằm ở vùng 0/180).
    """
    c = np.uint8([[color_bgr]])  # BGR
    hsv_color = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    H = int(hsv_color[0][0][0])

    lower_limit = np.array([max(H - 10, 0), 70, 70], dtype=np.uint8)
    upper_limit = np.array([min(H + 10, 179), 255, 255], dtype=np.uint8)
    return lower_limit, upper_limit


# ===================== CẤU HÌNH NGƯỠNG HSV =====================
YELLOW_BGR = [0, 255, 255]
RED_BGR = [0, 0, 255]

# VÀNG: dùng get_limits
YELLOW_LOWER, YELLOW_UPPER = get_limits(YELLOW_BGR)

# ĐỎ: dùng 2 khoảng HSV để bắt tốt hơn
RED_LOWER_1 = np.array([0, 80, 80], dtype=np.uint8)
RED_UPPER_1 = np.array([10, 255, 255], dtype=np.uint8)
RED_LOWER_2 = np.array([170, 80, 80], dtype=np.uint8)
RED_UPPER_2 = np.array([180, 255, 255], dtype=np.uint8)

# XANH DƯƠNG
BLUE_LOWER = np.array([90, 50, 50], dtype=np.uint8)
BLUE_UPPER = np.array([140, 255, 255], dtype=np.uint8)

# ===================== GIỚI HẠN DIỆN TÍCH =====================
MIN_AREA = 2000
MAX_AREA = 80000


# ===================== XỬ LÝ ẢNH =====================
def detect_shape(contour):
    area = cv2.contourArea(contour)
    peri = cv2.arcLength(contour, True)

    if peri > 0:
        circularity = 4 * math.pi * area / (peri ** 2)
    else:
        circularity = 0

    if circularity > 0.82:
        return "TRON"

    epsilon = 0.03 * peri
    approx = cv2.approxPolyDP(contour, epsilon, True)
    vertices = len(approx)

    if vertices > 6:
        epsilon = 0.04 * peri
        approx = cv2.approxPolyDP(contour, epsilon, True)
        vertices = len(approx)

    if vertices < 3:
        epsilon = 0.02 * peri
        approx = cv2.approxPolyDP(contour, epsilon, True)
        vertices = len(approx)

    if vertices == 3:
        return "TAM GIAC"

    elif vertices == 4:
        rect = cv2.minAreaRect(contour)
        (cx, cy), (width, height), angle = rect

        if width < height:
            width, height = height, width

        if height == 0:
            aspect_ratio = 1.0
        else:
            aspect_ratio = width / height

        if 0.85 <= aspect_ratio <= 1.15:
            return "VUONG"
        else:
            return "CHU NHAT"

    elif vertices > 4:
        rect = cv2.minAreaRect(contour)
        (cx, cy), (width, height), angle = rect

        if width < height:
            width, height = height, width

        rect_area = width * height
        if rect_area > 0:
            extent = area / rect_area
        else:
            extent = 0

        if extent > 0.80:
            if height == 0:
                aspect_ratio = 1.0
            else:
                aspect_ratio = width / height

            if 0.85 <= aspect_ratio <= 1.15:
                return "VUONG"
            else:
                return "CHU NHAT"

        if 0.45 <= extent <= 0.65:
            return "TAM GIAC"

        return "CHU NHAT"

    return "CHU NHAT"


def detect_color_and_shape(frame):
    """
    Trả về thêm:
    - cx, cy: tâm của vật trên khung hình
    - has_obj: True nếu có vật hợp lệ
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hsv = cv2.GaussianBlur(hsv, (5, 5), 0)

    mask_yellow = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)

    # MÀU ĐỎ: ghép 2 khoảng
    mask_red_1 = cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1)
    mask_red_2 = cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)
    mask_red = cv2.bitwise_or(mask_red_1, mask_red_2)

    mask_blue = cv2.inRange(hsv, BLUE_LOWER, BLUE_UPPER)

    kernel = np.ones((5, 5), np.uint8)
    mask_yellow = cv2.morphologyEx(mask_yellow, cv2.MORPH_OPEN, kernel)
    mask_yellow = cv2.morphologyEx(mask_yellow, cv2.MORPH_CLOSE, kernel)
    mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_OPEN, kernel)
    mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_CLOSE, kernel)
    mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_OPEN, kernel)
    mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, kernel)

    def get_valid_contour(mask):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return 0, None, None

        valid_contours = []
        for c in contours:
            area = cv2.contourArea(c)
            if MIN_AREA <= area <= MAX_AREA:
                valid_contours.append((area, c))

        if not valid_contours:
            return 0, None, None

        valid_contours.sort(key=lambda x: x[0], reverse=True)
        area, c = valid_contours[0]
        x, y, w, h = cv2.boundingRect(c)
        return area, (x, y, w, h), c

    area_yellow, bbox_yellow, cnt_yellow = get_valid_contour(mask_yellow)
    area_red, bbox_red, cnt_red = get_valid_contour(mask_red)
    area_blue, bbox_blue, cnt_blue = get_valid_contour(mask_blue)

    candidates = [
        (area_yellow, COLOR_YELLOW, bbox_yellow, cnt_yellow, (0, 255, 255), "VANG"),
        (area_red, COLOR_RED, bbox_red, cnt_red, (0, 0, 255), "DO"),
        (area_blue, COLOR_BLUE, bbox_blue, cnt_blue, (255, 0, 0), "XANH DUONG"),
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
    length_px = 0.0
    width_px = 0.0
    cx = -1.0
    cy = -1.0
    has_obj = False

    if best_area > 0 and best_bbox is not None and best_cnt is not None:
        has_obj = True
        shape_name = detect_shape(best_cnt)

        rect = cv2.minAreaRect(best_cnt)
        (cx, cy), (w_rect, h_rect), angle = rect   # Tâm của vật

        length_px = max(w_rect, h_rect)
        width_px = min(w_rect, h_rect)

        if shape_name == "TRON":
            (xc, yc), radius = cv2.minEnclosingCircle(best_cnt)
            length_px = width_px = 2.0 * radius

        x, y, w, h = cv2.boundingRect(best_cnt)

        box = cv2.boxPoints(rect)
        box = np.int32(box)
        cv2.drawContours(frame, [box], 0, best_color_bgr, 3)

        info_text = f"{best_color_name} - {shape_name} | L={length_px:.1f}px W={width_px:.1f}px"
        cv2.putText(
            frame,
            info_text,
            (x, max(20, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            best_color_bgr,
            2,
        )

    return frame, best_color_code, shape_name, length_px, width_px, cx, cy, has_obj


def shape2d_name_to_code(name: str) -> int:
    if name == "TAM GIAC":
        return SHAPE2D_TRIANGLE
    if name == "VUONG":
        return SHAPE2D_SQUARE
    if name == "CHU NHAT":
        return SHAPE2D_RECT
    if name == "TRON":
        return SHAPE2D_CIRCLE
    return SHAPE2D_NONE


def classify_3d_shape(
    shape2d_top: str,
    shape2d_side: str,
    length_cm: float,
    width_cm: float,
    height_cm: float,
):
    """
    shape2d_top  : hình 2D từ camera 1 (trên)
    shape2d_side : hình 2D từ camera 2 (ngang)
    """
    def approx_equal(a, b, ratio_tol=0.15):
        if a <= 0 or b <= 0:
            return False
        return abs(a - b) <= ratio_tol * (a + b) / 2.0

    # Nếu thiếu kích thước → không xác định 3D
    if length_cm <= 0 or width_cm <= 0 or height_cm <= 0:
        return "NONE", SHAPE3D_NONE

    # ===== RULE ĐẶC BIỆT: CAM 1 VUÔNG + CAM 2 VUÔNG → LẬP PHƯƠNG =====
    if shape2d_top == "VUONG" and shape2d_side == "VUONG":
        return "LAP PHUONG", SHAPE3D_CUBE

    # TRÒN (mặt trên) → KHỐI TRỤ
    if shape2d_top == "TRON":
        return "TRU TRON", SHAPE3D_CYLINDER

    # TAM GIÁC (mặt trên) → LĂNG TRỤ TAM GIÁC
    if shape2d_top == "TAM GIAC":
        return "LANG TRU TAM GIAC", SHAPE3D_TRI_PRISM

    # VUÔNG / CHỮ NHẬT (mặt trên)
    if shape2d_top in ("VUONG", "CHU NHAT"):
        # Nếu 3 cạnh xấp xỉ nhau → LẬP PHƯƠNG
        if approx_equal(length_cm, width_cm) and approx_equal(length_cm, height_cm) and approx_equal(width_cm, height_cm):
            return "LAP PHUONG", SHAPE3D_CUBE
        else:
            return "KHOI HOP CHU NHAT", SHAPE3D_RECT_BOX

    return "NONE", SHAPE3D_NONE


def encode_dim_to_code(value_cm: float, th1: float, th2: float) -> int:
    if value_cm <= 0:
        return 0
    if value_cm < th1:
        return 1
    if value_cm < th2:
        return 2
    return 3


# ===================== LỚP GIAO DIỆN CHÍNH =====================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("HỆ THỐNG QUÉT 3D ")
        self.resize(1800, 900)

        # Áp dụng style cho toàn bộ giao diện
        self.apply_style()

        self.plc_connected = False
        self.last_color_code = COLOR_NONE
        self.last_shape2d_code = SHAPE2D_NONE
        self.last_shape3d_code = SHAPE3D_NONE
        self.last_len_code = 0
        self.last_wid_code = 0
        self.last_hei_code = 0

        # dùng riêng cho đếm số lượng
        self.last_color_for_count = COLOR_NONE
        self.last_shape2d_for_count = "NONE"
        self.last_shape3d_for_count = "NONE"

        # Counters màu
        self.count_red = 0
        self.count_yellow = 0
        self.count_blue = 0

        # Counters 2D
        self.count_tron = 0
        self.count_vuong = 0
        self.count_tamgiac = 0
        self.count_chunhat = 0
        self.count_2d_total = 0

        # Counters 3D
        self.count_cylinder = 0
        self.count_triprism = 0
        self.count_cube = 0
        self.count_rectbox = 0
        self.count_3d_total = 0

        # Lưu giá trị hiện tại
        self.current_length_cm = 0.0
        self.current_width_cm = 0.0
        self.current_height_cm = 0.0
        self.current_shape2d_name = "NONE"       # hình 2D cam 1
        self.current_shape2d_cam2_name = "NONE"  # hình 2D cam 2
        self.current_shape3d_name = "NONE"
        self.current_color_name = "NONE"

        # Các label thông tin cũ (không đưa lên layout, chỉ dùng nội bộ nếu cần)
        self.label_cur_color = QtWidgets.QLabel()
        self.label_cur_shape2d = QtWidgets.QLabel()
        self.label_cur_shape3d = QtWidgets.QLabel()
        self.label_cur_dim = QtWidgets.QLabel(
            "Kích thước: L=0.0 x W=0.0 x H=0.0 cm"
        )
        # chữ kích thước to – nổi bật
        self.label_cur_dim.setAlignment(QtCore.Qt.AlignCenter)
        self.label_cur_dim.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #FACC15; padding: 6px;"
        )

        # ====== TRẠNG THÁI ỔN ĐỊNH ======
        self.prev_center = None        # (cx, cy) của frame trước
        self.stable_start_time = None  # thời điểm bắt đầu đứng yên
        self.object_stable = False     # chỉ khi True mới quét & gửi PLC

        # ====== CỜ: ĐÃ QUÉT XONG VẬT HIỆN TẠI CHƯA ======
        # True  -> đã quét xong 1 vật, chờ vật biến mất rồi mới quét tiếp
        # False -> vật mới / chưa quét
        self.scanned_current_obj = False

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
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # -------- Hàng trên: Start/Stop + 2 camera --------
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(10)
        main_layout.addLayout(top_layout, stretch=3)

        # Panel START/STOP
        ctrl_group = QtWidgets.QGroupBox("ĐIỀU KHIỂN")
        ctrl_layout = QtWidgets.QVBoxLayout(ctrl_group)
        ctrl_layout.setSpacing(12)

        self.btn_start = QtWidgets.QPushButton("BẮT ĐẦU QUÉT")
        self.btn_start.setFixedSize(160, 50)
        self.btn_start.setStyleSheet(
            "background-color: #22C55E; color: #0B1120; font-weight: 700; font-size: 16px;"
        )
        self.btn_start.clicked.connect(self.start_scanning)

        self.btn_stop = QtWidgets.QPushButton("DỪNG")
        self.btn_stop.setFixedSize(160, 50)
        self.btn_stop.setStyleSheet(
            "background-color: #EF4444; color: #F9FAFB; font-weight: 700; font-size: 16px;"
        )
        self.btn_stop.clicked.connect(self.stop_scanning)

        self.btn_reset = QtWidgets.QPushButton("RESET HỆ THỐNG")
        self.btn_reset.setFixedSize(160, 46)
        self.btn_reset.setStyleSheet(
            "background-color: #F97316; color: #111827; font-weight: 600; font-size: 14px;"
        )
        self.btn_reset.clicked.connect(self.reset_system)

        self.btn_toggle_cond = QtWidgets.QPushButton("CÀI ĐIỀU KIỆN GỬI MÃ")
        self.btn_toggle_cond.setFixedSize(180, 46)
        self.btn_toggle_cond.setStyleSheet(
            "background-color: #3B82F6; color: #F9FAFB; font-weight: 600; font-size: 14px;"
        )
        self.btn_toggle_cond.clicked.connect(self.toggle_condition_panel)

        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self.btn_start, alignment=QtCore.Qt.AlignHCenter)
        ctrl_layout.addWidget(self.btn_stop, alignment=QtCore.Qt.AlignHCenter)
        ctrl_layout.addWidget(self.btn_reset, alignment=QtCore.Qt.AlignHCenter)
        ctrl_layout.addWidget(self.btn_toggle_cond, alignment=QtCore.Qt.AlignHCenter)
        ctrl_layout.addStretch()

        top_layout.addWidget(ctrl_group, stretch=2)

        # Camera 1
        cam1_group = QtWidgets.QGroupBox("Camera 1 (TRÊN) ")
        cam1_layout = QtWidgets.QVBoxLayout(cam1_group)
        self.label_cam1 = QtWidgets.QLabel()
        self.label_cam1.setFixedSize(640, 480)
        self.label_cam1.setStyleSheet(
            "background-color: #020617; color: #9CA3AF; "
            "border: 1px solid #1F2937; border-radius: 10px;"
        )
        self.label_cam1.setAlignment(QtCore.Qt.AlignCenter)
        cam1_layout.addWidget(self.label_cam1)
        top_layout.addWidget(cam1_group, stretch=4)

        # Camera 2
        cam2_group = QtWidgets.QGroupBox("Camera 2 (NGANG)")
        cam2_layout = QtWidgets.QVBoxLayout(cam2_group)
        self.label_cam2 = QtWidgets.QLabel()
        self.label_cam2.setFixedSize(640, 480)
        self.label_cam2.setStyleSheet(
            "background-color: #020617; color: #9CA3AF; "
            "border: 1px solid #1F2937; border-radius: 10px;"
        )
        self.label_cam2.setAlignment(QtCore.Qt.AlignCenter)
        cam2_layout.addWidget(self.label_cam2)
        top_layout.addWidget(cam2_group, stretch=4)

        # -------- Hàng giữa: 3 cột --------
        mid_layout = QtWidgets.QHBoxLayout()
        mid_layout.setSpacing(10)
        main_layout.addLayout(mid_layout, stretch=2)

        # ========== CỘT 1: MÀU + HÌNH 2D ==========
        left_group = QtWidgets.QGroupBox("THỐNG KÊ MÀU & HÌNH 2D")
        left_vbox = QtWidgets.QVBoxLayout(left_group)
        left_vbox.setSpacing(8)

        # Nhóm MÀU
        self.group_color = QtWidgets.QGroupBox("Màu sắc (Số lượng)")
        color_layout = QtWidgets.QHBoxLayout(self.group_color)
        color_layout.setSpacing(8)

        self.label_color_do = QtWidgets.QLabel("ĐỎ\nSL: 0")
        self.label_color_vang = QtWidgets.QLabel("VÀNG\nSL: 0")
        self.label_color_xanh = QtWidgets.QLabel("XANH\nSL: 0")

        for lbl, col, bg in [
            (self.label_color_do, "#F97373", "#1F2933"),
            (self.label_color_vang, "#FACC15", "#1F2933"),
            (self.label_color_xanh, "#60A5FA", "#1F2933"),
        ]:
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setFixedSize(105, 60)
            lbl.setStyleSheet(
                "border-radius: 8px; border: 1px solid #4B5563; "
                f"font-weight: 700; color: {col}; background-color: {bg}; font-size: 13px;"
            )
            color_layout.addWidget(lbl)

        left_vbox.addWidget(self.group_color)

        # Nhóm HÌNH 2D
        self.group_shape2d = QtWidgets.QGroupBox("Hình 2D (Số lượng)")
        shape2d_layout = QtWidgets.QHBoxLayout(self.group_shape2d)
        shape2d_layout.setSpacing(8)

        self.label_tron = QtWidgets.QLabel("TRÒN\nSL: 0")
        self.label_vuong = QtWidgets.QLabel("VUÔNG\nSL: 0")
        self.label_tamgiac = QtWidgets.QLabel("TAM GIÁC\nSL: 0")
        self.label_chunhat = QtWidgets.QLabel("CHỮ NHẬT\nSL: 0")

        for lbl in [self.label_tron, self.label_vuong, self.label_tamgiac, self.label_chunhat]:
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setFixedSize(110, 60)
            lbl.setStyleSheet(
                "border-radius: 8px; border: 1px solid #4B5563; "
                "background-color: #020617; font-weight: 600; font-size: 13px;"
            )
            shape2d_layout.addWidget(lbl)

        left_vbox.addWidget(self.group_shape2d)

        self.label_total_2d = QtWidgets.QLabel("Tổng số vật 2D: 0")
        self.label_total_2d.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #E5E7EB; padding-top: 4px;"
        )
        left_vbox.addWidget(self.label_total_2d)

        left_vbox.addStretch()
        mid_layout.addWidget(left_group, stretch=1)

        # ========== CỘT 2: HÌNH 3D + KÍCH THƯỚC ==========
        center_group = QtWidgets.QGroupBox("HÌNH 3D & KÍCH THƯỚC")
        center_vbox = QtWidgets.QVBoxLayout(center_group)
        center_vbox.setSpacing(8)

        # Nhóm HÌNH 3D (SỐ LƯỢNG)
        self.group_shape3d_count = QtWidgets.QGroupBox("Hình 3D (Số lượng)")
        shape3d_layout = QtWidgets.QVBoxLayout(self.group_shape3d_count)

        row_3d = QtWidgets.QHBoxLayout()

        self.label_cylinder = QtWidgets.QLabel("TRỤ TRÒN\nSL: 0")
        self.label_triprism = QtWidgets.QLabel("LĂNG TRỤ TAM GIÁC\nSL: 0")
        self.label_cube = QtWidgets.QLabel("LẬP PHƯƠNG\nSL: 0")
        self.label_rectbox = QtWidgets.QLabel("HỘP CHỮ NHẬT\nSL: 0")

        for lbl in [self.label_cylinder, self.label_triprism, self.label_cube, self.label_rectbox]:
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setFixedSize(160, 60)
            lbl.setStyleSheet(
                "border-radius: 8px; border: 1px solid #4B5563; "
                "background-color: #020617; font-weight: 600; font-size: 13px;"
            )
            row_3d.addWidget(lbl)

        shape3d_layout.addLayout(row_3d)

        self.label_total_3d = QtWidgets.QLabel("Tổng số vật 3D: 0")
        self.label_total_3d.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #E5E7EB; padding-top: 4px;"
        )
        shape3d_layout.addWidget(self.label_total_3d)

        center_vbox.addWidget(self.group_shape3d_count)

        # Nhóm KÍCH THƯỚC VẬT ĐƯỢC QUÉT
        self.group_dim = QtWidgets.QGroupBox("Kích thước vật được quét")
        dim_info_layout = QtWidgets.QVBoxLayout(self.group_dim)

        dim_info_layout.addWidget(self.label_cur_dim)

        center_vbox.addWidget(self.group_dim)

        center_vbox.addStretch()
        mid_layout.addWidget(center_group, stretch=1)

        # ========== CỘT 3: ĐIỀU KIỆN GỬI MÃ (ẨN / HIỆN BẰNG NÚT) ==========
        self.right_group = QtWidgets.QGroupBox("CHỌN ĐIỀU KIỆN GỬI MÃ VỀ PLC")
        right_vbox = QtWidgets.QVBoxLayout(self.right_group)
        right_vbox.setSpacing(8)

        select_group = QtWidgets.QGroupBox("Mã 1 / 2 / 3 cho MÀU - 2D - 3D")
        select_layout = QtWidgets.QGridLayout(select_group)
        select_layout.setHorizontalSpacing(10)
        select_layout.setVerticalSpacing(6)

        # ====== MÀU ======
        header_color = QtWidgets.QLabel("MÀU → mã 1 / 2 / 3")
        header_color.setStyleSheet("font-weight: 700; color: #F9FAFB;")
        select_layout.addWidget(header_color, 0, 0, 1, 6)

        select_layout.addWidget(QtWidgets.QLabel("Màu cho mã 1:"), 1, 0)
        self.cb_color_t1 = QtWidgets.QComboBox()
        self.cb_color_t1.addItems(["Không chọn", "DO", "VANG", "XANH"])
        select_layout.addWidget(self.cb_color_t1, 1, 1)

        select_layout.addWidget(QtWidgets.QLabel("Màu cho mã 2:"), 1, 2)
        self.cb_color_t2 = QtWidgets.QComboBox()
        self.cb_color_t2.addItems(["Không chọn", "DO", "VANG", "XANH"])
        select_layout.addWidget(self.cb_color_t2, 1, 3)

        select_layout.addWidget(QtWidgets.QLabel("Màu cho mã 3:"), 1, 4)
        self.cb_color_t3 = QtWidgets.QComboBox()
        self.cb_color_t3.addItems(["Không chọn", "DO", "VANG", "XANH"])
        select_layout.addWidget(self.cb_color_t3, 1, 5)

        self.chk_use_color = QtWidgets.QCheckBox("Bật mã MÀU (DBW14)")
        self.chk_use_color.setChecked(True)
        select_layout.addWidget(self.chk_use_color, 2, 0, 1, 3)

        self.label_match_color = QtWidgets.QLabel("Đang gửi: 0 (DBW14)")
        select_layout.addWidget(self.label_match_color, 2, 3, 1, 3)

        # ====== HÌNH 2D ======
        header_2d = QtWidgets.QLabel("HÌNH 2D → mã 1 / 2 / 3")
        header_2d.setStyleSheet("font-weight: 700; color: #F9FAFB;")
        select_layout.addWidget(header_2d, 3, 0, 1, 6)

        select_layout.addWidget(QtWidgets.QLabel("2D cho mã 1:"), 4, 0)
        self.cb_shape2d_t1 = QtWidgets.QComboBox()
        self.cb_shape2d_t1.addItems(["Không chọn", "TRON", "VUONG", "TAM GIAC", "CHU NHAT"])
        select_layout.addWidget(self.cb_shape2d_t1, 4, 1)

        select_layout.addWidget(QtWidgets.QLabel("2D cho mã 2:"), 4, 2)
        self.cb_shape2d_t2 = QtWidgets.QComboBox()
        self.cb_shape2d_t2.addItems(["Không chọn", "TRON", "VUONG", "TAM GIAC", "CHU NHAT"])
        select_layout.addWidget(self.cb_shape2d_t2, 4, 3)

        select_layout.addWidget(QtWidgets.QLabel("2D cho mã 3:"), 4, 4)
        self.cb_shape2d_t3 = QtWidgets.QComboBox()
        self.cb_shape2d_t3.addItems(["Không chọn", "TRON", "VUONG", "TAM GIAC", "CHU NHAT"])
        select_layout.addWidget(self.cb_shape2d_t3, 4, 5)

        self.chk_use_2d = QtWidgets.QCheckBox("Bật mã 2D (DBW16)")
        self.chk_use_2d.setChecked(True)
        select_layout.addWidget(self.chk_use_2d, 5, 0, 1, 3)

        self.label_match_2d = QtWidgets.QLabel("Đang gửi: 0 (DBW16)")
        select_layout.addWidget(self.label_match_2d, 5, 3, 1, 3)

        # ====== HÌNH 3D ======
        header_3d = QtWidgets.QLabel("HÌNH 3D → mã 1 / 2 / 3")
        header_3d.setStyleSheet("font-weight: 700; color: #F9FAFB;")
        select_layout.addWidget(header_3d, 6, 0, 1, 6)

        select_layout.addWidget(QtWidgets.QLabel("3D cho mã 1:"), 7, 0)
        self.cb_shape3d_t1 = QtWidgets.QComboBox()
        self.cb_shape3d_t1.addItems(
            ["Không chọn", "TRU TRON", "LANG TRU TAM GIAC", "LAP PHUONG", "KHOI HOP CHU NHAT"]
        )
        select_layout.addWidget(self.cb_shape3d_t1, 7, 1)

        select_layout.addWidget(QtWidgets.QLabel("3D cho mã 2:"), 7, 2)
        self.cb_shape3d_t2 = QtWidgets.QComboBox()
        self.cb_shape3d_t2.addItems(
            ["Không chọn", "TRU TRON", "LANG TRU TAM GIAC", "LAP PHUONG", "KHOI HOP CHU NHAT"]
        )
        select_layout.addWidget(self.cb_shape3d_t2, 7, 3)

        select_layout.addWidget(QtWidgets.QLabel("3D cho mã 3:"), 7, 4)
        self.cb_shape3d_t3 = QtWidgets.QComboBox()
        self.cb_shape3d_t3.addItems(
            ["Không chọn", "TRU TRON", "LANG TRU TAM GIAC", "LAP PHUONG", "KHOI HOP CHU NHAT"]
        )
        select_layout.addWidget(self.cb_shape3d_t3, 7, 5)

        self.chk_use_3d = QtWidgets.QCheckBox("Bật mã 3D (DBW18)")
        self.chk_use_3d.setChecked(True)
        select_layout.addWidget(self.chk_use_3d, 8, 0, 1, 3)

        self.label_match_3d = QtWidgets.QLabel("Đang gửi: 0 (DBW18)")
        select_layout.addWidget(self.label_match_3d, 8, 3, 1, 3)

        right_vbox.addWidget(select_group)

        # ====== Điều kiện KÍCH THƯỚC ======
        dim_group = QtWidgets.QGroupBox("Điều kiện kích thước (DÀI / RỘNG / CAO)")
        dim_layout = QtWidgets.QGridLayout(dim_group)
        dim_layout.setHorizontalSpacing(10)
        dim_layout.setVerticalSpacing(6)

        self.chk_use_dim = QtWidgets.QCheckBox("Bật điều kiện L / W / H")
        self.chk_use_dim.setChecked(False)
        dim_layout.addWidget(self.chk_use_dim, 0, 0, 1, 4)

        # DÀI
        dim_layout.addWidget(QtWidgets.QLabel("DÀI (cm) từ:"), 1, 0)
        self.spin_len_min = QtWidgets.QDoubleSpinBox()
        self.spin_len_min.setRange(0, 1000)
        self.spin_len_min.setDecimals(1)
        self.spin_len_min.setSingleStep(0.5)
        self.spin_len_min.setValue(0.0)
        dim_layout.addWidget(self.spin_len_min, 1, 1)

        dim_layout.addWidget(QtWidgets.QLabel("đến:"), 1, 2)
        self.spin_len_max = QtWidgets.QDoubleSpinBox()
        self.spin_len_max.setRange(0, 1000)
        self.spin_len_max.setDecimals(1)
        self.spin_len_max.setSingleStep(0.5)
        self.spin_len_max.setValue(100.0)
        dim_layout.addWidget(self.spin_len_max, 1, 3)

        # RỘNG
        dim_layout.addWidget(QtWidgets.QLabel("RỘNG (cm) từ:"), 2, 0)
        self.spin_wid_min = QtWidgets.QDoubleSpinBox()
        self.spin_wid_min.setRange(0, 1000)
        self.spin_wid_min.setDecimals(1)
        self.spin_wid_min.setSingleStep(0.5)
        self.spin_wid_min.setValue(0.0)
        dim_layout.addWidget(self.spin_wid_min, 2, 1)

        dim_layout.addWidget(QtWidgets.QLabel("đến:"), 2, 2)
        self.spin_wid_max = QtWidgets.QDoubleSpinBox()
        self.spin_wid_max.setRange(0, 1000)
        self.spin_wid_max.setDecimals(1)
        self.spin_wid_max.setSingleStep(0.5)
        self.spin_wid_max.setValue(100.0)
        dim_layout.addWidget(self.spin_wid_max, 2, 3)

        # CAO
        dim_layout.addWidget(QtWidgets.QLabel("CAO (cm) từ:"), 3, 0)
        self.spin_hei_min = QtWidgets.QDoubleSpinBox()
        self.spin_hei_min.setRange(0, 1000)
        self.spin_hei_min.setDecimals(1)
        self.spin_hei_min.setSingleStep(0.5)
        self.spin_hei_min.setValue(0.0)
        dim_layout.addWidget(self.spin_hei_min, 3, 1)

        dim_layout.addWidget(QtWidgets.QLabel("đến:"), 3, 2)
        self.spin_hei_max = QtWidgets.QDoubleSpinBox()
        self.spin_hei_max.setRange(0, 1000)
        self.spin_hei_max.setDecimals(1)
        self.spin_hei_max.setSingleStep(0.5)
        self.spin_hei_max.setValue(100.0)
        dim_layout.addWidget(self.spin_hei_max, 3, 3)

        right_vbox.addWidget(dim_group)
        right_vbox.addStretch()

        mid_layout.addWidget(self.right_group, stretch=1)

        # Mặc định ẨN panel điều kiện, chỉ hiện khi bấm nút
        self.right_group.setVisible(False)

        # -------- Hàng cuối: trạng thái PLC + thông tin --------
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.setSpacing(10)
        main_layout.addLayout(status_layout)

        self.label_plc_status = QtWidgets.QLabel("PLC: Chưa kết nối")
        self.label_plc_status.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #F97316;"
        )

        self.label_info = QtWidgets.QLabel("...")
        self.label_info.setStyleSheet("font-size: 14px; color:#E5E7EB;")

        self.btn_quit = QtWidgets.QPushButton("Thoát")
        self.btn_quit.setFixedWidth(110)
        self.btn_quit.setStyleSheet(
            "background-color: #6B7280; color:#F9FAFB; font-weight: 600;"
        )
        self.btn_quit.clicked.connect(self.close)

        status_layout.addWidget(self.label_plc_status)
        status_layout.addStretch()
        status_layout.addWidget(self.label_info)
        status_layout.addStretch()
        status_layout.addWidget(self.btn_quit)

        self.update_plc_label()

        # Timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frames)
        self.timer.start(30)

    # ---------- STYLE CHUNG ----------
    def apply_style(self):
        self.setStyleSheet("""
            * {
                font-family: "Segoe UI", "Roboto", sans-serif;
            }
            QMainWindow {
                background-color: #020617;
            }
            QGroupBox {
                border: 1px solid #1F2937;
                border-radius: 10px;
                margin-top: 10px;
                background-color: #0B1120;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 2px 8px;
                color: #E5E7EB;
                font-weight: 700;
                background-color: transparent;
                border-radius: 0px;
            }
            QLabel {
                color: #E5E7EB;
                font-size: 13px;
            }
            QPushButton {
                border-radius: 8px;
                padding: 8px 14px;
                border: 1px solid #1F2937;
                background-color: #111827;
                color: #E5E7EB;
                font-weight: 600;
            }
            QPushButton:hover {
                border: 1px solid #2563EB;
                background-color: #1F2937;
            }
            QComboBox, QDoubleSpinBox {
                background-color: #020617;
                border: 1px solid #4B5563;
                border-radius: 6px;
                padding: 4px 6px;
                color:#E5E7EB;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #020617;
                selection-background-color: #2563EB;
                selection-color: #F9FAFB;
            }
            QCheckBox {
                color:#E5E7EB;
                font-size: 12px;
            }
            QScrollArea {
                background-color: transparent;
            }
        """)

    # ---------- ẨN / HIỆN PANEL CÀI ĐIỀU KIỆN ----------
    def toggle_condition_panel(self):
        visible = self.right_group.isVisible()
        # đảo trạng thái: đang hiện → ẩn, đang ẩn → hiện
        self.right_group.setVisible(not visible)
        if visible:
            self.btn_toggle_cond.setText("CÀI ĐIỀU KIỆN GỬI MÃ")
        else:
            self.btn_toggle_cond.setText("ẨN ĐIỀU KIỆN GỬI MÃ")

    # ---------- PLC ----------
    def connect_plc(self):
        try:
            self.client.connect(PLC_IP, RACK, SLOT)
            if self.client.get_connected():
                self.plc_connected = True
            else:
                self.plc_connected = False
                error_code = self.client.get_last_error()
                error_message = self.client.error_text(error_code)
                print(f"Lỗi kết nối Snap7: {error_message} (Mã lỗi: {error_code})")
        except Exception as e:
            print("Loi ket noi PLC:", e)
            self.plc_connected = False

    def update_plc_label(self):
        if self.plc_connected:
            self.label_plc_status.setText(f"PLC: Đã kết nối ({PLC_IP})")
            self.label_plc_status.setStyleSheet(
                "color: #22C55E; font-size: 14px; font-weight: 700;"
            )
        else:
            self.label_plc_status.setText("PLC: Không kết nối")
            self.label_plc_status.setStyleSheet(
                "color: #EF4444; font-size: 14px; font-weight: 700;"
            )

    def write_word_plc(self, addr_byte: int, value: int):
        if not self.plc_connected:
            return
        try:
            data = int(value).to_bytes(2, byteorder="big", signed=True)
            self.client.db_write(DB_NUMBER, addr_byte, data)
        except Exception as e:
            print("Loi ghi PLC:", e)
            self.plc_connected = False
            self.update_plc_label()

    def write_db_bool(self, db_number: int, byte_index: int, bit_index: int, value: bool):
        """
        Ghi 1 bit vào DB (dùng cho START/STOP,...)
        db_number : số DB (vd: 32)
        byte_index: byte trong DB (vd: 20 → DBX20.x)
        bit_index : bit trong byte (0..7) (vd: 0 → DBX20.0)
        value     : True/False
        """
        if not self.plc_connected:
            return
        try:
            # Đọc 1 byte hiện tại
            data = self.client.db_read(db_number, byte_index, 1)
            buf = bytearray(data)
            # Ghi bit
            set_bool(buf, 0, bit_index, bool(value))
            # Ghi ngược lại PLC
            self.client.db_write(db_number, byte_index, buf)
        except Exception as e:
            print("Lỗi ghi bit DB:", e)
            self.plc_connected = False
            self.update_plc_label()

    def plc_set_run(self, run: bool):
        """
        Bật/tắt bit Start_From_PC trong DB để ON/OFF chương trình PLC.
        run = True  → DBX20.0 = 1
        run = False → DBX20.0 = 0
        """
        self.write_db_bool(PLC_START_DB, PLC_START_BYTE, PLC_START_BIT, run)

    def send_color_to_plc(self, color_code: int):
        self.write_word_plc(COLOR_ADDR_BYTE, color_code)

    def send_shape2d_to_plc(self, shape_code: int):
        self.write_word_plc(SHAPE2D_ADDR_BYTE, shape_code)

    def send_shape3d_to_plc(self, shape3d_code: int):
        self.write_word_plc(SHAPE3D_ADDR_BYTE, shape3d_code)

    def send_dim_codes_to_plc(self, len_code: int, wid_code: int, hei_code: int):
        self.write_word_plc(LEN_CODE_ADDR_BYTE, len_code)
        self.write_word_plc(WID_CODE_ADDR_BYTE, wid_code)
        self.write_word_plc(HEI_CODE_ADDR_BYTE, hei_code)

    def send_match_color_to_plc(self, code: int):
        self.write_word_plc(MATCH_COLOR_ADDR_BYTE, code)

    def send_match_2d_to_plc(self, code: int):
        self.write_word_plc(MATCH_2D_ADDR_BYTE, code)

    def send_match_3d_to_plc(self, code: int):
        self.write_word_plc(MATCH_3D_ADDR_BYTE, code)

    # ---------- START / STOP ----------
    def start_scanning(self):
        # Bật chương trình PLC (Start_From_PC = 1)
        self.plc_set_run(True)

        if not self.timer.isActive():
            self.timer.start(30)
        self.label_info.setText("Đang QUÉT... (PLC RUN)")

    def stop_scanning(self):
        # Tắt chương trình PLC (Start_From_PC = 0)
        self.plc_set_run(False)

        if self.timer.isActive():
            self.timer.stop()
        # Khi stop gửi 0 hết
        self.send_color_to_plc(0)
        self.send_shape2d_to_plc(0)
        self.send_shape3d_to_plc(0)
        self.send_dim_codes_to_plc(0, 0, 0)
        self.send_match_color_to_plc(0)
        self.send_match_2d_to_plc(0)
        self.send_match_3d_to_plc(0)
        self.label_info.setText("ĐÃ DỪNG QUÉT (PLC STOP)")

    # ---------- NÚT RESET ----------
    def reset_system(self):
        self.last_color_code = COLOR_NONE
        self.last_shape2d_code = SHAPE2D_NONE
        self.last_shape3d_code = SHAPE3D_NONE
        self.last_len_code = 0
        self.last_wid_code = 0
        self.last_hei_code = 0

        self.last_color_for_count = COLOR_NONE
        self.last_shape2d_for_count = "NONE"
        self.last_shape3d_for_count = "NONE"

        # Reset counters màu
        self.count_red = 0
        self.count_yellow = 0
        self.count_blue = 0

        # Reset counters 2D
        self.count_tron = 0
        self.count_vuong = 0
        self.count_tamgiac = 0
        self.count_chunhat = 0
        self.count_2d_total = 0

        # Reset counters 3D
        self.count_cylinder = 0
        self.count_triprism = 0
        self.count_cube = 0
        self.count_rectbox = 0
        self.count_3d_total = 0

        self.current_length_cm = 0.0
        self.current_width_cm = 0.0
        self.current_height_cm = 0.0
        self.current_shape2d_name = "NONE"
        self.current_shape2d_cam2_name = "NONE"
        self.current_shape3d_name = "NONE"
        self.current_color_name = "NONE"

        self.prev_center = None
        self.stable_start_time = None
        self.object_stable = False
        self.scanned_current_obj = False  # cho phép quét lại vật tiếp theo

        # Cập nhật lại label màu
        self.label_color_do.setText("ĐỎ\nSL: 0")
        self.label_color_vang.setText("VÀNG\nSL: 0")
        self.label_color_xanh.setText("XANH\nSL: 0")

        # Cập nhật lại label 2D
        self.label_tron.setText("TRÒN\nSL: 0")
        self.label_vuong.setText("VUÔNG\nSL: 0")
        self.label_tamgiac.setText("TAM GIÁC\nSL: 0")
        self.label_chunhat.setText("CHỮ NHẬT\nSL: 0")
        self.label_total_2d.setText("Tổng số vật 2D: 0")

        # Cập nhật lại label 3D
        self.label_cylinder.setText("TRỤ TRÒN\nSL: 0")
        self.label_triprism.setText("LĂNG TRỤ TAM GIÁC\nSL: 0")
        self.label_cube.setText("LẬP PHƯƠNG\nSL: 0")
        self.label_rectbox.setText("HỘP CHỮ NHẬT\nSL: 0")
        self.label_total_3d.setText("Tổng số vật 3D: 0")

        # Kích thước
        self.label_cur_dim.setText("Kích thước: L=0.0 x W=0.0 x H=0.0 cm")

        self.label_match_color.setText("Đang gửi: 0 (DBW14)")
        self.label_match_2d.setText("Đang gửi: 0 (DBW16)")
        self.label_match_3d.setText("Đang gửi: 0 (DBW18)")

        self.send_color_to_plc(0)
        self.send_shape2d_to_plc(0)
        self.send_shape3d_to_plc(0)
        self.send_dim_codes_to_plc(0, 0, 0)
        self.send_match_color_to_plc(0)
        self.send_match_2d_to_plc(0)
        self.send_match_3d_to_plc(0)

        # Tùy bạn: reset thì có thể tắt luôn chương trình PLC
        self.plc_set_run(False)

        self.label_info.setText("ĐÃ RESET TOÀN BỘ DỮ LIỆU")

    # ---------- CẬP NHẬT TRẠNG THÁI ỔN ĐỊNH ----------
    def update_stable_state(self, has_obj: bool, cx: float, cy: float):
        if not has_obj:
            self.prev_center = None
            self.stable_start_time = None
            self.object_stable = False
            # khi KHÔNG có vật, cho phép lần sau quét vật mới
            self.scanned_current_obj = False
            return

        now = time.time()

        if self.prev_center is None:
            self.prev_center = (cx, cy)
            self.stable_start_time = now
            self.object_stable = False
            return

        dist = math.hypot(cx - self.prev_center[0], cy - self.prev_center[1])

        if dist <= STABLE_MOVE_THRESH_PX:
            if self.stable_start_time is None:
                self.stable_start_time = now
            elif now - self.stable_start_time >= STABLE_TIME_SEC:
                self.object_stable = True
        else:
            self.prev_center = (cx, cy)
            self.stable_start_time = now
            self.object_stable = False

    # ---------- CẬP NHẬT FRAME ----------
    def update_frames(self):
        ret1, frame1 = self.cap1.read()
        ret2, frame2 = self.cap2.read()

        has_obj_cam1 = False

        if ret1:
            (
                frame1,
                color_code,
                shape_name,
                length_px,
                width_px,
                cx,
                cy,
                has_obj_cam1,
            ) = detect_color_and_shape(frame1)

            self.update_stable_state(has_obj_cam1, cx, cy)

            # CHỈ QUÉT 1 LẦN CHO MỖI VẬT:
            # - object_stable = True (đứng yên đủ thời gian)
            # - has_obj_cam1 = True (có vật)
            # - scanned_current_obj = False (chưa quét vật này)
            if self.object_stable and has_obj_cam1 and (not self.scanned_current_obj):
                length_cm = length_px * CM_PER_PX_TOP
                width_cm = width_px * CM_PER_PX_TOP

                self.current_length_cm = length_cm
                self.current_width_cm = width_cm
                self.current_shape2d_name = shape_name

                self.update_color_display(color_code)
                self.update_shape2d_display(shape_name)
                self.update_color_counters(color_code)
                self.update_shape2d_counters(shape_name)

                if color_code != self.last_color_code:
                    self.send_color_to_plc(color_code)
                    self.last_color_code = color_code

                shape2d_code = shape2d_name_to_code(shape_name)
                if shape2d_code != self.last_shape2d_code:
                    self.send_shape2d_to_plc(shape2d_code)
                    self.last_shape2d_code = shape2d_code

                # Sau khi cập nhật thông tin từ cam1, cần 3D + điều kiện
                self.update_3d_and_dimensions()
                self.update_match_condition_and_send()

                # ĐÁNH DẤU ĐÃ QUÉT XONG VẬT NÀY
                self.scanned_current_obj = True
                self.label_info.setText("ĐÃ QUÉT XONG 1 VẬT - CHỜ VẬT TIẾP THEO")

            else:
                if has_obj_cam1:
                    if not self.object_stable:
                        self.label_info.setText("Đang chờ vật đứng yên để quét...")
                    else:
                        # đã stable nhưng đã quét rồi => chỉ chờ vật ra khỏi vùng
                        if self.scanned_current_obj:
                            self.label_info.setText("ĐÃ QUÉT VẬT, CHỜ VẬT RA KHỎI VÙNG...")
                else:
                    # KHÔNG CÓ VẬT → RESET VÀ GỬI 0
                    self.label_info.setText("Không có vật trong vùng quét")

                    self.current_length_cm = 0.0
                    self.current_width_cm = 0.0
                    self.current_height_cm = 0.0
                    self.current_shape2d_name = "NONE"
                    self.current_shape2d_cam2_name = "NONE"
                    self.current_shape3d_name = "NONE"
                    self.current_color_name = "NONE"

                    self.label_cur_dim.setText("Kích thước: L=0.0 x W=0.0 x H=0.0 cm")

                    if self.last_color_code != COLOR_NONE:
                        self.send_color_to_plc(0)
                        self.last_color_code = COLOR_NONE
                    if self.last_shape2d_code != SHAPE2D_NONE:
                        self.send_shape2d_to_plc(0)
                        self.last_shape2d_code = SHAPE2D_NONE
                    if self.last_shape3d_code != SHAPE3D_NONE:
                        self.send_shape3d_to_plc(0)
                        self.last_shape3d_code = SHAPE3D_NONE

                    if (
                        self.last_len_code != 0
                        or self.last_wid_code != 0
                        or self.last_hei_code != 0
                    ):
                        self.send_dim_codes_to_plc(0, 0, 0)
                        self.last_len_code = 0
                        self.last_wid_code = 0
                        self.last_hei_code = 0

                    self.send_match_color_to_plc(0)
                    self.send_match_2d_to_plc(0)
                    self.send_match_3d_to_plc(0)
                    self.label_match_color.setText("Đang gửi: 0 (DBW14)")
                    self.label_match_2d.setText("Đang gửi: 0 (DBW16)")
                    self.label_match_3d.setText("Đang gửi: 0 (DBW18)")

            self.show_frame_on_label(frame1, self.label_cam1)

        if ret2:
            (
                frame2,
                _,
                shape2_cam2,
                length2_px,
                width2_px,
                cx2,
                cy2,
                has_obj_cam2,
            ) = detect_color_and_shape(frame2)

            # Chiều cao lấy theo cạnh lớn hơn
            height_px = max(length2_px, width2_px)
            height_cm = height_px * CM_PER_PX_SIDE
            self.current_height_cm = height_cm

            # Lưu tên hình 2D từ camera 2
            self.current_shape2d_cam2_name = shape2_cam2 if has_obj_cam2 else "NONE"

            self.show_frame_on_label(frame2, self.label_cam2)

    # ---------- MÀU + ĐẾM ----------
    def update_color_display(self, color_code: int):
        if color_code == COLOR_YELLOW:
            text = "Màu: VÀNG"
            self.current_color_name = "VÀNG"
        elif color_code == COLOR_RED:
            text = "Màu: ĐỎ"
            self.current_color_name = "ĐỎ"
        elif color_code == COLOR_BLUE:
            text = "Màu: XANH DƯƠNG"
            self.current_color_name = "XANH DƯƠNG"
        else:
            text = "Màu: NONE"
            self.current_color_name = "NONE"

        self.label_info.setText(text)
        self.label_cur_color.setText(f"Màu: {self.current_color_name}")

        def base_style(lbl, col_txt, bg):
            return (
                "border-radius: 8px; border: 1px solid #4B5563; "
                f"font-weight: 700; color: {col_txt}; background-color: {bg}; font-size: 13px;"
            )

        self.label_color_do.setStyleSheet(base_style(self.label_color_do, "#F97373", "#1F2933"))
        self.label_color_vang.setStyleSheet(base_style(self.label_color_vang, "#FACC15", "#1F2933"))
        self.label_color_xanh.setStyleSheet(base_style(self.label_color_xanh, "#60A5FA", "#1F2933"))

        highlight_border = "3px solid #22C55E"
        if color_code == COLOR_RED:
            self.label_color_do.setStyleSheet(
                "border-radius: 8px; "
                f"border: {highlight_border}; font-weight: 800; color: #F97373; background-color: #020617; font-size: 13px;"
            )
        elif color_code == COLOR_YELLOW:
            self.label_color_vang.setStyleSheet(
                "border-radius: 8px; "
                f"border: {highlight_border}; font-weight: 800; color: #FACC15; background-color: #020617; font-size: 13px;"
            )
        elif color_code == COLOR_BLUE:
            self.label_color_xanh.setStyleSheet(
                "border-radius: 8px; "
                f"border: {highlight_border}; font-weight: 800; color: #60A5FA; background-color: #020617; font-size: 13px;"
            )

    def update_color_counters(self, color_code: int):
        if color_code != COLOR_NONE and color_code != self.last_color_for_count:
            if color_code == COLOR_RED:
                self.count_red += 1
            elif color_code == COLOR_YELLOW:
                self.count_yellow += 1
            elif color_code == COLOR_BLUE:
                self.count_blue += 1

            self.label_color_do.setText(f"ĐỎ\nSL: {self.count_red}")
            self.label_color_vang.setText(f"VÀNG\nSL: {self.count_yellow}")
            self.label_color_xanh.setText(f"XANH\nSL: {self.count_blue}")

            self.last_color_for_count = color_code

        if color_code == COLOR_NONE:
            self.last_color_for_count = COLOR_NONE

    # ---------- HÌNH 2D + ĐẾM ----------
    def update_shape2d_display(self, shape_name: str):
        def base(lbl, text, count):
            lbl.setText(f"{text}\nSL: {count}")
            lbl.setStyleSheet(
                "border-radius: 8px; border: 1px solid #4B5563; "
                "background-color: #020617; font-weight: 600; font-size: 13px;"
            )

        base(self.label_tron, "TRÒN", self.count_tron)
        base(self.label_vuong, "VUÔNG", self.count_vuong)
        base(self.label_tamgiac, "TAM GIÁC", self.count_tamgiac)
        base(self.label_chunhat, "CHỮ NHẬT", self.count_chunhat)

        highlight = (
            "background-color: #064E3B; border-radius: 8px; "
            "border: 2px solid #22C55E; font-weight: 700; font-size: 13px;"
        )

        if shape_name == "TRON":
            self.label_tron.setStyleSheet(highlight)
        elif shape_name == "VUONG":
            self.label_vuong.setStyleSheet(highlight)
        elif shape_name == "TAM GIAC":
            self.label_tamgiac.setStyleSheet(highlight)
        elif shape_name == "CHU NHAT":
            self.label_chunhat.setStyleSheet(highlight)

        self.label_cur_shape2d.setText(f"Hình 2D: {shape_name}")

    def update_shape2d_counters(self, shape_name: str):
        if shape_name != "NONE" and shape_name != self.last_shape2d_for_count:
            if shape_name == "TRON":
                self.count_tron += 1
            elif shape_name == "VUONG":
                self.count_vuong += 1
            elif shape_name == "TAM GIAC":
                self.count_tamgiac += 1
            elif shape_name == "CHU NHAT":
                self.count_chunhat += 1

            self.count_2d_total += 1

            self.label_tron.setText(f"TRÒN\nSL: {self.count_tron}")
            self.label_vuong.setText(f"VUÔNG\nSL: {self.count_vuong}")
            self.label_tamgiac.setText(f"TAM GIÁC\nSL: {self.count_tamgiac}")
            self.label_chunhat.setText(f"CHỮ NHẬT\nSL: {self.count_chunhat}")
            self.label_total_2d.setText(f"Tổng số vật 2D: {self.count_2d_total}")

            self.last_shape2d_for_count = shape_name

        if shape_name == "NONE":
            self.last_shape2d_for_count = "NONE"

    # ---------- HÌNH 3D + KÍCH THƯỚC ----------
    def update_shape3d_display(self, shape3d_name: str):
        def base(lbl, text, count):
            lbl.setText(f"{text}\nSL: {count}")
            lbl.setStyleSheet(
                "border-radius: 8px; border: 1px solid #4B5563; "
                "background-color: #020617; font-weight: 600; font-size: 13px;"
            )

        base(self.label_cylinder, "TRỤ TRÒN", self.count_cylinder)
        base(self.label_triprism, "LĂNG TRỤ TAM GIÁC", self.count_triprism)
        base(self.label_cube, "LẬP PHƯƠNG", self.count_cube)
        base(self.label_rectbox, "HỘP CHỮ NHẬT", self.count_rectbox)

        highlight = (
            "background-color: #064E3B; border-radius: 8px; "
            "border: 2px solid #22C55E; font-weight: 700; font-size: 13px;"
        )

        if shape3d_name == "TRU TRON":
            self.label_cylinder.setStyleSheet(highlight)
        elif shape3d_name == "LANG TRU TAM GIAC":
            self.label_triprism.setStyleSheet(highlight)
        elif shape3d_name == "LAP PHUONG":
            self.label_cube.setStyleSheet(highlight)
        elif shape3d_name == "KHOI HOP CHU NHAT":
            self.label_rectbox.setStyleSheet(highlight)

    def update_shape3d_counters(self, shape3d_name: str):
        if shape3d_name != "NONE" and shape3d_name != self.last_shape3d_for_count:
            if shape3d_name == "TRU TRON":
                self.count_cylinder += 1
            elif shape3d_name == "LANG TRU TAM GIAC":
                self.count_triprism += 1
            elif shape3d_name == "LAP PHUONG":
                self.count_cube += 1
            elif shape3d_name == "KHOI HOP CHU NHAT":
                self.count_rectbox += 1

            self.count_3d_total += 1
            self.label_total_3d.setText(f"Tổng số vật 3D: {self.count_3d_total}")

            self.label_cylinder.setText(f"TRỤ TRÒN\nSL: {self.count_cylinder}")
            self.label_triprism.setText(f"LĂNG TRỤ TAM GIÁC\nSL: {self.count_triprism}")
            self.label_cube.setText(f"LẬP PHƯƠNG\nSL: {self.count_cube}")
            self.label_rectbox.setText(f"HỘP CHỮ NHẬT\nSL: {self.count_rectbox}")

            self.last_shape3d_for_count = shape3d_name

        if shape3d_name == "NONE":
            self.last_shape3d_for_count = "NONE"

    def update_3d_and_dimensions(self):
        shape3d_name, shape3d_code = classify_3d_shape(
            self.current_shape2d_name,          # hình 2D từ camera 1 (trên)
            self.current_shape2d_cam2_name,     # hình 2D từ camera 2 (ngang)
            self.current_length_cm,
            self.current_width_cm,
            self.current_height_cm,
        )

        self.current_shape3d_name = shape3d_name

        # Cập nhật bộ đếm & hiển thị 3D
        self.update_shape3d_counters(shape3d_name)
        self.update_shape3d_display(shape3d_name)

        # Cập nhật kích thước
        self.label_cur_dim.setText(
            f"Kích thước: L={self.current_length_cm:.1f} x "
            f"W={self.current_width_cm:.1f} x "
            f"H={self.current_height_cm:.1f} cm"
        )

        self.label_cur_shape3d.setText(f"Hình 3D: {shape3d_name}")

        if shape3d_code != self.last_shape3d_code:
            self.send_shape3d_to_plc(shape3d_code)
            self.last_shape3d_code = shape3d_code

        len_code = encode_dim_to_code(self.current_length_cm, LEN_TH1_CM, LEN_TH2_CM)
        wid_code = encode_dim_to_code(self.current_width_cm, WID_TH1_CM, WID_TH2_CM)
        hei_code = encode_dim_to_code(self.current_height_cm, HEI_TH1_CM, HEI_TH2_CM)

        if (
            len_code != self.last_len_code
            or wid_code != self.last_wid_code
            or hei_code != self.last_hei_code
        ):
            self.send_dim_codes_to_plc(len_code, wid_code, hei_code)
            self.last_len_code = len_code
            self.last_wid_code = wid_code
            self.last_hei_code = hei_code

    # ---------- GỬI 3 MÃ THEO ĐIỀU KIỆN ----------
    def update_match_condition_and_send(self):
        if not self.chk_use_dim.isChecked():
            dim_ok = True
        else:
            L = self.current_length_cm
            W = self.current_width_cm
            H = self.current_height_cm

            L_ok = (self.spin_len_min.value() <= L <= self.spin_len_max.value()) and (L > 0)
            W_ok = (self.spin_wid_min.value() <= W <= self.spin_wid_max.value()) and (W > 0)
            H_ok = (self.spin_hei_min.value() <= H <= self.spin_hei_max.value()) and (H > 0)

            dim_ok = L_ok and W_ok and H_ok

        code_color = 0
        code_2d = 0
        code_3d = 0

        if dim_ok:
            def color_match(target: str) -> bool:
                if target == "DO":
                    return self.last_color_code == COLOR_RED
                if target == "VANG":
                    return self.last_color_code == COLOR_YELLOW
                if target == "XANH":
                    return self.last_color_code == COLOR_BLUE
                return False

            def shape2d_match(target: str) -> bool:
                return self.current_shape2d_name == target

            def shape3d_match(target: str) -> bool:
                return self.current_shape3d_name == target

            if self.chk_use_color.isChecked():
                if self.cb_color_t1.currentText() != "Không chọn" and color_match(self.cb_color_t1.currentText()):
                    code_color = 1
                elif self.cb_color_t2.currentText() != "Không chọn" and color_match(self.cb_color_t2.currentText()):
                    code_color = 2
                elif self.cb_color_t3.currentText() != "Không chọn" and color_match(self.cb_color_t3.currentText()):
                    code_color = 3

            if self.chk_use_2d.isChecked():
                if self.cb_shape2d_t1.currentText() != "Không chọn" and shape2d_match(self.cb_shape2d_t1.currentText()):
                    code_2d = 1
                elif self.cb_shape2d_t2.currentText() != "Không chọn" and shape2d_match(self.cb_shape2d_t2.currentText()):
                    code_2d = 2
                elif self.cb_shape2d_t3.currentText() != "Không chọn" and shape2d_match(self.cb_shape2d_t3.currentText()):
                    code_2d = 3

            if self.chk_use_3d.isChecked():
                if self.cb_shape3d_t1.currentText() != "Không chọn" and shape3d_match(self.cb_shape3d_t1.currentText()):
                    code_3d = 1
                elif self.cb_shape3d_t2.currentText() != "Không chọn" and shape3d_match(self.cb_shape3d_t2.currentText()):
                    code_3d = 2
                elif self.cb_shape3d_t3.currentText() != "Không chọn" and shape3d_match(self.cb_shape3d_t3.currentText()):
                    code_3d = 3

        self.send_match_color_to_plc(code_color)
        self.send_match_2d_to_plc(code_2d)
        self.send_match_3d_to_plc(code_3d)

        self.label_match_color.setText(f"Đang gửi: {code_color} (DBW14)")
        self.label_match_2d.setText(f"Đang gửi: {code_2d} (DBW16)")
        self.label_match_3d.setText(f"Đang gửi: {code_3d} (DBW18)")

    # ---------- HIỂN THỊ FRAME ----------
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
        if self.timer.isActive():
            self.timer.stop()
        if self.cap1.isOpened():
            self.cap1.release()
        if self.cap2.isOpened():
            self.cap2.release()
        if self.plc_connected:
            # Tắt chương trình PLC trước khi thoát
            self.plc_set_run(False)
            self.client.disconnect()
        cv2.destroyAllWindows()
        event.accept()


# ===================== MAIN =====================
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    # Font chung to, dễ nhìn
    app.setFont(QtGui.QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
