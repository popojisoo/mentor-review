import os

import pandas as pd
import streamlit as st

from storage import (
    init_storage,
    load_problems,
    load_reviews,
    resolve_image,
    save_problem,
    save_review,
    has_duplicate_review,
    storage_mode_label,
    use_cloud_storage,
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1226")


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

    image_src = resolve_image(row["image_path"])
    if image_src:
        st.image(image_src, use_container_width=True)
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

    if not use_cloud_storage():
        st.warning(
            "지금은 **임시 저장** 모드입니다. Streamlit Cloud에서는 데이터가 사라질 수 있습니다. "
            "아래 설정을 완료하면 Google에 영구 저장됩니다."
        )

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
            try:
                problem_id = save_problem(unit, comment, image_file.getvalue(), image_file.name)
                st.success(f"문제 #{problem_id}가 저장되었습니다!")
            except Exception as e:
                st.error(f"저장 중 오류가 발생했습니다: {e}")

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
    st.sidebar.caption(f"저장 방식: **{storage_mode_label()}**")

    page = st.sidebar.radio("화면 선택", ["학생용 화면", "관리자 화면"])

    if page == "학생용 화면":
        show_student_view()
    else:
        show_admin_view()


if __name__ == "__main__":
    main()
