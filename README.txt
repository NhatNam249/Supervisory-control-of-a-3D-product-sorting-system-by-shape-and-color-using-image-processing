# Hệ thống quét 3D bằng thị giác máy tính & PLC  
*(Python + OpenCV + PyQt5 + Snap7)*

Dự án này xây dựng một hệ thống thị giác máy tính sử dụng **2 camera** để:

- Nhận dạng **màu sắc** (đỏ, vàng, xanh dương)  
- Nhận dạng **hình 2D** (tròn, vuông, tam giác, chữ nhật)  
- Ước lượng **kích thước 3D** (dài, rộng, cao) từ hình chiếu phía trên và ngang  
- Suy luận **hình khối 3D** (trụ tròn, lăng trụ tam giác, lập phương, hộp chữ nhật)  
- Gửi **mã màu / hình 2D / hình 3D / mã kích thước / mã điều kiện** về PLC Siemens S7 qua Snap7  

Giao diện được xây dựng bằng **PyQt5**, hiển thị hình ảnh từ hai camera, thống kê số lượng vật theo màu, hình 2D, hình 3D, và cho phép cấu hình điều kiện để xuất mã về PLC.

---

## 1. Kiến trúc tổng quan

### 1.1. Các thành phần chính

- **Xử lý ảnh (OpenCV + NumPy)**
  - Chuyển đổi BGR → HSV, tạo mask cho **đỏ, vàng, xanh dương**
  - Lọc nhiễu bằng **morphology (OPEN/CLOSE)**
  - Tìm **contour lớn nhất** nằm trong khoảng diện tích cho phép
  - Nhận dạng **hình 2D** bằng:
    - Độ tròn (circularity)
    - Số đỉnh đa giác xấp xỉ (approxPolyDP)
    - Tỷ lệ cạnh (aspect ratio)
    - Extent (tỉ lệ diện tích contour / bounding box)

- **Ước lượng kích thước**
  - Sử dụng hệ số quy đổi pixel → cm:
    - Camera trên: `CM_PER_PX_TOP` cho **dài, rộng**
    - Camera ngang: `CM_PER_PX_SIDE` cho **cao**
  - Mã hóa kích thước thành **mã 1/2/3** bằng ngưỡng:
    - < ngưỡng 1  → mã 1  
    - < ngưỡng 2  → mã 2  
    - ≥ ngưỡng 2 → mã 3  

- **Suy luận hình khối 3D**
  - Dựa vào:
    - Hình 2D từ camera trên (`shape2d_top`)
    - Hình 2D từ camera ngang (`shape2d_side`)
    - Bộ 3 kích thước (L, W, H)
  - Quy tắc:
    - Mặt trên tròn → **trụ tròn**
    - Mặt trên tam giác → **lăng trụ tam giác**
    - Mặt trên vuông/ chữ nhật:
      - Nếu L ≈ W ≈ H → **lập phương**
      - Ngược lại → **hộp chữ nhật**
    - Trường hợp đặc biệt: cam trên vuông & cam ngang vuông → lập phương

- **Giao tiếp PLC (Snap7)**
  - Kết nối đến PLC S7 qua TCP/IP
  - Ghi dữ liệu vào **DB Word / DB Bit**
  - Có **bit Start_From_PC** để bật/tắt chương trình PLC
  - Mã hóa màu, hình 2D, 3D, kích thước, điều kiện vào các **DBW** cấu hình sẵn

- **Giao diện PyQt5**
  - Hiển thị 2 camera (trên, ngang)
  - Nút **BẮT ĐẦU QUÉT**, **DỪNG**, **RESET HỆ THỐNG**
  - Panel thống kê:
    - Số lượng từng **màu**
    - Số lượng từng **hình 2D**
    - Số lượng từng **hình 3D**
  - Panel **điều kiện gửi mã** (ẩn/hiện bằng nút)
    - Chọn màu/hình 2D/hình 3D ứng với mã 1/2/3
    - Chọn điều kiện về **khoảng kích thước** (dài/rộng/cao)
    - Gửi các mã match về PLC (DBW14, DBW16, DBW18)

---

## 2. Cấu trúc dự án

Ví dụ cấu trúc thư mục:

.
├── main.py      # File Python chính: giao diện + xử lý ảnh + PLC
└── README.md

> Đổi tên `main.py` theo ý bạn cho phù hợp với repo.

---

## 3. Yêu cầu hệ thống

- Python 3.8+  
- Thư viện Python:
  - opencv-python
  - numpy
  - python-snap7
  - PyQt5
- Library Snap7 đã cài đặt đúng cho hệ điều hành
- PLC Siemens S7 (ví dụ S7-1200/1500) cấu hình IP phù hợp
- 2 camera USB (hoặc IP camera, nếu sửa lại phần capture)

Cài đặt thư viện (gợi ý):

pip install opencv-python numpy python-snap7 PyQt5

---

## 4. Cấu hình trong mã nguồn

Tất cả cấu hình nằm ở đầu file Python.

### 4.1. PLC

PLC_IP = "192.168.0.1"  # ĐỔI thành IP PLC của bạn
RACK = 0
SLOT = 1

DB_NUMBER = 32          # DB chứa dữ liệu chính

Bit Start/Stop từ máy tính:

PLC_START_DB = 32      # DB chứa bit Start_From_PC
PLC_START_BYTE = 20    # DBX20.0 -> byte 20
PLC_START_BIT = 0      # DBX20.0

Mapping các DB Word:

Ý nghĩa                 | Kiểu | Địa chỉ | Nội dung
Mã màu                 | INT  | DBW0    | 0=NONE,1=VÀNG,2=ĐỎ,3=XANH
Mã hình 2D             | INT  | DBW4    | TAM GIÁC/VUÔNG/CHỮ NHẬT/TRÒN
Mã hình 3D             | INT  | DBW6    | TRỤ TRÒN/LĂNG TRỤ/LẬP PHƯƠNG/HỘP CN
Mã dài (1/2/3)         | INT  | DBW8    | 0=không xác định
Mã rộng (1/2/3)        | INT  | DBW10   |
Mã cao (1/2/3)         | INT  | DBW12   |
Mã theo điều kiện MÀU  | INT  | DBW14   | 0/1/2/3
Mã theo điều kiện 2D   | INT  | DBW16   | 0/1/2/3
Mã theo điều kiện 3D   | INT  | DBW18   | 0/1/2/3

Mã màu:

COLOR_NONE   = 0
COLOR_YELLOW = 1
COLOR_RED    = 2
COLOR_BLUE   = 3

Mã hình 2D:

SHAPE2D_NONE     = 0
SHAPE2D_TRIANGLE = 1
SHAPE2D_SQUARE   = 2
SHAPE2D_RECT     = 3
SHAPE2D_CIRCLE   = 4

Mã hình 3D:

SHAPE3D_NONE      = 0
SHAPE3D_CYLINDER  = 1
SHAPE3D_TRI_PRISM = 2
SHAPE3D_CUBE      = 3
SHAPE3D_RECT_BOX  = 4

### 4.2. Camera & quy đổi kích thước

CAM_INDEX_1 = 1  # Camera trên
CAM_INDEX_2 = 2  # Camera ngang

FRAME_WIDTH  = 350
FRAME_HEIGHT = 350

Nếu camera của bạn có index khác (0, 1, …), sửa lại CAM_INDEX_1, CAM_INDEX_2 cho đúng.

Quy đổi pixel → cm:

CM_PER_PX_TOP  = 0.017  # camera trên: dài & rộng
CM_PER_PX_SIDE = 0.01   # camera ngang: cao

Giá trị này phụ thuộc bố trí camera và khoảng cách tới vật. Bạn cần hiệu chỉnh lại cho đúng kích thước thực.

### 4.3. Ngưỡng kích thước cho mã 1/2/3

LEN_TH1_CM = 3.0
LEN_TH2_CM = 6.0
WID_TH1_CM = 3.0
WID_TH2_CM = 6.0
HEI_TH1_CM = 3.0
HEI_TH2_CM = 6.0

Được dùng trong:

encode_dim_to_code(value_cm, th1, th2)
0: không có/không đo được
1: value < th1
2: th1 <= value < th2
3: value >= th2

---

## 5. Chức năng chính trong mã nguồn

### 5.1. Xử lý màu & hình 2D

- get_limits(color_bgr)
  Tạo khoảng HSV tương ứng với màu BGR (không áp dụng cho đỏ do bị quấn ở Hue 0/180).

- detect_shape(contour)
  Nhận dạng hình dạng 2D từ contour:
  - Tính diện tích, chu vi, độ tròn
  - Nếu tròn → "TRON"
  - Nếu đa giác 3 đỉnh → "TAM GIAC"
  - Nếu 4 đỉnh → phân biệt vuông / chữ nhật bằng aspect ratio
  - Nếu nhiều đỉnh → dùng extent và aspect ratio để phân biệt

- detect_color_and_shape(frame)
  - Chuyển frame sang HSV
  - Tạo mask cho vàng / đỏ (2 dải Hue) / xanh dương
  - Lọc nhiễu và tìm contour hợp lệ theo diện tích
  - Chọn contour lớn nhất → xác định:
    - Màu (color_code)
    - Hình 2D (shape_name)
    - Chiều dài / rộng trong pixel
    - Tâm đối tượng (cx, cy)
  - Vẽ khung lên ảnh và overlay thông tin

### 5.2. Phân loại 3D & mã hóa kích thước

- shape2d_name_to_code(name)
  Chuyển chuỗi "TRON", "VUONG", "TAM GIAC", "CHU NHAT" → mã INT tương ứng.

- classify_3d_shape(shape2d_top, shape2d_side, length_cm, width_cm, height_cm)
  - Nếu thiếu kích thước → SHAPE3D_NONE
  - Nếu hình trên tròn → TRỤ TRÒN
  - Nếu hình trên tam giác → LĂNG TRỤ TAM GIÁC
  - Nếu vuông/ chữ nhật:
    - Nếu L ≈ W ≈ H → LẬP PHƯƠNG
    - Ngược lại → HỘP CHỮ NHẬT

- encode_dim_to_code(value_cm, th1, th2)
  Mã hóa kích thước thành 0/1/2/3 như mô tả ở trên.

### 5.3. Giao tiếp PLC

Các hàm:

- connect_plc()
  Kết nối tới PLC với PLC_IP, RACK, SLOT.

- write_word_plc(addr_byte, value)
  Ghi một word INT vào DB DB_NUMBER tại addr_byte.

- write_db_bool(db_number, byte_index, bit_index, value)
  Ghi 1 bit vào DB.

Hàm tiện ích:
  - plc_set_run(run) – bật/tắt bit Start_From_PC
  - send_color_to_plc(color_code)
  - send_shape2d_to_plc(shape_code)
  - send_shape3d_to_plc(shape3d_code)
  - send_dim_codes_to_plc(len_code, wid_code, hei_code)
  - send_match_color_to_plc(code)
  - send_match_2d_to_plc(code)
  - send_match_3d_to_plc(code)

Khi không kết nối được PLC hoặc xảy ra lỗi ghi, trạng thái sẽ chuyển sang không kết nối và label PLC trên giao diện cập nhật màu đỏ.

### 5.4. Giao diện & luồng hoạt động

Lớp chính: MainWindow(QtWidgets.QMainWindow)

Các nút điều khiển:

- BẮT ĐẦU QUÉT
  - Gọi plc_set_run(True)
  - Khởi động QTimer tạo vòng lặp quét camera
  - Cập nhật label trạng thái: “Đang QUÉT... (PLC RUN)”

- DỪNG
  - Gọi plc_set_run(False)
  - Dừng timer
  - Gửi 0 cho tất cả DBW liên quan (màu, hình 2D/3D, kích thước, match)
  - Cập nhật trạng thái: “ĐÃ DỪNG QUÉT (PLC STOP)”

- RESET HỆ THỐNG
  - Xóa toàn bộ bộ đếm màu/2D/3D
  - Đặt lại kích thước hiện tại = 0
  - Gửi 0 về PLC cho tất cả mã
  - Tắt luôn chương trình PLC (bit Start_From_PC = 0)

- CÀI ĐIỀU KIỆN GỬI MÃ / ẨN ĐIỀU KIỆN GỬI MÃ
  - Ẩn/hiện panel cấu hình điều kiện bên phải:
    - Chọn màu/2D/3D tương ứng với mã 1/2/3
    - Bật/tắt sử dụng từng loại (checkbox)
    - Bật/tắt và cấu hình điều kiện kích thước (L/W/H min/max)

Cơ chế “vật ổn định rồi mới quét”:

- Hàm update_stable_state(has_obj, cx, cy):
  - Nếu không có vật → reset trạng thái ổn định & cho phép quét vật mới (scanned_current_obj = False)
  - Nếu có vật:
    - Tính khoảng cách tâm vật frame hiện tại với frame trước
    - Nếu dịch chuyển < STABLE_MOVE_THRESH_PX trong thời gian ≥ STABLE_TIME_SEC → object_stable = True

- Trong update_frames() (camera 1):
  - Chỉ khi:
    - object_stable == True
    - has_obj_cam1 == True
    - scanned_current_obj == False
  - → mới:
    - Tính kích thước L, W
    - Cập nhật màu, hình 2D, bộ đếm
    - Gửi mã màu, 2D, 3D, kích thước
    - Gọi update_match_condition_and_send()
    - Đánh dấu scanned_current_obj = True (tránh quét lại cùng một vật)
  - Khi vật ra khỏi vùng quét (không còn detect contour) → reset về 0 và gửi 0 về PLC.

Camera 2:

- Cũng dùng detect_color_and_shape, nhưng chỉ quan tâm:
  - Hình 2D từ cam ngang (current_shape2d_cam2_name)
  - Kích thước theo chiều cao:
    height_px = max(length2_px, width2_px)
    height_cm = height_px * CM_PER_PX_SIDE

- Kết hợp với cam 1 để suy luận 3D.

---

## 6. Hướng dẫn sử dụng

1. Chuẩn bị phần cứng
   - Kết nối 2 camera với máy tính.
   - Đảm bảo PLC và PC cùng mạng, ping được tới PLC_IP.
   - Cấu hình DB trong PLC trùng với mapping trong mục 4.1.

2. Cấu hình phần mềm
   - Mở file Python, chỉnh:
     - PLC_IP, RACK, SLOT phù hợp với PLC.
     - CAM_INDEX_1, CAM_INDEX_2 theo thứ tự camera trong hệ thống.
     - Hiệu chỉnh CM_PER_PX_TOP, CM_PER_PX_SIDE theo kết quả đo thực tế.
     - Nếu cần, thay đổi ngưỡng diện tích MIN_AREA, MAX_AREA để phù hợp kích thước vật.

3. Cài đặt thư viện & chạy chương trình

pip install opencv-python numpy python-snap7 PyQt5
python main.py

4. Quy trình vận hành
   - Đặt vật vào vùng nhìn của camera.
   - Đợi vật đứng yên (tâm không di chuyển quá nhiều trong ≥ 1s).
   - Nhấn BẮT ĐẦU QUÉT (hoặc bật từ đầu).
   - Khi vật ổn định, chương trình:
     - Nhận dạng màu, hình 2D, kích thước, hình 3D.
     - Cập nhật các panel thống kê.
     - Gửi mã về PLC:
       - Mã màu / 2D / 3D / kích thước
       - Mã theo điều kiện (nếu điều kiện thỏa)
   - Sau khi vật rời khỏi vùng quét, chương trình gửi lại 0 để báo “không có vật”.
   - Nhấn DỪNG để tắt quét & stop chương trình PLC.
   - Nhấn RESET HỆ THỐNG nếu muốn xóa toàn bộ thống kê và đưa PLC về trạng thái ban đầu.

5. Sử dụng panel điều kiện gửi mã
   - Bấm CÀI ĐIỀU KIỆN GỬI MÃ để hiện panel.
   - Với từng loại:
     - MÀU (DBW14)
     - HÌNH 2D (DBW16)
     - HÌNH 3D (DBW18)
   - Chọn:
     - Màu/hình nào tương ứng với mã 1, 2, 3.
     - Bật/tắt bằng các checkbox Bật mã MÀU, Bật mã 2D, Bật mã 3D.
   - Nếu muốn kết hợp kích thước, bật Bật điều kiện L / W / H:
     - Nhập khoảng min–max cho DÀI / RỘNG / CAO.
     - Chỉ khi L, W, H nằm trong các khoảng này, các mã 1/2/3 mới được gửi.

---

## 7. Mở rộng & tùy biến

Bạn có thể dễ dàng mở rộng dự án:

- Thêm màu mới:
  - Định nghĩa ngưỡng HSV mới.
  - Bổ sung vào danh sách candidates trong detect_color_and_shape.
- Thêm loại hình 2D / 3D mới:
  - Mở rộng logic trong detect_shape và classify_3d_shape.
  - Bổ sung mã mới trong phần enum và mapping DB.
- Thay đổi ngưỡng nhận diện:
  - Chỉnh MIN_AREA, MAX_AREA, STABLE_TIME_SEC, STABLE_MOVE_THRESH_PX để phù hợp với tốc độ băng tải, kích thước vật.
- Tích hợp thêm chức năng PLC:
  - Đọc trạng thái từ PLC (ngã rẽ, cảm biến,…)
  - Điều khiển thêm bit DB/MB theo kết quả quét.

---

## 8. Góp ý & bản quyền

- Bạn có thể sử dụng README này làm mẫu, sửa lại tên dự án, cấu trúc, và license (ví dụ MIT, GPL, …) cho phù hợp với repo GitHub của mình.
- Nếu chia sẻ công khai, nên bổ sung:
  - Ảnh chụp giao diện
  - Sơ đồ nối dây PLC – Camera – PC
  - Ví dụ cấu hình DB trong TIA Portal / Step7.

README này được viết để mô tả mã nguồn hiện có, giải thích luồng xử lý, giao diện, cách sử dụng và giao tiếp PLC, giúp bạn dễ dàng đưa dự án lên GitHub và chia sẻ với người khác.
