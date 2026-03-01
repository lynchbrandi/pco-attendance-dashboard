import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh

# Refresh every 30 seconds (60,000 ms)
st_autorefresh(interval=30000, key="pco_refresh")

APP_ID = st.secrets["PCO_APP_ID"]
SECRET = st.secrets["PCO_SECRET"]


st.title("Attendance Dashboard")


# Manual refresh button (optional)
if st.button("Refresh now"):
    st.rerun()

# ✅ Today only (America/Chicago)
chicago = ZoneInfo("America/Chicago")
now = datetime.now(chicago)
today_date = now.date()

st.subheader(f"Today: {today_date.strftime('%A, %B %d, %Y')} (America/Chicago)")

# Build a UTC window for today (PCO timestamps are UTC/Z)
start_local = datetime.combine(today_date, time(0, 0), tzinfo=chicago)
end_local = start_local + timedelta(days=1)
start_utc = start_local.astimezone(ZoneInfo("UTC"))
end_utc = end_local.astimezone(ZoneInfo("UTC"))
st.caption(f"Last updated: {datetime.now(chicago).strftime('%I:%M:%S %p')} (Chicago)")
params = {
    "where[starts_at][gte]": start_utc.isoformat().replace("+00:00", "Z"),
    "where[starts_at][lt]": end_utc.isoformat().replace("+00:00", "Z"),
    "include": "event",
}

event_times_response = requests.get(
    "https://api.planningcenteronline.com/check-ins/v2/event_times",
    params=params,
    auth=(APP_ID, SECRET),
)

st.write("event_times status:", event_times_response.status_code)

if event_times_response.status_code != 200:
    st.error(event_times_response.text)
    st.stop()

payload = event_times_response.json()
event_times = payload.get("data", [])
included = payload.get("included", [])

# Build lookup: event_id -> event_name (e.g., "Sunday Worship")
event_name_by_id = {}
for item in included:
    if (item.get("type") or "").lower() == "event":
        event_name_by_id[item["id"]] = item.get("attributes", {}).get("name", "Sunday Worship")

st.write("event_times returned:", len(event_times))

# ✅ Filter to TODAY in Chicago (in case API filter returns extra)
attendance_data = []

for event in event_times:
    attrs = event.get("attributes", {})
    starts_at_str = attrs.get("starts_at")

    if not starts_at_str:
        continue

    starts_at_utc = datetime.fromisoformat(starts_at_str.replace("Z", "+00:00"))
    starts_at_chicago = starts_at_utc.astimezone(chicago)

    if starts_at_chicago.date() != today_date:
        continue

    # Get parent Event ID
    event_id = event.get("relationships", {}).get("event", {}).get("data", {}).get("id")

    # Get Event name (e.g. Sunday Worship)
    event_name = event_name_by_id.get(event_id, "Sunday Worship")

    attendance_data.append({
        "Event": event_name,
        "Starts At": starts_at_chicago.strftime("%I:%M %p"),
        "Total Check-ins": attrs.get("total_count", 0),
        "Regular": attrs.get("regular_count", 0),
        "Guests": attrs.get("guest_count", 0),
        "Volunteers": attrs.get("volunteer_count", 0),
    })

df = pd.DataFrame(attendance_data)

if not df.empty:
    st.metric("Total Attendance", int(df["Total Check-ins"].sum()))
    st.dataframe(df.sort_values("Starts At"), use_container_width=True)
else:
    st.info("No event times found for today (or check-ins haven’t started yet).")

