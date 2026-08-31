import streamlit as st

from datetime import datetime
import os
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from pulp import LpMaximize, LpMinimize, LpProblem, LpVariable, lpSum
import smtplib
from email.message import EmailMessage
import streamlit as st

# ==========================================
# GOOGLE SHEETS AUTHENTICATION
# ==========================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
GHSEET_NAME = 'Roots and Branch Portal DB'
ADMIN_PW = "admin123"

@st.cache_resource
def get_gspread_client():
    # Load credentials from Streamlit Secrets or local file
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=SCOPES
        )
    else:
        creds = Credentials.from_service_account_file(
            "service_account.json", scopes=SCOPES
        )
    return gspread.authorize(creds)


@st.cache_data(ttl=3600, show_spinner=False) # Cache data for 1 hour
def load_sheet_data(tab_name):
  gc = get_gspread_client()
  sheet = gc.open(GHSEET_NAME).worksheet(tab_name)
  records = sheet.get_all_records()

  df = pd.DataFrame(records)

  # Fallback column structure if sheet is currently empty
  if tab_name == 'Submissions' and (
      df.empty or 'parent_email' not in df.columns
  ):
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

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def parse_time(time_str):
    # Handle cases like 'N/A' or empty strings if they might appear
    if isinstance(time_str, str) and time_str.strip() != 'N/A' and time_str.strip() != '':
        return datetime.strptime(time_str, '%I:%M %p').time()
    return None # Or raise an error, depending on desired behavior

def check_time_overlap(start1_str, end1_str, start2_str, end2_str):
    start1 = parse_time(start1_str)
    end1 = parse_time(end1_str)
    start2 = parse_time(start2_str)
    end2 = parse_time(end2_str)

    if start1 is None or end1 is None or start2 is None or end2 is None:
        return False # Cannot determine overlap if times are invalid

    # Check if the time ranges overlap: (start1 < end2) and (start2 < end1)
    return (start1 < end2) and (start2 < end1)

def check_day_overlap(days1_str, days2_str):
    if not isinstance(days1_str, str) or not isinstance(days2_str, str):
        return False # Cannot parse if not strings
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

def generate_class_ids(df_classes_raw):
    df_temp = df_classes_raw.copy()

    df_temp['is_multi_day'] = df_temp['day_of_week'].str.contains(',', na=False)

    df_temp['first_day'] = df_temp['day_of_week'].apply(
        lambda x: x.split(',')[0].strip() if isinstance(x, str) and x.strip() else ''
    )

    day_order = {'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6, 'Sun': 7, '': 8}
    df_temp['day_order_val'] = df_temp['first_day'].map(day_order).fillna(8)

    # Sort logic: single-day first, then by day, then by title
    df_temp = df_temp.sort_values(by=['is_multi_day', 'day_order_val', 'title']).reset_index(drop=True)

    df_temp['class_id'] = ['C' + str(i + 1) for i in range(len(df_temp))]

    df_temp = df_temp.drop(columns=['is_multi_day', 'first_day', 'day_order_val'])
    return df_temp

# ==========================================
# PAGE CONFIGURATION & NAVIGATION
# ==========================================
st.set_page_config(
    page_title="Roots and Branches Bidding",
    page_icon="🎒",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Ensure tooltips wrap and don't get cut off on mobile portrait */
    div[data-testid="stTooltipContent"] {
        max-width: 85vw !important;
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🎒 Roots and Branches Bidding Portal")

tab_parent, tab_admin = st.tabs(["Parent Portal", "Admin Allocation"])

# Submission Handler Function (moved outside the main conditional block)
def process_submission(parent_email, student_name_for_lookup, student_name_display, student_grade_input, parent_name, eligible_classes):
    gc = get_gspread_client()
    sheet = gc.open(GHSEET_NAME).worksheet("Submissions")

    # Remove existing bids for this student matching student_name and student_grade
    all_rows = sheet.get_all_records()
    filtered_rows = [
        r
        for r in all_rows
        if not (
            str(r["student_name"]).strip().lower() == student_name_for_lookup
            and str(r["student_grade"]).strip() == str(student_grade_input).strip()
        )
    ]

    # Append new bids by checking session state for all eligible classes
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    bids_key = f"bids_{student_name_for_lookup}_{student_grade_input}"
    bids_dict = st.session_state.get(bids_key, {})

    bids_summary_lines = []

    # Iterate over ALL eligible classes to get their bids from persistent state
    for _, c_row in eligible_classes.iterrows():
        cid = str(c_row["class_id"])
        bid_val = bids_dict.get(cid, 0)

        if bid_val > 0:
            filtered_rows.append(
                {
                    "parent_email": parent_email,
                    "student_name": student_name_display, # Use display name for submission
                    "student_grade": student_grade_input, # Store 'K' if applicable
                    "parent_name": parent_name,
                    "class_id": cid,
                    "bid_amount": bid_val,
                    "updated_at": now,
                }
            )
            bids_summary_lines.append(f"- {c_row['title']}: {bid_val} points")

    # Overwrite sheet data
    sheet.clear()
    if filtered_rows:
        df_new = pd.DataFrame(filtered_rows)
        sheet.update(
            [df_new.columns.values.tolist()]
            + df_new.values.tolist()
        )
    st.cache_data.clear()
    submitted_flag_key = f"has_submitted_{student_name_for_lookup}_{student_grade_input}"
    st.session_state[submitted_flag_key] = True
    
    if bids_summary_lines:
        bids_summary_text = "\n".join(bids_summary_lines)
        send_confirmation_email(parent_email, student_name_display, bids_summary_text)
        
    st.success(f"✅ Bids successfully recorded for {student_name_display}!\n\nA confirmation email has been sent to **{parent_email}**.")
    st.balloons()


# ==========================================
# TAB 1: PARENT PORTAL
# ==========================================
with tab_parent:
    st.markdown("""
    ### Instructions
    - **Step 1:** Enter parent and student identification details, then click **Proceed to Step 2**
        - Your student is uniquely identified by their name (case insensitive) and grade - please check that you have entered these correctly.
    - **Step 2:** You have **100 points** to allocate across classes.
        - Your child's eligible classes (based on grade) will be displayed below, where you can enter a bid for each class.
        - If you have previously submitted bids for your student, they will appear and you can modify them.
        - As you allocate points to classes, your current bids are displayed at the top (but still not submitted).
        - You can allocate points to however many classes you want, but you will not be assigned more than what is allowed by the program (see "Assignment Method" below).
        - You may bid on classes that overlap. If you win more than 1, your student will be assigned to their highest-bid choice.
    - **Submitting:** Click **Submit / Update Bids** when you are ready to record or update your selections.
        - You can return to this site and modify previous submissions as many times as you want prior to the deadline.
        - Latest submissions will overwrite previous ones for the same student and grade.
    - At any time, you can refresh the page to start over. Any previously submitted bids will remain in the system (and can be modified).

    ### Assignment method
    - After the deadline, an algorithm will assign students to classes in descending order of bids to maximize the total bid points across all classes.
    - Ties are broken randomly, but no student can win a 2nd tie against a student that hasn't won any ties.
    - The algorithm respects the following constraints for each student: 
        - No more than 4 total classes total
        - No more than 3 classes that are not sports, private music, or private language
        - No overlapping classes
    """)
    st.divider()

    st.markdown("### Step 1: Parent/Student Identification")

    col1, col2 = st.columns(2)
    parent_email = (
        col1.text_input("Parent Email Address").strip().lower()
    )
    student_name_display = col2.text_input("Child's Full Name").strip() # Store for display
    student_name_for_lookup = student_name_display.lower() # For internal logic

    parent_name = col1.text_input("Parent Full Name").strip()

    # Updated student grade options with an empty default placeholder
    grade_options = ["Select Grade...", 'K', 1, 2, 3, 4, 5, 6, 7, 8]
    student_grade_input = col2.selectbox(
        "Child's Grade", options=grade_options, index=0
    )

    # Validation check for all 4 Step 1 fields
    all_fields_populated = bool(
        parent_email
        and student_name_display
        and parent_name
        and student_grade_input in ['K', 1, 2, 3, 4, 5, 6, 7, 8]
    )

    identity_signature = f"{parent_email}|{student_name_for_lookup}|{parent_name}|{student_grade_input}"
    if st.session_state.get("last_confirmed_identity") != identity_signature:
        st.session_state["step1_proceeded"] = False

    if not st.session_state.get("step1_proceeded", False):
        if st.button("Proceed to Step 2", type="primary", key="btn_proceed_step2"):
            if not all_fields_populated:
                st.error("⚠️ Please fill out all 4 fields (Parent Email, Child's Full Name, Parent Full Name, and Child's Grade) to proceed.")
            else:
                st.session_state["step1_proceeded"] = True
                st.session_state["last_confirmed_identity"] = identity_signature
                st.rerun()

    if st.session_state.get("step1_proceeded", False) and all_fields_populated:
        student_grade_int = grade_to_int(student_grade_input)
        df_classes_raw = load_sheet_data("Classes")
        df_classes = generate_class_ids(df_classes_raw) # Generate class_id here
        df_submissions = load_sheet_data("Submissions")

        # Safe lookup that won't crash if df_submissions is empty
        if (
            not df_submissions.empty
            and "student_name" in df_submissions.columns
            and "student_grade" in df_submissions.columns
        ):
          existing_lookup = df_submissions[
              (df_submissions["student_name"].astype(str).str.lower() == student_name_for_lookup)
              & (df_submissions["student_grade"].astype(str) == str(student_grade_input))
          ]
        else:
          existing_lookup = pd.DataFrame()

        if not existing_lookup.empty:
          st.info(
              f"ℹ️ Existing submission found for **{student_name_display}**. Modifying your"
              " entries below will overwrite previous bids."
          )
          saved_bids = dict(
              zip(
                  existing_lookup["class_id"].astype(str),
                  existing_lookup["bid_amount"].astype(int),
              )
          )
        else:
          saved_bids = {}

        st.divider()
        st.markdown("### Step 2: Allocate Bidding Points (Max 100)")

        # Filter classes by grade eligibility using student_grade_int
        eligible_classes = df_classes[
            (df_classes["grade_min"] <= student_grade_int)
            & (df_classes["grade_max"] >= student_grade_int)
        ]

        if eligible_classes.empty:
            st.warning("No eligible classes available for this grade level.")
        else:
            # Persistent bids dictionary in session state across filtering
            bids_key = f"bids_{student_name_for_lookup}_{student_grade_input}"
            if bids_key not in st.session_state:
                st.session_state[bids_key] = {
                    str(c_row["class_id"]): int(saved_bids.get(str(c_row["class_id"]), 0))
                    for _, c_row in eligible_classes.iterrows()
                }
            else:
                # Sync any newly loaded or uninitialized class_id into bids_key
                for _, c_row in eligible_classes.iterrows():
                    cid = str(c_row["class_id"])
                    if cid not in st.session_state[bids_key]:
                        st.session_state[bids_key][cid] = int(saved_bids.get(cid, 0))

            # Calculate total points spent based on ALL eligible classes
            total_spent = sum(
                st.session_state[bids_key].get(str(cid), 0)
                for cid in eligible_classes["class_id"]
            )
            points_left = 100 - total_spent

            # Action Buttons Area: Submit & Clear
            col_actions1, col_actions2 = st.columns([0.5, 0.5])

            confirm_key = f"confirm_mode_{student_name_for_lookup}_{student_grade_input}"
            if confirm_key not in st.session_state:
                st.session_state[confirm_key] = False

            confirm_clear_key = f"confirm_clear_mode_{student_name_for_lookup}_{student_grade_input}"
            if confirm_clear_key not in st.session_state:
                st.session_state[confirm_clear_key] = False

            with col_actions1:
                if st.button("Submit / Update Bids", type="primary", key=f"submit_bids_{student_name_for_lookup}_{student_grade_input}"):
                    if points_left < 0:
                        st.error("Invalid Bids: Please adjust your entries so total points do not exceed 100.")
                        st.session_state[confirm_key] = False
                    elif points_left == 0:
                        st.session_state[confirm_key] = False
                        process_submission(
                            parent_email,
                            student_name_for_lookup,
                            student_name_display,
                            student_grade_input,
                            parent_name,
                            eligible_classes,
                        )
                    else: # points_left > 0
                        st.session_state[confirm_key] = True

            with col_actions2:
                if st.button("Clear Current Bids", key=f"clear_bids_{student_name_for_lookup}_{student_grade_input}"):
                    st.session_state[confirm_clear_key] = True

            if st.session_state.get(confirm_clear_key, False):
                st.warning("⚠️ This would clear tentative bids made during this session. It would not affect previously submitted bids.")
                clear_col1, clear_col2 = st.columns(2)
                with clear_col1:
                    if st.button("Yes, Clear Current Bids", type="primary", key=f"btn_confirm_clear_{student_name_for_lookup}_{student_grade_input}"):
                        st.session_state[confirm_clear_key] = False
                        # Reset all tentative bids in session state to 0
                        st.session_state[bids_key] = {
                            str(c_row["class_id"]): 0 for _, c_row in eligible_classes.iterrows()
                        }
                        for _, c_row in eligible_classes.iterrows():
                            cid = str(c_row["class_id"])
                            num_key = f"bid_{student_name_for_lookup}_{student_grade_input}_{cid}"
                            st.session_state[num_key] = 0
                        st.rerun()
                with clear_col2:
                    if st.button("Cancel", key=f"btn_cancel_clear_{student_name_for_lookup}_{student_grade_input}"):
                        st.session_state[confirm_clear_key] = False
                        st.rerun()

            if st.session_state.get(confirm_key, False):
                st.warning(f"⚠️ You have **{points_left} points remaining** out of 100. Unallocated points will not be used in course placement. Are you sure you want to submit?")
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("Confirm Submission", type="primary", key=f"btn_confirm_{student_name_for_lookup}_{student_grade_input}"):
                        st.session_state[confirm_key] = False
                        process_submission(
                            parent_email,
                            student_name_for_lookup,
                            student_name_display,
                            student_grade_input,
                            parent_name,
                            eligible_classes,
                        )
                with btn_col2:
                    if st.button("Cancel", key=f"btn_cancel_{student_name_for_lookup}_{student_grade_input}"):
                        st.session_state[confirm_key] = False
                        st.rerun()

            # Display summary of non-zero bids
            submitted_flag_key = f"has_submitted_{student_name_for_lookup}_{student_grade_input}"
            has_newly_submitted = st.session_state.get(submitted_flag_key, False)
            has_previously_submitted = not existing_lookup.empty

            if has_newly_submitted:
                bids_header = "### Your Newly Submitted Bids"
            elif has_previously_submitted:
                bids_header = "### Your Previously Submitted Bids"
            else:
                bids_header = "### Your Current Bids (unsubmitted)"

            st.markdown(bids_header)

            # Display Points Used and Points Remaining metrics directly under Bids section header
            col_pts1, col_pts2 = st.columns(2)
            with col_pts1:
                st.metric("Points Used", f"{total_spent} / 100")
            with col_pts2:
                st.metric(
                    "Points Remaining",
                    f"{points_left}",
                    delta=None if points_left >= 0 else "Over Budget!",
                )

            if points_left < 0:
                st.error("⚠️ Invalid Bid Allocation: Total points used exceeds 100! Please reduce one or more bid amounts.")

            # Filter non-zero bids for read-only summary
            summary_rows = []
            for _, c_row in eligible_classes.iterrows():
                cid = str(c_row["class_id"])
                bid_val = st.session_state[bids_key].get(cid, 0)
                if bid_val > 0:
                    summary_rows.append(c_row)

            if summary_rows:
                for s_row in summary_rows:
                    cid = str(s_row["class_id"])
                    bid_val = st.session_state[bids_key].get(cid, 0)
                    g_disp = format_grade_display(s_row["grade_min"], s_row["grade_max"])
                    tooltip_text = f"Dates: {s_row['dates']}\n\nDescription: {s_row['description']}"

                    st.markdown(
                        f"- **{s_row['title']}**: **{bid_val} points** | "
                        f"Days: {s_row['day_of_week']} | Time: {s_row['start_time']} - {s_row['end_time']} | "
                        f"Cost: ${int(s_row['cost'])} | Grades: {g_disp}",
                        help=tooltip_text,
                    )
            else:
                st.info("No bids entered yet.")
            st.divider()

            # Add filters
            st.markdown("### Class Options")

            filter_day_key = f"filter_day_{student_name_for_lookup}_{student_grade_input}"
            filter_title_key = f"filter_title_{student_name_for_lookup}_{student_grade_input}"
            filter_cost_key = f"filter_cost_{student_name_for_lookup}_{student_grade_input}"

            def reset_filters():
                st.session_state[filter_day_key] = 'All'
                st.session_state[filter_title_key] = 'All'
                st.session_state[filter_cost_key] = 'All'

            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

            # Day of Week Filter (Mon-Fri only)
            all_days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
            selected_day = filter_col1.selectbox(
                'Day of Week',
                ['All'] + all_days,
                key=filter_day_key
            )

            # Title Filter (Dropdown)
            distinct_titles = ['All'] + sorted(eligible_classes['title'].unique().tolist())
            selected_title = filter_col2.selectbox(
                'Title',
                distinct_titles,
                key=filter_title_key
            )

            # Cost Filter (Dropdown of distinct costs)
            distinct_costs = ['All'] + sorted(eligible_classes['cost'].astype(int).unique().tolist())
            selected_cost = filter_col3.selectbox(
                'Cost',
                distinct_costs,
                key=filter_cost_key
            )

            # Remove All Filters Button
            with filter_col4:
                st.markdown("<br>", unsafe_allow_html=True) # Add some space to align
                st.button(
                    "Remove All Filters",
                    key=f"remove_filters_{student_name_for_lookup}_{student_grade_input}",
                    on_click=reset_filters
                )

            # Apply filters
            filtered_classes = eligible_classes.copy()

            if selected_day != 'All':
                filtered_classes = filtered_classes[
                    filtered_classes['day_of_week'].apply(lambda x: check_day_overlap(x, selected_day))
                ]

            if selected_title != 'All':
                filtered_classes = filtered_classes[
                    filtered_classes['title'] == selected_title
                ]

            if selected_cost != 'All':
                filtered_classes = filtered_classes[
                    filtered_classes['cost'] == int(selected_cost)
                ]

            if filtered_classes.empty:
                st.info("No classes match your filter criteria.")
            else:
                def update_num_bid_state(c_id, num_k):
                    new_val = int(st.session_state[num_k])
                    st.session_state[bids_key][c_id] = new_val

                for _, c_row in filtered_classes.iterrows():
                    cid = str(c_row["class_id"])
                    num_key = f"bid_{student_name_for_lookup}_{student_grade_input}_{cid}"

                    grade_display = format_grade_display(c_row['grade_min'], c_row['grade_max'])
                    tooltip_text = f"Dates: {c_row['dates']}\n\nDescription: {c_row['description']}"

                    current_val = int(st.session_state[bids_key].get(cid, 0))
                    st.session_state[num_key] = current_val

                    with st.container():
                        card_col1, card_col2 = st.columns([0.7, 0.3])
                        with card_col1:
                            st.markdown(f"**{c_row['title']}**", help=tooltip_text)
                            st.caption(
                                f"📅 **{c_row['day_of_week']}** | "
                                f"⏰ {c_row['start_time']} - {c_row['end_time']} | "
                                f"💵 ${int(c_row['cost'])} | "
                                f"🎓 Grades {grade_display} | "
                                f"👥 Cap: {c_row['capacity']}"
                            )
                        with card_col2:
                            st.number_input(
                                f"Bid for {c_row['title']}",
                                min_value=0,
                                max_value=100,
                                step=1,
                                key=num_key,
                                on_change=update_num_bid_state,
                                args=(cid, num_key),
                                label_visibility="collapsed"
                            )
                        st.markdown("---")


# ==========================================
# TAB 2: ADMIN ALLOCATION SOLVER
# ==========================================
with tab_admin:
    st.markdown("### Admin Controls")
    admin_password = st.text_input("Admin Password", type="password", key="admin_password_input")

    # New safe check:
    try:
        expected_password = st.secrets.get("ADMIN_PASSWORD", ADMIN_PW)
    except Exception:
        expected_password = ADMIN_PW

    if admin_password == expected_password:
        st.success("Admin Authenticated.")

        if st.button("Run Allocation Algorithm", type="primary", key="run_allocation_button"):
            df_classes_raw = load_sheet_data("Classes")
            df_classes = generate_class_ids(df_classes_raw) # Generate class_id here
            df_subs = load_sheet_data("Submissions")

            if df_subs.empty:
                st.error("No submissions found to allocate.")
            else:
                # Prepare Solver Sets
                students = df_subs["student_name"].str.lower().unique().tolist() # MODIFIED: Lowercase student names for consistency
                activities = df_classes["class_id"].tolist()
                capacities = dict(
                    zip(df_classes["class_id"], df_classes["capacity"].astype(int)) # Ensure capacity is int
                )
                class_counts_toward_max = dict(zip(df_classes['class_id'], df_classes['counts_toward_max'].astype(int)))

                private_music_class_ids = df_classes[
                    df_classes['title'].str.contains('private music', case=False, na=False)
                ]['class_id'].tolist()

                private_language_class_ids = df_classes[
                    df_classes['title'].str.contains('private language', case=False, na=False)
                ]['class_id'].tolist()

                # Map Overlaps (Same Day & Time Slot - UPDATED LOGIC)
                overlaps = []
                for i, row1 in df_classes.iterrows():
                    for j, row2 in df_classes.iterrows():
                        if i < j: # Avoid duplicate pairs and self-comparison
                            # Check for day overlap first (day_of_week is comma-separated)
                            if check_day_overlap(row1["day_of_week"], row2["day_of_week"]):
                                # If days overlap, check for time overlap using start_time and end_time
                                if check_time_overlap(row1["start_time"], row1["end_time"], row2["start_time"], row2["end_time"]):
                                    overlaps.append(
                                        (row1["class_id"], row2["class_id"])
                                    )

                # Build Bid Matrix
                bids = {s: {a: 0 for a in activities} for s in students}
                for _, row in df_subs.iterrows():
                    # Ensure student_name is lowercased for consistency with bids dict keys
                    bids[row["student_name"].lower()][row["class_id"]] = int(
                        row["bid_amount"]
                    )

                # --- STAGE 1: Maximize Satisfaction ---
                prob1 = LpProblem("Stage1_MaximizeBids", LpMaximize)
                x1 = {
                    (s, a): LpVariable(f"x1_{s}_{a}", cat="Binary")
                    for s in students
                    for a in activities
                }

                prob1 += lpSum(
                    bids[s][a] * x1[s, a] for s in students for a in activities
                )

                for a in activities:
                    prob1 += (
                        lpSum(x1[s, a] for s in students) <= capacities[a]
                    )
                for s in students:
                    # Constraint 2: Each student can have no more than 4 total class assignments
                    prob1 += lpSum(x1[s, a] for a in activities) <= 4

                    # Constraint 1: For classes with counts_toward_max == 1, each student can have at most 3
                    prob1 += lpSum(x1[s, a] for a in activities if class_counts_toward_max.get(a, 0) == 1) <= 3

                    # New Constraint: No more than one private music class
                    if private_music_class_ids:
                        prob1 += lpSum(x1[s, a] for a in activities if a in private_music_class_ids) <= 1

                    # New Constraint: No more than one private language class
                    if private_language_class_ids:
                        prob1 += lpSum(x1[s, a] for a in activities if a in private_language_class_ids) <= 1

                    for a1, a2 in overlaps:
                        prob1 += x1[s, a1] + x1[s, a2] <= 1  # Conflict constraint

                prob1.solve()
                max_bids = prob1.objective.value()

                # --- STAGE 2: Fair Tie-Breaking ---
                # Determine contested cutoff bids
                is_tied = {}
                for a in activities:
                    # Filter by where x1[s, a].varValue is effectively 1 (accounting for float precision)
                    allocated_students = [s for s in students if x1[s, a].varValue > 0.99]
                    alloc_bids = [bids[s][a] for s in allocated_students]

                    if alloc_bids and len(allocated_students) == capacities[a]:
                        # Find the minimum bid among allocated students for this activity
                        cutoff = min(alloc_bids)

                        # Count how many students bid >= cutoff (potential contenders)
                        contenders = sum(1 for s_all in students if bids[s_all][a] >= cutoff)

                        # Check if overdemanded (more contenders than capacity at cutoff)
                        overdemanded = contenders > capacities[a]

                        for s_all in students:
                            is_tied[s_all, a] = (
                                1
                                if (overdemanded and bids[s_all][a] == cutoff)
                                else 0
                            )
                    else:
                        for s_all in students:
                            is_tied[s_all, a] = 0

                prob2 = LpProblem("Stage2_BalanceTiebreakers", LpMinimize)
                x2 = {
                    (s, a): LpVariable(f"x2_{s}_{a}", cat="Binary")
                    for s in students
                    for a in activities
                }
                max_tie_wins = LpVariable(
                    "max_tie_wins", lowBound=0, cat="Integer"
                )

                prob2 += (
                    lpSum(
                        bids[s][a] * x2[s, a]
                        for s in students
                        for a in activities
                    )
                    == max_bids
                )

                for a in activities:
                    prob2 += (
                        lpSum(x2[s, a] for s in students) <= capacities[a]
                    )
                for s in students:
                    # Constraint 2: Each student can have no more than 4 total class assignments
                    prob2 += lpSum(x2[s, a] for a in activities) <= 4

                    # Constraint 1: For classes with counts_toward_max == 1, each student can have at most 3
                    prob2 += lpSum(x2[s, a] for a in activities if class_counts_toward_max.get(a, 0) == 1) <= 3

                    # New Constraint: No more than one private music class
                    if private_music_class_ids:
                        prob2 += lpSum(x2[s, a] for a in activities if a in private_music_class_ids) <= 1

                    # New Constraint: No more than one private language class
                    if private_language_class_ids:
                        prob2 += lpSum(x2[s, a] for a in activities if a in private_language_class_ids) <= 1

                    for a1, a2 in overlaps:
                        prob2 += x2[s, a1] + x2[s, a2] <= 1
                    prob2 += (
                        lpSum(is_tied[s, a] * x2[s, a] for a in activities)
                        <= max_tie_wins
                    )

                prob2 += max_tie_wins
                prob2.solve()

                # --- SAVE RESULTS ---
                assignments = []
                for s in students:
                    # Find the first submission row for this student to get parent_name, parent_email
                    student_info = df_subs[
                        df_subs["student_name"].str.lower() == s # Use lowercased student name for lookup
                    ].iloc[0]
                    for a in activities:
                        if x2[s, a].varValue == 1:
                            class_info = df_classes[
                                df_classes["class_id"] == a
                            ].iloc[0]
                            assignments.append(
                                {
                                    "student_name": student_info["student_name"], # Use original casing from submission
                                    "parent_name": student_info["parent_name"],
                                    "parent_email": student_info[
                                        "parent_email"
                                    ],
                                    "class_id": a,
                                    "class_title": class_info["title"],
                                    "day_of_week": class_info["day_of_week"],
                                    "start_time": class_info["start_time"],
                                    "end_time": class_info["end_time"],
                                    "dates": class_info["dates"],
                                    "cost": class_info["cost"],
                                }
                            )

                df_out = pd.DataFrame(assignments)
                gc = get_gspread_client()
                sheet_out = gc.open(GHSEET_NAME).worksheet(
                    "Final_Assignments"
                )
                sheet_out.clear()
                sheet_out.update(
                    [df_out.columns.values.tolist()] + df_out.values.tolist()
                )

                st.success(
                    "🎉 Allocation run complete! Results written to 'Final_Assignments' sheet."
                )
                st.dataframe(df_out)
