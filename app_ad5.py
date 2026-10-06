import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import create_engine, text

# ---------------------------------------------------------
# 1. DB 연결 설정 (Supabase PostgreSQL)
# ---------------------------------------------------------
@st.cache_resource
def get_db_engine():
    db_url = st.secrets["database"]["url"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return create_engine(
        db_url,
        pool_pre_ping=True,      # 끊어진 연결 자동 재접속
        pool_recycle=300,        # 5분마다 연결 재재생
        connect_args={"sslmode": "require", "connect_timeout": 10},
    )

engine = get_db_engine()

# 종목 코드 설정
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

@st.cache_data(ttl=60, show_spinner=False)
def get_current_price(symbol):
    clean_symbol = symbol.replace('.KS', '').replace('.KQ', '').strip()
    if clean_symbol.isdigit():
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            url_api = f"https://m.stock.naver.com/api/stock/{clean_symbol}/basic"
            res = requests.get(url_api, headers=headers, timeout=2)
            if res.status_code == 200:
                val = res.json().get('nowVal', '').replace(',', '')
                if val and float(val) > 0:
                    return float(val)
        except Exception:
            pass

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

        try:
            ticker = yf.Ticker(f"{clean_symbol}.KS")
            df = ticker.history(period="1d")
            if not df.empty:
                val = float(df['Close'].iloc[-1])
                if val > 0:
                    return val
        except Exception:
            pass
    else:
        try:
            ticker = yf.Ticker(symbol)
            price_usd = ticker.fast_info.get('lastPrice', None)
            if not price_usd:
                df = ticker.history(period="1d")
                if not df.empty:
                    price_usd = float(df['Close'].iloc[-1])
            if price_usd and price_usd > 0:
                return float(price_usd * 1350.0)
        except Exception:
            pass
    return 0.0

@st.cache_data(ttl=300, show_spinner=False)
def get_stock_history(symbol):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="3mo")
        if not df.empty:
            clean_symbol = symbol.replace('.KS', '').replace('.KQ', '').strip()
            if not clean_symbol.isdigit():
                for col in ['Open', 'High', 'Low', 'Close']:
                    df[col] = df[col] * 1350.0
            return df.reset_index()
    except Exception:
        pass
    return pd.DataFrame()

# ---------------------------------------------------------
# 2. 페이지 및 스타일 설정
# ---------------------------------------------------------
st.set_page_config(page_title="학생 모의주식 투자 대회", layout="wide")

st.markdown("""
    <style>
        html, body, [class*="css"], p, span, div, label { font-size: 20px !important; }
        input, button, select, textarea { font-size: 20px !important; }
        button[data-baseweb="tab"] { font-size: 24px !important; }
        h2, .stSubheader { font-size: 28px !important; }
        h1, .stTitle { font-size: 32px !important; }
        [data-testid="stMetricValue"] { font-size: 26px !important; }
    </style>
""", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

# ---------------------------------------------------------
# 3. 관리자 대시보드
# ---------------------------------------------------------
def render_admin_dashboard():
    st.title("⚙️ 관리자 전용 대시보드")
    st.info("관리자로 로그인되었습니다. 학생 명단 관리 및 초기 설정을 진행할 수 있습니다.")

    tab1, tab2, tab3 = st.tabs(["📊 전체 랭킹 및 데이터", "💰 시드 머니 관리", "👥 학생 명단 & CSV 업로드"])

    # TAB 1: 랭킹 및 데이터 다운로드
    with tab1:
        st.subheader("🏆 전체 참가자 실시간 데이터")
        all_users = pd.read_sql(text("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'"), engine)
        
        admin_leaderboard = []
        for _, u in all_users.iterrows():
            u_id, u_name, u_cash = u['student_id'], u['name'], float(u['cash'])
            u_port = pd.read_sql(text("SELECT symbol, quantity FROM portfolio WHERE student_id = :student_id"), engine, params={"student_id": u_id})
            u_stock_eval = 0
            if not u_port.empty:
                for _, row in u_port.iterrows():
                    p = get_current_price(row['symbol'])
                    u_stock_eval += p * int(row['quantity'])
                
            u_total_assets = u_cash + u_stock_eval
            u_return = ((u_total_assets - 10000000) / 10000000) * 100
            
            admin_leaderboard.append({
                "학번": u_id,
                "이름": u_name,
                "보유 예수금 (원)": f"{round(u_cash):,}",
                "총 자산 (원)": round(u_total_assets),
                "수익률 (%)": round(u_return, 2)
            })

        if admin_leaderboard:
            df_admin_lb = pd.DataFrame(admin_leaderboard).sort_values(by="총 자산 (원)", ascending=False).reset_index(drop=True)
            df_admin_lb.index += 1
            df_display = df_admin_lb.copy()
            df_display["총 자산 (원)"] = df_display["총 자산 (원)"].apply(lambda x: f"{x:,}")
            st.dataframe(df_display, width="stretch")

            csv_data = df_admin_lb.to_csv(index=True, encoding="utf-8-sig")
            st.download_button(
                label="📥 랭킹 데이터 CSV 다운로드",
                data=csv_data,
                file_name=f"student_ranks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )
        else:
            st.info("등록된 학생 회원이 없습니다.")

    # TAB 2: 시드 머니 관리
    with tab2:
        st.subheader("💵 시드 머니 지급 및 수정")
        col_m1, col_m2 = st.columns(2)
        all_students = pd.read_sql(text("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'"), engine)

        with col_m1:
            st.markdown("### 👤 개별 학생 예수금 수정")
            if not all_students.empty:
                student_options = {f"{row['student_id']} ({row['name']})": row['student_id'] for _, row in all_students.iterrows()}
                selected_label = st.selectbox("학생 선택", list(student_options.keys()))
                target_id = student_options[selected_label]
                
                curr_cash = all_students[all_students['student_id'] == target_id]['cash'].values[0]
                st.caption(f"현재 예수금: **{int(curr_cash):,} 원**")

                new_cash_val = st.number_input("설정할 예수금(원)", min_value=0, step=100000, value=int(curr_cash))
                if st.button("개별 금액 설정 완료", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(
                            text("UPDATE users SET cash = :cash WHERE student_id = :student_id"),
                            {"cash": new_cash_val, "student_id": target_id}
                        )
                    st.success("예수금이 수정되었습니다.")
                    st.rerun()

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

    # TAB 3: CSV 업로드 & 학생 명단 관리
    with tab3:
        st.subheader("📁 CSV 파일로 학생 명단 일괄 등록")
        
        sample_df = pd.DataFrame([
            {"학번": "10101", "이름": "김철수", "비밀번호": "1234", "시드머니": 10000000},
            {"학번": "10102", "이름": "이영희", "비밀번호": "", "시드머니": 10000000}
        ])
        sample_csv = sample_df.to_csv(index=False).encode('cp949', errors='ignore')
        st.download_button("📄 업로드 샘플 CSV 다운로드", sample_csv, "student_sample.csv", "text/csv")

        uploaded_file = st.file_uploader("CSV 파일을 선택하세요 (필수 열: 학번, 이름 / 선택 열: 비밀번호, 시드머니)", type=["csv"])
        
        if uploaded_file is not None:
            try:
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
                            is_reg = 1 if s_pw else 0

                            res = conn.execute(text("SELECT student_id FROM users WHERE student_id = :s_id"), {"s_id": s_id}).fetchone()
                            if res:
                                conn.execute(text("UPDATE users SET name = :name, password = :pw, cash = :cash, is_registered = :is_reg WHERE student_id = :s_id"),
                                    {"name": s_name, "pw": s_pw, "cash": s_cash, "is_reg": is_reg, "s_id": s_id}
                                )
                                updated_count += 1
                            else:
                                conn.execute(
                                    text("INSERT INTO users (student_id, name, cash, password, is_registered) VALUES (:s_id, :name, :cash, :pw, :is_reg)"),
                                    {"s_id": s_id, "name": s_name, "cash": s_cash, "pw": s_pw, "is_reg": is_reg}
                                )
                                added_count += 1
                    
                    st.success(f"완료! 신규 등록: {added_count}명 / 정보 갱신: {updated_count}명")
                    st.rerun()
            except Exception as e:
                st.error(f"CSV 파일 처리 중 오류가 발생했습니다: {e}")

        st.divider()
        st.subheader("➕ 개별 신규 학생 등록")
        
        with st.form("single_student_form"):
            new_student_id = st.text_input("학번 (예: 10101)").strip()
            new_name = st.text_input("이름").strip()
            new_pw = st.text_input("비밀번호 (선택사항 - 미입력 시 최초 로그인 시 설정)", type="password").strip() 
            new_cash = st.number_input("시드머니 (원)", min_value=0, value=10000000, step=1000000)
            
            is_reg = 1 if new_pw else 0
            submitted = st.form_submit_button("학생 추가", type="primary")

            if submitted:
                if not new_student_id or not new_name:
                    st.error("학번과 이름을 모두 입력해주세요.")
                else:
                    try:
                        with engine.begin() as conn:
                            # 중복 학번 확인
                            check_user = conn.execute(
                                text("SELECT student_id FROM users WHERE student_id = :s_id"), 
                                {"s_id": new_student_id}
                            ).fetchone()

                            if check_user:
                                st.error("이미 존재하는 학번입니다.")
                            else:
                                # users 테이블에 float/int 형태의 시드머니 전달
                                conn.execute(
                                    text("""
                                        INSERT INTO users (student_id, name, cash, password, is_registered) 
                                        VALUES (:s_id, :name, :cash, :pw, :is_reg)
                                    """),
                                    {
                                        "s_id": new_student_id, 
                                        "name": new_name, 
                                        "cash": float(new_cash), 
                                        "pw": new_pw, 
                                        "is_reg": is_reg
                                    }
                                )
                                st.success(f"학생 {new_name}({new_student_id})이 성공적으로 등록되었습니다!")
                                st.rerun()
                    except Exception as e:
                        st.error(f"등록 중 오류가 발생했습니다: {e}")
        
        st.divider()
        st.subheader("👥 등록된 학생 명단 및 회원 관리")
        
        all_users_df = pd.read_sql(
            text("SELECT student_id AS 학번, name AS 이름, cash AS 시드머니, is_registered AS 가입여부 FROM users WHERE student_id != 'admin' ORDER BY student_id ASC"), 
            engine
        )
        
        if not all_users_df.empty:
            all_users_df['시드머니'] = all_users_df['시드머니'].apply(lambda x: f"{int(x):,} 원")
            all_users_df['가입여부'] = all_users_df['가입여부'].apply(lambda x: "등록 완료" if str(x) == "1" else "미등록(최초로그인 대기)")
            st.dataframe(all_users_df, use_container_width=True, hide_index=True)
        else:
            st.info("등록된 학생이 없습니다.")

        col_reset, col_del = st.columns(2)
        
        del_students = pd.read_sql(text("SELECT student_id, name FROM users WHERE student_id != 'admin'"), engine)
        reset_options = {f"{row['student_id']} ({row['name']})": row['student_id'] for _, row in del_students.iterrows()}
            
        if reset_options:
            with col_reset:
                st.markdown("### 🔑 비밀번호 초기화")
                reset_label = st.selectbox("초기화할 학생 선택", list(reset_options.keys()))
                reset_target_id = reset_options[reset_label]
                
                if st.button("비밀번호 초기화 실행"):
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE users SET password = '', is_registered = 0 WHERE student_id = :s_id"), {"s_id": reset_target_id})
                    st.success("비밀번호가 초기화되었습니다. 재로그인 시 신규 비밀번호를 입력합니다.")
                    st.rerun()
        
            with col_del:
                st.markdown("### ❌ 계정 삭제")
                del_label = st.selectbox("삭제할 학생 선택", list(reset_options.keys()), key="del_select")
                del_target_id = reset_options[del_label]
                
                if st.button("선택한 학생 삭제", type="primary"):
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM users WHERE student_id = :s_id"), {"s_id": del_target_id})
                        conn.execute(text("DELETE FROM portfolio WHERE student_id = :s_id"), {"s_id": del_target_id})

                        #added_count -= 1
                    st.warning("학생 명단 및 투자 데이터가 삭제되었습니다.")
                    st.rerun()
        else:
            st.info("비밀번호 초기화 및 삭제할 학생 계정이 없습니다.")

# ---------------------------------------------------------
# 4. 로그인 및 라우팅
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

        if s_id.lower() == "admin":
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password FROM users WHERE student_id = 'admin'")).fetchone()
                admin_pw = res[0] if res else ""

            if s_pw == admin_pw:
                st.session_state['user'] = {"student_id": "admin", "name": "관리자"}
                st.rerun()
            else:
                st.error("관리자 비밀번호가 올바르지 않습니다.")

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

                    elif is_reg == 0:
                        with engine.begin() as conn:
                            conn.execute(
                                text("UPDATE users SET password = :pw, is_registered = 1 WHERE student_id = :s_id"),
                                {"pw": s_pw, "s_id": s_id}
                            )
                        st.success("🎉 최초 로그인 완료! 입력하신 비밀번호로 설정되었습니다.")
                        st.session_state['user'] = {"student_id": s_id, "name": db_name}
                        st.rerun()

                    else:
                        if db_pw == s_pw:
                            st.session_state['user'] = {"student_id": s_id, "name": db_name}
                            st.rerun()
                        else:
                            st.error("비밀번호가 올바르지 않습니다.")

# ---------------------------------------------------------
# 5. 메인 화면
# ---------------------------------------------------------
else:
    user_id = st.session_state.user["student_id"]
    user_name = st.session_state.user["name"]

    top_col1, top_col2 = st.columns([5, 1])
    with top_col1:
        st.title(f"🏆 {user_name} ({user_id}) 님의 대시보드")
    with top_col2:
        st.write("")
        if st.button("로그아웃", width="stretch"):
            st.session_state.user = None
            st.rerun()

    # [A] 관리자 모드
    if user_id == "admin":
        render_admin_dashboard()

    # [B] 학생 모드 (통합 포트폴리오 + 랭킹)
    else:
        with engine.connect() as conn:
            cash_row = conn.execute(
                text("SELECT cash FROM users WHERE student_id = :s_id"),
                {"s_id": user_id}
            ).fetchone()
        cash = float(cash_row[0]) if cash_row else 10000000.0

        portfolio_df = pd.read_sql(text("SELECT symbol, stock_name, quantity, buy_price FROM portfolio WHERE student_id = :s_id AND quantity > 0"), engine, params={"s_id": user_id})

        tab1, tab2 = st.tabs(["💼 내 포트폴리오", "🥇 실시간 랭킹"])

        # TAB 1: 내 포트폴리오
        with tab1:
            st.subheader("💼 내 보유 자산 현황")
            total_eval = cash

            if not portfolio_df.empty:
                portfolio_df['현재가'] = portfolio_df['symbol'].apply(get_current_price)
                portfolio_df['평가금액'] = portfolio_df['quantity'] * portfolio_df['현재가']
                portfolio_df['평가손익'] = portfolio_df['평가금액'] - (portfolio_df['quantity'] * portfolio_df['buy_price'])
                portfolio_df['수익률(%)'] = (portfolio_df['평가손익'] / (portfolio_df['quantity'] * portfolio_df['buy_price'])) * 100
                
                total_eval += portfolio_df['평가금액'].sum()
                
            col_p1, col_p2, col_p3 = st.columns(3)
            col_p1.metric("총 평가 자산", f"{total_eval:,.0f} 원")
            col_p2.metric("예수금 (현금)", f"{cash:,.0f} 원")
            col_p3.metric("누적 수익률", f"{((total_eval - 10000000) / 10000000) * 100:+.2f} %")

            st.divider()

            # 주식 차트 및 매수 창
            st.subheader("📈 관심 종목 차트 및 매수")
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
                else:
                    st.info("차트 데이터를 불러올 수 없습니다.")

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

                    if st.button("📉 매수 완료", key="btn_do_buy", type="primary", width="stretch"):
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

            # 보유 종목 목록 및 빠른 매도
            st.markdown("### 📋 보유 종목 목록 및 빠른 매도")

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

                            if st.button("📈 매도 실행", key=f"btn_sell_port_{p_symbol}", type="primary", use_container_width=True):
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
                st.info("현재 보유 중인 주식이 없습니다. 상단에서 원하는 종목을 매수해보세요!")

        # TAB 2: 랭킹
        with tab2:
            st.subheader("🏆 전체 참가자 실시간 랭킹")
            if st.button("🔄 랭킹 새로고침"): st.rerun()

            all_users = pd.read_sql(text("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'"), engine)
            leaderboard = []
            for _, u in all_users.iterrows():
                u_id, u_name, u_cash = u['student_id'], u['name'], float(u['cash'])
                u_port = pd.read_sql(text("SELECT symbol, quantity FROM portfolio WHERE student_id = :student_id"), engine, params={"student_id": u_id})
                u_stock_eval = sum(get_current_price(row['symbol']) * int(row['quantity']) for _, row in u_port.iterrows()) if not u_port.empty else 0
                u_total = u_cash + u_stock_eval
                leaderboard.append({
                    "학번": u_id, "이름": u_name,
                    "총 자산 (원)": round(u_total),
                    "수익률 (%)": round(((u_total - 10000000) / 10000000) * 100, 2)
                })

            if leaderboard:
                lb_df = pd.DataFrame(leaderboard).sort_values(by=["총 자산 (원)", "학번"], ascending=[False, True]).reset_index(drop=True)
                lb_df.index += 1

                st.dataframe(
                    lb_df, 
                    use_container_width=True,
                    column_config={
                        "학번": st.column_config.TextColumn("학번"),  
                        "총 자산 (원)": st.column_config.NumberColumn(
                            "총 자산 (원)",
                            format="%,d"  
                        ),
                        "수익률 (%)": st.column_config.NumberColumn(
                            "수익률 (%)",
                            format="%.2f%%"
                        )
                    }
                )
            else:
                st.info("참가자 데이터가 없습니다.")
