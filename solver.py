import pandas as pd
from pulp import LpMaximize, LpMinimize, LpProblem, LpVariable, lpSum
from utils import check_day_overlap, check_time_overlap

def run_allocation(df_classes, df_subs):
    students = df_subs["student_name"].str.lower().unique().tolist()
    activities = df_classes["class_id"].tolist()
    capacities = dict(zip(df_classes["class_id"], df_classes["capacity"].astype(int)))
    class_counts_toward_max = dict(zip(df_classes['class_id'], df_classes['counts_toward_max'].astype(int)))

    private_music_class_ids = df_classes[df_classes['title'].str.contains('private music', case=False, na=False)]['class_id'].tolist()
    private_language_class_ids = df_classes[df_classes['title'].str.contains('private language', case=False, na=False)]['class_id'].tolist()

    overlaps = []
    for i, row1 in df_classes.iterrows():
        for j, row2 in df_classes.iterrows():
            if i < j:
                if check_day_overlap(row1["day_of_week"], row2["day_of_week"]):
                    if check_time_overlap(row1["start_time"], row1["end_time"], row2["start_time"], row2["end_time"]):
                        overlaps.append((row1["class_id"], row2["class_id"]))

    bids = {s: {a: 0 for a in activities} for s in students}
    for _, row in df_subs.iterrows():
        bids[row["student_name"].lower()][row["class_id"]] = int(row["bid_amount"])

    # STAGE 1: Maximize Satisfaction
    prob1 = LpProblem("Stage1_MaximizeBids", LpMaximize)
    x1 = {(s, a): LpVariable(f"x1_{s}_{a}", cat="Binary") for s in students for a in activities}
    prob1 += lpSum(bids[s][a] * x1[s, a] for s in students for a in activities)

    for a in activities:
        prob1 += (lpSum(x1[s, a] for s in students) <= capacities[a])
        
    for s in students:
        prob1 += lpSum(x1[s, a] for a in activities) <= 4
        prob1 += lpSum(x1[s, a] for a in activities if class_counts_toward_max.get(a, 0) == 1) <= 3
        if private_music_class_ids:
            prob1 += lpSum(x1[s, a] for a in activities if a in private_music_class_ids) <= 1
        if private_language_class_ids:
            prob1 += lpSum(x1[s, a] for a in activities if a in private_language_class_ids) <= 1
        for a1, a2 in overlaps:
            prob1 += x1[s, a1] + x1[s, a2] <= 1

    prob1.solve()
    max_bids = prob1.objective.value()

    # STAGE 2: Fair Tie-Breaking
    is_tied = {}
    for a in activities:
        allocated_students = [s for s in students if x1[s, a].varValue > 0.99]
        alloc_bids = [bids[s][a] for s in allocated_students]

        if alloc_bids and len(allocated_students) == capacities[a]:
            cutoff = min(alloc_bids)
            contenders = sum(1 for s_all in students if bids[s_all][a] >= cutoff)
            overdemanded = contenders > capacities[a]
            for s_all in students:
                is_tied[s_all, a] = 1 if (overdemanded and bids[s_all][a] == cutoff) else 0
        else:
            for s_all in students:
                is_tied[s_all, a] = 0

    prob2 = LpProblem("Stage2_BalanceTiebreakers", LpMinimize)
    x2 = {(s, a): LpVariable(f"x2_{s}_{a}", cat="Binary") for s in students for a in activities}
    max_tie_wins = LpVariable("max_tie_wins", lowBound=0, cat="Integer")

    prob2 += (lpSum(bids[s][a] * x2[s, a] for s in students for a in activities) == max_bids)

    for a in activities:
        prob2 += (lpSum(x2[s, a] for s in students) <= capacities[a])
        
    for s in students:
        prob2 += lpSum(x2[s, a] for a in activities) <= 4
        prob2 += lpSum(x2[s, a] for a in activities if class_counts_toward_max.get(a, 0) == 1) <= 3
        if private_music_class_ids:
            prob2 += lpSum(x2[s, a] for a in activities if a in private_music_class_ids) <= 1
        if private_language_class_ids:
            prob2 += lpSum(x2[s, a] for a in activities if a in private_language_class_ids) <= 1
        for a1, a2 in overlaps:
            prob2 += x2[s, a1] + x2[s, a2] <= 1
        prob2 += (lpSum(is_tied[s, a] * x2[s, a] for a in activities) <= max_tie_wins)

    prob2 += max_tie_wins
    prob2.solve()

    assignments = []
    for s in students:
        student_info = df_subs[df_subs["student_name"].str.lower() == s].iloc[0]
        for a in activities:
            if x2[s, a].varValue == 1:
                class_info = df_classes[df_classes["class_id"] == a].iloc[0]
                assignments.append({
                    "student_name": student_info["student_name"],
                    "parent_name": student_info["parent_name"],
                    "parent_email": student_info["parent_email"],
                    "class_id": a,
                    "class_title": class_info["title"],
                    "day_of_week": class_info["day_of_week"],
                    "start_time": class_info["start_time"],
                    "end_time": class_info["end_time"],
                    "dates": class_info["dates"],
                    "cost": class_info["cost"],
                })

    return pd.DataFrame(assignments)
