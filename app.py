import streamlit as st
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ---------------------------------------------------------
# 1. DB 초기화
# ---------------------------------------------------------
DB_FILE = "stock_sim.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
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
    conn.commit()
    conn.close()

init_db()

import yfinance as yf

# 종목 코드 설정 (한국 주식은 종목코드 뒤에 .KS를 붙여야 yfinance에서 인식합니다)
STOCKS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "현대차": "005380.KS",
    "LG에너지솔루션": "373220.KS",
    "KODEX 200": "069500.KS"
}

# 네이버/KRX 블로킹을 우회하는 우수한 안정성의 주가 수집 함수
@st.cache_data(ttl=30, show_spinner=False)
def get_current_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        
        # 1. fast_info로 실시간가 조회 시도
        price = ticker.fast_info.get('lastPrice', None)
        if price is not None and price > 0:
            return float(price)
            
        # 2. fast_info 실패 시 최근 1일 데이터의 종가 가져오기
        df = ticker.history(period="1d")
        if not df.empty:
            return float(df['Close'].iloc[-1])
            
        return 0.0
    except Exception as e:
        return 0.0

# ---------------------------------------------------------
# 2. 페이지 설정 및 세션
# ---------------------------------------------------------
st.set_page_config(page_title="학생 모의주식 투자 대회", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

# ---------------------------------------------------------
# 3. 로그인 화면
# ---------------------------------------------------------
if st.session_state.user is None:
    st.title("📈 학생 모의주식 투자 대회")
    st.subheader("로그인하여 가상 투자에 참여하세요!")

    col1, col2 = st.columns(2)
    with col1:
        student_id = st.text_input("학번 (예: 20260101)")
        name = st.text_input("이름")
        start_button = st.button("투자 시작하기", type="primary")

    if start_button:
        if student_id and name:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE student_id = ?", (student_id,))
            user = c.fetchone()
            
            if not user:
                initial_cash = 10000000.0
                c.execute("INSERT INTO users VALUES (?, ?, ?)", (student_id, name, initial_cash))
                conn.commit()
            
            conn.close()
            st.session_state.user = {"student_id": student_id, "name": name}
            st.rerun()
        else:
            st.warning("학번과 이름을 모두 입력해주세요.")

# ---------------------------------------------------------
# 4. 메인 화면
# ---------------------------------------------------------
else:
    user_id = st.session_state.user["student_id"]
    user_name = st.session_state.user["name"]

    top_col1, top_col2 = st.columns([4, 1])
    with top_col1:
        st.title(f"🏆 {user_name} ({user_id}) 님의 대시보드")
    with top_col2:
        if st.button("로그아웃"):
            st.session_state.user = None
            st.rerun()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT cash FROM users WHERE student_id = ?", (user_id,))
    cash = float(c.fetchone()[0])

    portfolio_df = pd.read_sql_query(
        "SELECT symbol, stock_name, quantity, buy_price FROM portfolio WHERE student_id = ? AND quantity > 0",
        conn, params=(user_id,)
    )

    tab1, tab2, tab3 = st.tabs(["🛒 주식 매매", "💼 내 포트폴리오", "🥇 실시간 랭킹"])

    # -----------------------------------------------------
    # TAB 1: 주식 매매
    # -----------------------------------------------------
    with tab1:
        st.subheader("주식 매수 / 매도")
        selected_stock_name = st.selectbox("종목 선택", list(STOCKS.keys()))
        symbol = STOCKS[selected_stock_name]
        
        current_price = get_current_price(symbol)
        
        col_info1, col_info2 = st.columns(2)
        col_info1.metric("현재가", f"{current_price:,.0f} 원")
        col_info2.metric("보유 예수금", f"{cash:,.0f} 원")

        trade_col1, trade_col2 = st.columns(2)
        with trade_col1:
            qty = st.number_input("수량 선택", min_value=1, value=1, step=1)
            total_order_price = current_price * qty
            st.write(f"총 주문 금액: **{total_order_price:,.0f} 원**")

            if st.button("🔴 매수하기", use_container_width=True):
                if current_price <= 0:
                    st.error("현재가 정보를 불러올 수 없습니다.")
                elif cash >= total_order_price:
                    new_cash = cash - total_order_price
                    c.execute("UPDATE users SET cash = ? WHERE student_id = ?", (new_cash, user_id))
                    
                    c.execute("SELECT quantity, buy_price FROM portfolio WHERE student_id = ? AND symbol = ?", (user_id, symbol))
                    item = c.fetchone()
                    if item:
                        old_qty, old_price = int(item[0]), float(item[1])
                        new_qty = old_qty + qty
                        new_buy_price = ((old_qty * old_price) + total_order_price) / new_qty
                        c.execute("UPDATE portfolio SET quantity = ?, buy_price = ? WHERE student_id = ? AND symbol = ?",
                                  (int(new_qty), float(new_buy_price), user_id, symbol))
                    else:
                        c.execute("INSERT INTO portfolio VALUES (?, ?, ?, ?, ?)",
                                  (user_id, symbol, selected_stock_name, int(qty), float(current_price)))
                    conn.commit()
                    st.success(f"{selected_stock_name} {qty}주 매수 완료!")
                    st.rerun()
                else:
                    st.error("예수금이 부족합니다!")

        with trade_col2:
            # 보유 수량 정확하게 매칭 조회
            user_stock = portfolio_df[portfolio_df['symbol'] == symbol] if not portfolio_df.empty else pd.DataFrame()
            held_qty = int(user_stock['quantity'].values[0]) if not user_stock.empty else 0
            st.write(f"현재 보유 수량: **{held_qty} 주**")

            if st.button("🔵 매도하기", use_container_width=True):
                if held_qty >= qty:
                    sell_amount = current_price * qty
                    new_cash = cash + sell_amount
                    c.execute("UPDATE users SET cash = ? WHERE student_id = ?", (new_cash, user_id))
                    
                    new_qty = held_qty - qty
                    if new_qty > 0:
                        c.execute("UPDATE portfolio SET quantity = ? WHERE student_id = ? AND symbol = ?", (int(new_qty), user_id, symbol))
                    else:
                        c.execute("DELETE FROM portfolio WHERE student_id = ? AND symbol = ?", (user_id, symbol))
                    conn.commit()
                    st.success(f"{selected_stock_name} {qty}주 매도 완료!")
                    st.rerun()
                else:
                    st.error("매도할 수량이 부족합니다!")

    # -----------------------------------------------------
    # TAB 2: 내 포트폴리오
    # -----------------------------------------------------
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

            st.dataframe(portfolio_df[['stock_name', 'quantity', 'buy_price', '현재가', '평가금액', '수익률(%)']], use_container_width=True)
        else:
            st.info("현재 보유 중인 주식이 없습니다.")

    # -----------------------------------------------------
    # TAB 3: 실시간 랭킹
    # -----------------------------------------------------
    with tab3:
        st.subheader("🏆 전체 참가자 실시간 랭킹")
        if st.button("🔄 랭킹 새로고침"):
            st.rerun()

        all_users = pd.read_sql_query("SELECT student_id, name, cash FROM users", conn)
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

        lb_df = pd.DataFrame(leaderboard).sort_values(by="총 자산 (원)", ascending=False).reset_index(drop=True)
        lb_df.index += 1
        st.dataframe(lb_df, use_container_width=True)

    conn.close()