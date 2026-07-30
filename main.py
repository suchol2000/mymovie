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


# ------------------------------------------------------------
# 탭 구성
# ------------------------------------------------------------

tab1, tab2 = st.tabs([
    "📋 날짜별 박스오피스",
    "📈 기간별 관객수 추이"
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
        help="오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다."
    )

    target_dt = selected_date.strftime("%Y%m%d")

    st.caption(f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}")

    try:
        box_list = get_daily_boxoffice(target_dt)

    except Exception as e:
        st.error(str(e))
        st.stop()

    if not box_list:
        st.warning("그날은 아직 집계 전입니다.")
        st.stop()

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


# ------------------------------------------------------------
# 탭 2. 기간별 관객수 추이
# ------------------------------------------------------------

with tab2:
    st.subheader("📈 기간별 관객수 추이")

    st.info(
        "기간별 관객수 추이는 각 날짜의 박스오피스 TOP 10 영화 관객수를 합산한 값입니다."
    )

    default_start = yesterday - timedelta(days=6)

    selected_range = st.date_input(
        "조회할 날짜 범위를 선택하세요",
        value=(default_start, yesterday),
        max_value=yesterday,
        help="오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다."
    )

    if not isinstance(selected_range, tuple) or len(selected_range) != 2:
        st.warning("시작 날짜와 끝 날짜를 모두 선택해 주세요.")
        st.stop()

    start_date, end_date = selected_range

    if start_date > end_date:
        st.warning("시작 날짜가 끝 날짜보다 늦을 수 없습니다.")
        st.stop()

    if end_date > yesterday:
        st.warning("오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다.")
        st.stop()

    # 너무 긴 기간을 한 번에 조회하면 API 요청이 많아질 수 있으므로 제한합니다.
    max_days = 31
    selected_days = (end_date - start_date).days + 1

    if selected_days > max_days:
        st.warning(f"한 번에 최대 {max_days}일까지만 조회할 수 있습니다.")
        st.stop()

    date_list = pd.date_range(start=start_date, end=end_date, freq="D")

    trend_rows = []

    with st.spinner("기간별 박스오피스 데이터를 불러오는 중입니다..."):
        for date_value in date_list:
            date_obj = date_value.date()
            target_dt = date_obj.strftime("%Y%m%d")

            try:
                daily_box_list = get_daily_boxoffice(target_dt)

            except Exception as e:
                st.error(str(e))
                st.stop()

            if not daily_box_list:
                trend_rows.append({
                    "날짜": date_obj,
                    "관객수": None,
                    "영화수": 0
                })
                continue

            daily_df = make_boxoffice_dataframe(daily_box_list)

            total_audience = daily_df["audiCnt"].sum()

            trend_rows.append({
                "날짜": date_obj,
                "관객수": int(total_audience),
                "영화수": len(daily_df)
            })

    trend_df = pd.DataFrame(trend_rows)

    valid_trend_df = trend_df.dropna(subset=["관객수"]).copy()

    if valid_trend_df.empty:
        st.warning("선택한 기간은 아직 집계 전입니다.")
        st.stop()

    # 요약 지표
    total_period_audience = valid_trend_df["관객수"].sum()
    max_row = valid_trend_df.sort_values("관객수", ascending=False).iloc[0]
    avg_audience = valid_trend_df["관객수"].mean()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "기간 총 관객수",
        f"{int(total_period_audience):,}명"
    )

    c2.metric(
        "가장 관객이 많았던 날",
        max_row["날짜"].strftime("%Y-%m-%d"),
        f"{int(max_row['관객수']):,}명"
    )

    c3.metric(
        "일평균 관객수",
        f"{int(avg_audience):,}명"
    )

    # 선그래프
    st.subheader("📉 일별 관객수 선그래프")

    chart_df = valid_trend_df.copy()
    chart_df["날짜"] = pd.to_datetime(chart_df["날짜"])

    st.line_chart(
        chart_df.set_index("날짜")["관객수"]
    )

    # 기간별 표
    st.subheader("📋 기간별 관객수 표")

    display_trend_df = valid_trend_df.copy()

    st.dataframe(
        display_trend_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "날짜": st.column_config.DateColumn(
                "날짜",
                format="YYYY-MM-DD"
            ),
            "관객수": st.column_config.NumberColumn(
                "관객수",
                format="%d명"
            ),
            "영화수": st.column_config.NumberColumn(
                "집계 영화 수",
                format="%d편"
            )
        }
    )
