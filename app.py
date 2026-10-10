import pandas as pd
from datetime import date
import math

import streamlit as st
from supabase import create_client
from postgrest.exceptions import APIError

st.set_page_config(page_title="Banana Cold Store", page_icon="🍌")
# Simple access gate for the competition demo.
import hmac

configured_password = st.secrets.get("APP_PASSWORD", "")

if not configured_password:
    st.error("Set APP_PASSWORD in the app's private secrets.")
    st.stop()

if not st.session_state.get("access_granted", False):
    st.subheader("Enter the demo password")

    with st.form("demo_login"):
        entered_password = st.text_input(
            "Password",
            type="password",
        )
        login_clicked = st.form_submit_button("Open app")

    if login_clicked:
        if hmac.compare_digest(
            entered_password.encode("utf-8"),
            str(configured_password).encode("utf-8"),
        ):
            st.session_state["access_granted"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()

if st.sidebar.button("Log out", key="demo_logout"):
    st.session_state.clear()
    st.rerun()

st.title("🍌 Banana Cold Store")
st.write("Add a banana batch and keep its details saved.")

# Read the private connection settings.
try:
    db = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SECRET_KEY"],
    )
except Exception:
    st.error(
        "Check the details in .streamlit/secrets.toml, "
        "then restart the app."
    )
    st.stop()

# Photo preview; the AI model will be connected later.
photo = st.file_uploader(
    "Banana photo — optional for now",
    type=["jpg", "jpeg", "png"],
)

if photo is not None:
    st.image(photo, caption="Photo preview", width=350)

st.caption(
    "For now, only batch details are saved. "
    "Photos are not saved or checked by AI yet."
)

with st.form("add_batch"):
    batch_id = st.text_input(
        "Batch number",
        placeholder="BATCH-001",
    )

    quantity = st.number_input(
        "Quantity in kilograms",
        min_value=0.0,
        step=1.0,
    )

    arrival_date = st.date_input(
        "Arrival date",
        value=date.today(),
        max_value=date.today(),
    )

    storage_zone = st.text_input(
        "Storage zone",
        value="Zone A",
    )

    submitted = st.form_submit_button("Save batch")

if submitted:
    if not batch_id.strip():
        st.warning("Enter a batch number.")
    elif not math.isfinite(quantity) or quantity <= 0:
        st.warning("Enter a quantity greater than zero.")
    elif not storage_zone.strip():
        st.warning("Enter a storage zone.")
    else:
        batch = {
            "batch_id": batch_id.strip().upper(),
            "quantity_kg": float(quantity),
            "arrival_date": arrival_date.isoformat(),
            "storage_zone": storage_zone.strip(),
        }

        try:
            db.table("batches").insert(batch).execute()
            st.success("Batch saved!")
        except APIError as error:
            if error.code == "23505":
                st.warning(
                    "That batch number already exists. "
                    "Use a different number."
                )
            else:
                st.error(
                    "Could not save. Check that the batches table "
                    "exists and your connection settings are correct."
                )
        except Exception:
            st.error(
                "Could not confirm the save. Check your internet, "
                "then refresh and look for the batch below."
            )

st.subheader("Recently saved batches")

try:
    result = (
        db.table("batches")
        .select(
            "batch_id,quantity_kg,arrival_date,storage_zone,status"
        )
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    )

    if result.data:
        st.dataframe(result.data, hide_index=True)
    else:
        st.info("No batches saved yet. Add your first one above.")
except Exception:
    st.error(
        "Could not load batches. Check your internet, "
        "connection settings, and that the batches table exists."
    )
    st.divider()
st.subheader("🌡️ Storage temperature checker")

st.caption(
    "Profile: mature-green Cavendish bananas, storage at 13–14°C. "
    "This checks individual readings, not remaining shelf life."
)

# Made-up readings for testing the app.
demo_csv = """timestamp,storage_zone,temperature_c
2026-10-10T08:00:00+05:00,Zone A,13.5
2026-10-10T09:00:00+05:00,Zone A,18.0
2026-10-10T10:00:00+05:00,Zone A,11.0
2026-10-10T11:00:00+05:00,Zone A,14.0
"""

st.download_button(
    "Download demo temperature file",
    data=demo_csv,
    file_name="demo_temperature_logs.csv",
    mime="text/csv",
)

st.caption("The demo file contains made-up data, not real sensor readings.")

log_file = st.file_uploader(
    "Upload your temperature CSV file",
    type=["csv"],
    key="temperature_upload",
)

if log_file is None:
    st.info("No temperature file uploaded. Storage conditions are unknown.")
else:
    try:
        logs = pd.read_csv(log_file)

        required = {"timestamp", "storage_zone", "temperature_c"}

        if not required.issubset(logs.columns):
            raise ValueError(
                "The file needs these columns: "
                "timestamp, storage_zone, temperature_c"
            )

        if logs.empty:
            raise ValueError("The file has no readings.")

        logs["temperature_c"] = pd.to_numeric(
            logs["temperature_c"], errors="coerce"
        )

        times = pd.to_datetime(
            logs["timestamp"], errors="coerce", utc=True
        )

        zones = logs["storage_zone"].fillna("").astype(str).str.strip()

        if (
            times.isna().any()
            or not logs["temperature_c"].apply(math.isfinite).all()
            or zones.eq("").any()
        ):
            raise ValueError(
                "Some rows have missing or invalid dates, "
                "temperatures, or storage zones. Fix them and upload again."
            )

        logs["storage_zone"] = zones

        zone = st.selectbox(
            "Choose a storage zone",
            sorted(logs["storage_zone"].unique()),
        )

        selected = logs[logs["storage_zone"] == zone].copy()

        def temperature_status(value):
            if value < 13:
                return "Below range — check chilling exposure"
            if value > 14:
                return "Above range — check cooling"
            return "Within selected range"

        selected["Check"] = selected["temperature_c"].apply(
            temperature_status
        )

        outside = (
            (selected["temperature_c"] < 13)
            | (selected["temperature_c"] > 14)
        ).sum()

        st.dataframe(selected, hide_index=True)

        if outside:
            st.warning(
                f"{outside} of {len(selected)} readings are outside "
                "the selected storage range. Review this zone."
            )
        else:
            st.success("All uploaded readings are within the selected range.")

        is_demo = st.checkbox(
            "These are demo / simulated readings",
            value=True,
        )
        if st.button("Save readings for this zone"):
            records = []

            for _, row in selected.iterrows():
                records.append({
                    "storage_zone": row["storage_zone"],
                    "recorded_at": pd.to_datetime(
                        row["timestamp"], utc=True
                    ).isoformat(),
                    "temperature_c": float(row["temperature_c"]),
                    "is_demo": is_demo,
                })

            try:
                db.table("temperature_logs").upsert(
                    records,
                    on_conflict="storage_zone,recorded_at,is_demo",
                    ignore_duplicates=True,
                ).execute()

                st.success(
                    "Save completed! Existing readings were kept; "
                    "new readings were added."
                )
            except Exception:
                st.error(
                    "Could not confirm the save. Check your connection "
                    "and the temperature_logs table before retrying."
                )

        st.caption(
            "Readings are saved only when you click Save. "
            "Batch matching and checks for missing times come next."
        )
        

    except ValueError as error:
        st.error(str(error))
    except Exception as error:
        st.error(f"Error type: {type(error).__name__}")
        if isinstance(error, NameError):
            st.error(f"Missing variable: {error.name}")
st.divider()
st.subheader("📋 Saved temperature readings")

reading_type = st.radio(
    "Which readings do you want to see?",
    ["Demo readings", "Real readings"],
    horizontal=True,
    key="saved_reading_type",
)

st.button("Refresh saved readings", key="refresh_saved_logs")

try:
    saved_result = (
        db.table("temperature_logs")
        .select("storage_zone,recorded_at,temperature_c,is_demo")
        .eq("is_demo", reading_type == "Demo readings")
        .order("recorded_at", desc=True)
        .limit(500)
        .execute()
    )

    if not saved_result.data:
        st.info("No saved readings of this type yet.")
    else:
        saved_logs = pd.DataFrame(saved_result.data)

        saved_logs["Time (Pakistan)"] = (
            pd.to_datetime(saved_logs["recorded_at"], utc=True)
            .dt.tz_convert("Asia/Karachi")
            .dt.strftime("%Y-%m-%d %H:%M")
        )

        saved_logs["Storage check"] = saved_logs["temperature_c"].apply(
            lambda value: (
                "Below range" if value < 13
                else "Above range" if value > 14
                else "Within range"
            )
        )

        st.caption(
            "Showing up to 500 most recent readings of the selected type. "
            "Storage check uses the mature-green Cavendish 13–14°C profile."
        )

        st.dataframe(
            saved_logs[
                [
                    "storage_zone",
                    "Time (Pakistan)",
                    "temperature_c",
                    "Storage check",
                ]
            ],
            hide_index=True,
        )

except Exception:
    st.error(
        "Could not load saved readings. "
        "Check your connection, then click Refresh saved readings."
    )           
st.divider()
st.subheader("🍌 Check a batch's storage history")

st.caption(
    "For batches that have stayed in their recorded storage zone. "
    "Temperature alerts help guide inspection; they do not prove spoilage."
)

try:
    review_batches = (
        db.table("batches")
        .select("batch_id,arrival_date,storage_zone,arrived_at")
        .order("created_at", desc=True)
        .limit(100)
        .execute()
    ).data

    if not review_batches:
        st.info("Save a batch first.")
    else:
        batch_lookup = {
            item["batch_id"]: item for item in review_batches
        }

        chosen_id = st.selectbox(
            "Choose a batch to review",
            list(batch_lookup),
            key="review_batch",
        )

        chosen_batch = batch_lookup[chosen_id]

        st.write("Storage zone:", chosen_batch["storage_zone"])
        st.write("Arrival date:", chosen_batch["arrival_date"])

        existing_arrival = chosen_batch.get("arrived_at")

        default_time = (
            pd.Timestamp(existing_arrival)
            .tz_convert("Asia/Karachi")
            .time()
            if existing_arrival
            else None
        )

        arrival_clock = st.time_input(
            "Arrival time — Pakistan time",
            value=default_time,
            key=f"arrival_clock_{chosen_id}",
        )

        if st.button("Save arrival time", key="save_arrival_time"):
            if arrival_clock is None:
                st.warning("Enter the arrival time first.")
            else:
                arrival_stamp = pd.Timestamp(
                    f"{chosen_batch['arrival_date']} "
                    f"{arrival_clock.isoformat()}"
                ).tz_localize("Asia/Karachi")

                if arrival_stamp > pd.Timestamp.now(tz="UTC"):
                    st.warning("Arrival time cannot be in the future.")
                else:
                    updated = (
                        db.table("batches")
                        .update({"arrived_at": arrival_stamp.isoformat()})
                        .eq("batch_id", chosen_id)
                        .execute()
                    )

                    if updated.data:
                        chosen_batch["arrived_at"] = arrival_stamp.isoformat()
                        st.success("Arrival time saved.")
                    else:
                        st.error("No batch was updated. Refresh and try again.")

        review_demo = st.checkbox(
            "Use demo readings for this check",
            value=True,
            key="review_demo",
        )

        if review_demo:
            st.info("DEMO CHECK — uses simulated temperature readings.")

        if st.button("Check this batch", key="check_batch_history"):
            if not chosen_batch.get("arrived_at"):
                st.warning("Save the arrival time first.")
            else:
                matched = (
                    db.table("temperature_logs")
                    .select("recorded_at,temperature_c")
                    .eq("storage_zone", chosen_batch["storage_zone"])
                    .eq("is_demo", review_demo)
                    .gte("recorded_at", chosen_batch["arrived_at"])
                    .lte("recorded_at", pd.Timestamp.now(tz="UTC").isoformat())
                    .order("recorded_at", desc=True)
                    .limit(500)
                    .execute()
                ).data

                if not matched:
                    st.warning(
                        "No matching readings. Storage conditions are unknown."
                    )
                else:
                    history = pd.DataFrame(matched)

                    outside_count = (
                        (history["temperature_c"] < 13)
                        | (history["temperature_c"] > 14)
                    ).sum()

                    st.write(
                        f"{len(history)} readings found for {chosen_id}."
                    )

                    if outside_count:
                        st.warning(
                            f"{outside_count} readings are outside 13–14°C. "
                            "Review the storage conditions and inspect the batch."
                        )
                    else:
                        st.info(
                            "No readings outside 13–14°C were found "
                            "in the returned records."
                        )

                    if len(history) == 500:
                        st.warning(
                            "Showing only the latest 500 matching readings. "
                            "Earlier history may be missing."
                        )

                    st.caption(
                        "Profile: mature-green Cavendish storage. "
                        "Gaps between readings are not checked yet. "
                        "This does not approve the batch for dispatch."
                    )

except APIError as error:
    st.error(f"Database request failed. Error code: {error.code}")
except Exception as error:
    st.error(f"Batch check could not finish: {type(error).__name__}")

# Paste this at the END of your existing app.py, starting at the far left.
st.divider()
st.subheader("🍌 AI banana photo check")
st.caption(
    "Prototype trained on 30 images. Upload a clear, centered banana sample. "
    "This classifies the photo, not the whole batch, and does not certify food safety."
)

ai_photo = st.file_uploader(
    "Choose a photo for the AI to check",
    type=["jpg", "jpeg", "png"],
    key="ai_banana_photo",
)

if ai_photo is not None:
    st.image(ai_photo, caption="Sample for AI inspection", width=350)

if st.button("Check banana ripeness", key="run_banana_ai"):
    if ai_photo is None:
        st.warning("Upload a banana photo first.")
    else:
        try:
            from PIL import Image
            from io import BytesIO
            from predict import predict_ripeness

            with st.spinner("Checking the banana photo..."):
                with Image.open(BytesIO(ai_photo.getvalue())) as sample:
                    prediction = predict_ripeness(sample)

            st.write("Predicted ripeness:", prediction["label"].upper())
            st.dataframe(
                [
                    {"Class": name, "Model score": round(score, 4)}
                    for name, score in prediction["scores"].items()
                ],
                hide_index=True,
            )
            st.caption("Model version: " + prediction["model_version"])
            st.info(
                "Model scores are not measured accuracy or spoilage probability. "
                "A person must review the sample. This result is not saved to a batch yet."
            )
        except FileNotFoundError:
            st.error("Model missing. Put banana_model.pt inside your models folder.")
        except ModuleNotFoundError:
            st.error("Check that predict.py is beside app.py and install requirements-ai.txt.")
        except Exception as error:
            st.error(f"AI check failed: {type(error).__name__}. Share this error type for help.")


# ---------- BATCH INSPECTION DASHBOARD ----------

import math
import pandas as pd
import streamlit as st

st.divider()
st.subheader("📋 Batch inspection dashboard")

st.caption(
    "Temperature profile: mature-green Cavendish bananas, 13–14°C. "
    "Assumes each batch stayed in its recorded storage zone."
)

dashboard_source = st.radio(
    "Which saved temperature readings should this dashboard use?",
    ["Demo readings", "Real readings"],
    key="dashboard_reading_source",
)

st.caption(
    "Demo and real readings are checked separately. "
    "Use Demo readings for the example CSV."
)

if st.button("Load / refresh dashboard", key="load_batch_dashboard"):
    try:
        dashboard_now = pd.Timestamp.now(tz="UTC")
        dashboard_demo = dashboard_source == "Demo readings"

        batch_response = (
            db.table("batches")
            .select(
                "batch_id,quantity_kg,storage_zone,"
                "arrival_date,arrived_at,status",
                count="exact",
            )
            .neq("status", "Dispatched")
            .order("arrival_date")
            .order("batch_id")
            .limit(100)
            .execute()
        )

        dashboard_batches = batch_response.data or []
        dashboard_rows = []

        if (batch_response.count or 0) > len(dashboard_batches):
            st.warning(
                "Showing only the first 100 batches by arrival date."
            )

        for batch in dashboard_batches:
            arrival = pd.to_datetime(
                batch.get("arrived_at"),
                utc=True,
                errors="coerce",
            )

            row = {
                "Batch": batch["batch_id"],
                "Zone": batch["storage_zone"],
                "Quantity (kg)": batch["quantity_kg"],
                "Arrival date": batch["arrival_date"],
                "Saved status": batch.get("status", ""),
                "Readings checked": 0,
                "Outside range": 0,
                "Latest reading (Pakistan)": "Unknown",
                "Finding": "",
                "Action": "",
                "_priority": 1,
            }

            if pd.isna(arrival) or arrival > dashboard_now:
                row["Finding"] = "Arrival time missing or invalid"
                row["Action"] = "Set the correct arrival time"
                dashboard_rows.append(row)
                continue

            if not str(batch.get("storage_zone") or "").strip():
                row["Finding"] = "Storage zone missing"
                row["Action"] = "Correct the batch storage zone"
                dashboard_rows.append(row)
                continue

            try:
                log_response = (
                    db.table("temperature_logs")
                    .select(
                        "recorded_at,temperature_c",
                        count="exact",
                    )
                    .eq("storage_zone", batch["storage_zone"])
                    .eq("is_demo", dashboard_demo)
                    .gte("recorded_at", arrival.isoformat())
                    .lte("recorded_at", dashboard_now.isoformat())
                    .order("recorded_at", desc=True)
                    .limit(500)
                    .execute()
                )

                readings = log_response.data or []
                partial = (
                    (log_response.count or 0) > len(readings)
                )

                if not readings:
                    row["Finding"] = "No matching readings"
                    row["Action"] = "Obtain storage records"

                else:
                    temperatures = [
                        float(item["temperature_c"])
                        for item in readings
                    ]

                    if not all(
                        math.isfinite(value)
                        for value in temperatures
                    ):
                        raise ValueError("Invalid temperature")

                    outside_count = sum(
                        value < 13 or value > 14
                        for value in temperatures
                    )

                    latest = pd.to_datetime(
                        readings[0]["recorded_at"],
                        utc=True,
                    )

                    row["Readings checked"] = len(readings)
                    row["Outside range"] = outside_count
                    row["Latest reading (Pakistan)"] = (
                        latest.tz_convert("Asia/Karachi")
                        .strftime("%Y-%m-%d %H:%M")
                    )

                    if outside_count:
                        row["Finding"] = (
                            f"{outside_count} readings outside range"
                        )
                        row["Action"] = (
                            "Inspect batch and review storage"
                        )
                        row["_priority"] = 0
                    else:
                        row["Finding"] = (
                            "No alerts in checked readings"
                        )
                        row["Action"] = (
                            "Review record coverage and inspect"
                        )
                        row["_priority"] = 2

                    if partial:
                        row["Finding"] += (
                            "; only latest 500 readings checked"
                        )
                        row["Action"] += "; review older records"
                        row["_priority"] = min(
                            row["_priority"], 1
                        )

            except Exception:
                row["Finding"] = "Could not check temperature records"
                row["Action"] = "Check connection and saved data"
                row["_priority"] = 1

            dashboard_rows.append(row)

        if dashboard_rows:
            dashboard_table = pd.DataFrame(dashboard_rows)

            dashboard_table = dashboard_table.sort_values(
                ["_priority", "Arrival date", "Batch"]
            )

            st.dataframe(
                dashboard_table.drop(columns=["_priority"]),
                hide_index=True,
            )

            st.info(
                "Inspection order: temperature alerts first, "
                "missing or incomplete information next, then "
                "batches with no alerts in checked readings. "
                "Within each group, earlier arrival dates come first."
            )

            st.caption(
                "This is an inspection list, not dispatch approval "
                "or a prediction of which batch will spoil first. "
                "Gaps between readings and stale records are not "
                "automatically assessed here. Check the latest "
                "reading time; no alerts does not prove safe storage."
            )
        else:
            st.info("No batches found. Save a batch first.")

    except Exception as error:
        st.error(
            "Could not load the dashboard. Check your connection "
            "and that batches includes the arrived_at column. "
            f"Error type: {type(error).__name__}"
        )

# ---------- OPERATOR REVIEW ----------

from datetime import datetime, timezone

st.divider()
st.subheader("📝 Record an operator decision")

st.caption(
    "Record a person's decision after reviewing the batch and "
    "its storage records. Temperature alerts alone do not approve dispatch."
)

operator_batches = []

try:
    operator_response = (
        db.table("batches")
        .select("batch_id,status", count="exact")
        .neq("status", "Dispatched")
        .order("batch_id")
        .limit(100)
        .execute()
    )

    operator_batches = operator_response.data or []

    if (operator_response.count or 0) > len(operator_batches):
        st.warning("Only the first 100 available batches are listed.")

except Exception:
    st.error("Could not load batches. Check your connection.")

if operator_batches:
    operator_batch_id = st.selectbox(
        "Choose the batch to review",
        [item["batch_id"] for item in operator_batches],
        key="operator_batch_choice",
    )

    operator_current = next(
        item for item in operator_batches
        if item["batch_id"] == operator_batch_id
    )

    st.write("Current saved status:", operator_current["status"])

    with st.form(key=f"operator_review_{operator_batch_id}"):
        operator_name = st.text_input("Your name")

        operator_demo = st.checkbox(
            "This is a demo / practice decision",
            value=True,
        )

        operator_decision = st.selectbox(
            "Decision",
            [
                "Awaiting inspection",
                "On hold",
                "Approved for dispatch",
            ],
        )

        operator_notes = st.text_area(
            "Inspection notes / reason",
            placeholder=(
                "Example: Temperature alerts found. "
                "Hold pending physical inspection."
            ),
        )

        operator_confirm = st.checkbox(
            "For dispatch approval: I confirm the physical inspection "
            "and storage-record review are complete, and any alerts "
            "or missing records have been addressed. "
            "For a demo, this represents a simulated inspection."
        )

        operator_save = st.form_submit_button("Save decision")

    if operator_save:
        if not operator_name.strip():
            st.warning("Enter your name.")

        elif not operator_notes.strip():
            st.warning("Write the reason for your decision.")

        elif (
            operator_decision == "Approved for dispatch"
            and not operator_confirm
        ):
            st.warning(
                "Complete and confirm the review before approving dispatch."
            )

        else:
            try:
                operator_saved = (
                    db.table("batches")
                    .update({
                        "status": operator_decision,
                        "operator_name": operator_name.strip(),
                        "inspection_notes": operator_notes.strip(),
                        "reviewed_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "review_is_demo": operator_demo,
                    })
                    .eq("batch_id", operator_batch_id)
                    .eq("status", operator_current["status"])
                    .execute()
                )

                if operator_saved.data:
                    st.success(
                        f"Saved for {operator_batch_id}: "
                        f"{operator_decision}"
                    )
                    st.info(
                        "Click Load / refresh dashboard above "
                        "to see the updated status."
                    )
                else:
                    st.warning(
                        "No update confirmed. The batch may have changed. "
                        "Refresh the page and check its status."
                    )

            except Exception:
                st.error(
                    "Could not confirm the save. Refresh and check "
                    "the batch status before trying again."
                )

    st.caption(
        "This form stores the latest decision; saving again replaces "
        "the previous review details. Demo decisions are labelled in "
        "the database and must remain separate from real dispatch."
    )

else:
    st.info("No batches available for review.")

# ---------- DISPATCH LIST ----------

from datetime import datetime, timezone

st.divider()
st.subheader("🚚 Dispatch list")

st.caption(
    "Only batches approved by an operator appear here. "
    "Earlier arrival dates appear first. "
    "This MVP records whole-batch dispatch only."
)

dispatch_mode = st.radio(
    "Dispatch records to work with",
    ["Demo / practice", "Real"],
    key="dispatch_mode",
)

dispatch_demo = dispatch_mode == "Demo / practice"

if dispatch_demo:
    st.info(
        "Demo mode: recording dispatch simulates a batch leaving storage."
    )
else:
    st.info(
        "Real mode: record dispatch only after the batch actually leaves."
    )

dispatch_batches = []

try:
    dispatch_response = (
        db.table("batches")
        .select(
            "batch_id,quantity_kg,storage_zone,arrival_date,"
            "operator_name,inspection_notes,reviewed_at",
            count="exact",
        )
        .eq("status", "Approved for dispatch")
        .eq("review_is_demo", dispatch_demo)
        .order("arrival_date")
        .order("batch_id")
        .limit(100)
        .execute()
    )

    dispatch_batches = dispatch_response.data or []

    if (dispatch_response.count or 0) > len(dispatch_batches):
        st.warning("Showing the first 100 approved batches.")

except Exception:
    st.error("Could not load the dispatch list. Check your connection.")

if dispatch_batches:
    st.dataframe(dispatch_batches, hide_index=True)

    dispatch_batch_id = st.selectbox(
        "Choose an approved batch",
        [batch["batch_id"] for batch in dispatch_batches],
        key="dispatch_batch_choice",
    )

    dispatch_selected = next(
        batch for batch in dispatch_batches
        if batch["batch_id"] == dispatch_batch_id
    )

    st.write(
        "Whole batch quantity:",
        dispatch_selected["quantity_kg"],
        "kg",
    )
    st.write(
        "Operator review notes:",
        dispatch_selected.get("inspection_notes") or "None recorded",
    )

    with st.form(
        key=f"dispatch_form_{dispatch_batch_id}_{dispatch_demo}"
    ):
        dispatch_person = st.text_input(
            "Name of person recording dispatch"
        )

        dispatch_ref = st.text_input(
            "Delivery / dispatch reference",
            placeholder="Example: DEMO-DELIVERY-001",
        )

        dispatch_confirm = st.checkbox(
            "I confirm this whole batch has left storage."
            if not dispatch_demo
            else "I confirm this is a simulated whole-batch dispatch."
        )

        dispatch_submit = st.form_submit_button("Record dispatch")

    if dispatch_submit:
        if not dispatch_person.strip():
            st.warning("Enter the name of the person recording dispatch.")

        elif not dispatch_ref.strip():
            st.warning("Enter a delivery or dispatch reference.")

        elif not dispatch_confirm:
            st.warning("Tick the confirmation box first.")

        elif not dispatch_selected.get("reviewed_at"):
            st.warning(
                "This batch needs a recorded operator review first."
            )

        else:
            try:
                dispatch_result = (
                    db.table("batches")
                    .update({
                        "status": "Dispatched",
                        "dispatched_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "dispatched_by": dispatch_person.strip(),
                        "dispatch_reference": dispatch_ref.strip(),
                        "dispatch_is_demo": dispatch_demo,
                    })
                    .eq("batch_id", dispatch_batch_id)
                    .eq("status", "Approved for dispatch")
                    .eq("review_is_demo", dispatch_demo)
                    .eq(
                        "reviewed_at",
                        dispatch_selected["reviewed_at"],
                    )
                    .eq(
                        "quantity_kg",
                        dispatch_selected["quantity_kg"],
                    )
                    .execute()
                )

                if dispatch_result.data:
                    st.success(
                        f"Dispatch recorded for {dispatch_batch_id}."
                    )
                    st.info(
                        "Refresh the page to update the list. "
                        "This batch will no longer appear as approved."
                    )
                else:
                    st.warning(
                        "No dispatch recorded. The batch may already "
                        "be dispatched or its review may have changed. "
                        "Refresh the page before continuing."
                    )

            except Exception:
                st.error(
                    "Could not confirm dispatch. Refresh and check "
                    "the batch's saved status before retrying."
                )

else:
    st.info(
        "No approved batches in this mode. "
        "Batches on hold or awaiting inspection cannot be dispatched."
    )

# ---------- DISPATCH HISTORY ----------

st.divider()
st.subheader("📦 Dispatch history")

history_mode = st.radio(
    "Which dispatch history do you want to see?",
    ["Demo / practice", "Real"],
    key="dispatch_history_mode",
)

if st.button("Load / refresh history", key="load_dispatch_history"):
    try:
        history_response = (
            db.table("batches")
            .select(
                "batch_id,quantity_kg,storage_zone,"
                "dispatched_at,dispatched_by,dispatch_reference",
                count="exact",
            )
            .eq("status", "Dispatched")
            .eq(
                "dispatch_is_demo",
                history_mode == "Demo / practice",
            )
            .order("dispatched_at", desc=True)
            .limit(100)
            .execute()
        )

        history_records = history_response.data or []

        if history_records:
            history_table = pd.DataFrame(history_records)

            history_table["dispatched_at"] = (
                pd.to_datetime(
                    history_table["dispatched_at"],
                    utc=True,
                    errors="coerce",
                )
                .dt.tz_convert("Asia/Karachi")
                .dt.strftime("%Y-%m-%d %H:%M")
            )

            history_table = history_table.rename(columns={
                "batch_id": "Batch",
                "quantity_kg": "Dispatched quantity (kg)",
                "storage_zone": "Storage zone",
                "dispatched_at": "Dispatch time (Pakistan)",
                "dispatched_by": "Recorded by",
                "dispatch_reference": "Reference",
            })

            st.dataframe(history_table, hide_index=True)

            st.caption(
                "Showing the latest 100 dispatches at most. "
                "Demo dispatches represent practice transactions."
            )

            if (history_response.count or 0) > len(history_records):
                st.warning(
                    "Older dispatches exist but are not shown here."
                )

        else:
            st.info("No dispatches recorded in this mode yet.")

    except Exception:
        st.error(
            "Could not load dispatch history. Check your connection "
            "and that the dispatch fields exist in Supabase."
        )