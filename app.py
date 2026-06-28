import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ── 경로 및 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
PROBLEMS_CSV = DATA_DIR / "problems.csv"
REVIEWS_CSV = DATA_DIR / "reviews.csv"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1226")

PROBLEM_COLUMNS = ["problem_id", "unit", "comment", "image_path", "created_at"]
REVIEW_COLUMNS = [
    "review_id",
    "problem_id",
    "student_name",
    "completed",
    "reflection",
    "submitted_at",
]


def init_storage():
    """data·uploads 폴더와 CSV 파일을 없으면 생성한다."""
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


def load_problems() -> pd.DataFrame:
    df = pd.read_csv(PROBLEMS_CSV, encoding="utf-8-sig")
    if df.empty:
        return df
    df["problem_id"] = df["problem_id"].astype(int)
    return df.sort_values("problem_id", ascending=False).reset_index(drop=True)


def load_reviews() -> pd.DataFrame:
    df = pd.read_csv(REVIEWS_CSV, encoding="utf-8-sig")
    if df.empty:
        return df
    df["problem_id"] = df["problem_id"].astype(int)
    return df


def save_problem(unit: str, comment: str, image_bytes: bytes, image_name: str):
    df = load_problems()
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


def save_review(problem_id: int, student_name: str, completed: str, reflection: str):
    df = load_reviews()
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


def has_duplicate_review(problem_id: int, student_name: str) -> bool:
    df = load_reviews()
    if df.empty:
        return False
    mask = (df["problem_id"] == problem_id) & (
        df["student_name"].str.strip() == student_name.strip()
    )
    return mask.any()


# ── 화면 ──────────────────────────────────────────────────────
def show_student_view():
    problems = load_problems()

    if problems.empty:
        st.info("아직 등록된 문제가 없습니다. 관리자가 문제를 업로드하면 여기에 표시됩니다.")
        return

    st.subheader("복습 문제 목록")
    st.caption("카드를 클릭해 문제를 선택하세요.")

    cols_per_row = 3
    for start in range(0, len(problems), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, (_, row) in enumerate(problems.iloc[start : start + cols_per_row].iterrows()):
            with cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"**문제 #{row['problem_id']}**")
                    st.markdown(f"📚 {row['unit']}")
                    preview = str(row["comment"])[:40]
                    if len(str(row["comment"])) > 40:
                        preview += "…"
                    st.caption(preview)
                    if st.button("보기", key=f"select_{row['problem_id']}", use_container_width=True):
                        st.session_state["selected_problem_id"] = int(row["problem_id"])

    selected_id = st.session_state.get("selected_problem_id")
    if selected_id is None:
        return

    selected = problems[problems["problem_id"] == selected_id]
    if selected.empty:
        return

    row = selected.iloc[0]
    st.divider()
    st.subheader(f"문제 #{row['problem_id']} · {row['unit']}")

    image_full_path = BASE_DIR / row["image_path"]
    if image_full_path.exists():
        st.image(str(image_full_path), use_container_width=True)
    else:
        st.warning("문제 사진을 찾을 수 없습니다.")

    st.markdown("**선생님 코멘트**")
    st.write(row["comment"])

    st.divider()
    st.subheader("복습 기록 제출")

    with st.form("review_form"):
        student_name = st.text_input("번호 또는 이름", placeholder="예: 12번, 홍길동")
        completed = st.radio("복습 완료 여부", ["완료", "미완료"], horizontal=True)
        reflection = st.text_input("한 줄 질문 / 소감", placeholder="궁금한 점이나 복습 소감을 적어주세요.")
        submitted = st.form_submit_button("제출하기", use_container_width=True)

    if submitted:
        if not student_name.strip():
            st.error("번호 또는 이름을 입력해 주세요.")
        elif has_duplicate_review(selected_id, student_name):
            st.error("이미 이 문제에 대한 기록을 제출했습니다. 중복 제출은 불가합니다.")
        else:
            save_review(selected_id, student_name, completed, reflection)
            st.success(f"{student_name.strip()}님, 복습 기록이 저장되었습니다!")
            st.balloons()


def show_admin_view():
    st.subheader("문제 업로드")

    if not st.session_state.get("admin_authenticated"):
        password = st.text_input("관리자 비밀번호", type="password")
        if st.button("로그인"):
            if password == ADMIN_PASSWORD:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
        return

    st.success("관리자로 로그인되었습니다.")
    if st.button("로그아웃"):
        st.session_state["admin_authenticated"] = False
        st.rerun()

    with st.form("upload_form"):
        unit = st.text_input("단원", placeholder="예: 2단원 일차함수")
        comment = st.text_area("문제 코멘트", placeholder="복습 포인트나 풀이 힌트를 적어주세요.")
        image_file = st.file_uploader("문제 사진", type=["png", "jpg", "jpeg", "webp"])
        uploaded = st.form_submit_button("문제 업로드", use_container_width=True)

    if uploaded:
        if not unit.strip():
            st.error("단원을 입력해 주세요.")
        elif not comment.strip():
            st.error("문제 코멘트를 입력해 주세요.")
        elif image_file is None:
            st.error("문제 사진을 업로드해 주세요.")
        else:
            problem_id = save_problem(unit, comment, image_file.getvalue(), image_file.name)
            st.success(f"문제 #{problem_id}가 업로드되었습니다!")

    st.divider()
    st.subheader("문제별 복습 현황")

    problems = load_problems()
    reviews = load_reviews()

    if problems.empty:
        st.info("등록된 문제가 없습니다.")
        return

    if reviews.empty:
        st.info("아직 제출된 복습 기록이 없습니다.")
        return

    display_rows = []
    for _, problem in problems.iterrows():
        problem_reviews = reviews[reviews["problem_id"] == problem["problem_id"]]
        if problem_reviews.empty:
            display_rows.append(
                {
                    "문제 번호": int(problem["problem_id"]),
                    "단원": problem["unit"],
                    "학생": "-",
                    "복습 완료": "-",
                    "질문/소감": "-",
                    "제출 시각": "-",
                }
            )
        else:
            for _, rev in problem_reviews.iterrows():
                display_rows.append(
                    {
                        "문제 번호": int(problem["problem_id"]),
                        "단원": problem["unit"],
                        "학생": rev["student_name"],
                        "복습 완료": rev["completed"],
                        "질문/소감": rev["reflection"],
                        "제출 시각": rev["submitted_at"],
                    }
                )

    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)


def main():
    st.set_page_config(
        page_title="학급 멘토멘티 복습 기록장",
        page_icon="📖",
        layout="wide",
    )
    init_storage()

    st.title("학급 멘토멘티 복습 기록장")

    page = st.sidebar.radio("화면 선택", ["학생용 화면", "관리자 화면"])

    if page == "학생용 화면":
        show_student_view()
    else:
        show_admin_view()


if __name__ == "__main__":
    main()
