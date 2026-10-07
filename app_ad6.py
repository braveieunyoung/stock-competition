# =========================================================
# 필요한 라이브러리(패키지) 불러오기
# =========================================================
import streamlit as st            # 웹 애플리케이션 UI 생성을 위한 라이브러리
import pandas as pd               # 데이터 프레임(표 형태 데이터) 처리 및 분석용 라이브러리
import requests                   # 웹 서버에 HTTP 요청을 보내기 위한 라이브러리 (크롤링/API용)
from bs4 import BeautifulSoup     # HTML 웹 페이지 파싱(분석)용 라이브러리
from datetime import datetime     # 날짜 및 시간 처리용 라이브러리
import yfinance as yf             # 야후 파이낸스 주식 데이터 수집용 라이브러리
import plotly.graph_objects as go # Plotly 인터랙티브 차트(캔들차트 등) 생성용
import plotly.express as px       # Plotly 간편 선 그래프 생성용
from sqlalchemy import create_engine, text # PostgreSQL DB 연결 및 SQL 쿼리 실행용


# ---------------------------------------------------------
# 1. DB 연결 및 환율, 시세 조회 함수 설정
# ---------------------------------------------------------

# @st.cache_resource: DB 연결 객체처럼 앱 전체에서 재사용해야 하는 자원을 캐싱(저장)하여 재연결 비용 절감
@st.cache_resource
def get_db_engine():
    """Streamlit Secrets에서 DB 접속 정보를 가져와 SQLAlchemy Engine을 생성하는 함수"""
    db_url = st.secrets["database"]["url"]
    
    # SQLAlchemy 최신 버전 호환성을 위해 접속 주소의 드라이버 명칭 변경 (postgresql -> postgresql+psycopg2)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return create_engine(
        db_url,
        pool_pre_ping=True,      # 끊어진 연결(Connection)을 자동으로 감지하고 재접속
        pool_recycle=300,        # 5분(300초)마다 연결을 자동으로 재생성하여 커넥션 타임아웃 방지
        connect_args={"sslmode": "require", "connect_timeout": 10}, # SSL 보안 연결 및 10초 타임아웃 설정
    )

# DB 연결 엔진 객체 생성
engine = get_db_engine()


# @st.cache_data: 데이터 조회 결과를 일정 시간(ttl=300초) 동안 저장하여 반복적인 API 요청을 줄임
@st.cache_data(ttl=300, show_spinner=False)
def get_exchange_rate():
    """실시간 달러/원(USD/KRW) 환율을 가져오는 함수 (실패 시 기본값 1350.0원 반환)"""
    try:
        ticker = yf.Ticker("USDKRW=X")
        # 최근 시장가(lastPrice) 조회 시도
        rate = ticker.fast_info.get('lastPrice', None)
        if not rate:
            # fast_info 조회 실패 시 1일 차트 종가 가져오기
            df = ticker.history(period="1d")
            if not df.empty:
                rate = float(df['Close'].iloc[-1])
        if rate and rate > 0:
            return float(rate)
    except Exception:
        pass
    return 1350.0       # 환율 조회 실패 시 사용할 예비(Fallback) 환율값


# 거래 가능한 종목 리스트 사전 (종목명: yfinance/네이버 심볼)
STOCKS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "NAVER": "035420.KS",
    "현대차": "005380.KS",
    "LG에너지솔루션": "373220.KS",
    "셀트리온": "068270.KS",
    "기아": "000270.KS",
    "한화오션": "042660.KS",
    "POSCO홀딩스": "005490.KS",
    "KODEX200(ETF)": "069500.KS",
    "KODEX 미국S&P500(ETF)": "379800.KS",
    "KODEX 미국나스닥100(ETF)": "379810.KS",
    "에코프로비엠 (코스닥)": "247540.KQ",
    "애플 (미국)": "AAPL",
    "테슬라 (미국)": "TSLA",
    "엔비디아 (미국)": "NVDA"
}


@st.cache_data(ttl=30, show_spinner=False)
def get_current_price(symbol):
    """
    주식 종목 심볼을 받아 현재가를 원화(KRW) 기준으로 가져오는 함수 (30초 캐싱)
    국내주식: 네이버 모바일 API -> 네이버 크롤링 -> yfinance 순으로 시도
    미국주식: yfinance 조회 후 실시간 환율을 곱해 원화로 변환
    """
    # 심볼에서 확장자(.KS, .KQ) 제거
    clean_symbol = symbol.replace('.KS', '').replace('.KQ', '').strip()
    
    # 1. 국내 주식인 경우 (숫자로만 이루어진 코드)
    if clean_symbol.isdigit():
        headers = {'User-Agent': 'Mozilla/5.0'} # 웹 크롤링 차단 방지용 차단 해제 헤더
        
        # 1차 시도: 네이버 금융 모바일 API (가장 빠름)
        try:
            url_api = f"https://m.stock.naver.com/api/stock/{clean_symbol}/basic"
            res = requests.get(url_api, headers=headers, timeout=2)
            if res.status_code == 200:
                val = res.json().get('nowVal', '').replace(',', '')
                if val and float(val) > 0:
                    return float(val)
        except Exception:
            pass

        # 2차 시도: 네이버 금융 PC 웹 페이지 파싱 (크롤링)
        try:
            url_web = f"https://finance.naver.com/item/main.naver?code={clean_symbol}"
            res = requests.get(url_web, headers=headers, timeout=2)
            soup = BeautifulSoup(res.text, 'html.parser')
            price_tag = soup.select_one('p.no_today span.blind')
            if price_tag:
                val = float(price_tag.text.replace(',', ''))
                if val > 0:
                    return val
        except Exception:
            pass

        # 3차 시도: yfinance 백업 데이터 가져오기
        try:
            ticker = yf.Ticker(f"{clean_symbol}.KS")
            df = ticker.history(period="1d")
            if not df.empty:
                val = float(df['Close'].iloc[-1])
                if val > 0:
                    return val
        except Exception:
            pass

    # 2. 해외 주식인 경우 (문자로 구성된 티커: AAPL, TSLA 등)
    else:
        try:
            ticker = yf.Ticker(symbol)
            price_usd = ticker.fast_info.get('lastPrice', None)
            if not price_usd:
                df = ticker.history(period="1d")
                if not df.empty:
                    price_usd = float(df['Close'].iloc[-1])
            if price_usd and price_usd > 0:
                exchange_rate = get_exchange_rate()  # 실시간 달러 환율 적용하여 원화로 계산
                return float(price_usd * exchange_rate)
        except Exception:
            pass
            
    return 0.0 # 시세 조회 실패 시 0 반환


@st.cache_data(ttl=300, show_spinner=False)
def get_stock_history(symbol):
    """최근 3개월간의 주가 과거 데이터를 가져오는 함수 (미국 주식은 환율 반영)"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo") # 3개월 주가 내역 요청
        if not df.empty:
            clean_symbol = symbol.replace('.KS', '').replace('.KQ', '').strip()
            # 해외 주식인 경우 과거 OHLC(시가,고가,저가,종가) 데이터 전체에 환율을 곱해 원화로 변경
            if not clean_symbol.isdigit():
                exchange_rate = get_exchange_rate()
                for col in ['Open', 'High', 'Low', 'Close']:
                    df[col] = df[col] * exchange_rate
            return df.reset_index()
    except Exception:
        pass
    return pd.DataFrame()


def analyze_stock_indicators(df):
    """주가 과거 데이터를 바탕으로 MA 교차, RSI, 볼린저밴드 지표를 계산해 투자 팁을 생성하는 함수"""
    if len(df) < 20:
        return None

    df_calc = df.copy()

    # 1. 이동평균선 계산 (5일, 20일)
    df_calc['MA5'] = df_calc['Close'].rolling(window=5).mean()
    df_calc['MA20'] = df_calc['Close'].rolling(window=20).mean()

    # 2. RSI (상대강도지수, 14일 기준) 계산
    delta = df_calc['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_calc['RSI'] = 100 - (100 / (1 + rs))

    # 3. 볼린저 밴드 계산 (20일 이동평균, 표준편차 2배수)
    df_calc['BB_Middle'] = df_calc['MA20']
    std = df_calc['Close'].rolling(window=20).std()
    df_calc['BB_Upper'] = df_calc['BB_Middle'] + (std * 2)
    df_calc['BB_Lower'] = df_calc['BB_Middle'] - (std * 2)

    latest = df_calc.iloc[-1]

    tips = []
    signal_score = 0      # 매수(+)/매도(-) 점수

    # [분석 1] 이동평균선 추세
    if latest['MA5'] >= latest['MA20']:
        tips.append(("success", "**이동평균선(상승 추세)**: 5일선이 20일선 위에 위치하여 단기 상승 흐름을 유지하고 있습니다."))
        signal_score += 1
    else:
        tips.append(("warning", "**이동평균선(하락 추세)**: 5일선이 20일선 아래에 위치하여 단기 조정/하락 흐름에 있습니다."))
        signal_score -= 1

    # [분석 2] RSI (상대강도지수)
    rsi_val = latest['RSI']
    if pd.notna(rsi_val):
        if rsi_val <= 30:
            tips.append(("info", f"**RSI 과매도 ({rsi_val:.1f})**: 주가가 과도하게 하락하여 단기 반등(저점 매수 기회)을 기대해볼 수 있습니다."))
            signal_score += 1
        elif rsi_val >= 70:
            tips.append(("warning", f"**RSI 과매수 ({rsi_val:.1f})**: 단기 급등으로 주가가 과열되어 차익 실현 및 조정 가능성이 있습니다."))
            signal_score -= 1
        else:
            tips.append(("secondary", f"**RSI 중립 ({rsi_val:.1f})**: 과열이나 과매도 없이 안정적인 세를 유지하고 있습니다."))

    # [분석 3] 볼린저 밴드
    close_val = latest['Close']
    upper_val = latest['BB_Upper']
    lower_val = latest['BB_Lower']
    
    if close_val >= upper_val:
        tips.append(("warning", "**볼린저 밴드**: 주가가 상한 변동 폭 최상단에 도달하여 단기 저항을 받을 수 있습니다."))
        signal_score -= 1
    elif close_val <= lower_val:
        tips.append(("info", "**볼린저 밴드**: 주가가 하한 변동 폭 최하단에 도달하여 기술적 반등 가능성이 있습니다."))
        signal_score += 1
    else:
        tips.append(("secondary", "**볼린저 밴드**: 주가가 정상 변동 범위 내부에서 움직이고 있습니다."))

    # [분석 4] 종합 판단
    if signal_score >= 1:
        tips.append(("success", "**종합 판단**: 상승 전환 가능성이 높거나 저점 매수 기회로 해석되는 구간입니다."))
    elif signal_score <= -1:
        tips.append(("warning", "**종합 판단**: 하락 추세 또는 과열 위험이 존재하므로 관망 및 신중한 매수를 권장합니다."))
    else:
        tips.append(("secondary", "**종합 판단**: 지표별 신호가 상충하거나 중립 상태이므로 명확한 방향성이 나올 때까지 관망하세요."))

    return tips


# ---------------------------------------------------------
# 2. 페이지 기본 설정 및 Custom CSS 적용
# ---------------------------------------------------------
# Streamlit 웹 페이지 제목 및 레이아웃 설정 (wide: 화면 전체 넓이 사용)
st.set_page_config(page_title="모의주식 투자", layout="wide")

# 가시성을 높이기 위해 폰트 크기를 키우는 CSS 스타일 주입
st.markdown("""
    <style>
        /* 매수/매도 버튼 스타일 강화 (버튼 느낌 극대화) */
        div[data-testid="stButton"] > button {
            background-color: #4A5568 !important; /* 선명한 다크 그레이 배경 */
            color: white !important;               /* 글자색 흰색 */
            font-weight: bold !important;
            border-radius: 8px !important;         /* 둥근 테두리 */
            border: none !important;
            padding: 10px 20px !important;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important; /* 입체감 그림자 */
            transition: all 0.2s ease-in-out !important;
        }
        
        /* 마우스 호버(Hover) 시 효과 */
        div[data-testid="stButton"] > button:hover {
            background-color: #2D3748 !important; /* 더 진한 회색 */
            transform: translateY(-2px);           /* 살짝 떠오르는 효과 */
            box-shadow: 0 6px 8px rgba(0, 0, 0, 0.15) !important;
        }
    </style>
""", unsafe_allow_html=True)

# 세션 상태(Session State)에 사용자 로그인 정보 변수 초기화
if "user" not in st.session_state:
    st.session_state.user = None


# ---------------------------------------------------------
# 3. 관리자 전용 대시보드 화면 정의
# ---------------------------------------------------------
def render_admin_dashboard():
    """관리자(admin) 계정으로 접속 시 표시되는 관리자 전용 화면"""
    st.title("⚙ 관리자 전용 대시보드")
    st.info("관리자로 로그인되었습니다. 학생 명단 관리 및 초기 설정을 진행할 수 있습니다.")

    # 관리자 기능 탭 3개 생성
    tab1, tab2, tab3 = st.tabs(["📊 전체 랭킹 및 데이터", "💰 시드 머니 관리", "👥 학생 명단 & CSV 업로드"])

    # TAB 1: 랭킹 및 데이터 다운로드 + 개별 학생 포트폴리오 상세 조회
    with tab1:
        st.subheader("🏆 전체 참가자 실시간 데이터")
        if st.button("🔄 랭킹 새로고침", key="admin_rank_refresh"):
            st.rerun()
        
        all_users = pd.read_sql(
            text("SELECT student_id, name, cash, COALESCE(init_cash, 10000000) as init_cash FROM users WHERE student_id != 'admin'"), 
            engine
        )
        
        admin_leaderboard = []
        for _, u in all_users.iterrows():
            u_id, u_name = u['student_id'], u['name']
            u_cash = float(u['cash'])
            u_init_cash = float(u['init_cash']) if float(u['init_cash']) > 0 else 10000000.0
            
            u_port = pd.read_sql(text("SELECT symbol, quantity FROM portfolio WHERE student_id = :student_id"), engine, params={"student_id": u_id})
            u_stock_eval = 0
            if not u_port.empty:
                for _, row in u_port.iterrows():
                    p = get_current_price(row['symbol'])
                    u_stock_eval += p * int(row['quantity'])
                
            u_total_assets = u_cash + u_stock_eval
            u_return = ((u_total_assets - u_init_cash) / u_init_cash) * 100
            
            admin_leaderboard.append({
                "학번": u_id,
                "이름": u_name,
                "보유 예수금 (원)": round(u_cash),
                "총 자산 (원)": round(u_total_assets),
                "수익률 (%)": round(u_return, 2)
            })

        if admin_leaderboard:
            df_admin_lb = pd.DataFrame(admin_leaderboard).sort_values(by=["수익률 (%)","총 자산 (원)"], ascending=False).reset_index(drop=True)
            df_admin_lb.index += 1

            st.dataframe(
                df_admin_lb, 
                use_container_width=True,
                column_config={
                    "학번": st.column_config.TextColumn("학번"),
                    "이름": st.column_config.TextColumn("이름"),
                    "보유 예수금 (원)": st.column_config.NumberColumn("보유 예수금 (원)", format="%,d"),
                    "총 자산 (원)": st.column_config.NumberColumn("총 자산 (원)", format="%,d"),
                    "수익률 (%)": st.column_config.NumberColumn("수익률 (%)", format="%.2f%%")
                }
            )

            # CSV 다운로드 버튼 (BOM 포함 바이트 스트림 적용으로 엑셀 한글 깨짐 방지)
            csv_bytes = df_admin_lb.to_csv(index=True, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📥 랭킹 데이터 CSV 다운로드",
                data=csv_bytes,
                file_name=f"student_ranks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

            st.divider()

            # --- 🔍 학생별 투자 종목 리스트 상세 조회 영역 ---
            st.subheader("🔍 개별 학생 투자 포트폴리오 상세 조회")
            
            # 드롭다운 옵션 생성 (예: "10101 (김철수)")
            student_list_opts = {f"{row['학번']} ({row['이름']})": row['학번'] for _, row in df_admin_lb.iterrows()}
            selected_student_label = st.selectbox("포트폴리오를 조회할 학생 선택", list(student_list_opts.keys()))
            selected_student_id = student_list_opts[selected_student_label]

            # 선택한 학생의 포트폴리오 정보 불러오기
            selected_port = pd.read_sql(
                text("SELECT symbol, stock_name, quantity, buy_price FROM portfolio WHERE student_id = :s_id AND quantity > 0"),
                engine,
                params={"s_id": selected_student_id}
            )

            if not selected_port.empty:
                selected_port['현재가'] = selected_port['symbol'].apply(get_current_price)
                selected_port['평가금액'] = selected_port['quantity'] * selected_port['현재가']
                selected_port['평가손익'] = selected_port['평가금액'] - (selected_port['quantity'] * selected_port['buy_price'])
                selected_port['수익률(%)'] = (selected_port['평가손익'] / (selected_port['quantity'] * selected_port['buy_price'])) * 100

                # 보기 좋게 가공
                display_port = selected_port[['stock_name', 'symbol', 'quantity', 'buy_price', '현재가', '평가금액', '평가손익', '수익률(%)']].copy()
                display_port.columns = ['종목명', '종목코드', '보유수량', '평균매수가', '현재가', '평가금액', '평가손익', '수익률(%)']

                st.dataframe(
                    display_port,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "보유수량": st.column_config.NumberColumn(format="%,d 주"),
                        "평균매수가": st.column_config.NumberColumn(format="%,d 원"),
                        "현재가": st.column_config.NumberColumn(format="%,d 원"),
                        "평가금액": st.column_config.NumberColumn(format="%,d 원"),
                        "평가손익": st.column_config.NumberColumn(format="%,d 원"),
                        "수익률(%)": st.column_config.NumberColumn(format="%.2f%%")
                    }
                )
            else:
                st.info(f"💡 {selected_student_label} 학생은 현재 보유 중인 주식이 없습니다 (전액 예수금 보유 중).")

        else:
            st.info("등록된 학생 회원이 없습니다.")

    # -----------------------------------------------------
    # TAB 2: 시드 머니(예수금) 관리
    # -----------------------------------------------------
    with tab2:
        st.subheader("💵 시드 머니 지급 및 수정")
        col_m1, col_m2 = st.columns(2)
        all_students = pd.read_sql(text("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'"), engine)
    
        # 개별 학생 예수금 추가
        with col_m1:
            st.markdown("### 👤 개별 학생 예수금 수정")
            if not all_students.empty:
                student_options = {f"{row['student_id']} ({row['name']})": row['student_id'] for _, row in all_students.iterrows()}
                selected_label = st.selectbox("학생 선택", list(student_options.keys()))
                target_id = student_options[selected_label]
                
                curr_cash = float(all_students[all_students['student_id'] == target_id]['cash'].values[0])
                st.caption(f"현재 예수금: **{int(curr_cash):,} 원**")
        
                add_cash = st.number_input("추가할 예수금 (원)", min_value=0, step=100000, key="individual_add_cash")
                
                final_cash = int(curr_cash + add_cash)
                st.caption(f"수정 후 예상 예수금: **{final_cash:,} 원**")
        
                # 콜백 함수: 버튼 클릭 시 DB의 개별 학생 현금 데이터 수정
                def update_individual_cash():
                    val = st.session_state.individual_add_cash
                    if val > 0:
                        with engine.begin() as conn: # 트랜잭션 처리
                            conn.execute(
                                text("UPDATE users SET cash = cash + :add_cash WHERE student_id = :student_id"),
                                {"add_cash": val, "student_id": target_id}
                            )
                        st.session_state.individual_add_cash = 0
                        st.toast(f"예수금이 추가되었습니다. (최종 예수금: {curr_cash + val:,.0f}원)")
    
                st.button("개별 금액 설정 완료", type="primary", on_click=update_individual_cash)

        # 전체 학생 예수금 일괄 추가
        with col_m2:
            st.markdown("### 📢 전체 학생 일괄 추가 지급")
            add_cash_val = st.number_input("전체 추가 지급 금액(원)", min_value=0, step=100000, value=1000000)
            if st.button("전체 일괄 지급 실행"):
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE users SET cash = cash + :add_cash WHERE student_id != 'admin'"),
                        {"add_cash": add_cash_val}
                    )
                st.success(f"모든 학생에게 {add_cash_val:,} 원이 일괄 지급되었습니다.")
                st.rerun()

    # -----------------------------------------------------
    # TAB 3: CSV 업로드 및 학생 명단 관리
    # -----------------------------------------------------
    with tab3:
        st.subheader("📁 CSV 파일로 학생 명단 일괄 등록")
        
        # CSV 샘플 데이터 다운로드 기능
        sample_df = pd.DataFrame([
            {"학번": "10101", "이름": "김철수", "비밀번호": "1234", "시드머니": 10000000},
            {"학번": "10102", "이름": "이영희", "비밀번호": "", "시드머니": 10000000}
        ])
        sample_csv = sample_df.to_csv(index=False).encode('cp949', errors='ignore')
        st.download_button("📄 업로드 샘플 CSV 다운로드", sample_csv, "student_sample.csv", "text/csv")

        # 파일 업로더
        uploaded_file = st.file_uploader("CSV 파일을 선택하세요 (필수 열: 학번, 이름 / 선택 열: 비밀번호, 시드머니)", type=["csv"])
        
        if uploaded_file is not None:
            try:
                # UTF-8 또는 CP949(EUC-KR) 인코딩 자동 처리
                try:
                    df_upload = pd.read_csv(uploaded_file, dtype={'학번': str, '비밀번호': str}, encoding='utf-8-sig')
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    df_upload = pd.read_csv(uploaded_file, dtype={'학번': str, '비밀번호': str}, encoding='cp949')

                st.write("📋 미리보기:", df_upload.head())
                
                if st.button("🚀 DB에 명단 일괄 등록하기", type="primary"):
                    added_count = 0
                    updated_count = 0
                    
                    with engine.begin() as conn:
                        for _, row in df_upload.iterrows():
                            s_id = str(row['학번']).strip()
                            s_name = str(row['이름']).strip()
                            s_pw = str(row['비밀번호']).strip() if pd.notna(row.get('비밀번호')) and str(row.get('비밀번호')).strip() != 'nan' else ""
                            
                            s_cash = float(row['시드머니']) if '시드머니' in row and pd.notna(row['시드머니']) else 10000000.0
                            is_reg = 1 if s_pw else 0 # 비밀번호가 미리 존재하면 가입 완료 처리

                            # 이미 존재하는 학번이면 UPDATE, 신규 학번이면 INSERT
                            res = conn.execute(text("SELECT student_id FROM users WHERE student_id = :s_id"), {"s_id": s_id}).fetchone()
                            if res:
                                conn.execute(text("UPDATE users SET name = :name, password = :pw, cash = :cash, is_registered = :is_reg WHERE student_id = :s_id"),
                                    {"name": s_name, "pw": s_pw, "cash": s_cash, "is_reg": is_reg, "s_id": s_id}
                                )
                                updated_count += 1
                            else:
                                conn.execute(
                                    text("INSERT INTO users (student_id, name, cash, init_cash, password, is_registered) VALUES (:s_id, :name, :cash, :init_cash, :pw, :is_reg)"),
                                    {"s_id": s_id, "name": s_name, "cash": s_cash, "init_cash": s_cash, "pw": s_pw, "is_reg": is_reg}
                                )
                                added_count += 1
                    
                    st.success(f"완료! 신규 등록: {added_count}명 / 정보 갱신: {updated_count}명")
                    st.rerun()
            except Exception as e:
                st.error(f"CSV 파일 처리 중 오류가 발생했습니다: {e}")

        st.divider()
        st.subheader("➕ 개별 신규 학생 등록")
        
        # 단일 학생 직접 등록 폼
        with st.form("single_student_form"):
            new_student_id = st.text_input("학번 (예: 10101)").strip()
            new_name = st.text_input("이름").strip()
            new_pw = st.text_input("비밀번호 (선택사항)", type="password").strip() 
            new_cash_input = st.number_input("시드머니 (원)", min_value=0, value=10000000, step=1000000)
            
            is_reg = 1 if new_pw else 0
            submitted = st.form_submit_button("학생 추가", type="primary")

            if submitted:
                if not new_student_id or not new_name:
                    st.error("학번과 이름을 모두 입력해주세요.")
                else:
                    try:
                        is_success = False
                        with engine.begin() as conn:
                            check_user = conn.execute(
                                text("SELECT student_id FROM users WHERE student_id = :s_id"), 
                                {"s_id": new_student_id}
                            ).fetchone()

                            if check_user:
                                st.error("이미 존재하는 학번입니다.")
                            else:
                                conn.execute(
                                    text("""
                                        INSERT INTO users (student_id, name, cash, init_cash, password, is_registered) 
                                        VALUES (:s_id, :name, :cash, :init_cash, :pw, :is_reg)
                                    """),
                                    {
                                        "s_id": new_student_id, 
                                        "name": new_name, 
                                        "cash": float(new_cash_input), 
                                        "init_cash": float(new_cash_input),
                                        "pw": new_pw, 
                                        "is_reg": is_reg
                                    }
                                )
                                is_success = True

                        if is_success:
                            st.success(f"학생 {new_name}({new_student_id})이 성공적으로 등록되었습니다!")
                            st.rerun()

                    except Exception as e:
                        st.error(f"등록 중 오류가 발생했습니다: {e}")
        
        st.divider()
        st.subheader("👥 등록된 학생 명단 및 회원 관리")
        
        # 전체 학생 목록 출력
        all_users = pd.read_sql(
            text("SELECT student_id, name, cash, is_registered FROM users WHERE student_id != 'admin' ORDER BY student_id ASC"), 
            engine
        )
        
        if not all_users.empty:
            user_list = []
            for _, row in all_users.iterrows():
                s_id = row['student_id']
                s_name = row['name']
                s_cash = float(row['cash'])
                is_reg = "등록 완료" if str(row['is_registered']) == "1" else "미등록(최초로그인 대기)"
                
                u_port = pd.read_sql(
                    text("SELECT symbol, quantity FROM portfolio WHERE student_id = :s_id"), 
                    engine, 
                    params={"s_id": s_id}
                )
                stock_eval = 0.0
                if not u_port.empty:
                    for _, p_row in u_port.iterrows():
                        stock_eval += get_current_price(p_row['symbol']) * int(p_row['quantity'])
                
                total_assets = s_cash + stock_eval
                
                user_list.append({
                    "학번": s_id,
                    "이름": s_name,
                    "예수금 (원)": f"{int(round(s_cash)):,} 원",
                    "총자산 (원)": f"{int(round(total_assets)):,} 원",
                    "가입여부": is_reg
                })
            
            df_manage = pd.DataFrame(user_list)
            st.dataframe(df_manage, use_container_width=True, hide_index=True)
        else:
            st.info("등록된 학생이 없습니다.")

        # 비밀번호 초기화 및 계정 삭제 기능
        col_reset, col_del = st.columns(2)
        
        del_students = pd.read_sql(text("SELECT student_id, name FROM users WHERE student_id != 'admin'"), engine)
        reset_options = {f"{row['student_id']} ({row['name']})": row['student_id'] for _, row in del_students.iterrows()}
            
        if reset_options:
            # 1. 비밀번호 초기화
            with col_reset:
                st.markdown("### 🔑 비밀번호 초기화")
                reset_label = st.selectbox("초기화할 학생 선택", list(reset_options.keys()))
                reset_target_id = reset_options[reset_label]
                
                if st.button("비밀번호 초기화 실행"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE users SET password = '', is_registered = 0 WHERE student_id = :s_id"), {"s_id": reset_target_id})
                    st.success("비밀번호가 초기화되었습니다. 재로그인 시 신규 비밀번호를 입력합니다.")
                    st.rerun()
        
            # 2. 계정 삭제
            with col_del:
                st.markdown("### ❌ 계정 삭제")
                del_label = st.selectbox("삭제할 학생 선택", list(reset_options.keys()), key="del_select")
                del_target_id = reset_options[del_label]
                
                if st.button("선택한 학생 삭제", type="primary"):
                    with engine.begin() as conn:
                        # 학생 정보 및 해당 학생의 주식 보유 잔고(portfolio) 삭제
                        conn.execute(text("DELETE FROM users WHERE student_id = :s_id"), {"s_id": del_target_id})
                        conn.execute(text("DELETE FROM portfolio WHERE student_id = :s_id"), {"s_id": del_target_id})

                    st.warning("학생 명단 및 투자 데이터가 삭제되었습니다.")
                    st.rerun()
        else:
            st.info("비밀번호 초기화 및 삭제할 학생 계정이 없습니다.")


# ---------------------------------------------------------
# 4. 로그인 및 인증 로직 (라우팅)
# ---------------------------------------------------------
if st.session_state.get('user') is None:
    st.title("📈 학생 모의주식 투자 대회")
    st.subheader("로그인하여 가상 투자에 참여하세요!")

    col1, col2 = st.columns(2)
    with col1:
        student_id = st.text_input("학번 (관리자: admin)", max_chars=10)
        name = st.text_input("이름 (관리자인 경우 생략 가능)")
        password = st.text_input("비밀번호", type="password")
        login_button = st.button("로그인 / 접속하기", type="primary")

    if login_button:
        s_id = student_id.strip()
        s_name = name.strip()
        s_pw = password.strip()

        # A. 관리자(admin) 로그인
        if s_id.lower() == "admin":
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password FROM users WHERE student_id = 'admin'")).fetchone()
                admin_pw = res[0] if res else ""

            if s_pw == admin_pw:
                st.session_state['user'] = {"student_id": "admin", "name": "관리자"}
                st.rerun()
            else:
                st.error("관리자 비밀번호가 올바르지 않습니다.")

        # B. 학생 사용자 로그인
        else:
            if not s_id or not s_name or not s_pw:
                st.warning("학번, 이름, 비밀번호를 모두 입력해 주세요.")
            else:
                with engine.connect() as conn:
                    user_row = conn.execute(
                        text("SELECT name, password, is_registered FROM users WHERE student_id = :s_id"),
                        {"s_id": s_id}
                    ).fetchone()

                if not user_row:
                    st.error("❌ 등록되지 않은 학번입니다. 선생님(관리자)에게 명단 등록을 요청하세요.")
                else:
                    db_name, db_pw, is_reg = user_row[0], user_row[1], user_row[2]

                    if db_name != s_name:
                        st.error("학번과 이름이 일치하지 않습니다!")

                    # 최초 로그인인 경우: 사용자가 입력한 비밀번호를 회원 비밀번호로 자동 저장
                    elif is_reg == 0:
                        with engine.begin() as conn:
                            conn.execute(
                                text("UPDATE users SET password = :pw, is_registered = 1 WHERE student_id = :s_id"),
                                {"pw": s_pw, "s_id": s_id}
                            )
                        st.success("🎉 최초 로그인 완료! 입력하신 비밀번호로 설정되었습니다.")
                        st.session_state['user'] = {"student_id": s_id, "name": db_name}
                        st.rerun()

                    # 기존 가입자의 경우: 비밀번호 검증
                    else:
                        if db_pw == s_pw:
                            st.session_state['user'] = {"student_id": s_id, "name": db_name}
                            st.rerun()
                        else:
                            st.error("비밀번호가 올바르지 않습니다.")


# ---------------------------------------------------------
# 5. 학생 메인 화면 (로그인 후)
# ---------------------------------------------------------
else:
    user_id = st.session_state.user["student_id"]
    user_name = st.session_state.user["name"]

    # 상단 헤더 영역 (사용자 환영 인사 및 로그아웃 버튼)
    top_col1, top_col2 = st.columns([5, 1])
    with top_col1:
        st.title(f"🏆 {user_name} ({user_id}) 님의 대시보드")
    with top_col2:
        st.write("")
        if st.button("로그아웃", width="stretch"):
            st.session_state.user = None # 세션 정보 삭제
            st.rerun()

    # 로그인한 사용자가 관리자인 경우 관리자 화면 출력
    if user_id == "admin":
        render_admin_dashboard()

    # [B] 학생 모드 (포트폴리오 / 주문 및 분석 / 랭킹)
    else:
        # DB에서 예수금(cash)과 초기 시드머니(init_cash)를 함께 조회
        with engine.connect() as conn:
            user_row = conn.execute(
                text("SELECT cash, COALESCE(init_cash, 10000000) as init_cash FROM users WHERE student_id = :s_id"),
                {"s_id": user_id}
            ).fetchone()

        if user_row:
            cash = float(user_row[0])
            init_cash = float(user_row[1]) if float(user_row[1]) > 0 else 10000000.0
        else:
            cash = 10000000.0
            init_cash = 10000000.0

        portfolio_df = pd.read_sql(text("SELECT symbol, stock_name, quantity, buy_price FROM portfolio WHERE student_id = :s_id AND quantity > 0"), engine, params={"s_id": user_id})

        # 3개 탭 구성
        tab1, tab2, tab3 = st.tabs(["💼 내 포트폴리오", "📈 주문", "🥇 실시간 랭킹"])

        # =========================================================
        # TAB 1: 내 포트폴리오 (자산 현황 + 보유 종목 리스트)
        # =========================================================
        with tab1:
            st.subheader("💼 내 보유 자산 현황")
            total_eval = cash # 총 평가 자산의 초기값 = 보유 현금

            if not portfolio_df.empty:
                # 보유 주식의 실시간 평가 금액 계산
                portfolio_df['현재가'] = portfolio_df['symbol'].apply(get_current_price)
                portfolio_df['평가금액'] = portfolio_df['quantity'] * portfolio_df['현재가']
                portfolio_df['평가손익'] = portfolio_df['평가금액'] - (portfolio_df['quantity'] * portfolio_df['buy_price'])
                portfolio_df['수익률(%)'] = (portfolio_df['평가손익'] / (portfolio_df['quantity'] * portfolio_df['buy_price'])) * 100
                
                total_eval += portfolio_df['평가금액'].sum() # 총 자산 = 현금 + 주식 평가액 합계
                
            # 자산 요약 메트릭 카드
            cum_return = ((total_eval - init_cash) / init_cash) * 100
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("총 평가 자산", f"{total_eval:,.0f} 원")
            col_p2.metric("예수금 (현금)", f"{cash:,.0f} 원")
            col_p3.metric("누적 수익률", f"{cum_return:+.2f} %")

            st.divider()

            # --- 보유 종목 리스트 (표 형태) ---
            st.subheader("📋 내 보유 종목 리스트")
            if not portfolio_df.empty:
                display_df = portfolio_df[['stock_name', 'symbol', 'quantity', 'buy_price', '현재가', '평가금액', '평가손익', '수익률(%)']].copy()
                display_df.columns = ['종목명', '종목코드', '보유수량', '평균매수가', '현재가', '평가금액', '평가손익', '수익률(%)']

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "보유수량": st.column_config.NumberColumn(format="%,d 주"),
                        "평균매수가": st.column_config.NumberColumn(format="%,d 원"),
                        "현재가": st.column_config.NumberColumn(format="%,d 원"),
                        "평가금액": st.column_config.NumberColumn(format="%,d 원"),
                        "평가손익": st.column_config.NumberColumn(format="%,d 원"),
                        "수익률(%)": st.column_config.NumberColumn(format="%.2f%%")
                    }
                )
            else:
                st.info("현재 보유 중인 주식이 없습니다. '주문 및 분석' 탭에서 주식을 매수해보세요!")

        # =========================================================
        # TAB 2: 주문 및 분석 (차트, AI 분석, 매수, 매도)
        # =========================================================
        with tab2:
            st.subheader("📈 종목 차트 및 매수")
            col_select, col_price, col_cash = st.columns([2, 1, 1])
            with col_select:
                selected_stock_name = st.selectbox("종목 선택", list(STOCKS.keys()))
                symbol = STOCKS[selected_stock_name]
                current_price = get_current_price(symbol)

            with col_price:
                st.metric(label="현재가", value=f"{current_price:,.0f} 원")

            with col_cash:
                st.metric(label="보유 예수금", value=f"{cash:,.0f} 원")

            left_col, right_col = st.columns([1.3, 1])

            # 좌측: 주가 차트 및 AI 투자 팁 출력
            with left_col:
                st.caption(f"**{selected_stock_name}** 최근 3개월 차트")
                df_hist = get_stock_history(symbol)
                if not df_hist.empty:
                    chart_tab1, chart_tab2 = st.tabs(["🕯 캔들 차트", "📈 선 차트"])
                    with chart_tab1:
                        fig_candle = go.Figure(data=[go.Candlestick(
                            x=df_hist['Date'], open=df_hist['Open'], high=df_hist['High'],
                            low=df_hist['Low'], close=df_hist['Close'],
                            increasing_line_color='#e12343', decreasing_line_color='#1261c4'
                        )])
                        fig_candle.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False)
                        st.plotly_chart(fig_candle, width="stretch")

                    with chart_tab2:
                        fig_line = px.line(df_hist, x='Date', y='Close')
                        fig_line.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig_line, width="stretch")

                # 💡 AI 데이터 분석 및 투자 팁
                st.markdown("#### 💡 AI 데이터 분석 및 투자 팁")
                analysis_tips = analyze_stock_indicators(df_hist)
                if analysis_tips:
                    col_t1, col_t2, col_t3 = st.columns(3)
                    with col_t1:
                        st.markdown("**📈 이동평균선**")
                        st.caption(analysis_tips[0][1])
                    with col_t2:
                        st.markdown("**📊 RSI 지표**")
                        st.caption(analysis_tips[1][1])
                    with col_t3:
                        st.markdown("**🔔 볼린저 밴드**")
                        st.caption(analysis_tips[2][1])
                    st.divider()
                    st.info(analysis_tips[3][1])

            # 우측: 주식 매수 주문 폼
            max_buy_qty = int(cash // current_price) if current_price > 0 else 0
            buy_key = f"buy_input_{symbol}"
            if buy_key not in st.session_state: 
                st.session_state[buy_key] = 1

            with right_col:
                with st.container(border=True):
                    st.markdown("**⚡ 주식 매수 주문**")
                    st.caption(f"최대 매수 가능: **{max_buy_qty:,}** 주")
                    if st.button("최대 수량 채우기 (매수)", key="btn_max_buy", width="stretch"):
                        st.session_state[buy_key] = max(1, max_buy_qty)
                        st.rerun()

                    buy_qty = st.number_input("매수 수량 선택", min_value=1, max_value=max(1, max_buy_qty) if max_buy_qty > 0 else 1, step=1, key=buy_key)
                    total_buy_price = current_price * buy_qty
                    st.markdown(f"총 매수 금액: **:red[{total_buy_price:,.0f} 원]**")

                    if st.button("📉 매수 완료", key="btn_do_buy", type="secondary", width="stretch"):
                        if current_price <= 0:
                            st.error("현재가를 불러올 수 없습니다.")
                        elif cash >= total_buy_price:
                            new_cash = cash - total_buy_price
                            with engine.begin() as conn:
                                conn.execute(
                                    text("UPDATE users SET cash = :cash WHERE student_id = :s_id"),
                                    {"cash": new_cash, "s_id": user_id}
                                )
                                item = conn.execute(
                                    text("SELECT quantity, buy_price FROM portfolio WHERE student_id = :s_id AND symbol = :sym"),
                                    {"s_id": user_id, "sym": symbol}
                                ).fetchone()

                                if item:
                                    old_qty, old_price = int(item[0]), float(item[1])
                                    new_qty = old_qty + buy_qty
                                    new_buy_price = ((old_qty * old_price) + total_buy_price) / new_qty
                                    conn.execute(
                                        text("UPDATE portfolio SET quantity = :qty, buy_price = :price WHERE student_id = :s_id AND symbol = :sym"),
                                        {"qty": new_qty, "price": new_buy_price, "s_id": user_id, "sym": symbol}
                                    )
                                else:
                                    conn.execute(
                                        text("INSERT INTO portfolio (student_id, symbol, stock_name, quantity, buy_price) VALUES (:s_id, :sym, :s_name, :qty, :price)"),
                                        {"s_id": user_id, "sym": symbol, "s_name": selected_stock_name, "qty": buy_qty, "price": current_price}
                                    )
                            st.success(f"{selected_stock_name} {buy_qty}주 매수 완료!")
                            st.rerun()
                        else:
                            st.error("예수금이 부족합니다!")

            st.divider()

            # --- 보유 종목 및 매도 영역 ---
            st.markdown("### 📋 보유 종목 및 매도")

            if not portfolio_df.empty:
                for idx, row in portfolio_df.iterrows():
                    p_symbol = row['symbol']
                    p_name = row['stock_name']
                    p_qty = int(row['quantity'])
                    p_buy_price = float(row['buy_price'])
                    p_curr_price = float(row['현재가'])
                    p_eval_price = float(row['평가금액'])
                    p_return = float(row['수익률(%)'])

                    with st.container(border=True):
                        c_info, c_sell = st.columns([2.5, 1.5])

                        with c_info:
                            st.markdown(f"#### **{p_name}** (`{p_symbol}`)")
                            m1, m2, m3, m4 = st.columns(4)
                            m1.caption(f"보유 수량\n\n**{p_qty:,} 주**")
                            m2.caption(f"평균 매수가\n\n**{int(round(p_buy_price)):,} 원**")
                            m3.caption(f"현재가\n\n**{int(round(p_curr_price)):,} 원**")
                            m4.caption(f"평가금액\n\n**{int(round(p_eval_price)):,} 원**")

                            return_color = "red" if p_return > 0 else "blue" if p_return < 0 else "gray"
                            st.markdown(f"수익률: :{return_color}[**{'+' if p_return > 0 else ''}{p_return:.2f}%**]")

                        with c_sell:
                            st.markdown("**⚡ 즉시 매도**")
                            sell_port_key = f"sell_port_qty_{p_symbol}"
                            
                            sell_port_qty = st.number_input(
                                "매도 수량", 
                                min_value=1, 
                                max_value=p_qty, 
                                value=p_qty, 
                                step=1, 
                                key=sell_port_key
                            )
                            
                            est_sell_amount = p_curr_price * sell_port_qty
                            st.caption(f"예상 매도금액: **{int(round(est_sell_amount)):,} 원**")

                            if st.button("📈 매도 실행", key=f"btn_sell_port_{p_symbol}", type="secondary", use_container_width=True):
                                if p_qty >= sell_port_qty > 0:
                                    new_cash = cash + est_sell_amount
                                    with engine.begin() as conn:
                                        conn.execute(
                                            text("UPDATE users SET cash = :cash WHERE student_id = :s_id"),
                                            {"cash": new_cash, "s_id": user_id}
                                        )
                                        remain_qty = p_qty - sell_port_qty
                                        if remain_qty > 0:
                                            conn.execute(
                                                text("UPDATE portfolio SET quantity = :qty WHERE student_id = :s_id AND symbol = :sym"),
                                                {"qty": remain_qty, "s_id": user_id, "sym": p_symbol}
                                            )
                                        else:
                                            conn.execute(
                                                text("DELETE FROM portfolio WHERE student_id = :s_id AND symbol = :sym"),
                                                {"s_id": user_id, "sym": p_symbol}
                                            )
                                    st.success(f"{p_name} {sell_port_qty}주 매도 완료!")
                                    st.rerun()
                                else:
                                    st.error("매도 수량이 올바르지 않습니다.")
            else:
                st.info("현재 보유 중인 주식이 없습니다.")

        # =========================================================
        # TAB 3: 학생용 실시간 랭킹 화면
        # =========================================================
        with tab3:
            st.subheader("🏆 전체 참가자 실시간 랭킹")
            if st.button("🔄 랭킹 새로고침", key="student_rank_refresh"): 
                st.rerun()

            all_users = pd.read_sql(
                text("SELECT student_id, name, cash, COALESCE(init_cash, 10000000) as init_cash FROM users WHERE student_id != 'admin'"), 
                engine
            )
            leaderboard = []
            for _, u in all_users.iterrows():
                u_id, u_name = u['student_id'], u['name']
                u_cash = float(u['cash'])
                u_init_cash = float(u['init_cash']) if float(u['init_cash']) > 0 else 10000000.0
                
                u_port = pd.read_sql(text("SELECT symbol, quantity FROM portfolio WHERE student_id = :student_id"), engine, params={"student_id": u_id})
                u_stock_eval = sum(get_current_price(row['symbol']) * int(row['quantity']) for _, row in u_port.iterrows()) if not u_port.empty else 0
                u_total = u_cash + u_stock_eval
                u_return = ((u_total - u_init_cash) / u_init_cash) * 100
                
                leaderboard.append({
                    "학번": u_id, 
                    "이름": u_name,
                    "총 자산 (원)": round(u_total),
                    "수익률 (%)": round(u_return, 2)
                })

            if leaderboard:
                lb_df = pd.DataFrame(leaderboard).sort_values(by=["수익률 (%)", "총 자산 (원)"], ascending=[False, False]).reset_index(drop=True)
                lb_df.index += 1

                st.dataframe(
                    lb_df, 
                    use_container_width=True,
                    column_config={
                        "학번": st.column_config.TextColumn("학번"),  
                        "이름": st.column_config.TextColumn("이름"),  
                        "총 자산 (원)": st.column_config.NumberColumn("총 자산 (원)", format="%,d"),
                        "수익률 (%)": st.column_config.NumberColumn("수익률 (%)", format="%.2f%%")
                    }
                )
            else:
                st.info("참가자 데이터가 없습니다.")
