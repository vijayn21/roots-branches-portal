import streamlit as st
import pandas as pd

from database import load_sheet_data, save_submission_to_db, save_final_assignments
from utils import (
    generate_class_ids,
    grade_to_int,
    format_grade_display,
    check_day_overlap,
    send_confirmation_email
)
from solver import run_allocation

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
        pointer-events: auto !important; /* Allow interaction with the tooltip */
        overflow-y: auto !important;     /* Enable internal scrolling */
        max-height: 50vh !important;     /* Ensure it doesn't take up the whole screen */
    }
    
    div[data-testid="stTooltipHoverTarget"] {
        pointer-events: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🎒 Roots and Branches Bidding Portal")

tab_parent, tab_admin = st.tabs(["Parent Portal", "Admin Allocation"])

def process_submission(parent_email, student_name_for_lookup, student_name_display, student_grade_input, parent_name, eligible_classes):
    bids_key = f"bids_{student_name_for_lookup}_{student_grade_input}"
    bids_dict = st.session_state.get(bids_key, {})

    bids_summary_lines = save_submission_to_db(
        student_name_for_lookup, 
        student_grade_input, 
        parent_email, 
        student_name_display, 
        parent_name, 
        eligible_classes, 
        bids_dict
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
        - Enter bids for each eligible class shown below (based on the child's grade).
        - If you have previously submitted bids for your student, they will appear and you can modify them.
        - As you allocate points to classes, your current bids are updated (but still not submitted)
        - You can allocate points to however many classes you want, but you will not be assigned more than what is allowed by the program (see "Assignment Method" below)
        - You may bid on classes that overlap. If you win more than 1, your student will be assigned to their highest-bid choice.
    - **Submitting:** Click **Submit / Update Bids** when you are ready to record or update your selections.
        - You can return to this site and modify previous submissions as many times as you want prior to the deadline
        - Latest submissions will overwrite previous ones for the same student and grade.
    - At any time, you can refresh the page to start over. Any previously submitted bids will remain in the system (and can be modified).

    ### Assignment method
    - After the deadline, an algorithm will assign students to classes in descending order of bids to maximize the total bid points across all classes
    - Ties are broken randomly, but no student can win a 2nd tie against a student that hasn't won any ties
    - The algorithm respects the following constraints for each student: 
        - No more than 4 total classes total
        - No more than 3 classes that are not sports, private music, or private language
        - No overlapping classes
    """)
    st.divider()

    st.markdown("### Step 1: Parent/Student Identification")

    step1_done = st.session_state.get("step1_proceeded", False)
    step1_help = "If you wish to edit this information, please start over by refreshing the page." if step1_done else None

    # Retrieve values from session state if step1 is done, otherwise use the widget return values
    if step1_done:
        parent_email = st.session_state.get("saved_parent_email", "").strip().lower()
        student_name_display = st.session_state.get("saved_student_name", "").strip()
        student_name_for_lookup = student_name_display.lower()
        parent_name = st.session_state.get("saved_parent_name", "").strip()
        student_grade_input = st.session_state.get("saved_student_grade", "Select Grade...")
        
        col1, col2 = st.columns(2)
        col1.text_input("Parent Email Address", value=parent_email, disabled=True, help=step1_help, key="input_parent_email")
        col2.text_input("Child's Full Name", value=student_name_display, disabled=True, help=step1_help, key="input_student_name")
        col1.text_input("Parent Full Name", value=parent_name, disabled=True, help=step1_help, key="input_parent_name")
        col2.text_input("Child's Grade", value=str(student_grade_input), disabled=True, help=step1_help, key="input_student_grade")
    else:
        col1, col2 = st.columns(2)
        parent_email = col1.text_input("Parent Email Address").strip().lower()
        student_name_display = col2.text_input("Child's Full Name").strip()
        student_name_for_lookup = student_name_display.lower()
        parent_name = col1.text_input("Parent Full Name").strip()
        grade_options = ["Select Grade...", 'K', 1, 2, 3, 4, 5, 6, 7, 8]
        student_grade_input = col2.selectbox("Child's Grade", options=grade_options, index=0)

    all_fields_populated = bool(
        parent_email
        and student_name_display
        and parent_name
        and student_grade_input in ['K', 1, 2, 3, 4, 5, 6, 7, 8]
    )

    identity_signature = f"{parent_email}|{student_name_for_lookup}|{parent_name}|{student_grade_input}"
    if not step1_done and st.session_state.get("last_confirmed_identity") != identity_signature:
        st.session_state["step1_proceeded"] = False

    if not step1_done:
        if st.button("Proceed to Step 2", type="primary", key="btn_proceed_step2"):
            import re
            email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
            
            if not all_fields_populated:
                st.error("⚠️ Please fill out all 4 fields (Parent Email, Child's Full Name, Parent Full Name, and Child's Grade) to proceed.")
            elif not re.match(email_pattern, parent_email):
                st.error("⚠️ Please enter a valid email address.")
            else:
                st.session_state["step1_proceeded"] = True
                st.session_state["last_confirmed_identity"] = identity_signature
                # Save the values to session state so they persist when inputs are disabled
                st.session_state["saved_parent_email"] = parent_email
                st.session_state["saved_student_name"] = student_name_display
                st.session_state["saved_parent_name"] = parent_name
                st.session_state["saved_student_grade"] = student_grade_input
                st.rerun()

    if step1_done and all_fields_populated:
        student_grade_int = grade_to_int(student_grade_input)
        df_classes_raw = load_sheet_data("Classes")
        df_classes = generate_class_ids(df_classes_raw)
        df_submissions = load_sheet_data("Submissions")

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
          saved_bids = dict(zip(existing_lookup["class_id"].astype(str), existing_lookup["bid_amount"].astype(int)))
        else:
          saved_bids = {}

        st.divider()
        st.markdown("### Step 2: Allocate Bidding Points (Max 100)")

        eligible_classes = df_classes[
            (df_classes["grade_min"] <= student_grade_int)
            & (df_classes["grade_max"] >= student_grade_int)
        ]

        if eligible_classes.empty:
            st.warning("No eligible classes available for this grade level.")
        else:
            bids_key = f"bids_{student_name_for_lookup}_{student_grade_input}"
            if bids_key not in st.session_state:
                st.session_state[bids_key] = {
                    str(c_row["class_id"]): int(saved_bids.get(str(c_row["class_id"]), 0))
                    for _, c_row in eligible_classes.iterrows()
                }
            else:
                for _, c_row in eligible_classes.iterrows():
                    cid = str(c_row["class_id"])
                    if cid not in st.session_state[bids_key]:
                        st.session_state[bids_key][cid] = int(saved_bids.get(cid, 0))

            total_spent = sum(
                st.session_state[bids_key].get(str(cid), 0)
                for cid in eligible_classes["class_id"]
            )
            points_left = 100 - total_spent

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
                        process_submission(parent_email, student_name_for_lookup, student_name_display, student_grade_input, parent_name, eligible_classes)
                    else:
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
                        process_submission(parent_email, student_name_for_lookup, student_name_display, student_grade_input, parent_name, eligible_classes)
                with btn_col2:
                    if st.button("Cancel", key=f"btn_cancel_{student_name_for_lookup}_{student_grade_input}"):
                        st.session_state[confirm_key] = False
                        st.rerun()

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

            col_pts1, col_pts2 = st.columns(2)
            with col_pts1:
                st.metric("Points Used", f"{total_spent} / 100")
            with col_pts2:
                st.metric("Points Remaining", f"{points_left}", delta=None if points_left >= 0 else "Over Budget!")

            if points_left < 0:
                st.error("⚠️ Invalid Bid Allocation: Total points used exceeds 100! Please reduce one or more bid amounts.")

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

            st.markdown("### Class Options")

            filter_day_key = f"filter_day_{student_name_for_lookup}_{student_grade_input}"
            filter_title_key = f"filter_title_{student_name_for_lookup}_{student_grade_input}"
            filter_cost_key = f"filter_cost_{student_name_for_lookup}_{student_grade_input}"

            def reset_filters():
                st.session_state[filter_day_key] = 'All'
                st.session_state[filter_title_key] = 'All'
                st.session_state[filter_cost_key] = 'All'

            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

            all_days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
            selected_day = filter_col1.selectbox('Day of Week', ['All'] + all_days, key=filter_day_key)
            
            distinct_titles = ['All'] + sorted(eligible_classes['title'].unique().tolist())
            selected_title = filter_col2.selectbox('Title', distinct_titles, key=filter_title_key)
            
            distinct_costs = ['All'] + sorted(eligible_classes['cost'].astype(int).unique().tolist())
            selected_cost = filter_col3.selectbox('Cost', distinct_costs, key=filter_cost_key)

            with filter_col4:
                st.markdown("<br>", unsafe_allow_html=True)
                st.button("Remove All Filters", key=f"remove_filters_{student_name_for_lookup}_{student_grade_input}", on_click=reset_filters)

            filtered_classes = eligible_classes.copy()
            if selected_day != 'All':
                filtered_classes = filtered_classes[filtered_classes['day_of_week'].apply(lambda x: check_day_overlap(x, selected_day))]
            if selected_title != 'All':
                filtered_classes = filtered_classes[filtered_classes['title'] == selected_title]
            if selected_cost != 'All':
                filtered_classes = filtered_classes[filtered_classes['cost'] == int(selected_cost)]

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
                            st.markdown(f"**{c_row['title']}**")
                            st.caption(
                                f"📅 **{c_row['day_of_week']}** | "
                                f"⏰ {c_row['start_time']} - {c_row['end_time']} | "
                                f"💵 ${int(c_row['cost'])} | "
                                f"🎓 Grades {grade_display} | "
                                f"👥 Cap: {c_row['capacity']}"
                            )
                            with st.expander("ℹ️ Class Description & Dates"):
                                st.markdown(f"**Dates:** {c_row['dates']}")
                                st.markdown(f"**Description:** {c_row['description']}")
                        with card_col2:
                            st.number_input(
                                f"Bid for {c_row['title']}",
                                min_value=0, max_value=100, step=1,
                                key=num_key,
                                on_change=update_num_bid_state, args=(cid, num_key),
                                label_visibility="collapsed"
                            )
                        st.markdown("---")


# ==========================================
# TAB 2: ADMIN ALLOCATION SOLVER
# ==========================================
with tab_admin:
    st.markdown("### Admin Controls")
    admin_password = st.text_input("Admin Password", type="password", key="admin_password_input")

    try:
        expected_password = st.secrets.get("ADMIN_PASSWORD", "admin123")
    except Exception:
        expected_password = "admin123"

    if admin_password == expected_password:
        st.success("Admin Authenticated.")

        if st.button("Run Allocation Algorithm", type="primary", key="run_allocation_button"):
            df_classes_raw = load_sheet_data("Classes")
            df_classes = generate_class_ids(df_classes_raw)
            df_subs = load_sheet_data("Submissions")

            if df_subs.empty:
                st.error("No submissions found to allocate.")
            else:
                df_out = run_allocation(df_classes, df_subs)
                save_final_assignments(df_out)

                st.success("🎉 Allocation run complete! Results written to 'Final_Assignments' sheet.")
                st.dataframe(df_out)
