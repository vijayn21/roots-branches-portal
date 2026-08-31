import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
GHSEET_NAME = 'Roots and Branch Portal DB'

@st.cache_resource
def get_gspread_client():
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES
        )
    else:
        creds = Credentials.from_service_account_file(
            "service_account.json", scopes=SCOPES
        )
    return gspread.authorize(creds)

@st.cache_data(ttl=3600, show_spinner=False)
def load_sheet_data(tab_name):
    gc = get_gspread_client()
    sheet = gc.open(GHSEET_NAME).worksheet(tab_name)
    records = sheet.get_all_records()
    df = pd.DataFrame(records)

    if tab_name == 'Submissions' and (df.empty or 'parent_email' not in df.columns):
        return pd.DataFrame(
            columns=[
                'parent_email',
                'student_name',
                'student_grade',
                'parent_name',
                'class_id',
                'bid_amount',
                'updated_at',
            ]
        )
    if tab_name == 'Final_Assignments' and (df.empty or 'class_id' not in df.columns):
        return pd.DataFrame(
            columns=[
                'student_name',
                'parent_name',
                'parent_email',
                'class_id',
                'class_title',
                'day_of_week',
                'start_time',
                'end_time',
                'dates',
                'cost',
            ]
        )
    return df

def save_submission_to_db(student_name_for_lookup, student_grade_input, parent_email, student_name_display, parent_name, eligible_classes, bids_dict):
    gc = get_gspread_client()
    sheet = gc.open(GHSEET_NAME).worksheet("Submissions")

    all_rows = sheet.get_all_records()
    filtered_rows = [
        r for r in all_rows
        if not (
            str(r["student_name"]).strip().lower() == student_name_for_lookup
            and str(r["student_grade"]).strip() == str(student_grade_input).strip()
        )
    ]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    bids_summary_lines = []

    for _, c_row in eligible_classes.iterrows():
        cid = str(c_row["class_id"])
        bid_val = bids_dict.get(cid, 0)
        if bid_val > 0:
            filtered_rows.append({
                "parent_email": parent_email,
                "student_name": student_name_display,
                "student_grade": student_grade_input,
                "parent_name": parent_name,
                "class_id": cid,
                "bid_amount": bid_val,
                "updated_at": now,
            })
            bids_summary_lines.append(f"- {c_row['title']}: {bid_val} points")

    sheet.clear()
    if filtered_rows:
        df_new = pd.DataFrame(filtered_rows)
        sheet.update([df_new.columns.values.tolist()] + df_new.values.tolist())
        
    return bids_summary_lines

def save_final_assignments(df_out):
    gc = get_gspread_client()
    sheet_out = gc.open(GHSEET_NAME).worksheet("Final_Assignments")
    sheet_out.clear()
    sheet_out.update([df_out.columns.values.tolist()] + df_out.values.tolist())
