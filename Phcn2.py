from datetime import datetime
from google import genai
import sqlite3
import streamlit as st

# --- CƠ SỞ DỮ LIỆU SQLITE ---
DB_NAME = "phcn_clinical.db"


def init_db():
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  # Bảng Bệnh nhân
  c.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            age INTEGER,
            gender TEXT,
            phone TEXT,
            address TEXT,
            created_at TEXT
        )
    """)
  # Bảng Lượng giá & Hồ sơ khám (lưu kết quả từ Gemini hoặc chẩn đoán sẵn)
  c.execute("""
        CREATE TABLE IF NOT EXISTS clinical_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            exam_date TEXT,
            region TEXT,
            symptoms TEXT,
            red_flags TEXT,
            test_results TEXT,
            gemini_response TEXT,
            FOREIGN KEY (patient_id) REFERENCES patients (id)
        )
    """)
  conn.commit()
  conn.close()


init_db()

# --- DỮ LIỆU ĐỀ XUẤT NGHIỆM PHÁP & CỜ ĐỎ ---
RED_FLAGS_DATA = {
    "Cột sống thắt lưng": [
        "Đau ngực/bụng dữ dội lan ra sau lưng (nghi ngờ phình tách động mạch chủ)",
        (
            "Hội chứng chùm đuôi ngựa (bí tiểu, tiểu không tự chủ, mất cảm giác"
            " vùng yên ngựa)"
        ),
        "Sụt cân không rõ nguyên nhân, sốt, tiền sử ung thư",
        "Yếu cơ tiến triển nhanh (liệt vận động rõ rệt)",
        "Đau tăng nhiều về đêm, không giảm khi nghỉ ngơi",
    ],
    "Cột sống cổ": [
        (
            "Dấu hiệu tủy sống (rối loạn thăng bằng, tê yếu cả 2 tay và 2 chân,"
            " phản xạ bệnh lý tháp)"
        ),
        "Đau đầu dữ dội đột ngột, chóng mặt kèm rối loạn vận nhãn",
        "Sốt, cứng cổ rõ kèm dấu hiệu màng não",
        "Tiền sử chấn thương năng lực cao",
    ],
    "Vai": [
        "Đau vai dữ dội kèm sốt, sưng nóng đỏ khớp (nghi ngờ viêm khớp nhiễm khuẩn)",
        "Mất cơ lực đột ngột hoàn toàn sau chấn thương (nghi đứt gân cơ chóp xoay diện rộng)",
        "Đau lan tỏa kèm tê buốt ngực hoặc tay trái (loại trừ bệnh lý tim mạch)",
    ],
    "Khớp gối": [
        "Gối sưng to đột ngột, tràn dịch máu cấp sau chấn thương",
        "Khóa khớp cơ học (không thể duỗi hoặc gập gối hoàn toàn)",
        "Sốt cao kèm sưng nóng đỏ một bên khớp gối",
    ],
}

TESTS_DATA = {
    "Cột sống thắt lưng": [
        {
            "name": "Nghiệm pháp Lasegue (Straight Leg Raise - SLR)",
            "purpose": (
                "Đánh giá rễ thần kinh bị chèn ép (L4-S1) / căng rễ thần kinh"
            ),
            "instruction": (
                "Bệnh nhân nằm ngửa, chân duỗi thẳng. Người khám nâng chân"
                " bệnh nhân lên từ từ khi gối thẳng cho đến khi đau hoặc hạn"
                " chế."
            ),
            "positive": (
                "Đau chói lan xuống mặt sau chân theo góc dưới 60 độ (gợi ý"
                " chèn ép rễ)."
            ),
        },
        {
            "name": "Nghiệm pháp Bragard",
            "purpose": "Xác định thêm tổn thương rễ thần kinh khi Lasegue dương tính",
            "instruction": (
                "Từ vị trí Lasegue dương tính, hạ chân xuống một chút cho hết"
                " đau, sau đó thực hiện gập cổ chân tối đa (dorsiflexion)."
            ),
            "positive": "Làm xuất hiện lại cơn đau lan xuống chân.",
        },
        {
            "name": "Nghiệm pháp Schober",
            "purpose": "Đánh giá độ linh hoạt và biên độ vận động cột sống thắt lưng",
            "instruction": (
                "Đánh dấu mốc gai sau L5, đo lên trên 10cm. Yêu cầu bệnh nhân cúi"
                " người tối đa không gối, đo khoảng cách mới."
            ),
            "positive": "Khoảng cách tăng dưới 5cm (giảm độ linh hoạt).",
        },
    ],
    "Cột sống cổ": [
        {
            "name": "Nghiệm pháp ép đỉnh (Spurling Test)",
            "purpose": "Đánh giá hội chứng rễ thần kinh cổ do chèn ép lỗ tiếp hợp",
            "instruction": "Bệnh nhân ngồi, nghiêng và quay đầu về bên đau, người khám ấn nhẹ lực dọc trục từ trên xuống.",
            "positive": "Đau lan tỏa xuống bả vai hoặc tay cùng bên.",
        }
    ],
    "Vai": [
        {
            "name": "Nghiệm pháp Neer",
            "purpose": "Đánh giá hội chứng chèn ép khoang dưới mỏm cùng vai",
            "instruction": "Người khám cố định xương bả vai, chủ động nâng cánh tay bệnh nhân lên ở tư thế xoay trong.",
            "positive": "Đau chói ở vùng trước ngoài vai khi tay đưa lên cao.",
        }
    ],
    "Khớp gối": [
        {
            "name": "Nghiệm pháp bập bềnh xương bánh chè",
            "purpose": "Đánh giá dịch tràn trong ổ khớp gối",
            "instruction": "Dùng tay ép hai bên túi cùng cơ tứ đầu đùi, tay kia ấn xương bánh chè xuống.",
            "positive": "Xương bánh chè có cảm giác chạm vào mặt xương đùi (bập bềnh).",
        }
    ],
}

# --- KHO CHẨN ĐOÁN LÂM SÀNG SẴN CÓ & BÀI TẬP PHCN ---
BUILTIN_CLINICAL_DATA = {
    "Cột sống thắt lưng": {
        "diagnosis": (
            "• **Nhận định sơ bộ:** Hội chứng thắt lưng cấp / Thoái hóa cột"
            " sống thắt lưng / Nghi ngờ chèn ép rễ thần kinh.\n• **Cơ chế"
            " tổn thương:** Căng cơ cạnh sống, mất vững phân đoạn hoặc quá"
            " tải đĩa đệm vùng L4-S1."
        ),
        "exercises": [
            (
                "1. **Kéo giãn nhóm cơ dựng sống (Knees-to-chest):** Nằm ngửa,"
                " ôm gối sát ngực nhẹ nhàng để giảm áp lực cột sống."
            ),
            (
                "2. **Bài tập rắn hổ mang (Cobra stretch):** Nằm sấp, chống tay"
                " nâng nửa thân trên lên từ từ (nếu hợp cơ chế đĩa đệm)."
            ),
            (
                "3. **Ổn định cơ lõi (Core stability):** Tập gồng cơ bụng tĩnh"
                " để bảo vệ vùng thắt lưng khi vận động."
            ),
        ],
    },
    "Cột sống cổ": {
        "diagnosis": (
            "• **Nhận định sơ bộ:** Hội chứng cổ - vai - gáy / Căng cơ vùng cổ"
            " cấp / Thoái hóa đốt sống cổ.\n• **Cơ chế tổn thương:** Co thắt"
            " cơ thang trên, cơ ức đòn chũm do sai tư thế hoặc lạnh."
        ),
        "exercises": [
            (
                "1. **Kéo giãn cơ thang trên:** Nghiêng đầu sang bên đối diện,"
                " dùng tay kéo nhẹ nhàng giữ 15-20 giây."
            ),
            (
                "2. **Thu cằm (Chin tucks):** Kéo cằm thẳng ra sau tạo cằm đôi"
                " để giảm áp lực đốt sống cổ trên."
            ),
            (
                "3. **Vận động chủ động:** Xoay, nghiêng cổ biên độ nhẹ nhàng"
                " trong giới hạn không đau."
            ),
        ],
    },
    "Vai": {
        "diagnosis": (
            "• **Nhận định sơ bộ:** Viêm gân cơ chóp xoay / Hội chứng chèn ép"
            " khoang dưới mỏm cùng vai.\n• **Cơ chế tổn thương:** Viêm hoặc"
            " kẹt gân cơ trên gai khi dạng tay."
        ),
        "exercises": [
            (
                "1. **Con lắc Codman:** Thả lỏng vai, dùng lực thân mình đu đưa"
                " tay theo vòng tròn nhỏ."
            ),
            (
                "2. **Kéo giãn bao khớp sau:** Kéo tay đau bắt chéo qua ngực"
                " sang bên đối diện."
            ),
            (
                "3. **Tăng cường cơ chóp xoay:** Tập với dây kháng lực nhẹ khi"
                " đã giảm đau cấp."
            ),
        ],
    },
    "Khớp gối": {
        "diagnosis": (
            "• **Nhận định sơ bộ:** Thoái hóa khớp gối / Hội chứng bánh chè -"
            " đùi / Quá tải gân bánh chè.\n• **Cơ chế tổn thương:** Mất cân"
            " bằng lực cơ tứ đầu đùi hoặc tổn thương sụn khớp."
        ),
        "exercises": [
            (
                "1. **Gồng cơ tứ đầu đùi tĩnh:** Nằm duỗi thẳng chân, gồng cơ đùi"
                " ép sát khoeo xuống mặt giường (giữ 5-10 giây)."
            ),
            (
                "2. **Nâng chân thẳng (Straight leg raise):** Nâng chân cách"
                " mặt giường 20cm, giữ thẳng gối để mạnh cơ đùi trước."
            ),
            (
                "3. **Gập duỗi gối chủ động không tải:** Ngồi mép ghế đá chân"
                " nhẹ nhàng."
            ),
        ],
    },
}

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(
    page_title="Trợ lý Lâm sàng PHCN & Gemini", page_icon="🩺", layout="wide"
)

st.title("🩺 Trợ lý Lâm sàng PHCN tích hợp Gemini AI")
st.markdown(
    "Quản lý hồ sơ, chẩn đoán lâm sàng có sẵn, đề xuất bài tập PHCN và phân tích"
    " nâng cao qua AI."
)

# --- SIDEBAR: CẤU HÌNH API KEY ---
st.sidebar.header("⚙️ Cấu hình hệ thống")
api_key_input = st.sidebar.text_input(
    "Google Gemini API Key", type="password", help="Nhập API Key để kết nối AI"
)

menu = st.sidebar.selectbox(
    "Chọn chức năng",
    [
        "Quản lý Bệnh nhân",
        "Khám & Lượng giá Lâm sàng",
        "Theo dõi Tiến triển",
        "Sao lưu / Khôi phục Dữ liệu",
    ],
)

# --- CHỨC NĂNG 1: QUẢN LÝ BỆNH NHÂN ---
if menu == "Quản lý Bệnh nhân":
  st.header("👤 Quản lý Hồ sơ Bệnh nhân")

  with st.form("patient_form"):
    col1, col2 = st.columns(2)
    with col1:
      name = st.text_input("Họ và tên bệnh nhân")
      age = st.number_input("Tuổi", min_value=1, max_value=120, value=30)
      gender = st.selectbox("Giới tính", ["Nam", "Nữ", "Khác"])
    with col2:
      phone = st.text_input("Số điện thoại")
      address = st.text_input("Địa chỉ")

    submitted = st.form_submit_button("Tạo hồ sơ mới")
    if submitted:
      if name:
        code = f"BN{datetime.now().strftime('%Y%m%d%H%M%S')}"
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO patients (code, name, age, gender, phone, address,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, name, age, gender, phone, address, created_at),
        )
        conn.commit()
        conn.close()
        st.success(
            f"Đã tạo thành công hồ sơ cho bệnh nhân: **{name}** (Mã: {code})"
        )
      else:
        st.warning("Vui lòng nhập tên bệnh nhân!")

  st.markdown("---")
  st.subheader("Danh sách bệnh nhân đã lưu")
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute("SELECT code, name, age, gender, phone, created_at FROM patients")
  rows = c.fetchall()
  conn.close()

  if rows:
    for r in rows:
      st.write(
          f"🔹 **Mã:** {r[0]} | **Họ tên:** {r[1]} | **Tuổi:** {r[2]} | **Giới"
          f" tính:** {r[3]} | **SĐT:** {r[4]} | **Ngày tạo:** {r[5]}"
      )
  else:
    st.info("Chưa có bệnh nhân nào trong cơ sở dữ liệu.")

# --- CHỨC NĂNG 2: KHÁM & LƯỢNG GIÁ LÂM SÀNG ---
elif menu == "Khám & Lượng giá Lâm sàng":
  st.header("📋 Khám, Sàng lọc & Chẩn đoán Lâm sàng")

  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute("SELECT id, code, name FROM patients")
  patients = c.fetchall()
  conn.close()

  if not patients:
    st.warning("Vui lòng tạo hồ sơ bệnh nhân trước khi tiến hành khám.")
  else:
    patient_dict = {f"{p[1]} - {p[2]}": p[0] for p in patients}
    selected_p = st.selectbox("Chọn bệnh nhân", list(patient_dict.keys()))
    patient_id = patient_dict[selected_p]

    region = st.selectbox(
        "Vùng cơ thể cần lượng giá",
        ["Cột sống thắt lưng", "Cột sống cổ", "Vai", "Khớp gối"],
    )

    st.markdown("### 1. Khai thác triệu chứng")
    symptoms = st.text_area(
        "Mô tả triệu chứng (Vị trí đau, tính chất, thời gian, hướng lan...)"
    )

    st.markdown("### 2. Sàng lọc dấu hiệu cờ đỏ (Red Flags)")
    red_flags_list = RED_FLAGS_DATA.get(
        region, [f"Dấu hiệu bất thường tại {region}"]
    )
    selected_red_flags = []
    for rf in red_flags_list:
      if st.checkbox(rf, key=rf):
        selected_red_flags.append(rf)

    if selected_red_flags:
      st.error(
          "⚠️ **CẢNH BÁO CỜ ĐỎ:** Phát hiện dấu hiệu nguy hiểm cần lưu ý khi đánh"
          " giá."
      )

    st.markdown("### 3. Nghiệm pháp lâm sàng")
    suggested_tests = TESTS_DATA.get(region, [])
    test_results_dict = {}
    if suggested_tests:
      for test in suggested_tests:
        with st.expander(f"🧪 {test['name']}"):
          st.write(f"**Mục đích:** {test['purpose']}")
          st.write(f"**Cách thực hiện:** {test['instruction']}")
          st.write(f"**Tiêu chuẩn dương tính:** {test['positive']}")
          res = st.radio(
              f"Kết quả cho {test['name']}",
              ["Chưa thực hiện", "Âm tính (-)", "Dương tính (+)"],
              key=test["name"],
          )
          test_results_dict[test["name"]] = res
    else:
      st.info("Đang cập nhật thêm nghiệm pháp cho vùng này.")

    # --- 4. HIỂN THỊ CHẨN ĐOÁN LÂM SÀNG & BÀI TẬP CÓ SẴN (OFFLINE) ---
    st.markdown("---")
    st.markdown("### 🩺 4. Chẩn đoán lâm sàng & Bài tập PHCN (Có sẵn)")
    builtin_info = BUILTIN_CLINICAL_DATA.get(region, {})

    st.markdown(
        f"**Nhận định chẩn đoán sơ bộ tại vùng {region}:**\n\n"
        f"{builtin_info.get('diagnosis', 'Đang cập nhật...')}"
    )

    st.markdown("**Đề xuất bài tập PHCN tiêu chuẩn:**")
    for ex in builtin_info.get("exercises", []):
      st.write(f"- {ex}")

    # --- 5. XỬ LÝ & PHÂN TÍCH QUA GEMINI AI (TÙY CHỌN) ---
    st.markdown("---")
    st.markdown("### 🤖 5. Phân tích chuyên sâu bổ sung qua Gemini AI")
    gemini_output = ""

    # Tạo prompt chuẩn
    generated_prompt = f"""Dưới góc độ chuyên gia Vật lý trị liệu và Phục hồi chức năng (PHCN), hãy tiếp nhận bộ dữ liệu khám lâm sàng sau đây và đưa ra đánh giá chuyên sâu:
- Vùng khảo sát: {region}
- Triệu chứng ghi nhận: {symptoms if symptoms else 'Chưa mô tả'}
- Dấu hiệu cờ đỏ (Red flags): {', '.join(selected_red_flags) if selected_red_flags else 'Không ghi nhận'}
- Kết quả nghiệm pháp: {str(test_results_dict)}

Yêu cầu phân tích:
1. Nhận định nguyên nhân cấu trúc/cơ học tiềm ẩn.
2. Đánh giá mức độ an toàn và cảnh báo cần thiết.
3. Đề xuất hướng can thiệp PHCN phù hợp."""

    if st.button("🚀 Gửi dữ liệu sang Gemini phân tích thêm"):
      if not api_key_input:
        st.error("Vui lòng nhập Google Gemini API Key ở thanh bên trái.")
      elif not symptoms:
        st.warning("Vui lòng nhập mô tả triệu chứng.")
      else:
        with st.spinner("Đang đẩy dữ liệu sang Gemini AI..."):
          try:
            client = genai.Client(api_key=api_key_input)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=generated_prompt,
            )
            gemini_output = response.text
            st.success("Nhận kết quả từ Gemini thành công!")
          except Exception as e:
            st.error(f"Lỗi kết nối Gemini API: {e}")

    with st.expander("📋 Hoặc bấm vào đây để lấy Prompt copy thủ công sang Gemini"):
      st.info(
          "Bạn có thể sao chép đoạn nội dung dưới đây và dán trực tiếp vào"
          " ứng dụng Gemini:"
      )
      st.code(generated_prompt, language="text")

    if gemini_output:
      st.markdown("#### 🤖 Phản hồi mở rộng từ Gemini:")
      st.markdown(gemini_output)

        if st.button("Lưu hồ sơ khám & Kết quả vào cơ sở dữ liệu"):
      exam_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      rf_str = ", ".join(selected_red_flags)
      tr_str = str(test_results_dict)

      ai_text = gemini_output if gemini_output else "Chỉ dùng chẩn đoán sẵn có."
      combined_response = (
          "[Chẩn đoán sẵn có]\n"
          + builtin_info.get("diagnosis", "")
          + "\n\n[AI Response]\n"
          + ai_text
      )

      conn = sqlite3.connect(DB_NAME)
      c = conn.cursor()
      c.execute(
          """
                INSERT INTO clinical_records (patient_id, exam_date, region, symptoms, red_flags, test_results, gemini_response)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
          (
              patient_id,
              exam_date,
              region,
              symptoms,
              rf_str,
              tr_str,
              combined_response,
          ),
      )
      conn.commit()
      conn.close()
      st.success("Đã lưu toàn bộ hồ sơ khám và hướng dẫn PHCN vào cơ sở dữ liệu!")


# --- CHỨC NĂNG 3: THEO DÕI TIẾN TRIỂN ---
elif menu == "Theo dõi Tiến triển":
  st.header("📈 Lịch sử Khám & Đánh giá Lâm sàng")

  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute("SELECT id, code, name FROM patients")
  patients = c.fetchall()
  conn.close()

  if not patients:
    st.info("Chưa có dữ liệu bệnh nhân.")
  else:
    patient_dict = {f"{p[1]} - {p[2]}": p[0] for p in patients}
    selected_p = st.selectbox(
        "Chọn bệnh nhân xem lịch sử", list(patient_dict.keys())
    )
    patient_id = patient_dict[selected_p]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """
            SELECT exam_date, region, symptoms, red_flags, test_results, gemini_response
            FROM clinical_records WHERE patient_id = ?
        """,
        (patient_id,),
    )
    records = c.fetchall()
    conn.close()

    if records:
      for idx, rec in enumerate(records, 1):
        st.markdown(f"### Lần khám #{idx} - Ngày: {rec[0]}")
        st.write(f"**Vùng lượng giá:** {rec[1]}")
        st.write(f"**Triệu chứng:** {rec[2]}")
        st.write(f"**Cờ đỏ:** {rec[3] if rec[3] else 'Không có'}")
        st.write(f"**Nghiệm pháp:** {rec[4]}")
        if rec[5]:
          st.markdown(f"**Chi tiết chẩn đoán & Hướng dẫn PHCN:**\n{rec[5]}")
        st.markdown("---")
    else:
      st.info("Bệnh nhân này chưa có bản ghi nào.")

# --- CHỨC NĂNG 4: SAO LƯU / KHÔI PHỤC ---
elif menu == "Sao lưu / Khôi phục Dữ liệu":
  st.header("💾 Sao lưu và Khôi phục Cơ sở dữ liệu SQLite")
  st.write(
      "Bạn có thể tải xuống tệp `phcn_clinical.db` để lưu trữ dữ liệu an toàn."
  )
  with open(DB_NAME, "rb") as f:
    st.download_button(
        label="Tải xuống tệp cơ sở dữ liệu (.db)",
        data=f,
        file_name="phcn_clinical.db",
        mime="application/octet-stream",
    )
