import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import sqlite3
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.title("Insurance Executive Analytics Dashboard")

# =========================================================
# DATABASE CONNECTION
# =========================================================
conn = sqlite3.connect("insurance.db", check_same_thread=False)
cursor = conn.cursor()

# =========================================================
# DATABASE CONTROL
# =========================================================
st.sidebar.subheader("Database Control")

if st.sidebar.button("Clear All Data"):
    cursor.execute("DROP TABLE IF EXISTS claims")
    conn.commit()
    st.sidebar.success("Database Cleared")
    st.rerun()

# =========================================================
# FILE UPLOAD
# =========================================================
uploaded_file = st.file_uploader("Upload Monthly Excel File", type=["xlsx"])

if uploaded_file:
    df_upload = pd.read_excel(uploaded_file)
    df_upload.columns = df_upload.columns.str.strip()

    for col in ["Requested Amount", "Accepted Amount"]:
        df_upload[col] = (
            df_upload[col]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.replace(" ", "", regex=False)
        )
        df_upload[col] = pd.to_numeric(df_upload[col], errors="coerce")

    df_upload = df_upload.drop_duplicates()
    df_upload.to_sql("claims", conn, if_exists="append", index=False)
    st.success("Data uploaded successfully")

# =========================================================
# LOAD DATA
# =========================================================
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='claims'")
if not cursor.fetchone():
    st.warning("Upload first file")
    st.stop()

df = pd.read_sql("SELECT * FROM claims", conn)

if df.empty:
    st.warning("Database empty")
    st.stop()

df = df.drop_duplicates()

for col in ["Requested Amount", "Accepted Amount"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

if "Accident Date" in df.columns:
    df["Accident Date"] = pd.to_datetime(df["Accident Date"], errors="coerce")

# =========================================================
# FILTERS
# =========================================================
st.sidebar.subheader("Filters (Optional)")

filter_cols = ["Month","Approval Type","Claim Form Type","Client Name","Treatment Doctor"]

for col in filter_cols:
    df[col] = df[col].astype(str).str.strip()

if st.sidebar.button("Reset Filters"):
    for col in filter_cols:
        st.session_state[col] = []
    st.rerun()

filtered_df = df.copy()

for col in filter_cols:
    options = sorted(df[col].dropna().unique())
    selected = st.sidebar.multiselect(col, options, key=col)
    if selected:
        filtered_df = filtered_df[filtered_df[col].isin(selected)]

# =========================================================
# ACCOUNTING FORMAT
# =========================================================
def acc(x):
    if pd.isna(x):
        return "-"
    return f"{x:,.0f}"

# =========================================================
# KPIs
# =========================================================
total_requested = filtered_df["Requested Amount"].sum()
total_accepted = filtered_df["Accepted Amount"].sum()
claims_count = len(filtered_df)
unique_members = filtered_df["Insured Card No"].nunique()

avg_cost_per_claim = total_requested / claims_count if claims_count else 0
avg_cost_per_member = total_requested / unique_members if unique_members else 0
approval_rate = (total_accepted / total_requested * 100) if total_requested else 0

# MoM Growth %
mom_growth = 0
if "Accident Date" in filtered_df.columns:
    temp = filtered_df.copy()
    temp["YearMonth"] = temp["Accident Date"].dt.to_period("M")
    monthly = temp.groupby("YearMonth")["Accepted Amount"].sum().sort_index()
    if len(monthly) > 1:
        mom_growth = ((monthly.iloc[-1] - monthly.iloc[-2]) / monthly.iloc[-2]) * 100

col1, col2, col3 = st.columns(3)
col1.metric("Total Requested", acc(total_requested))
col2.metric("Total Accepted", acc(total_accepted))
col3.metric("Claims Count", claims_count)

col4, col5, col6 = st.columns(3)
col4.metric("Avg Cost per Claim", acc(avg_cost_per_claim))
col5.metric("Avg Cost per Member", acc(avg_cost_per_member))
col6.metric("Approval Rate %", f"{approval_rate:.2f}%")

st.metric("MoM Growth % (Accepted)", f"{mom_growth:.2f}%")

st.markdown("---")

# =========================================================
# CHARTS
# =========================================================
st.subheader("Requested vs Accepted - Approval Type")

approval_comp = (
    filtered_df.groupby("Approval Type")[["Requested Amount","Accepted Amount"]]
    .sum()
    .reset_index()
)

fig1 = go.Figure()
fig1.add_bar(x=approval_comp["Approval Type"], y=approval_comp["Requested Amount"], name="Requested")
fig1.add_bar(x=approval_comp["Approval Type"], y=approval_comp["Accepted Amount"], name="Accepted")
fig1.update_layout(barmode='group')
st.plotly_chart(fig1, use_container_width=True)

st.subheader("Approval Type Distribution")
approval_dist = filtered_df["Approval Type"].value_counts(normalize=True).reset_index()
approval_dist.columns = ["Approval Type","Percentage"]
fig2 = px.pie(approval_dist, names="Approval Type", values="Percentage")
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Claim Type Breakdown (Accepted)")
claim_break = filtered_df.groupby("Claim Form Type")["Accepted Amount"].sum().reset_index()
fig3 = px.bar(claim_break, x="Claim Form Type", y="Accepted Amount", text_auto=True)
st.plotly_chart(fig3, use_container_width=True)

if "Accident Date" in filtered_df.columns:
    st.subheader("Monthly Trend")
    ts = filtered_df.copy()
    ts["YearMonth"] = ts["Accident Date"].dt.to_period("M")
    monthly_trend = ts.groupby("YearMonth")[["Requested Amount","Accepted Amount"]].sum().reset_index()
    monthly_trend["YearMonth"] = monthly_trend["YearMonth"].astype(str)

    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(x=monthly_trend["YearMonth"], y=monthly_trend["Requested Amount"], mode='lines+markers', name="Requested"))
    fig4.add_trace(go.Scatter(x=monthly_trend["YearMonth"], y=monthly_trend["Accepted Amount"], mode='lines+markers', name="Accepted"))
    st.plotly_chart(fig4, use_container_width=True)

# =========================================================
# DOCTOR PERFORMANCE
# =========================================================
st.subheader("Doctor Performance")

doctor_perf = (
    filtered_df.groupby("Treatment Doctor")
    .agg({"Requested Amount":"sum","Accepted Amount":"sum","Approval ID":"count"})
    .rename(columns={"Approval ID":"Total Claims"})
    .reset_index()
)

doctor_perf["Rejection Rate %"] = np.where(
    doctor_perf["Requested Amount"] != 0,
    ((doctor_perf["Requested Amount"] - doctor_perf["Accepted Amount"]) /
     doctor_perf["Requested Amount"]) * 100,
    0
)

counts = filtered_df.groupby(["Treatment Doctor","Approval Type"]).size().unstack(fill_value=0).reset_index()
doctor_perf = doctor_perf.merge(counts, on="Treatment Doctor", how="left")

den = doctor_perf.get("Pre-Authorization",0) + doctor_perf.get("Regular",0)
doctor_perf["Online %"] = np.where(den != 0, (doctor_perf.get("Pre-Authorization",0) / den) * 100, 0)

doctor_perf["Avg Cost per Claim"] = doctor_perf["Requested Amount"] / doctor_perf["Total Claims"]

doctor_perf = doctor_perf.sort_values("Accepted Amount", ascending=False)

doctor_display = doctor_perf.copy()
doctor_display["Requested Amount"] = doctor_display["Requested Amount"].apply(acc)
doctor_display["Accepted Amount"] = doctor_display["Accepted Amount"].apply(acc)
doctor_display["Avg Cost per Claim"] = doctor_display["Avg Cost per Claim"].round(0).apply(acc)
doctor_display["Rejection Rate %"] = doctor_display["Rejection Rate %"].round(2).astype(str) + " %"
doctor_display["Online %"] = doctor_display["Online %"].round(2).astype(str) + " %"
doctor_display.index = range(1, len(doctor_display)+1)

st.dataframe(doctor_display)

# =========================================================
# CLIENT PERFORMANCE
# =========================================================
st.subheader("Client Performance Ranking")

client_perf = (
    filtered_df.groupby("Client Name")
    .agg({"Requested Amount":"sum","Accepted Amount":"sum","Approval ID":"count"})
    .rename(columns={"Approval ID":"Total Claims"})
    .reset_index()
)

client_perf["Rejection Rate %"] = np.where(
    client_perf["Requested Amount"] != 0,
    ((client_perf["Requested Amount"] - client_perf["Accepted Amount"]) /
     client_perf["Requested Amount"]) * 100,
    0
)

client_perf["Avg Cost per Claim"] = client_perf["Requested Amount"] / client_perf["Total Claims"]
client_perf = client_perf.sort_values("Accepted Amount", ascending=False)

client_display = client_perf.copy()
client_display["Requested Amount"] = client_display["Requested Amount"].apply(acc)
client_display["Accepted Amount"] = client_display["Accepted Amount"].apply(acc)
client_display["Avg Cost per Claim"] = client_display["Avg Cost per Claim"].round(0).apply(acc)
client_display["Rejection Rate %"] = client_display["Rejection Rate %"].round(2).astype(str) + " %"
client_display.index = range(1, len(client_display)+1)

st.dataframe(client_display)

# =========================================================
# TOP 20 CLIENT MEMBERS
# =========================================================
st.subheader("Top 20 Client Members")

top_members = (
    filtered_df.groupby(["Client Name","Insured Card No","Insured Full Name"])
    .agg({"Accepted Amount":"sum","Approval ID":"count"})
    .rename(columns={"Approval ID":"Total Claims"})
    .sort_values("Accepted Amount", ascending=False)
    .head(20)
    .reset_index()
)

top_members["Accepted Amount"] = top_members["Accepted Amount"].apply(acc)
top_members.index = range(1, len(top_members)+1)
st.dataframe(top_members)

# =========================================================
# TOP 10 PROVIDERS
# =========================================================
st.subheader("Top 10 Providers")

top_providers = (
    filtered_df.groupby("Provider Name")
    .agg({"Accepted Amount":"sum","Approval ID":"count"})
    .rename(columns={"Approval ID":"Total Claims"})
    .sort_values("Accepted Amount", ascending=False)
    .head(10)
    .reset_index()
)

top_providers["Accepted Amount"] = top_providers["Accepted Amount"].apply(acc)
top_providers.index = range(1, len(top_providers)+1)
st.dataframe(top_providers)