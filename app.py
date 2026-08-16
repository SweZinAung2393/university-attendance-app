import streamlit as st
from groq import Groq
import base64
import sqlite3
import pandas as pd
from datetime import datetime
import json
import io

# 1. Page Configuration
st.set_page_config(page_title="Smart Roll Call & Attendance System", layout="wide")

# Groq Client Initialization (Streamlit Secrets မှ API Key ကို ယူမည်)
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# 2. Database Initialization (SQLite) - ဌာန၊ ဘာသာရပ်၊ ဆရာနာမည်များ အပါအဝင်
def init_db():
    conn = sqlite3.connect('attendance_system.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            department_name TEXT,
            subject_name TEXT,
            subject_code TEXT,
            teacher_name TEXT,
            semester TEXT,
            class_name TEXT,
            month_year TEXT,
            roll_no TEXT,
            student_name TEXT,
            total_present INTEGER,
            total_absent INTEGER,
            attendance_percentage REAL,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

st.title("📋 Smart Roll Call & Attendance Management System")
st.write("ဘာသာရပ်၊ ဆရာအမည်နှင့် ကျောင်းသား Roll No များပါဝင်သော Roll Call စာရွက်ပုံကို အလိုအလျောက်ဖတ်ရှု၍ သိမ်းဆည်းခြင်း")

# Sidebar Settings
st.sidebar.header("⚙️ ဆက်တင်များနှင့် စစ်ထုတ်ရန်")
selected_semester = st.sidebar.selectbox("Semester ကို ရွေးပါ", ["First Semester", "Second Semester"])
selected_class = st.sidebar.text_input("အခန်းအမည် (Class/Section)", value="VI CS")
selected_month = st.sidebar.text_input("လနှင့်နှစ် (Month-Year)", value=datetime.now().strftime("%Y-%m"))

# 3. File Uploader for Roll Call Image
uploaded_file = st.file_uploader("Roll Call စာရွက်ပုံကို တင်ပါ (JPG, PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    st.image(uploaded_file, caption="Uploaded Roll Call Form", use_container_width=True)
    
    if st.button("🔍 AI ဖြင့် ဖတ်ရှုပြီး Database သို့ သိမ်းမည်"):
        with st.spinner("စာရွက်ကို စစ်ဆေးပြီး အချက်အလက်များ သိမ်းဆည်းနေပါပြီ..."):
            image_bytes = uploaded_file.getvalue()
            mime_type = uploaded_file.type
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # AI ကို Header အချက်အလက်များနှင့် ကျောင်းသားစာရင်းများကို JSON ဖြင့် တိကျစွာတောင်းမည့် Prompt
            prompt = """
            Analyze this student attendance sheet image carefully.
            Extract the following information from the header:
            - department_name (string)
            - subject_name (string)
            - subject_code (string)
            - teacher_name (string)

            And extract each student's record:
            - roll_no (string, e.g., "VI CS-42")
            - student_name (string)
            - total_present (integer)
            - total_absent (integer)

            Return ONLY a valid JSON object with two keys: "header" (an object containing department_name, subject_name, subject_code, teacher_name) and "students" (an array of student objects). No extra text or markdown ticks.
            """
            
            try:
                response = client.chat.completions.create(
                    model="qwen/qwen3.6-27b",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    temperature=0.1
                )
                
                ai_raw_result = response.choices[0].message.content.strip()
                if ai_raw_result.startswith("```json"):
                    ai_raw_result = ai_raw_result[7:]
                if ai_raw_result.endswith("```"):
                    ai_raw_result = ai_raw_result[:-3]
                
                parsed_data = json.loads(ai_raw_result.strip())
                header = parsed_data.get("header", {})
                students = parsed_data.get("students", [])
                
                # Database ထဲသို့ ထည့်သွင်းခြင်း
                conn = sqlite3.connect('attendance_system.db')
                cursor = conn.cursor()
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                for row in students:
                    p = row.get("total_present", 0)
                    a = row.get("total_absent", 0)
                    total_classes = p + a
                    percentage = (p / total_classes * 100) if total_classes > 0 else 0.0
                    
                    cursor.execute('''
                        INSERT INTO attendance_records 
                        (department_name, subject_name, subject_code, teacher_name, semester, class_name, month_year, roll_no, student_name, total_present, total_absent, attendance_percentage, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        header.get("department_name", "N/A"),
                        header.get("subject_name", "N/A"),
                        header.get("subject_code", "N/A"),
                        header.get("teacher_name", "N/A"),
                        selected_semester,
                        selected_class,
                        selected_month,
                        row.get("roll_no"),
                        row.get("student_name"),
                        p,
                        a,
                        round(percentage, 2),
                        current_time
                    ))
                
                conn.commit()
                conn.close()
                st.success("🎉 ဘာသာရပ်ဆိုင်ရာ အချက်အလက်များနှင့် ကျောင်းသားစာရင်းများကို Database ထဲသို့ အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ!")
                
            except Exception as e:
                st.error(f"Error ဖြစ်ပွားပါသည်: {e}")

# 4. Database Records Viewer & Dashboard Section
st.markdown("---")
st.subheader("📈 Attendance Dashboard နှင့် စာရင်းချုပ်များ")

conn = sqlite3.connect('attendance_system.db')
df = pd.read_sql("SELECT * FROM attendance_records", conn)
conn.close()

if not df.empty:
    col1, col2, col3 = st.columns(3)
    with col1:
        f_class = st.selectbox("အခန်းအလိုက် စစ်ထုတ်ရန်", df['class_name'].unique())
    with col2:
        f_month = st.selectbox("လအလိုက် စစ်ထုတ်ရန်", df['month_year'].unique())
    with col3:
        f_subject = st.selectbox("ဘာသာရပ်အလိုက် စစ်ထုတ်ရန်", df['subject_name'].unique())
    
    filtered_df = df[(df['class_name'] == f_class) & (df['month_year'] == f_month) & (df['subject_name'] == f_subject)]
    
    if not filtered_df.empty:
        # Header Info Display
        first_row = filtered_df.iloc[0]
        st.info(f"📚 **ဌာန:** {first_row['department_name']} | **ဘာသာရပ်:** {first_row['subject_name']} ({first_row['subject_code']}) | **သင်ကြားသည့်ဆရာ/ဆရာမ:** {first_row['teacher_name']}")
        
        # Table Display
        display_cols = ['roll_no', 'student_name', 'total_present', 'total_absent', 'attendance_percentage', 'semester', 'month_year']
        st.dataframe(filtered_df[display_cols], use_container_width=True)
        
        # Excel Export Button
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='Attendance Report')
        excel_data = output.getvalue()
        
        st.download_button(
            label="📥 Excel ဖိုင်ဖြင့် Report ထုတ်ယူရန်",
            data=excel_data,
            file_name=f"Attendance_{first_row['subject_code']}_{f_month}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Warning System for Low Attendance (< 75%)
        low_attendance = filtered_df[filtered_df['attendance_percentage'] < 75]
        if not low_attendance.empty:
            st.warning("⚠️ အောက်ပါကျောင်းသားများသည် ဤဘာသာရပ်တွင် တက်ရောက်မှုနှုန်း 75% အောက် နည်းပါနေပါသည် -")
            st.dataframe(low_attendance[['roll_no', 'student_name', 'attendance_percentage']], use_container_width=True)
    else:
        st.info("ရွေးချယ်ထားသော အချက်အလက်များနှင့် ကိုက်ညီသော စာရင်း မရှိသေးပါ။")
else:
    st.info("လက်ရှိ Database ထဲတွင် သိမ်းဆည်းထား
