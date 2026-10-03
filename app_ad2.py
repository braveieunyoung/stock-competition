import streamlit as st
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px

# ---------------------------------------------------------
# 1. DB 초기화
# ---------------------------------------------------------
DB_FILE = "stock_sim.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # users 테이블에 role 컬럼(admin/user) 추가 고려 또는 admin 계정 초기 등록
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    student_id TEXT PRIMARY KEY,
                    name TEXT,
                    cash REAL
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS portfolio (
                    student_id TEXT,
                    symbol TEXT,
                    stock_name TEXT,
                    quantity INTEGER,
                    buy_price REAL,
                    PRIMARY KEY (student_id, symbol)
                )''')
    
    # 관리자 계정이 없으면 기본 등록 (학번: admin, 이름: 관리자, 초기 예수금: 0)
    c.execute("SELECT * FROM users WHERE student_id = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin', '관리자', 0)")

    conn.commit()
    conn.close()

init_db()

# 종목 코드 설정
STOCKS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "현대차": "005380.KS",
    "LG에너지솔루션": "373220.KS",
    "KODEX 200": "069500.KS",
    "셀트리온": "068270.KS",
    "기아": "000270.KS",
    "POSCO홀딩스": "005490.KS",
    "에코프로비엠 (코스닥)": "247540.KQ",
    "알테오젠 (코스닥)": "196170.KQ",
    "애플 (미국)": "AAPL",
    "테슬라 (미국)": "TSLA",
    "엔비디아 (미국)": "NVDA"
}

@st.cache_data(ttl=60, show_spinner=False)
def get_current_price(symbol):
    clean_symbol = symbol.replace('.KS', '').replace('.KQ', '').strip()
    
    if clean_symbol.isdigit():
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
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
# 2. 페이지 설정 및 세션 & 커스텀 CSS (글자 크기 확대)
# ---------------------------------------------------------
st.set_page_config(page_title="학생 모의주식 투자 대회", layout="wide")

st.markdown("""
    <style>
        html, body, [class*="css"], p, span, div, label {
            font-size: 20px !important;
        }
        input, button, select, textarea {
            font-size: 20px !important;
        }
        button[data-baseweb="tab"] {
            font-size: 24px !important;
        }
        h2, .stSubheader {
            font-size: 28px !important;
        }
        h1, .stTitle {
            font-size: 32px !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 26px !important;
        }
    </style>
""", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

# ---------------------------------------------------------
# 3. 관리자 전용 대시보드 화면
# ---------------------------------------------------------
def render_admin_dashboard():
    st.title("⚙️ 관리자 전용 대시보드")
    st.info("관리자로 로그인되었습니다. 회원 정보 및 시드 머니를 제어할 수 있습니다.")

    tab1, tab2, tab3 = st.tabs(["📊 전체 랭킹 및 데이터", "💰 시드 머니 관리", "👥 회원 관리"])

    conn = sqlite3.connect(DB_FILE)

    # 1) 전체 데이터 및 랭킹 다운로드
    with tab1:
        st.subheader("🏆 전체 참가자 실시간 데이터")
        all_users = pd.read_sql_query("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'", conn)
        
        admin_leaderboard = []
        for _, u in all_users.iterrows():
            u_id, u_name, u_cash = u['student_id'], u['name'], float(u['cash'])
            u_port = pd.read_sql_query("SELECT symbol, quantity FROM portfolio WHERE student_id = ?", conn, params=(u_id,))
            
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
            
            # 자산 포맷팅
            df_display = df_admin_lb.copy()
            df_display["총 자산 (원)"] = df_display["총 자산 (원)"].apply(lambda x: f"{x:,}")
            st.dataframe(df_display, width="stretch")

            # CSV 파일 다운로드
            csv_data = df_admin_lb.to_csv(index=True, encoding="utf-8-sig")
            st.download_button(
                label="📥 랭킹 데이터 CSV 다운로드",
                data=csv_data,
                file_name=f"student_ranks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )
        else:
            st.info("등록된 학생 회원이 없습니다.")

    # 2) 시드 머니 관리 (개별 및 일괄)
    with tab2:
        st.subheader("💵 시드 머니 지급 및 수정")
        col_m1, col_m2 = st.columns(2)

        all_students = pd.read_sql_query("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'", conn)

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
                    c = conn.cursor()
                    c.execute("UPDATE users SET cash = ? WHERE student_id = ?", (new_cash_val, target_id))
                    conn.commit()
                    st.success("예수금이 수정되었습니다.")
                    st.rerun()

        with col_m2:
            st.markdown("### 📢 전체 학생 일괄 추가 지급")
            add_cash_val = st.number_input("전체 추가 지급 금액(원)", min_value=0, step=100000, value=1000000)
            if st.button("전체 일괄 지급 실행"):
                c = conn.cursor()
                c.execute("UPDATE users SET cash = cash + ? WHERE student_id != 'admin'", (add_cash_val,))
                conn.commit()
                st.success(f"모든 학생에게 {add_cash_val:,} 원이 일괄 지급되었습니다.")
                st.rerun()

    # 3) 회원 관리
    with tab3:
        st.subheader("👥 회원 목록 및 계정 삭제")
        all_users_df = pd.read_sql_query("SELECT student_id AS 학번, name AS 이름, cash AS 예수금 FROM users", conn)
        all_users_df["예수금"] = all_users_df["예수금"].apply(lambda x: f"{int(x):,} 원")
        st.dataframe(all_users_df, width="stretch", hide_index=True)

        st.divider()
        st.markdown("### ❌ 계정 삭제")
        del_students = pd.read_sql_query("SELECT student_id, name FROM users WHERE student_id != 'admin'", conn)
        if not del_students.empty:
            del_options = {f"{row['student_id']} ({row['name']})": row['student_id'] for _, row in del_students.iterrows()}
            del_label = st.selectbox("삭제할 학생 계정 선택", list(del_options.keys()))
            del_target_id = del_options[del_label]

            if st.button("선택한 계정 삭제", type="primary"):
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE student_id = ?", (del_target_id,))
                c.execute("DELETE FROM portfolio WHERE student_id = ?", (del_target_id,))
                conn.commit()
                st.warning("계정 및 포트폴리오 데이터가 삭제되었습니다.")
                st.rerun()

    conn.close()

# ---------------------------------------------------------
# 4. 로그인 및 라우팅
# ---------------------------------------------------------
if st.session_state.get('user') is None:
    st.title("📈 학생 모의주식 투자 대회")
    st.subheader("로그인하여 가상 투자에 참여하세요!")

    col1, col2 = st.columns(2)
    with col1:
        student_id = st.text_input("학번 5자리 (관리자: admin)", max_chars=10)
        name = st.text_input("이름 (관리자인 경우 생략 가능)")
        start_button = st.button("투자 시작하기 / 로그인", type="primary")

    if start_button:
        s_id = student_id.strip()
        s_name = name.strip()

        # 관리자 로그인 체크
        if s_id.lower() == "admin":
            st.session_state['user'] = {"student_id": "admin", "name": "관리자"}
            st.rerun()

        # 학생 로그인 체크
        elif not s_id or not s_name:
            st.warning("학번과 이름을 모두 입력해주세요.")
        elif len(s_id) != 5 or not s_id.isdigit():
            st.error("학번은 5자리 숫자로 입력해야 합니다! (예: 10101)")
        else:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE student_id = ?", (s_id,))
            user = c.fetchone()
            
            if user:
                db_name = user[1]
                if db_name != s_name:
                    st.error(f"이미 등록된 학번입니다! 입력하신 이름('{s_name}')이 기존 이름('{db_name}')과 다릅니다.")
                    conn.close()
                else:
                    conn.close()
                    st.session_state['user'] = {"student_id": s_id, "name": db_name}
                    st.rerun()
            else:
                initial_cash = 10000000.0
                c.execute("INSERT INTO users VALUES (?, ?, ?)", (s_id, s_name, initial_cash))
                conn.commit()
                conn.close()
                st.session_state['user'] = {"student_id": s_id, "name": s_name}
                st.rerun()

# ---------------------------------------------------------
# 5. 메인 화면 (로그인 성공 시)
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

    # [A] 관리자 모드 실행
    if user_id == "admin":
        render_admin_dashboard()

    # [B] 학생 모드 실행 (기존 전체 학생 기능 코드 연동)
    else:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT cash FROM users WHERE student_id = ?", (user_id,))
        cash_row = c.fetchone()
        cash = float(cash_row[0]) if cash_row else 10000000.0

        portfolio_df = pd.read_sql_query(
            "SELECT symbol, stock_name, quantity, buy_price FROM portfolio WHERE student_id = ? AND quantity > 0",
            conn, params=(user_id,)
        )

        tab1, tab2, tab3 = st.tabs(["🛒 주식 매매", "💼 내 포트폴리오", "🥇 실시간 랭킹"])

        # TAB 1: 주식 매매
        with tab1:
            col_select, col_price, col_cash = st.columns([2, 1, 1])
            
            with col_select:
                selected_stock_name = st.selectbox("종목 선택", list(STOCKS.keys()))
                symbol = STOCKS[selected_stock_name]
                current_price = get_current_price(symbol)

            with col_price:
                st.metric(label="현재가", value=f"{current_price:,.0f} 원")

            with col_cash:
                st.metric(label="보유 예수금", value=f"{cash:,.0f} 원")

            st.divider()

            left_col, right_col = st.columns([1.3, 1])

            with left_col:
                st.subheader(f"📊 {selected_stock_name} 최근 3개월 차트")
                df_hist = get_stock_history(symbol)
                if not df_hist.empty:
                    chart_tab1, chart_tab2 = st.tabs(["🕯️ 캔들 차트", "📈 선 차트"])
                    
                    with chart_tab1:
                        fig_candle = go.Figure(data=[go.Candlestick(
                            x=df_hist['Date'],
                            open=df_hist['Open'],
                            high=df_hist['High'],
                            low=df_hist['Low'],
                            close=df_hist['Close'],
                            increasing_line_color='#e12343',
                            decreasing_line_color='#1261c4',
                            name="주가"
                        )])
                        fig_candle.update_layout(
                            height=380,
                            margin=dict(l=10, r=10, t=10, b=10),
                            xaxis_rangeslider_visible=False,
                            yaxis_title="주가(원)"
                        )
                        st.plotly_chart(fig_candle, width="stretch")

                    with chart_tab2:
                        fig_line = px.line(
                            df_hist, 
                            x='Date', 
                            y='Close', 
                            labels={'Date': '날짜', 'Close': '주가(원)'}
                        )
                        fig_line.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
                        st.plotly_chart(fig_line, width="stretch")
                else:
                    st.info("차트 데이터를 불러올 수 없습니다.")

            max_buy_qty = int(cash // current_price) if current_price > 0 else 0
            user_stock = portfolio_df[portfolio_df['symbol'] == symbol] if not portfolio_df.empty else pd.DataFrame()
            max_sell_qty = int(user_stock['quantity'].values[0]) if not user_stock.empty else 0

            buy_key = f"buy_input_{symbol}"
            sell_key = f"sell_input_{symbol}"

            if buy_key not in st.session_state:
                st.session_state[buy_key] = 1
            if sell_key not in st.session_state:
                st.session_state[sell_key] = 1

            with right_col:
                with st.container(border=True):
                    st.subheader("💳 주식 주문")
                    trade_tab_buy, trade_tab_sell = st.tabs(["📉 매수", "📈 매도"])

                    with trade_tab_buy:
                        st.caption(f"최대 매수 가능: **{max_buy_qty:,}** 주")
                        if st.button("최대 수량 채우기 (매수)", key="btn_max_buy", width="stretch"):
                            st.session_state[buy_key] = max(1, max_buy_qty)
                            st.rerun()

                        buy_qty = st.number_input(
                            "매수 수량 선택", 
                            min_value=1, 
                            max_value=max(1, max_buy_qty) if max_buy_qty > 0 else 1, 
                            step=1,
                            key=buy_key
                        )
                        
                        total_buy_price = current_price * buy_qty
                        st.markdown(f"총 매수 금액: **:red[{total_buy_price:,.0f} 원]**")

                        if st.button("📉 매수 완료", key="btn_do_buy", type="primary", width="stretch"):
                            if current_price <= 0:
                                st.error("현재가 정보를 불러올 수 없습니다.")
                            elif max_buy_qty == 0:
                                st.error("예수금이 부족하여 매수할 수 없습니다.")
                            elif cash >= total_buy_price:
                                new_cash = cash - total_buy_price
                                c.execute("UPDATE users SET cash = ? WHERE student_id = ?", (new_cash, user_id))
                                
                                c.execute("SELECT quantity, buy_price FROM portfolio WHERE student_id = ? AND symbol = ?", (user_id, symbol))
                                item = c.fetchone()
                                if item:
                                    old_qty, old_price = int(item[0]), float(item[1])
                                    new_qty = old_qty + buy_qty
                                    new_buy_price = ((old_qty * old_price) + total_buy_price) / new_qty
                                    c.execute("UPDATE portfolio SET quantity = ?, buy_price = ? WHERE student_id = ? AND symbol = ?",
                                              (int(new_qty), float(new_buy_price), user_id, symbol))
                                else:
                                    c.execute("INSERT INTO portfolio VALUES (?, ?, ?, ?, ?)",
                                              (user_id, symbol, selected_stock_name, int(buy_qty), float(current_price)))
                                conn.commit()
                                st.success(f"{selected_stock_name} {buy_qty}주 매수 완료!")
                                st.rerun()
                            else:
                                st.error("예수금이 부족합니다!")

                    with trade_tab_sell:
                        st.caption(f"보유 수량: **{max_sell_qty:,}** 주")
                        if st.button("전량 매도 선택", key="btn_max_sell", width="stretch"):
                            st.session_state[sell_key] = max(1, max_sell_qty)
                            st.rerun()

                        sell_qty = st.number_input(
                            "매도 수량 선택", 
                            min_value=1, 
                            max_value=max(1, max_sell_qty) if max_sell_qty > 0 else 1, 
                            step=1,
                            key=sell_key
                        )
                        
                        total_sell_price = current_price * sell_qty
                        st.markdown(f"총 매도 금액: **:blue[{total_sell_price:,.0f} 원]**")

                        if st.button("📈 매도 완료", key="btn_do_sell", type="primary", width="stretch"):
                            if max_sell_qty >= sell_qty and max_sell_qty > 0:
                                sell_amount = current_price * sell_qty
                                new_cash = cash + sell_amount
                                c.execute("UPDATE users SET cash = ? WHERE student_id = ?", (new_cash, user_id))
                                
                                new_qty = max_sell_qty - sell_qty
                                if new_qty > 0:
                                    c.execute("UPDATE portfolio SET quantity = ? WHERE student_id = ? AND symbol = ?", (int(new_qty), user_id, symbol))
                                else:
                                    c.execute("DELETE FROM portfolio WHERE student_id = ? AND symbol = ?", (user_id, symbol))
                                conn.commit()
                                st.success(f"{selected_stock_name} {sell_qty}주 매도 완료!")
                                st.rerun()
                            else:
                                st.error("매도할 수량이 부족합니다!")

        # TAB 2: 내 포트폴리오
        with tab2:
            st.subheader("내 보유 자산 현황")
            total_eval = cash
            
            if not portfolio_df.empty:
                portfolio_df['현재가'] = portfolio_df['symbol'].apply(get_current_price)
                portfolio_df['평가금액'] = portfolio_df['quantity'] * portfolio_df['현재가']
                portfolio_df['평가손익'] = portfolio_df['평가금액'] - (portfolio_df['quantity'] * portfolio_df['buy_price'])
                portfolio_df['수익률(%)'] = (portfolio_df['평가손익'] / (portfolio_df['quantity'] * portfolio_df['buy_price'])) * 100
                
                stock_eval_total = portfolio_df['평가금액'].sum()
                total_eval += stock_eval_total

                col_p1, col_p2, col_p3 = st.columns(3)
                col_p1.metric("총 평가 자산", f"{total_eval:,.0f} 원")
                col_p2.metric("예수금 (현금)", f"{cash:,.0f} 원")
                total_return = ((total_eval - 10000000) / 10000000) * 100
                col_p3.metric("누적 수익률", f"{total_return:+.2f} %")

                display_df = portfolio_df.copy()
                display_df = display_df.rename(columns={
                    'stock_name': '종목명',
                    'quantity': '보유 수량',
                    'buy_price': '평균 매수가',
                    '현재가': '현재가',
                    '평가금액': '평가금액',
                    '수익률(%)': '수익률'
                })

                display_df['보유 수량'] = display_df['보유 수량'].apply(lambda x: f"{int(x):,} 주")
                display_df['평균 매수가'] = display_df['평균 매수가'].apply(lambda x: f"{int(round(x)):,} 원")
                display_df['현재가'] = display_df['현재가'].apply(lambda x: f"{int(round(x)):,} 원")
                display_df['평가금액'] = display_df['평가금액'].apply(lambda x: f"{int(round(x)):,} 원")
                display_df['수익률'] = display_df['수익률'].apply(lambda x: f"{'+' if x > 0 else ''}{x:.2f} %")

                cols = ['종목명', '보유 수량', '평균 매수가', '현재가', '평가금액', '수익률']
                st.dataframe(display_df[cols], width="stretch", hide_index=True)

            else:
                st.info("현재 보유 중인 주식이 없습니다.")

        # TAB 3: 실시간 랭킹
        with tab3:
            st.subheader("🏆 전체 참가자 실시간 랭킹")
            if st.button("🔄 랭킹 새로고침"):
                st.rerun()

            all_users = pd.read_sql_query("SELECT student_id, name, cash FROM users WHERE student_id != 'admin'", conn)
            leaderboard = []

            for _, u in all_users.iterrows():
                u_id, u_name, u_cash = u['student_id'], u['name'], float(u['cash'])
                u_port = pd.read_sql_query("SELECT symbol, quantity FROM portfolio WHERE student_id = ?", conn, params=(u_id,))
                
                u_stock_eval = 0
                if not u_port.empty:
                    for _, row in u_port.iterrows():
                        p = get_current_price(row['symbol'])
                        u_stock_eval += p * int(row['quantity'])
                    
                u_total_assets = u_cash + u_stock_eval
                u_return = ((u_total_assets - 10000000) / 10000000) * 100
                
                leaderboard.append({
                    "학번": u_id,
                    "이름": u_name,
                    "총 자산 (원)": round(u_total_assets),
                    "수익률 (%)": round(u_return, 2)
                })

            if leaderboard:
                lb_df = pd.DataFrame(leaderboard).sort_values(by="총 자산 (원)", ascending=False).reset_index(drop=True)
                lb_df.index += 1
                st.dataframe(lb_df, width="stretch")
            else:
                st.info("참가자 데이터가 없습니다.")

        conn.close()