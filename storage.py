import io
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
PROBLEMS_CSV = DATA_DIR / "problems.csv"
REVIEWS_CSV = DATA_DIR / "reviews.csv"

PROBLEM_COLUMNS = ["problem_id", "unit", "comment", "image_path", "created_at"]
REVIEW_COLUMNS = [
    "review_id",
    "problem_id",
    "student_name",
    "completed",
    "reflection",
    "submitted_at",
]

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def use_cloud_storage() -> bool:
    try:
        return (
            "gcp_service_account" in st.secrets
            and "GOOGLE_SHEET_URL" in st.secrets
            and "GOOGLE_DRIVE_FOLDER_ID" in st.secrets
        )
    except Exception:
        return False


def storage_mode_label() -> str:
    return "클라우드 저장 (Google)" if use_cloud_storage() else "로컬 저장 (임시)"


# ── 로컬 저장 ─────────────────────────────────────────────────
def init_local_storage():
    DATA_DIR.mkdir(exist_ok=True)
    UPLOADS_DIR.mkdir(exist_ok=True)
    if not PROBLEMS_CSV.exists():
        pd.DataFrame(columns=PROBLEM_COLUMNS).to_csv(
            PROBLEMS_CSV, index=False, encoding="utf-8-sig"
        )
    if not REVIEWS_CSV.exists():
        pd.DataFrame(columns=REVIEW_COLUMNS).to_csv(
            REVIEWS_CSV, index=False, encoding="utf-8-sig"
        )


def _load_local_problems() -> pd.DataFrame:
    df = pd.read_csv(PROBLEMS_CSV, encoding="utf-8-sig")
    if df.empty:
        return df
    df["problem_id"] = df["problem_id"].astype(int)
    return df.sort_values("problem_id", ascending=False).reset_index(drop=True)


def _load_local_reviews() -> pd.DataFrame:
    df = pd.read_csv(REVIEWS_CSV, encoding="utf-8-sig")
    if df.empty:
        return df
    df["problem_id"] = df["problem_id"].astype(int)
    return df


def _save_local_problem(unit: str, comment: str, image_bytes: bytes, image_name: str) -> int:
    df = _load_local_problems()
    next_id = int(df["problem_id"].max()) + 1 if not df.empty else 1

    ext = Path(image_name).suffix or ".jpg"
    filename = f"problem_{next_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    image_path = UPLOADS_DIR / filename
    image_path.write_bytes(image_bytes)

    new_row = pd.DataFrame(
        [
            {
                "problem_id": next_id,
                "unit": unit.strip(),
                "comment": comment.strip(),
                "image_path": str(image_path.relative_to(BASE_DIR)),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )
    pd.concat([df, new_row], ignore_index=True).to_csv(
        PROBLEMS_CSV, index=False, encoding="utf-8-sig"
    )
    return next_id


def _save_local_review(
    problem_id: int, student_name: str, completed: str, reflection: str
):
    df = _load_local_reviews()
    next_id = int(df["review_id"].max()) + 1 if not df.empty else 1

    new_row = pd.DataFrame(
        [
            {
                "review_id": next_id,
                "problem_id": problem_id,
                "student_name": student_name.strip(),
                "completed": completed,
                "reflection": reflection.strip(),
                "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
    )
    pd.concat([df, new_row], ignore_index=True).to_csv(
        REVIEWS_CSV, index=False, encoding="utf-8-sig"
    )


# ── Google Sheets + Drive ─────────────────────────────────────
@st.cache_resource
def _get_google_clients():
    import gspread
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_info, scopes=GOOGLE_SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_url(st.secrets["GOOGLE_SHEET_URL"])
    drive = build("drive", "v3", credentials=creds)
    return gc, spreadsheet, drive


def _ensure_worksheet(spreadsheet, title: str, columns: list[str]):
    import gspread

    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(columns))
        ws.append_row(columns)
        return ws

    first_row = ws.row_values(1)
    if not first_row:
        ws.append_row(columns)
    return ws


def _sheet_to_df(ws, id_column: str) -> pd.DataFrame:
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=ws.row_values(1))
    df = pd.DataFrame(records)
    if id_column in df.columns and not df.empty:
        df[id_column] = pd.to_numeric(df[id_column], errors="coerce").astype("Int64")
        df = df.dropna(subset=[id_column])
        df[id_column] = df[id_column].astype(int)
    return df


def _upload_image_to_drive(drive, image_bytes: bytes, image_name: str) -> str:
    folder_id = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
    ext = Path(image_name).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(ext, "image/jpeg")
    filename = f"problem_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext or '.jpg'}"

    from googleapiclient.http import MediaIoBaseUpload

    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=mime_type, resumable=True)
    uploaded = (
        drive.files()
        .create(body=metadata, media_body=media, fields="id")
        .execute()
    )
    file_id = uploaded["id"]
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}"


def _load_cloud_problems() -> pd.DataFrame:
    _, spreadsheet, _ = _get_google_clients()
    ws = _ensure_worksheet(spreadsheet, "problems", PROBLEM_COLUMNS)
    df = _sheet_to_df(ws, "problem_id")
    if df.empty:
        return df
    return df.sort_values("problem_id", ascending=False).reset_index(drop=True)


def _load_cloud_reviews() -> pd.DataFrame:
    _, spreadsheet, _ = _get_google_clients()
    ws = _ensure_worksheet(spreadsheet, "reviews", REVIEW_COLUMNS)
    return _sheet_to_df(ws, "review_id")


def _save_cloud_problem(unit: str, comment: str, image_bytes: bytes, image_name: str) -> int:
    _, spreadsheet, drive = _get_google_clients()
    ws = _ensure_worksheet(spreadsheet, "problems", PROBLEM_COLUMNS)
    df = _load_cloud_problems()
    next_id = int(df["problem_id"].max()) + 1 if not df.empty else 1

    image_url = _upload_image_to_drive(drive, image_bytes, image_name)
    ws.append_row(
        [
            next_id,
            unit.strip(),
            comment.strip(),
            image_url,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ],
        value_input_option="USER_ENTERED",
    )
    return next_id


def _save_cloud_review(
    problem_id: int, student_name: str, completed: str, reflection: str
):
    _, spreadsheet, _ = _get_google_clients()
    ws = _ensure_worksheet(spreadsheet, "reviews", REVIEW_COLUMNS)
    df = _load_cloud_reviews()
    next_id = int(df["review_id"].max()) + 1 if not df.empty else 1

    ws.append_row(
        [
            next_id,
            problem_id,
            student_name.strip(),
            completed,
            reflection.strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ],
        value_input_option="USER_ENTERED",
    )


# ── 공통 API ──────────────────────────────────────────────────
def init_storage():
    if use_cloud_storage():
        _, spreadsheet, _ = _get_google_clients()
        _ensure_worksheet(spreadsheet, "problems", PROBLEM_COLUMNS)
        _ensure_worksheet(spreadsheet, "reviews", REVIEW_COLUMNS)
    else:
        init_local_storage()


def load_problems() -> pd.DataFrame:
    if use_cloud_storage():
        return _load_cloud_problems()
    return _load_local_problems()


def load_reviews() -> pd.DataFrame:
    if use_cloud_storage():
        return _load_cloud_reviews()
    return _load_local_reviews()


def save_problem(unit: str, comment: str, image_bytes: bytes, image_name: str) -> int:
    if use_cloud_storage():
        return _save_cloud_problem(unit, comment, image_bytes, image_name)
    return _save_local_problem(unit, comment, image_bytes, image_name)


def save_review(problem_id: int, student_name: str, completed: str, reflection: str):
    if use_cloud_storage():
        _save_cloud_review(problem_id, student_name, completed, reflection)
    else:
        _save_local_review(problem_id, student_name, completed, reflection)


def has_duplicate_review(problem_id: int, student_name: str) -> bool:
    df = load_reviews()
    if df.empty:
        return False
    mask = (df["problem_id"] == problem_id) & (
        df["student_name"].astype(str).str.strip() == student_name.strip()
    )
    return bool(mask.any())


def resolve_image(image_path: str) -> str | None:
    if not image_path or pd.isna(image_path):
        return None
    path_str = str(image_path).strip()
    if path_str.startswith("http://") or path_str.startswith("https://"):
        return path_str
    local_path = BASE_DIR / path_str
    if local_path.exists():
        return str(local_path)
    return None
