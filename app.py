"""배달의민족 협력사 영업담당자 확인 (Streamlit)

담당자 이름 + 매니저 등록번호가 모두 일치하는 1명만 증빙 카드로 보여준다.
- 원본 시트 ID·gid는 st.secrets(sheet_id, sheet_gid)에서 읽는다 (A 협력사명, B 매니저등록번호, C 담당자명, D E메일, E 휴대폰, F 공정영업 수료일)
- 서비스계정(st.secrets["gcp_service_account"])이 없으면 예시 데이터로 도는 미리보기 모드
"""
import html
import re
import time

import streamlit as st
import streamlit.components.v1 as components

HEADER_ROWS = 1
# 헤더 확인: team_name / sales_manager_number / sales_manager_name / email / mobile_number / 공정영업교육 수료일
COL = {"company": "A", "manager_no": "B", "name": "C", "email": "D", "phone": "E", "edu_date": "F"}
MAX_FAILS, LOCK_SEC = 5, 60

st.set_page_config(page_title="배민 영업담당자 확인", page_icon="✅", layout="centered")
st.markdown(
    """
<style>
  #MainMenu, header, footer, [data-testid="stToolbar"] {visibility: hidden; height: 0;}
  .stApp {background: linear-gradient(180deg, #E6F8F7 0px, #F4F6F7 360px);}
  .block-container {max-width: 440px; padding-top: 1rem; padding-bottom: 2rem;}
  .brand {display:flex; align-items:center; justify-content:space-between; margin-bottom:14px;}
  .brand b {display:flex; align-items:center; gap:8px; font-weight:800; color:#1A9C97; font-size:15px;}
  .brand b i {width:10px; height:10px; border-radius:50%; background:#2AC1BC; display:inline-block;}
  .brand span {font-size:12px; color:#1A9C97; background:#fff; border:1px solid #BFEDEB; padding:4px 10px; border-radius:999px; font-weight:700;}

  .hero {position:relative; overflow:hidden; background:linear-gradient(135deg,#2AC1BC 0%,#1A9C97 100%); color:#fff;
         border-radius:22px; padding:22px 20px 20px; box-shadow:0 10px 30px rgba(26,156,151,.25); margin-bottom:16px;}
  .hero::before {content:""; position:absolute; right:-40px; top:-40px; width:160px; height:160px; border-radius:50%; background:rgba(255,255,255,.10);}
  .hero::after {content:""; position:absolute; right:30px; bottom:-60px; width:120px; height:120px; border-radius:50%; background:rgba(255,255,255,.08);}
  .hero .ico {width:52px; height:52px; border-radius:16px; background:rgba(255,255,255,.2); display:flex; align-items:center; justify-content:center; margin-bottom:14px;}
  .hero h1 {font-size:clamp(20px, 6.2vw, 25px); line-height:1.3; margin:0; padding:0; color:#fff; white-space:nowrap; letter-spacing:-.5px; font-weight:800;}
  .hero p {font-size:14px; line-height:1.55; margin:8px 0 0; opacity:.92;}
  .chips {display:flex; flex-wrap:wrap; gap:6px; margin-top:16px; position:relative; z-index:1;}
  .chips span {font-size:12px; font-weight:700; background:rgba(255,255,255,.18); padding:6px 10px; border-radius:999px;}

  [data-testid="stForm"] {background:#fff; border-radius:20px; padding:20px 18px 18px; box-shadow:0 4px 18px rgba(0,0,0,.06); border:0;}
  .stTextInput label p {font-weight:700; font-size:14px;}
  .stTextInput input {height:50px; font-size:17px;}
  .stFormSubmitButton button, .stButton button {width:100%; height:52px; font-size:17px; font-weight:800; border-radius:12px;}

  .note {font-size:12px !important; color:#9AA4AE; text-align:center; line-height:1.6; margin-top:20px;}
</style>
""",
    unsafe_allow_html=True,
)


def _secret(key, default=None):
    try:
        return st.secrets[key]
    except Exception:
        return default


def norm(v) -> str:
    return re.sub(r"\s+", "", str(v or "")).lower()


def format_phone(v) -> str:
    """시트 숫자서식으로 앞자리 0이 빠진 번호(1012345678)도 010-1234-5678로 맞춘다."""
    d = re.sub(r"[^0-9]", "", str(v or ""))
    if not d:
        return str(v or "").strip()
    if not d.startswith("0"):
        d = "0" + d
    if d.startswith("02"):
        return f"02-{d[2:-4]}-{d[-4:]}" if len(d) in (9, 10) else d
    if len(d) in (10, 11):
        return f"{d[:3]}-{d[3:-4]}-{d[-4:]}"
    return d


def norm_no(v) -> str:
    return norm(v).lstrip("0")


@st.cache_data(ttl=300, show_spinner=False)
def load_rows():
    """시트 전체를 서버 메모리에만 캐시 (5분). 화면으로는 일치한 1행만 나간다."""
    sa = _secret("gcp_service_account")
    if not sa or not _secret("sheet_id"):
        return None
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        dict(sa), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(_secret("sheet_id")).get_worksheet_by_id(int(_secret("sheet_gid")))
    return ws.get_all_values()[HEADER_ROWS:]


def lookup(name: str, manager_no: str):
    rows = load_rows()
    if rows is None:  # 미리보기 모드
        if manager_no.strip() == "0000":
            return None
        return {"company": "(예시) 협력사", "name": name, "email": "sample@example.com",
                "phone": "010-0000-0000", "edu_date": "2026-09-01"}
    idx = {k: ord(v.upper()) - 65 for k, v in COL.items()}
    qn, qno = norm(name), norm_no(manager_no)
    for r in rows:
        r = r + [""] * (max(idx.values()) + 1 - len(r))
        if norm(r[idx["name"]]) == qn and norm_no(r[idx["manager_no"]]) == qno:
            hit = {k: r[i].strip() for k, i in idx.items() if k != "manager_no"}
            hit["phone"] = format_phone(hit["phone"])
            return hit
    return None


def render_card(d: dict):
    e = {k: html.escape(v or "") for k, v in d.items()}
    tel = re.sub(r"[^0-9+]", "", d.get("phone") or "")
    edu = (f'<span class="edu">{e["edu_date"]}<span class="chk">수료</span></span>'
           if d.get("edu_date") else '<span class="none">미수료</span>')
    components.html(
        f"""
<style>
  * {{box-sizing:border-box;}}
  body {{margin:0; font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR",sans-serif; color:#1F2328; -webkit-font-smoothing:antialiased;}}
  .card {{background:#fff; border-radius:20px; overflow:hidden; box-shadow:0 6px 24px rgba(0,0,0,.08); margin:4px 4px 12px;}}
  .top {{background:#2AC1BC; color:#fff; padding:18px 20px 20px; position:relative; overflow:hidden;}}
  .top::after {{content:""; position:absolute; top:0; left:-60%; width:40%; height:100%;
     background:linear-gradient(100deg,transparent,rgba(255,255,255,.28),transparent); animation:shine 2.6s linear infinite;}}
  @keyframes shine {{to {{left:130%;}}}}
  .org {{font-size:13px; opacity:.9; font-weight:700;}}
  .title {{font-size:20px; font-weight:800; margin-top:4px;}}
  .badge {{display:inline-flex; align-items:center; gap:6px; margin-top:12px; background:rgba(255,255,255,.22); padding:6px 12px; border-radius:999px; font-size:13px; font-weight:800;}}
  .dot {{width:8px; height:8px; border-radius:50%; background:#fff; animation:pulse 1.2s ease-in-out infinite;}}
  @keyframes pulse {{0%,100% {{opacity:1; transform:scale(1);}} 50% {{opacity:.3; transform:scale(.7);}}}}
  .profile {{display:flex; gap:16px; padding:20px; align-items:center; border-bottom:1px solid #E5E7EB;}}
  .photo {{width:88px; height:110px; border-radius:12px; background:#F4F6F7; border:1.5px dashed #CBD2D9; display:flex; align-items:center; justify-content:center; color:#9AA4AE; font-size:13px; flex:none;}}
  .company {{font-size:14px; color:#6B7280; font-weight:700;}}
  .name {{font-size:26px; font-weight:800; margin-top:4px; letter-spacing:-.5px;}}
  .role {{font-size:13px; color:#1A9C97; font-weight:700; margin-top:6px;}}
  .rows {{padding:6px 20px 8px;}}
  .row {{display:flex; justify-content:space-between; gap:12px; padding:14px 0; border-bottom:1px solid #E5E7EB; font-size:15px;}}
  .row:last-child {{border-bottom:0;}}
  .k {{color:#6B7280; flex:none;}}
  .v {{font-weight:700; text-align:right; word-break:break-all;}}
  .v a {{color:inherit; text-decoration:none;}}
  .edu {{display:inline-flex; align-items:center; gap:6px;}}
  .chk {{background:#E6F8F7; color:#1A9C97; font-size:12px; padding:3px 8px; border-radius:999px;}}
  .none {{color:#E5484D;}}
  .stamp {{background:#E6F8F7; padding:14px 20px; font-size:13px; color:#1A9C97; display:flex; justify-content:space-between; align-items:center;}}
  .stamp b {{font-variant-numeric:tabular-nums; font-size:15px;}}
  .foot {{color:#6B7280; font-size:12px; line-height:1.6; text-align:center; margin:0 8px;}}
</style>
<div class="card">
  <div class="top"><div class="org">배달의민족</div><div class="title">협력사 영업담당자</div>
    <div class="badge"><span class="dot"></span>등록 확인됨</div></div>
  <div class="profile"><div class="photo">사진</div>
    <div><div class="company">{e["company"]}</div><div class="name">{e["name"]}</div>
    <div class="role">배민 공식 협력사 영업담당자</div></div></div>
  <div class="rows">
    <div class="row"><span class="k">협력사명</span><span class="v">{e["company"]}</span></div>
    <div class="row"><span class="k">E메일</span><span class="v"><a href="mailto:{e["email"]}">{e["email"] or "-"}</a></span></div>
    <div class="row"><span class="k">휴대폰번호</span><span class="v"><a href="tel:{tel}">{e["phone"] or "-"}</a></span></div>
    <div class="row"><span class="k">공정영업 교육 수료일</span><span class="v">{edu}</span></div>
  </div>
  <div class="stamp"><span>실시간 조회 시각</span><b id="clock"></b></div>
</div>
<p class="foot">시각이 계속 흐르고 상단 표시가 움직이면 실시간 조회 화면이에요.<br>캡처 이미지는 확인 화면으로 인정되지 않아요.</p>
<script>
  const p = n => String(n).padStart(2, "0");
  const t = () => {{ const d = new Date();
    document.getElementById("clock").textContent =
      `${{d.getFullYear()}}.${{p(d.getMonth()+1)}}.${{p(d.getDate())}} ${{p(d.getHours())}}:${{p(d.getMinutes())}}:${{p(d.getSeconds())}}`; }};
  t(); setInterval(t, 1000);
</script>
""",
        height=600,
    )


ss = st.session_state
ss.setdefault("fails", 0)
ss.setdefault("locked_until", 0.0)
ss.setdefault("hit", None)

st.markdown('<div class="brand"><b><i></i>배달의민족</b><span>공식 협력사 확인</span></div>', unsafe_allow_html=True)

if ss.hit:
    render_card(ss.hit)
    if st.button("다른 담당자 조회", type="secondary", use_container_width=True):
        ss.hit = None
        st.rerun()
    st.stop()

st.markdown(
    '<div class="hero">'
    '<div class="ico"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
    '<path d="M9 12l2 2 4-4"/></svg></div>'
    '<h1>협력사 영업담당자 확인</h1>'
    '<p>찾아온 영업담당자가 배달의민족에 등록된<br>공식 협력사 담당자인지 바로 확인하세요.</p>'
    '<div class="chips"><span>✓ 공식 등록 여부</span><span>✓ 공정영업 교육 수료</span><span>✓ 실시간 조회</span></div>'
    '</div>',
    unsafe_allow_html=True,
)

with st.form("q", border=False):
    name = st.text_input("담당자 이름", placeholder="이름 입력")
    no = st.text_input("매니저 등록번호", placeholder="매니저 등록번호 입력")
    go = st.form_submit_button("확인하기", type="primary", use_container_width=True)

if go:
    wait = ss.locked_until - time.time()
    if wait > 0:
        st.error(f"조회 실패가 많아 잠시 막혔어요. {int(wait) + 1}초 뒤 다시 시도해주세요.")
    elif not name.strip() or not no.strip():
        st.warning("이름과 매니저 등록번호를 모두 입력해주세요.")
    else:
        try:
            with st.spinner("확인 중…"):
                hit = lookup(name, no)
        except Exception as ex:
            print(f"[lookup error] {type(ex).__name__}: {str(ex)[:300]}", flush=True)
            hit = False
            st.error("일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.")
        if hit:
            ss.fails, ss.hit = 0, hit
            st.rerun()
        elif hit is None:
            ss.fails += 1
            if ss.fails >= MAX_FAILS:
                ss.fails, ss.locked_until = 0, time.time() + LOCK_SEC
            time.sleep(0.8)
            st.error("일치하는 영업담당자가 없습니다.\n\n이름과 매니저 등록번호를 다시 확인해주세요.")

st.markdown(
    '<div class="note">조회 결과가 없거나 의심스러우면 상담을 멈추고<br>배민외식업광장 고객센터(1600-0987)로 문의해주세요.</div>',
    unsafe_allow_html=True,
)

if _secret("gcp_service_account") is None:
    st.caption("⚙️ 미리보기 모드 — 서비스계정이 없어 예시 데이터로 표시돼요.")
