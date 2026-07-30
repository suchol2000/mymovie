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
# KOBIS 인증키 가져오기
# ------------------------------------------------------------
# Streamlit Cloud의 Secrets에 아래처럼 저장해 두어야 합니다.
#
# KOBIS_KEY = "발급받은_인증키"
# ------------------------------------------------------------

KOBIS_KEY = st.secrets["KOBIS_KEY"]


# ------------------------------------------------------------
# 날짜 선택
# ------------------------------------------------------------
# 오늘 박스오피스는 아직 집계 전이므로
# 사용자가 고를 수 있는 가장 늦은 날짜는 '어제'입니다.
# ------------------------------------------------------------

today_korea = datetime.now(ZoneInfo("Asia/Seoul")).date()
yesterday = today_korea - timedelta(days=1)

selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday,
    max_value=yesterday,
    help="오늘 자료는 아직 집계 전이므로 어제까지만 선택할 수 있습니다."
)

target_dt = selected_date.strftime("%Y%m%d")

st.caption(f"조회 기준일: {selected_date.strftime('%Y-%m-%d')}")


# ------------------------------------------------------------
# KOBIS 일별 박스오피스 API 요청
# ------------------------------------------------------------

url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

res = requests.get(
    url,
    params={
        "key": KOBIS_KEY,
        "targetDt": target_dt
    },
    timeout=10
)

if res.status_code != 200:
    st.error(f"요청이 실패했습니다. 상태코드: {res.status_code}")
    st.stop()

data = res.json()


# ------------------------------------------------------------
# 인증키 오류 확인
# ------------------------------------------------------------
# KOBIS는 인증키가 틀려도 상태코드 200을 줄 수 있습니다.
# 대신 faultInfo라는 상자가 들어옵니다.
# ------------------------------------------------------------

if "faultInfo" in data:
    st.error("인증키가 올바르지 않습니다. Secrets의 KOBIS_KEY를 확인해 주세요.")
    st.stop()


# ------------------------------------------------------------
# 박스오피스 목록 꺼내기
# ------------------------------------------------------------

box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

if not box_list:
    st.warning("그날은 아직 집계 전입니다.")
    st.stop()


# ------------------------------------------------------------
# 데이터프레임 만들기
# ------------------------------------------------------------

df = pd.DataFrame(box_list)


# ------------------------------------------------------------
# 글자로 온 숫자들을 진짜 숫자로 바꾸기
# ------------------------------------------------------------
# KOBIS API의 값들은 대부분 문자열로 들어옵니다.
# 계산과 정렬을 위해 숫자로 바꿔 줍니다.
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# 순위 증감 표시 만들기
# ------------------------------------------------------------
# rankInten:
# 양수면 전날보다 순위가 오른 것
# 음수면 전날보다 순위가 내려간 것
# 0이면 변동 없음
# ------------------------------------------------------------

def make_rank_change_text(row):
    rank_inten = row["rankInten"]

    # KOBIS에는 신작 여부를 알려 주는 rankOldAndNew 값도 있습니다.
    # NEW이면 새로 진입한 영화로 표시합니다.
    if row.get("rankOldAndNew", "") == "NEW":
        return "NEW"

    if rank_inten > 0:
        return f"🔴 ▲ {rank_inten}"

    if rank_inten < 0:
        return f"🔵 ▼ {abs(rank_inten)}"

    return "—"


df["순위증감"] = df.apply(make_rank_change_text, axis=1)


# ------------------------------------------------------------
# 누적관객 100만 명 이상 영화에 트로피 붙이기
# ------------------------------------------------------------

df["영화명표시"] = df.apply(
    lambda row: f"{row['movieNm']} 🏆" if row["audiAcc"] > 1_000_000 else row["movieNm"],
    axis=1
)


# ------------------------------------------------------------
# 순위 기준으로 정렬
# ------------------------------------------------------------

df = df.sort_values("rank").reset_index(drop=True)


# ------------------------------------------------------------
# 1위 영화 지표 카드
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# 표를 한국어 열 이름으로 정리
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# 박스오피스 표 표시
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# 관객수 상위 5편 막대그래프
# ------------------------------------------------------------

st.subheader("📈 관객수 상위 5편")

top5 = table.sort_values("관객수", ascending=False).head(5)

st.bar_chart(
    top5.set_index("영화명")["관객수"]
)


# ------------------------------------------------------------
# 안내 문구
# ------------------------------------------------------------

st.caption(
    "🔴 ▲는 전날보다 순위가 오른 영화, 🔵 ▼는 전날보다 순위가 내려간 영화입니다. "
    "🏆는 누적관객 100만 명을 넘은 영화입니다."
)
