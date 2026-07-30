import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------

st.set_page_config(
    page_title="박스오피스 대시보드",
    layout="wide"
)

st.title("🎬 박스오피스 대시보드")


# ------------------------------------------------------------
# KOBIS 인증키
# ------------------------------------------------------------

KOBIS_KEY = st.secrets["KOBIS_KEY"]

KOBIS_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"


# ------------------------------------------------------------
# 날짜 설정
# ------------------------------------------------------------

today_korea = datetime.now(ZoneInfo("Asia/Seoul")).date()
yesterday = today_korea - timedelta(days=1)

st.caption("오늘 박스오피스는 아직 집계 전이므로 어제 날짜까지만 조회할 수 있습니다.")


# ------------------------------------------------------------
# KOBIS API 호출 함수
# ------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_daily_boxoffice(target_dt):
    """
    target_dt 형식: YYYYMMDD
    KOBIS 일별 박스오피스 데이터를 가져옵니다.
    """

    res = requests.get(
        KOBIS_URL,
        params={
            "key": KOBIS_KEY,
            "targetDt": target_dt
        },
        timeout=10
    )

    if res.status_code != 200:
        raise RuntimeError(f"요청 실패, 상태코드: {res.status_code}")

    data = res.json()

    # KOBIS는 인증키가 틀려도 status_code 200을 줄 수 있습니다.
    if "faultInfo" in data:
        raise ValueError("인증키가 올바르지 않습니다. Secrets의 KOBIS_KEY를 확인해 주세요.")

    box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

    return box_list


# ------------------------------------------------------------
# 데이터 정리 함수
# ------------------------------------------------------------

def make_boxoffice_dataframe(box_list):
    """
    KOBIS 박스오피스 목록을 데이터프레임으로 바꾸고
    숫자 열을 정리합니다.
    """

    df = pd.DataFrame(box_list)

    if df.empty:
        return df

    number_cols = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
        "showCnt"
    ]

    for col in number_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def make_rank_change_text(row):
    """
    rankInten 값을 이용해 순위 증감을 표시합니다.
    양수: 순위 상승
    음수: 순위 하락
    0: 변동 없음
    """

    rank_inten = row["rankInten"]

    if row.get("rankOldAndNew", "") == "NEW":
        return "NEW"

    if rank_inten > 0:
        return f"🔴 ▲ {rank_inten}"

    if rank_inten < 0:
        return f"🔵 ▼ {abs(rank_inten)}"

    return "—"


def add_display_columns(df):
    """
    표시에 필요한 열을 추가합니다.
    """

    df["순위증감"] = df.apply(make_rank_change_text, axis=1)

    df["영화명표시"] = df.apply(
        lambda row: f"{row['movieNm']} 🏆" if row["audiAcc"] > 1_000_000 else row["movieNm"],
        axis=1
    )

    df = df.sort_values("rank").reset_index(drop=True)

    return df


def make_date_range_dataframe(start_date, end_date):
    """
    선택한 날짜 범위의 일별 박스오피스 데이터를 모두 합쳐서 하나의 데이터프레임으로 만듭니다.
    """

    date_list = pd.date_range(start=start_date, end=end_date, freq="D")

    rows = []

    for date_value in date_list:
        date_obj = date_value.date()
        target_dt = date_obj.strftime("%Y%m%d")

        daily_box_list = get_daily_boxoffice(target_dt)

        if not daily_box_list:
            continue

        daily_df = make_boxoffice_dataframe(daily_box_list)

        if daily_df.empty:
            continue

        daily_df["날짜"] = date_obj

        rows.append(daily_df)

    if not rows:
        return pd.DataFrame()

    result_df = pd.concat(rows, ignore_index=True)

    return result_df


# ------------------------------------------------------------
# 탭 구성
# ------------------------------------------------------------

tab1, tab2 = st.tabs([
    "📋 날짜별 박스오피스",
    "🎞️ 영화별 관객수 추이"
])


# ------------------------------------------------------------
# 탭 1. 날짜별 박스오피스
# ------------------------------------------------------------

with tab1:
    st.subheader("📅 날짜별 박스오피스 조회")

    selected_date = st.date_input(
        "조회할 날짜를 선택하세요",
        value=yesterday,
        max_value=yesterday,
        help="오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다.",
        key="single_date"
    )

    target_dt = selected_date.strftime("%Y%m%d")

    st.caption(f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}")

    try:
        box_list = get_daily_boxoffice(target_dt)

        if not box_list:
            st.warning("그날은 아직 집계 전입니다.")

        else:
            df = make_boxoffice_dataframe(box_list)
            df = add_display_columns(df)

            # 1위 영화 지표 카드
            top = df.iloc[0]

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "선택한 날짜 1위",
                top["영화명표시"]
            )

            c2.metric(
                "관객수",
                f"{top['audiCnt']:,}명"
            )

            c3.metric(
                "누적 관객",
                f"{top['audiAcc']:,}명"
            )

            # 표 정리
            table = df[
                [
                    "rank",
                    "순위증감",
                    "영화명표시",
                    "openDt",
                    "audiCnt",
                    "audiAcc",
                    "scrnCnt"
                ]
            ].copy()

            table.columns = [
                "순위",
                "순위 증감",
                "영화명",
                "개봉일",
                "관객수",
                "누적관객",
                "스크린수"
            ]

            st.subheader("📋 박스오피스 TOP 10")

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "관객수": st.column_config.NumberColumn(
                        "관객수",
                        format="%d명"
                    ),
                    "누적관객": st.column_config.NumberColumn(
                        "누적관객",
                        format="%d명"
                    ),
                    "스크린수": st.column_config.NumberColumn(
                        "스크린수",
                        format="%d개"
                    )
                }
            )

            st.caption(
                "🔴 ▲는 전날보다 순위가 오른 영화, 🔵 ▼는 전날보다 순위가 내려간 영화입니다. "
                "🏆는 누적관객 100만 명을 넘은 영화입니다."
            )

            # 관객수 상위 5편 막대그래프
            st.subheader("📊 관객수 상위 5편")

            top5 = table.sort_values("관객수", ascending=False).head(5)

            st.bar_chart(
                top5.set_index("영화명")["관객수"]
            )

    except Exception as e:
        st.error(str(e))


# ------------------------------------------------------------
# 탭 2. 영화별 관객수 추이
# ------------------------------------------------------------

with tab2:
    st.subheader("🎞️ 영화별 관객수 추이")

    st.info(
        "날짜 범위를 선택하면 해당 기간의 일별 박스오피스 TOP 10에 등장한 영화 목록이 만들어집니다. "
        "그중 영화 제목을 선택하면 그 영화의 일별 관객수 추이를 선그래프로 볼 수 있습니다."
    )

    default_start = yesterday - timedelta(days=6)

    selected_range = st.date_input(
        "조회할 날짜 범위를 선택하세요",
        value=(default_start, yesterday),
        max_value=yesterday,
        help="오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다.",
        key="movie_range"
    )

    if not isinstance(selected_range, tuple) or len(selected_range) != 2:
        st.warning("시작 날짜와 끝 날짜를 모두 선택해 주세요.")

    else:
        start_date, end_date = selected_range

        if start_date > end_date:
            st.warning("시작 날짜가 끝 날짜보다 늦을 수 없습니다.")

        elif end_date > yesterday:
            st.warning("오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다.")

        else:
            # 너무 긴 기간을 한 번에 조회하면 API 요청이 많아질 수 있으므로 제한합니다.
            max_days = 31
            selected_days = (end_date - start_date).days + 1

            if selected_days > max_days:
                st.warning(f"한 번에 최대 {max_days}일까지만 조회할 수 있습니다.")

            else:
                try:
                    with st.spinner("선택한 기간의 박스오피스 데이터를 불러오는 중입니다..."):
                        range_df = make_date_range_dataframe(start_date, end_date)

                    if range_df.empty:
                        st.warning("선택한 기간은 아직 집계 전입니다.")

                    else:
                        # 영화 목록 만들기
                        movie_options_df = (
                            range_df[["movieCd", "movieNm"]]
                            .drop_duplicates()
                            .sort_values("movieNm")
                            .reset_index(drop=True)
                        )

                        # 같은 제목의 영화가 있을 수 있으므로 movieCd를 기준으로 선택합니다.
                        movie_name_count = movie_options_df["movieNm"].value_counts().to_dict()

                        movie_label_dict = {}

                        for _, row in movie_options_df.iterrows():
                            movie_cd = row["movieCd"]
                            movie_nm = row["movieNm"]

                            if movie_name_count.get(movie_nm, 0) > 1:
                                movie_label_dict[movie_cd] = f"{movie_nm} ({movie_cd})"
                            else:
                                movie_label_dict[movie_cd] = movie_nm

                        selected_movie_cd = st.selectbox(
                            "영화 제목을 선택하세요",
                            options=movie_options_df["movieCd"].tolist(),
                            format_func=lambda code: movie_label_dict.get(code, code)
                        )

                        selected_movie_name = movie_label_dict[selected_movie_cd]

                        # 선택한 영화 데이터만 추출
                        movie_df = range_df[range_df["movieCd"] == selected_movie_cd].copy()

                        # 날짜별로 빠진 날짜를 보이게 하기 위해 전체 날짜 틀을 만듭니다.
                        full_date_df = pd.DataFrame({
                            "날짜": pd.date_range(start=start_date, end=end_date, freq="D").date
                        })

                        movie_trend_df = full_date_df.merge(
                            movie_df[
                                [
                                    "날짜",
                                    "movieNm",
                                    "rank",
                                    "audiCnt",
                                    "audiAcc",
                                    "scrnCnt"
                                ]
                            ],
                            on="날짜",
                            how="left"
                        )

                        # TOP 10에 없던 날짜 처리 옵션
                        fill_missing_zero = st.checkbox(
                            "일별 TOP 10에 없던 날짜를 0명으로 표시",
                            value=False,
                            help="체크하지 않으면 TOP 10에 없던 날짜는 선그래프에서 빈 값으로 처리됩니다."
                        )

                        chart_df = movie_trend_df.copy()

                        if fill_missing_zero:
                            chart_df["관객수"] = chart_df["audiCnt"].fillna(0)
                        else:
                            chart_df["관객수"] = chart_df["audiCnt"]

                        chart_df["날짜"] = pd.to_datetime(chart_df["날짜"])

                        actual_df = movie_trend_df.dropna(subset=["audiCnt"]).copy()

                        if actual_df.empty:
                            st.warning("선택한 기간에 해당 영화의 박스오피스 데이터가 없습니다.")

                        else:
                            total_audience = int(actual_df["audiCnt"].sum())
                            max_row = actual_df.sort_values("audiCnt", ascending=False).iloc[0]
                            latest_row = actual_df.sort_values("날짜", ascending=False).iloc[0]

                            c1, c2, c3 = st.columns(3)

                            c1.metric(
                                "기간 내 관객수 합계",
                                f"{total_audience:,}명"
                            )

                            c2.metric(
                                "가장 관객이 많았던 날",
                                max_row["날짜"].strftime("%Y-%m-%d"),
                                f"{int(max_row['audiCnt']):,}명"
                            )

                            c3.metric(
                                "마지막 집계일 순위",
                                f"{int(latest_row['rank'])}위",
                                latest_row["날짜"].strftime("%Y-%m-%d")
                            )

                            st.subheader(f"📈 {selected_movie_name} 관객수 추이")

                            st.line_chart(
                                chart_df.set_index("날짜")["관객수"]
                            )

                            st.caption(
                                "이 그래프는 선택한 기간의 KOBIS 일별 박스오피스 TOP 10 자료를 기준으로 합니다. "
                                "따라서 영화가 TOP 10에 없던 날짜의 실제 관객수는 이 API만으로는 확인되지 않을 수 있습니다."
                            )

                            # 상세 표 표시
                            st.subheader("📋 날짜별 상세 데이터")

                            display_df = movie_trend_df.copy()

                            display_df = display_df.rename(
                                columns={
                                    "rank": "순위",
                                    "audiCnt": "관객수",
                                    "audiAcc": "누적관객",
                                    "scrnCnt": "스크린수"
                                }
                            )

                            display_df = display_df[
                                [
                                    "날짜",
                                    "순위",
                                    "관객수",
                                    "누적관객",
                                    "스크린수"
                                ]
                            ]

                            st.dataframe(
                                display_df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "날짜": st.column_config.DateColumn(
                                        "날짜",
                                        format="YYYY-MM-DD"
                                    ),
                                    "순위": st.column_config.NumberColumn(
                                        "순위",
                                        format="%d위"
                                    ),
                                    "관객수": st.column_config.NumberColumn(
                                        "관객수",
                                        format="%d명"
                                    ),
                                    "누적관객": st.column_config.NumberColumn(
                                        "누적관객",
                                        format="%d명"
                                    ),
                                    "스크린수": st.column_config.NumberColumn(
                                        "스크린수",
                                        format="%d개"
                                    )
                                }
                            )

                except Exception as e:
                    st.error(str(e))
