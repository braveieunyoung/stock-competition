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
            u_return = ((u_total_
