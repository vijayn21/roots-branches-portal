import pandas as pd
from datetime import datetime
import smtplib
from email.message import EmailMessage
import streamlit as st

def parse_time(time_str):
    if isinstance(time_str, str) and time_str.strip() != 'N/A' and time_str.strip() != '':
        return datetime.strptime(time_str, '%I:%M %p').time()
    return None

def check_time_overlap(start1_str, end1_str, start2_str, end2_str):
    start1 = parse_time(start1_str)
    end1 = parse_time(end1_str)
    start2 = parse_time(start2_str)
    end2 = parse_time(end2_str)

    if start1 is None or end1 is None or start2 is None or end2 is None:
        return False 

    return (start1 < end2) and (start2 < end1)

def check_day_overlap(days1_str, days2_str):
    if not isinstance(days1_str, str) or not isinstance(days2_str, str):
        return False
    days1 = set(day.strip() for day in days1_str.split(',') if day.strip())
    days2 = set(day.strip() for day in days2_str.split(',') if day.strip())
    return bool(days1.intersection(days2))

def grade_to_int(grade_str_or_int):
    if grade_str_or_int == 'K':
        return 0
    return int(grade_str_or_int)

def format_grade_display(min_grade, max_grade):
    min_display = 'K' if min_grade == 0 else str(int(min_grade))
    max_display = 'K' if max_grade == 0 else str(int(max_grade))
    if min_grade == max_grade:
        return min_display
    return f"{min_display}-{max_display}"

def generate_class_ids(df_classes_raw):
    df_temp = df_classes_raw.copy()
    df_temp['is_multi_day'] = df_temp['day_of_week'].str.contains(',', na=False)
    df_temp['first_day'] = df_temp['day_of_week'].apply(
        lambda x: x.split(',')[0].strip() if isinstance(x, str) and x.strip() else ''
    )
    day_order = {'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6, 'Sun': 7, '': 8}
    df_temp['day_order_val'] = df_temp['first_day'].map(day_order).fillna(8)
    df_temp = df_temp.sort_values(by=['is_multi_day', 'day_order_val', 'title']).reset_index(drop=True)
    df_temp['class_id'] = ['C' + str(i + 1) for i in range(len(df_temp))]
    df_temp = df_temp.drop(columns=['is_multi_day', 'first_day', 'day_order_val'])
    return df_temp

def send_confirmation_email(recipient_email, student_name, bids_summary_text):
    sender_email = st.secrets.get("EMAIL_ADDRESS")
    sender_password = st.secrets.get("EMAIL_PASSWORD")
    
    if not sender_email or not sender_password:
        print("Email secrets not found. Skipping confirmation email.")
        return

    msg = EmailMessage()
    msg['Subject'] = f'Roots and Branches Bidding Confirmation for {student_name}'
    msg['From'] = sender_email
    msg['To'] = recipient_email

    body = f"Hello,\n\nThank you for submitting your bids for {student_name}.\n\n"
    body += "Here is a summary of your currently recorded bids:\n\n"
    body += bids_summary_text
    body += "\n\nYou can return to the portal at any time before the deadline to update these bids."
    body += "\n\nBest,\nRoots and Branches Team"

    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send confirmation email: {e}")
