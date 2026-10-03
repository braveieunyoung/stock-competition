import streamlit as st
import pandas as pd

# -------------------------------------------------------------------
# [예시 데이터베이스/상태 저장] 실무에서는 DB(SQLite, PostgreSQL 등) 연결 사용
# -------------------------------------------------------------------
if "users" not in st.session_state:
    # role: 'admin' 또는 'user'
    st.session_state.users = {
        "admin": {"name": "관리자", "role": "admin", "cash": 0},
        "10101": {"name": "ㅁㅁ", "role": "user", "cash": 10000000},
        "10202": {"name": "ㄷㄷ", "role": "user", "cash": 10000000},
    }

# -------------------------------------------------------------------
# 관리자 전용 대시보드 화면
# -------------------------------------------------------------------
def render_admin_dashboard():
    st.title("⚙️ 관리자 전용 대시보드")
    st.info("관리자로 로그인되었습니다. 회원 및 게임 환경을 관리할 수 있습니다.")
    
    # 탭으로 관리자 기능 구분
    tab1, tab2, tab3 = st.tabs(["📊 전체 랭킹 및 데이터", "💰 시드 머니 관리", "👥 회원 관리"])

    # ---------------------------------------------------------------
    # TAB 1: 랭킹 및 참가자 데이터 조회
    # ---------------------------------------------------------------
    with tab1:
        st.subheader("🏆 전체 참가자 실시간 데이터")
        
        # 실제 데이터베이스 연동 시 유저별 평가금액 + 예수금 계산 로직 연결
        rank_data = []
        for student_id, info in st.session_state.users.items():
            if info["role"] == "user":
                # 예시 데이터 생성 (실제 구현 시 주식 보유 현황과 매핑)
                total_asset = info["cash"]  # 예수금 + 주식 평가금
                return_rate = ((total_asset - 10000000) / 10000000) * 100
                rank_data.append({
                    "학번": student_id,
                    "이름": info["name"],
                    "보유 예수금(원)": f"{info['cash']:,}",
                    "총 자산(원)": f"{total_asset:,}",
                    "수익률(%)": round(return_rate, 2)
                })
        
        if rank_data:
            df_rank = pd.DataFrame(rank_data)
            st.dataframe(df_rank, use_container_width=True)
            
            # CSV 다운로드 기능
            csv = df_rank.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 랭킹 데이터 CSV 다운로드",
                data=csv,
                file_name="student_ranks.csv",
                mime="text/csv",
            )
        else:
            st.write("등록된 학생 회원이 없습니다.")

    # ---------------------------------------------------------------
    # TAB 2: 시드 머니(초기 자금) 지급 및 관리
    # ---------------------------------------------------------------
    with tab2:
        st.subheader("💵 시드 머니 일괄 및 개별 지급")
        
        col1, col2 = st.columns(2)
        
        # 1. 개별 학생 시드 머니 수정/지급
        with col1:
            st.markdown("### 👤 개별 학생 시드 머니 수정")
            student_list = [uid for uid, info in st.session_state.users.items() if info["role"] == "user"]
            
            if student_list:
                selected_student = st.selectbox("학생 선택", student_list)
                current_cash = st.session_state.users[selected_student]["cash"]
                st.caption(f"현재 보유 예수금: **{current_cash:,}원**")
                
                new_cash = st.number_input("설정할 시드 머니 금액(원)", min_value=0, step=100000, value=current_cash)
                if st.button("개별 금액 변경 완료"):
                    st.session_state.users[selected_student]["cash"] = new_cash
                    st.success(f"{selected_student} 학생의 시드 머니가 {new_cash:,}원으로 변경되었습니다.")
                    st.rerun()

        # 2. 전체 학생 일괄 지급
        with col2:
            st.markdown("### 📢 전체 학생 일괄 지급")
            add_all_cash = st.number_input("전체 추가 지급 금액(원)", min_value=0, step=100000, value=1000000)
            if st.button("전체 학생에게 일괄 지급"):
                for uid, info in st.session_state.users.items():
                    if info["role"] == "user":
                        info["cash"] += add_all_cash
                st.success(f"모든 학생에게 {add_all_cash:,}원이 일괄 지급되었습니다.")
                st.rerun()

    # ---------------------------------------------------------------
    # TAB 3: 회원 관리 (조회, 비밀번호 초기화, 삭제)
    # ---------------------------------------------------------------
    with tab3:
        st.subheader("👥 회원 목록 및 계정 관리")
        
        user_list = []
        for uid, info in st.session_state.users.items():
            user_list.append({"학번/아이디": uid, "이름": info["name"], "권한": info["role"]})
        
        st.table(pd.DataFrame(user_list))
        
        st.divider()
        st.markdown("### ⚠️ 계정 제어")
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            target_user = st.selectbox("제어할 계정 선택", [u for u in st.session_state.users.keys() if u != "admin"])
            if st.button("비밀번호 초기화 (1234로 설정)"):
                # 실제 DB 비밀번호 해시 업데이트 로직
                st.success(f"{target_user} 계정의 비밀번호가 '1234'로 초기화되었습니다.")
                
        with col_m2:
            if target_user and st.button("❌ 계정 삭제", type="primary"):
                del st.session_state.users[target_user]
                st.warning(f"{target_user} 계정이 삭제되었습니다.")
                st.rerun()

# 학생 로그인 시 호출되는 실제 매매 화면 함수
def render_student_dashboard(user_id, user_info):
    st.title(f"📈 {user_info['name']} ({user_id}) 님의 주식 투자 대시보드")
    
    # 1. 상단 자산 현황 요약
    col1, col2, col3 = st.columns(3)
    col1.metric("보유 예수금", f"{user_info['cash']:,} 원")
    col2.metric("총 평가 금액", f"{user_info['cash']:,} 원")
    col3.metric("수익률", "0.00 %")

    st.divider()

    # 2. 주식 거래 / 잔고 확인 탭
    tab1, tab2 = st.tabs(["🛒 주식 매수/매도", "💼 내 포트폴리오"])
    
    with tab1:
        st.subheader("주식 주문")
        stock_name = st.selectbox("종목 선택", ["삼성전자", "SK하이닉스", "NAVER", "카카오"])
        qty = st.number_input("수량", min_value=1, value=1)
        
        col_buy, col_sell = st.columns(2)
        with col_buy:
            if st.button("매수하기", use_container_width=True):
                st.success(f"{stock_name} {qty}주 매수 주문이 완료되었습니다.")
        with col_sell:
            if st.button("매도하기", use_container_width=True):
                st.info(f"{stock_name} {qty}주 매도 주문이 완료되었습니다.")

    with tab2:
        st.subheader("현재 보유 주식")
        st.write("현재 보유 중인 주식이 없습니다.")

# -------------------------------------------------------------------
# 메인 로그인/페이지 라우팅 로직
# -------------------------------------------------------------------
def main():
    # 세션 상태 체크 (예시용 로그인 처리)
    if "logged_in_user" not in st.session_state:
        st.session_state.logged_in_user = None

    # 로그인 안 되어 있을 때
    if not st.session_state.logged_in_user:
        st.title("🔑 모의주식 투자 대회 로그인")
        user_id = st.text_input("학번/아이디")
        # 관리자 테스트용 안내
        st.caption("※ 관리자 아이디: `admin`")
        
        if st.button("로그인"):
            if user_id in st.session_state.users:
                st.session_state.logged_in_user = user_id
                st.rerun()
            else:
                st.error("존재하지 않는 아이디입니다.")
    else:
        # 로그인 상태
        current_user = st.session_state.users[st.session_state.logged_in_user]
        
        # 우측 상단 로그아웃 버튼
        col_head1, col_head2 = st.columns([4, 1])
        with col_head2:
            if st.button("로그아웃"):
                st.session_state.logged_in_user = None
                st.rerun()

        # 권한별 분기 처리
        if current_user["role"] == "admin":
            render_admin_dashboard()
        else:
            # 기존에 만드셨던 학생 매매 화면 함수(또는 render_student_dashboard)를 호출
            render_student_dashboard(st.session_state.logged_in_user, current_user)

if __name__ == "__main__":
    main()