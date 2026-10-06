import requests

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.api.v1.admission_module.models.api.greythr_sync_model import User

GREYTHR_API_URL = "https://api.greythr.com/employee/v2/employees"
ACCESS_TOKEN = "ory_at_a9j4nT5uBT4AVD1HH1NDOtZ0fDnWswH-sa_RHv-G2FI.6sg9sLhfwS8c0DUt7fI_hGRjo7KJUsWFHORXvL2HJ80"
DOMAIN = "testapisso.greythr.com"


def fetch_all_greythr_users():
    headers = {
        "ACCESS-TOKEN": ACCESS_TOKEN,
        "x-greythr-domain": DOMAIN,
        "Content-Type": "application/json"
    }

    page = 1
    size = 100
    all_employees = []

    while True:
        url = f"{GREYTHR_API_URL}?page={page}&size={size}"
        response = requests.get(url, headers=headers)
        # print(response.url)  # 🔥 DEBUG: Check the actual URL being called
        # print("STATUS:", response.status_code)
        # print("RESPONSE:", response.text)  # 🔥 IMPORTANT

        if response.status_code != 200:
            break

        result = response.json()
        employees = result.get("data", [])
        # print(f"Fetched {employees} employees from page {page}")  # 🔥 DEBUG
        if not employees:
            break

        all_employees.extend(employees)
        page += 1

    return all_employees


def sync_emp_bulk(db: Session):
    employees = fetch_all_greythr_users()
    # print(f"Total employees fetched from API: {len(employees)}")  # 🔥 DEBUG

    if not employees:
        return {"status": False, "message": "No API data"}

    # 🔹 Step 1: Prepare API email → emp_id map
    api_map = {}

    for emp in employees:
        email = emp.get("email")
        emp_id = emp.get("employeeId")

        if email and emp_id:
            email = email.lower().strip()
            api_map[email] = emp_id

    if not api_map:
        return {"status": False, "message": "No valid records"}

    # 🔹 Step 2: Fetch all matching users in ONE query
    users = db.query(User.id, User.email).filter(
        func.lower(User.email).in_(list(api_map.keys()))
    ).all()

    # 🔹 Step 3: Prepare bulk update list
    update_data = []

    for user in users:
        email = user.email.lower().strip()

        if email in api_map:
            update_data.append({
                "id": user.id,
                "emp_id": str(api_map[email]),  # convert to string if needed
                "Grety_HR_Sync": 1
            })

    # 🔹 Step 4: Bulk update
    if update_data:
        db.bulk_update_mappings(User, update_data)
        db.commit()

    return {
        "status": True,
        "updated_count": len(update_data)
    }