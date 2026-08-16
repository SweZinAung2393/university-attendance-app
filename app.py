import streamlit as st
from groq import Groq
import base64
import sqlite3
import pandas as pd
from datetime import datetime
import json
import io

st.set_page_config(page_title="Smart Roll Call & Attendance System", layout="wide")

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

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

st.title("Smart Roll Call & Attendance Management System")
st.write("ဘာသာရပ်၊ ဆရာအမည်နှင့် ကျောင်းသား Roll No များပါဝင်သော Roll Call စာရွက်ပုံကို အလိုအလျောက်ဖတ်ရှု၍ သိမ်းဆည်းခြင်း")

st.sidebar.header("Settings & Filters")
selected_semester = st.sidebar.selectbox("Select Semester", ["First Semester", "Second Semester"])
selected_class = st.sidebar.text_input("Class/Section", value="VI CS")
selected_month = st.sidebar.text_input("Month-Year", value=datetime.now().strftime("%Y-%m"))

uploaded_file = st.file_uploader("Upload Roll Call Form (JPG, PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file:
    st.image(uploaded_file, caption="Uploaded Roll Call Form", use_container_width=True)
    
    if st.button("AI Attendance ဖတ်မည်"):
        with st.spinner("Processing image and extracting data..."):
            image_bytes = uploaded_file.getvalue()
            mime_type = uploaded_file.type
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            prompt = """
            Analyze this student attendance sheet image carefully.
            Extract the following information from the header:
            - department_name (string)
            - subject_name (string)
            - subject_code (string)
            - teacher_name (string)

            And extract each student's record:
            - roll_no (string)
            - student_name (string)
            - total_present (integer)
            - total_absent (integer)

            Return ONLY a valid JSON object with two keys: "header" and "students". No extra text or markdown ticks.
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
                st.success("Successfully saved to Database!")
                
            except Exception as e:
                st.error(f"Error occurred: {e}")

st.markdown("---")
st.subheader("Attendance Dashboard")

conn = sqlite3.connect('attendance_system.db')
df = pd.read_sql("SELECT * FROM attendance_records", conn)
conn.close()

if not df.empty:
    col1, col2, col3 = st.columns(3)
    with col1:
        f_class = st.selectbox("Filter Class", df['class_name'].unique())
    with col2:
        f_month = st.selectbox("Filter Month", df['month_year'].unique())
    with col3:
        f_subject = st.selectbox("Filter Subject", df['subject_name'].unique())
    
    filtered_df = df[(df['class_name'] == f_class) & (df['month_year'] == f_month) & (df['subject_name'] == f_subject)]
    
    if not filtered_df.empty:
        first_row = filtered_df.iloc[0]
        st.info(f"Department: {first_row['department_name']} | Subject: {first_row['subject_name']} ({first_row['subject_code']}) | Teacher: {first_row['teacher_name']}")
        
        display_cols = ['roll_no', 'student_name', 'total_present', 'total_absent', 'attendance_percentage', 'semester', 'month_year']
        st.dataframe(filtered_df[display_cols], use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            filtered_df.to_excel(writer, index=False, sheet_name='Report')
        excel_data = output.getvalue()
        
        st.download_button(
            label="Download Excel Report",
            data=excel_data,
            file_name=f"Attendance_{first_row['subject_code']}_{f_month}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        low_attendance = filtered_df[filtered_df['attendance_percentage'] < 75]
        if not low_attendance.empty:
            st.warning("Students with attendance below 75%:")
            st.dataframe(low_attendance[['roll_no', 'student_name', 'attendance_percentage']], use_container_width=True)
    else:
        st.info("No records found for selected filters.")
else:
    st.info("No data in Database yet.")
