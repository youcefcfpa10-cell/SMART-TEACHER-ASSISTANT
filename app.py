
# -*- coding: utf-8 -*-
"""Smart Teacher Assistant — APC | تطبيق Streamlit لإنتاج وثائق مبنية على RNFC."""

from __future__ import annotations

import io
import os
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
import pandas as pd
import streamlit as st

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from pptx import Presentation
from pptx.dml.color import RGBColor as PPTColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches as PPTInches, Pt as PPTPt

from apc_engine import APCEngine
from logigramme import LogigrammeGenerator
from rnfc_connector import DATA_DIR, RNFCConnector, RNFCConnectorError

from cloud_auth import (
    CloudConfigurationError,
    CloudAccessError,
    attach_user_token,
    cloud_configured,
    create_admin_client,
    create_public_client,
    get_access_status,
    is_admin,
    issue_license_code,
    list_teacher_projects,
    load_teacher_project,
    make_session_id,
    normalize_license_code,
    redeem_license,
    register_session,
    save_teacher_project,
    start_trial,
)


# ============================================================
# إعدادات التطبيق
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = BASE_DIR / "PHOTOS"

BLUE, GOLD, DARK = "#0A2A5A", "#D4AF37", "#182230"

st.set_page_config(
    page_title="المساعد الذكي للأستاذ — APC",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    html, body, .stApp {{
        direction: rtl!important;
        text-align: right!important;
        background: #F7F9FC;
        color: {DARK};
    }}

    [data-testid="stSidebar"] {{
        direction: rtl!important;
        background: #F9FBFF;
        border-left: 2px solid {GOLD};
    }}

    h1, h2, h3 {{
        color: {BLUE};
    }}

    .stButton>button,
    .stDownloadButton>button {{
        background: {BLUE};
        color: white;
        border-radius: 8px;
        font-weight: 700;
    }}

    .hero {{
        background: linear-gradient(135deg, {BLUE}, #174685);
        border-radius: 16px;
        padding: 1.4rem 1.8rem;
        color: white;
        margin-bottom: 1rem;
        border-bottom: 5px solid {GOLD};
    }}

    .hero h1 {{
        color: white!important;
    }}

    .note {{
        background: #fff;
        border-right: 5px solid {GOLD};
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# إدارة جلسة المستخدم
# ============================================================

def _store_auth_session(client, auth_session, user):
    st.session_state["cloud_access_token"] = auth_session.access_token
    st.session_state["cloud_user_id"] = user.id
    st.session_state["cloud_user_email"] = user.email or ""
    st.session_state["cloud_client"] = client
    st.session_state.setdefault("cloud_session_id", make_session_id())


def _logout_cloud():
    client = st.session_state.get("cloud_client")

    try:
        if client:
            client.auth.sign_out()
    except Exception:
        pass

    for key in (
        "cloud_access_token",
        "cloud_user_id",
        "cloud_user_email",
        "cloud_client",
        "cloud_access_status",
        "cloud_session_id",
    ):
        st.session_state.pop(key, None)


# ============================================================
# شاشة تسجيل الدخول وإنشاء الحساب
# ============================================================

def _render_auth_screen():

    st.markdown(
        """
        <div class="hero">
            <h1>🎓 المساعد الذكي للأستاذ</h1>
            <p>فضاء سحابي خاص بكل أستاذ</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "أنشئ حسابك أو سجل الدخول للوصول إلى حقائبك "
        "المحفوظة من أجهزتك المختلفة."
    )

    login_tab, signup_tab = st.tabs(
        ["تسجيل الدخول", "إنشاء حساب جديد"]
    )

    # تسجيل الدخول
    with login_tab:

        with st.form("cloud_login_form"):

            email = st.text_input("البريد الإلكتروني")

            password = st.text_input(
                "كلمة المرور",
                type="password",
            )

            submitted = st.form_submit_button(
                "دخول",
                use_container_width=True,
            )

        if submitted:

            try:
                client = create_public_client()

                result = client.auth.sign_in_with_password(
                    {
                        "email": email.strip(),
                        "password": password,
                    }
                )

                if not result.session or not result.user:

                    st.error(
                        "تعذر إنشاء جلسة دخول. تحقق من البريد "
                        "وكلمة المرور وتأكيد البريد الإلكتروني."
                    )

                else:

                    _store_auth_session(
                        client,
                        result.session,
                        result.user,
                    )

                    st.rerun()

            except Exception as exc:

                st.error(
                    f"تعذر تسجيل الدخول: {exc}"
                )

        # استعادة كلمة المرور
        with st.form("password_reset_form"):

            reset_email = st.text_input(
                "البريد لاستعادة كلمة المرور"
            )

            reset_submit = st.form_submit_button(
                "إرسال رابط استعادة كلمة المرور"
            )

        if reset_submit:

            try:

                create_public_client().auth.reset_password_for_email(
                    reset_email.strip()
                )

                st.success(
                    "إذا كان البريد مسجلاً، فستصلك رسالة "
                    "لإعادة تعيين كلمة المرور."
                )

            except Exception as exc:

                st.error(
                    f"تعذر إرسال طلب الاستعادة: {exc}"
                )

    # إنشاء حساب جديد
    with signup_tab:

        with st.form("cloud_signup_form"):

            full_name = st.text_input("الاسم الكامل")

            email_new = st.text_input(
                "البريد الإلكتروني",
                key="signup_email",
            )

            password_new = st.text_input(
                "كلمة المرور",
                type="password",
                key="signup_password",
            )

            password_confirm = st.text_input(
                "تأكيد كلمة المرور",
                type="password",
            )

            accepted = st.checkbox(
                "أوافق على شروط الاستخدام وسياسة الخصوصية"
            )

            submitted_new = st.form_submit_button(
                "إنشاء الحساب وبدء التجربة",
                use_container_width=True,
            )

        if submitted_new:

            if (
                not full_name.strip()
                or not email_new.strip()
                or len(password_new) < 8
            ):

                st.error(
                    "أدخل الاسم والبريد، واجعل كلمة المرور 8 أحرف على الأقل."
                )

            elif password_new != password_confirm:

                st.error(
                    "كلمتا المرور غير متطابقتين."
                )

            elif not accepted:

                st.error(
                    "يجب الموافقة على شروط الاستخدام وسياسة الخصوصية."
                )

            else:

                try:

                    client = create_public_client()

                    result = client.auth.sign_up(
                        {
                            "email": email_new.strip(),
                            "password": password_new,
                            "options": {
                                "data": {
                                    "full_name": full_name.strip()
                                }
                            },
                        }
                    )

                    if result.session and result.user:

                        _store_auth_session(
                            client,
                            result.session,
                            result.user,
                        )

                        st.success(
                            "تم إنشاء الحساب. تبدأ التجربة عند أول دخول ناجح."
                        )

                        st.rerun()

                    else:

                        st.success(
                            "تم إرسال طلب إنشاء الحساب. تحقق من بريدك "
                            "الإلكتروني لتأكيد الحساب، ثم سجل الدخول."
                        )

                except Exception as exc:

                    st.error(
                        f"تعذر إنشاء الحساب: {exc}"
                    )


# ============================================================
# تفعيل الترخيص
# ============================================================

def _render_license_activation(client):

    st.warning(
        "انتهت التجربة المجانية أو لا يوجد ترخيص فعال لهذا الحساب. "
        "أدخل رمز الترخيص المخصص لبريدك الإلكتروني."
    )

    with st.form("redeem_license_form"):

        code = st.text_input("رمز الترخيص")

        submitted = st.form_submit_button(
            "تفعيل الترخيص",
            use_container_width=True,
        )

    if submitted:

        try:

            result = redeem_license(
                client,
                normalize_license_code(code),
            )

            if result.get("success"):

                st.success(
                    f"تم تفعيل الترخيص حتى: "
                    f"{result.get('expires_at', '—')}"
                )

                st.rerun()

            st.error(
                "لم يتم تفعيل الترخيص."
            )

        except Exception as exc:

            st.error(
                f"تعذر تفعيل الترخيص: {exc}"
            )

    if st.button(
        "تسجيل الخروج",
        key="expired_logout",
    ):

        _logout_cloud()
        st.rerun()


# ============================================================
# عرض حالة الحساب والاشتراك
# ============================================================

def _render_account_status():

    status = st.session_state.get(
        "cloud_access_status",
        {},
    )

    if not status:
        return

    with st.sidebar.expander(
        "📋 حالة الحساب والاشتراك",
        expanded=True,
    ):

        email = st.session_state.get(
            "cloud_user_email",
            "",
        )

        st.caption("معلومات الحساب")

        st.write(
            f"📧 البريد الإلكتروني: {email or '—'}"
        )

        kind = status.get("kind", "")

        if kind == "trial":

            st.success(
                "نوع الاشتراك: تجربة مجانية"
            )

            st.write(
                "🆓 حالة الحساب: فترة تجريبية فعالة"
            )

        elif kind == "license":

            st.success(
                "نوع الاشتراك: ترخيص فعال"
            )

            st.write(
                "🔐 حالة الحساب: مرخص"
            )

        elif kind == "revoked":

            st.error(
                "حالة الترخيص: موقوف"
            )

        elif kind == "expired":

            st.warning(
                "حالة الاشتراك: منتهية"
            )

        trial_ends_at = status.get(
            "trial_ends_at"
        )

        expires_at = status.get(
            "expires_at"
        )

        def display_date(value):

            if not value:
                return "غير متوفر"

            try:

                parsed = datetime.fromisoformat(
                    str(value).replace("Z", "+00:00")
                )

                if parsed.tzinfo is None:

                    parsed = parsed.replace(
                        tzinfo=timezone.utc
                    )

                return parsed.astimezone().strftime(
                    "%Y-%m-%d %H:%M"
                )

            except (ValueError, TypeError):

                return str(value)

        if kind == "trial":

            st.write(
                f"📅 تاريخ انتهاء التجربة: "
                f"{display_date(trial_ends_at)}"
            )

        elif kind == "license":

            st.write(
                f"📅 تاريخ انتهاء الترخيص: "
                f"{display_date(expires_at)}"
            )

        if expires_at:

            try:

                expiry = datetime.fromisoformat(
                    str(expires_at).replace("Z", "+00:00")
                )

                if expiry.tzinfo is None:

                    expiry = expiry.replace(
                        tzinfo=timezone.utc
                    )

                remaining_seconds = (
                    expiry - datetime.now(timezone.utc)
                ).total_seconds()

                if remaining_seconds > 0:

                    remaining_days = math.ceil(
                        remaining_seconds / 86400
                    )

                    st.metric(
                        "الأيام المتبقية",
                        remaining_days,
                    )

                else:

                    st.metric(
                        "الأيام المتبقية",
                        0,
                    )

            except (ValueError, TypeError):

                st.caption(
                    "تعذر حساب الأيام المتبقية."
                )

        st.divider()

        max_sessions = status.get(
            "max_sessions"
        )

        if max_sessions is not None:

            st.write(
                f"💻 عدد الجلسات المتزامنة المسموحة: "
                f"{max_sessions}"
            )


# ============================================================
# لوحة المصمم وإدارة الحسابات
# ============================================================

def _render_admin_panel():

    st.header(
        "لوحة المصمم — إدارة الحسابات والتراخيص"
    )

    try:

        admin = create_admin_client()

        profiles = (
            admin.table("profiles")
            .select(
                "id,email,full_name,trial_started_at,trial_ends_at,created_at"
            )
            .order("created_at", desc=True)
            .limit(500)
            .execute()
            .data
            or []
        )

        licenses = (
            admin.table("licenses")
            .select(
                "user_id,status,expires_at,max_sessions"
            )
            .execute()
            .data
            or []
        )

        license_map = {
            x["user_id"]: x
            for x in licenses
        }

        st.metric(
            "عدد الحسابات",
            len(profiles),
        )

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "البريد الإلكتروني": p.get("email"),
                        "الاسم": p.get("full_name"),
                        "بداية التجربة": p.get("trial_started_at"),
                        "نهاية التجربة": p.get("trial_ends_at"),
                        "حالة الترخيص": license_map.get(
                            p["id"], {}
                        ).get(
                            "status",
                            "تجربة / دون ترخيص",
                        ),
                        "نهاية الترخيص": license_map.get(
                            p["id"], {}
                        ).get(
                            "expires_at",
                            "—",
                        ),
                        "الجلسات المسموحة": license_map.get(
                            p["id"], {}
                        ).get(
                            "max_sessions",
                            2,
                        ),
                    }
                    for p in profiles
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader(
            "إصدار رمز ترخيص"
        )

        if not profiles:

            st.info(
                "لا توجد حسابات مسجلة بعد."
            )

        else:

            options = {
                f"{p.get('email')} — {p.get('full_name') or 'دون اسم'}": p["id"]
                for p in profiles
            }

            with st.form("issue_license_form"):

                chosen = st.selectbox(
                    "حساب الأستاذ",
                    list(options),
                )

                duration = st.number_input(
                    "مدة الترخيص بالأيام",
                    min_value=1,
                    max_value=3650,
                    value=365,
                )

                max_sessions = st.number_input(
                    "عدد الجلسات المتزامنة",
                    min_value=1,
                    max_value=20,
                    value=3,
                )

                valid_days = st.number_input(
                    "صلاحية الرمز قبل استعماله (أيام)",
                    min_value=1,
                    max_value=365,
                    value=30,
                )

                issue = st.form_submit_button(
                    "إنشاء رمز الترخيص",
                    use_container_width=True,
                )

            if issue:

                code = issue_license_code(
                    admin,
                    options[chosen],
                    int(duration),
                    int(max_sessions),
                    int(valid_days),
                )

                st.session_state["new_license_code_once"] = code

                st.success(
                    "تم إنشاء الرمز. انسخه وأرسله إلى الأستاذ المحدد؛ "
                    "لن يعرض مرة أخرى بعد مغادرة هذه الجلسة."
                )

        if st.session_state.get("new_license_code_once"):

            st.code(
                st.session_state["new_license_code_once"]
            )

            if st.button(
                "إخفاء الرمز",
                key="hide_license_code",
            ):

                st.session_state.pop(
                    "new_license_code_once",
                    None,
                )

                st.rerun()

        st.subheader(
            "إدارة ترخيص قائم"
        )

        if profiles:

            revoke_options = {
                f"{p.get('email')} — {p.get('full_name') or 'دون اسم'}": p["id"]
                for p in profiles
            }

            with st.form("revoke_license_form"):

                revoke_teacher = st.selectbox(
                    "حساب الأستاذ",
                    list(revoke_options),
                    key="revoke_teacher",
                )

                confirm_revoke = st.checkbox(
                    "أؤكد إيقاف الترخيص لهذا الحساب"
                )

                revoke = st.form_submit_button(
                    "إيقاف الترخيص"
                )

            if revoke:

                if not confirm_revoke:

                    st.error(
                        "يرجى تأكيد عملية الإيقاف."
                    )

                else:

                    (
                        admin.table("licenses")
                        .update({"status": "revoked"})
                        .eq(
                            "user_id",
                            revoke_options[revoke_teacher],
                        )
                        .execute()
                    )

                    st.success(
                        "تم إيقاف الترخيص. لن يتمكن الحساب "
                        "من الوصول بعد إعادة التحقق."
                    )

    except Exception as exc:

        st.error(
            f"تعذر تحميل لوحة المصمم. تحقق من إعدادات "
            f"المفتاح الإداري وصلاحيات الحساب: {exc}"
        )


# ============================================================
# التحقق من صلاحية الحساب قبل دخول التطبيق
# ============================================================

def cloud_access_gate() -> bool:

    """Fail-closed cloud login gate; local bypass must be explicitly enabled."""

    if not cloud_configured():

        if (
            os.getenv("ALLOW_LOCAL_DEV", "false").lower() == "true"
            and os.getenv("APP_ENV", "local").lower() != "production"
        ):

            st.warning(
                "وضع التطوير المحلي مفعّل. هذا الوضع غير محمي "
                "بالحسابات ولا يجوز نشره للعامة."
            )

            return True

        st.error(
            "لم تُضبط إعدادات Supabase بعد. أضف مفاتيح المشروع "
            "إلى متغيرات البيئة في منصة الاستضافة."
        )

        st.stop()

    token = st.session_state.get(
        "cloud_access_token"
    )

    if not token:

        _render_auth_screen()
        return False

    try:

        client = (
            st.session_state.get("cloud_client")
            or create_public_client()
        )

        attach_user_token(
            client,
            token,
        )

        start_trial(client)

        status = get_access_status(client)

        if not status.get("allowed"):

            _render_license_activation(client)
            return False

        st.session_state["cloud_client"] = client

        st.session_state["cloud_access_status"] = status

        st.session_state.setdefault(
            "cloud_session_id",
            make_session_id(),
        )

        session_result = register_session(
            client,
            st.session_state["cloud_session_id"],
        )

        if not session_result.get("allowed"):

            st.error(
                f"{session_result.get('message', 'تم بلوغ الحد المسموح للجلسات')} "
                f"({session_result.get('active_count')}/"
                f"{session_result.get('max_sessions')}). "
                f"أغلق جلسة أخرى ثم أعد المحاولة."
            )

            if st.button(
                "تسجيل الخروج",
                key="session_limit_logout",
            ):

                _logout_cloud()
                st.rerun()

            return False

        return True

    except Exception as exc:

        st.error(
            f"تعذر التحقق من الحساب أو الترخيص: {exc}"
        )

        if st.button(
            "العودة إلى تسجيل الدخول",
            key="auth_relogin",
        ):

            _logout_cloud()
            st.rerun()

        return False


# ============================================================
# مساحة عمل الأستاذ والحقائب المحفوظة
# ============================================================

def render_teacher_workspace():

    client = st.session_state.get(
        "cloud_client"
    )

    if not client:
        return

    st.sidebar.divider()

    # عرض حالة الحساب والاشتراك
    _render_account_status()

    st.sidebar.divider()

    st.sidebar.subheader(
        "حقائبي المحفوظة"
    )

    try:

        projects = list_teacher_projects(client)

        if projects:

            labels = {
                f"{p['title']} — {str(p.get('updated_at', ''))[:10]}": p["id"]
                for p in projects
            }

            chosen = st.sidebar.selectbox(
                "استرجاع حقيبة",
                list(labels),
                key="saved_project_choice",
            )

            if st.sidebar.button(
                "فتح الحقيبة",
                use_container_width=True,
            ):

                item = load_teacher_project(
                    client,
                    labels[chosen],
                )

                if item and item.get("payload"):

                    payload = item["payload"]

                    st.session_state["selected_specialite"] = payload.get(
                        "specialite"
                    )

                    st.session_state["apc_form"] = payload.get(
                        "form"
                    )

                    st.session_state["selected_competences"] = payload.get(
                        "competences",
                        [],
                    )

                    st.session_state["competence_select"] = [
                        x.get("id")
                        for x in payload.get("competences", [])
                        if x.get("id")
                    ]

                    st.session_state["selected_mode"] = payload.get(
                        "mode",
                        "APC_strict",
                    )

                    st.session_state["logigramme_mode"] = payload.get(
                        "mode",
                        "APC_strict",
                    )

                    st.success(
                        "تم استرجاع الحقيبة إلى مساحة العمل."
                    )

                    st.rerun()

        else:

            st.sidebar.caption(
                "لم تحفظ أي حقيبة بعد."
            )

    except Exception as exc:

        st.sidebar.warning(
            f"تعذر تحميل قائمة الحقائب: {exc}"
        )

    if is_admin(
        st.session_state.get("cloud_user_id", "")
    ):

        if st.sidebar.button(
            "لوحة المصمم",
            use_container_width=True,
            key="open_admin_panel",
        ):

            st.session_state["show_admin_panel"] = True

    if st.sidebar.button(
        "تسجيل الخروج",
        use_container_width=True,
        key="cloud_logout",
    ):

        _logout_cloud()
        st.rerun()


# ============================================================
# أدوات معالجة بيانات RNFC
# ============================================================

def clean(value: Any, default: str = "—") -> str:

    if value is None:
        return default

    text = str(value).strip()

    return (
        default
        if text.casefold() in {"", "nan", "none", "null"}
        else text
    )


def label(item: Dict[str, Any]) -> str:

    return clean(
        item.get("label_ar")
        or item.get("label")
        or item.get("label_fr"),
        "غير معنون",
    )


def option_label(item: Dict[str, Any]) -> str:

    code = clean(
        item.get("code"),
        "",
    )

    return (
        f"{code} — {label(item)}"
        if code
        else label(item)
    )


def unique_by_id(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

    result = []
    seen = set()

    for item in items:

        if not isinstance(item, dict):
            continue

        key = str(
            item.get("id")
            or item.get("code")
            or label(item)
        )

        if key not in seen:

            seen.add(key)
            result.append(item)

    return result


# ============================================================
# إنشاء وثائق Word
# ============================================================

def add_doc_heading(doc, text: str, level: int = 1):

    h = doc.add_heading(
        text,
        level=level,
    )

    h.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    for run in h.runs:

        run.font.name = "Arial"
        run.font.color.rgb = RGBColor(10, 42, 90)

    return h


def add_doc_paragraph(doc, text: Any, bold: bool = False):

    p = doc.add_paragraph()

    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    r = p.add_run(
        str(text)
    )

    r.font.name = "Arial"
    r.font.size = Pt(10.5)
    r.bold = bold

    return p


def add_doc_table(doc, headers: List[str], rows: List[List[Any]]):

    table = doc.add_table(
        rows=1,
        cols=len(headers),
    )

    table.style = "Table Grid"

    for i, value in enumerate(headers):

        cell = table.rows[0].cells[i]
        cell.text = str(value)

    for row in rows:

        cells = table.add_row().cells

        for i, value in enumerate(row):

            cells[i].text = str(value)

    for row in table.rows:

        for cell in row.cells:

            for p in cell.paragraphs:

                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

                for run in p.runs:

                    run.font.name = "Arial"
                    run.font.size = Pt(9)

    return table


def build_word_document(
    specialite: Dict[str, Any],
    competences: List[Dict[str, Any]],
    fiches: List[Dict[str, Any]],
    dossier: Dict[str, Any],
    matrix_df: pd.DataFrame,
    form: Dict[str, Any],
    quality: Dict[str, Any],
) -> bytes:

    doc = docx.Document()

    for section in doc.sections:

        section.top_margin = Inches(.65)
        section.bottom_margin = Inches(.65)
        section.left_margin = Inches(.7)
        section.right_margin = Inches(.7)

    add_doc_heading(
        doc,
        "الحقيبة البيداغوجية وفق المقاربة بالكفاءات (APC)",
        0,
    )

    add_doc_paragraph(
        doc,
        f"التخصص: {label(specialite)}",
        True,
    )

    add_doc_paragraph(
        doc,
        f"رمز التخصص: {clean(specialite.get('code'))} | "
        f"المؤسسة: {form.get('institution') or 'غير محددة'}",
    )

    add_doc_paragraph(
        doc,
        f"المستوى: {form.get('niveau') or 'غير محدد'} | "
        f"نمط التكوين: {form.get('mode')} | "
        f"المقياس: {form.get('module') or 'يحدد وفق البرنامج'}",
    )

    add_doc_paragraph(
        doc,
        f"الحجم الساعي: {form['total_hours']} ساعة | "
        f"المرجع: {form.get('reference') or 'ملف RNFC المحلي'}",
    )

    add_doc_heading(
        doc,
        "1. بطاقة تعريف المرجعية",
        1,
    )

    def paired_text(field: str) -> str:

        value = specialite.get(field, {})

        if isinstance(value, dict):

            ar = value.get("ar", "")
            fr = value.get("fr", "")

            return (
                " | ".join(x for x in (ar, fr) if x)
                or "—"
            )

        return clean(value)

    add_doc_table(
        doc,
        ["المجال", "البيانات"],
        [
            ["القطاع", dossier.get("secteur", "—")],
            ["الشعبة / المجال", dossier.get("domaine", "—")],
            ["المجال الفرعي", dossier.get("sous_domaine", "—")],
            ["نوع التكوين", paired_text("type_formation")],
            ["الشهادة", paired_text("diplome")],
            ["مدة التكوين", paired_text("duree")],
            ["المستوى الدراسي", paired_text("niveau_scolaire")],
            ["نمط التكوين الوارد في RNFC", paired_text("mode_formation")],
            ["مصدر البيانات", st.session_state.get("rnfc_source", "ملف RNFC المحلي")],
            ["ورقة Excel", specialite.get("source_sheet", "—")],
            ["عدد العناصر التأهيلية المحددة", len(competences)],
        ],
    )

    for title, field in [
        ("الهدف العام المرجعي", "objectif_reference"),
        ("تعريف المهنة", "definition_metier"),
        ("المناصب أو التسميات المهنية", "appellations_metier"),
        ("شروط الالتحاق/المتطلبات الواردة", "conditions_acces"),
        ("التطور التنظيمي", "evolution_reglementaire"),
        ("كيفية التقييم حسب المرجع", "modalites_evaluation"),
    ]:

        value = paired_text(field)

        if value != "—":

            add_doc_heading(
                doc,
                title,
                2,
            )

            add_doc_paragraph(
                doc,
                value,
            )

    complementary = specialite.get(
        "ressources_complementaires",
        [],
    )

    if complementary:

        add_doc_heading(
            doc,
            "الوحدات / المواد التكميلية الواردة في RNFC (modc)",
            2,
        )

        add_doc_table(
            doc,
            ["العنصر", "المقابل الفرنسي"],
            [
                [
                    x.get("label_ar") or x.get("label", "—"),
                    x.get("label_fr", "—"),
                ]
                for x in complementary
            ],
        )

    cqp = specialite.get(
        "competences_professionnelles_cqp",
        [],
    )

    if cqp:

        add_doc_heading(
            doc,
            "قائمة CQP الواردة في RNFC (listcqp)",
            2,
        )

        add_doc_table(
            doc,
            ["العنصر", "المقابل الفرنسي"],
            [
                [
                    x.get("label_ar") or x.get("label", "—"),
                    x.get("label_fr", "—"),
                ]
                for x in cqp
            ],
        )

    add_doc_heading(
        doc,
        "2. مصفوفة الكفاءات والعلاقات القبلية",
        1,
    )

    matrix_rows = (
        matrix_df.fillna("").astype(str).values.tolist()
        if not matrix_df.empty
        else [["لا توجد بيانات كافية"]]
    )

    add_doc_table(
        doc,
        list(matrix_df.columns) if not matrix_df.empty else ["الحالة"],
        matrix_rows,
    )

    for idx, (competence, fiche) in enumerate(
        zip(competences, fiches),
        1,
    ):

        doc.add_page_break()

        add_doc_heading(
            doc,
            f"3.{idx}. بطاقة التعلم: {fiche['competence']['nom']}",
            1,
        )

        add_doc_paragraph(
            doc,
            f"الرمز: {fiche['competence']['code']}",
        )

        add_doc_paragraph(
            doc,
            f"الوصف المرجعي: {fiche['competence']['description']}",
        )

        add_doc_paragraph(
            doc,
            f"الهدف الوسيط: {fiche['objectif_intermediaire']}",
            True,
        )

        if fiche.get("prerequisites"):

            add_doc_paragraph(
                doc,
                "المكتسبات القبلية: "
                + "؛ ".join(fiche["prerequisites"]),
            )

        if fiche.get("conditions"):

            add_doc_paragraph(
                doc,
                "شروط الإنجاز: "
                + "؛ ".join(fiche["conditions"]),
            )

        add_doc_heading(
            doc,
            "الوضعية المشكلة ومراحل التعلم",
            2,
        )

        add_doc_table(
            doc,
            [
                "المرحلة",
                "المدة",
                "الوضعية / المهمة",
                "نشاط الأستاذ",
                "نشاط المتكون",
                "الأثر المنتظر",
            ],
            [
                [
                    p["titre_ar"],
                    f"{p['duree_min']} د",
                    p["scenario"],
                    p["role_formateur"],
                    p["role_apprenant"],
                    "إنتاج أو أثر قابل للملاحظة",
                ]
                for p in fiche["phases"]
            ],
        )

        add_doc_heading(
            doc,
            "المحتوى والموارد",
            2,
        )

        add_doc_table(
            doc,
            ["العنصر", "التفصيل", "مصدره"],
            [
                [
                    x["element"],
                    x["detail"],
                    x.get("source", "مقترح"),
                ]
                for x in fiche["contenu_cours"]
            ]
            or [
                [
                    "غير متوفر",
                    "يستكمل من المرجع",
                    "غير محدد",
                ]
            ],
        )

        add_doc_heading(
            doc,
            "شبكة تقييم الأداء",
            2,
        )

        add_doc_table(
            doc,
            [
                "المعيار",
                "الوزن المقترح %",
                "المؤشر",
                "حالة المصدر",
            ],
            [
                [
                    x["critere"],
                    x["poids_propose"],
                    x["indicateurs"],
                    x.get("source", "مقترح"),
                ]
                for x in fiche["grille_evaluation"]
            ],
        )

        add_doc_paragraph(
            doc,
            "تنبيه: الأوزان والمؤشرات التي لا يثبت ورودها "
            "في المرجع تعد مقترحات قابلة للتعديل وليست معايير رسمية.",
        )

    add_doc_heading(
        doc,
        "4. تقرير فحص الاتساق البيداغوجي",
        1,
    )

    add_doc_table(
        doc,
        ["عنصر الفحص", "النتيجة"],
        [
            [k, v]
            for k, v in quality.items()
        ],
    )

    add_doc_paragraph(
        doc,
        "لا تعتمد الحقيبة إدارياً قبل استكمال العناصر غير المتوفرة "
        "ومطابقة المدة والمعايير مع البرنامج الرسمي والوثائق الأصلية.",
    )

    buffer = io.BytesIO()

    doc.save(buffer)

    return buffer.getvalue()


# ============================================================
# إنشاء عرض PowerPoint
# ============================================================

def set_ppt_text(
    shape,
    text: str,
    font_size: int = 20,
    bold: bool = False,
):

    tf = shape.text_frame

    tf.clear()

    p = tf.paragraphs[0]

    p.text = str(text)
    p.alignment = PP_ALIGN.RIGHT

    p.font.size = PPTPt(font_size)
    p.font.bold = bold
    p.font.name = "Arial"
    p.font.color.rgb = PPTColor(24, 34, 48)


def build_ppt(
    specialite: Dict[str, Any],
    competences: List[Dict[str, Any]],
    fiches: List[Dict[str, Any]],
    form: Dict[str, Any],
) -> bytes:

    prs = Presentation()

    prs.slide_width = PPTInches(13.333)
    prs.slide_height = PPTInches(7.5)

    blank = prs.slide_layouts[6]

    def slide(title: str, bullets: List[str]):

        s = prs.slides.add_slide(blank)

        box = s.shapes.add_textbox(
            PPTInches(.5),
            PPTInches(.25),
            PPTInches(12.3),
            PPTInches(.7),
        )

        set_ppt_text(
            box,
            title,
            22,
            True,
        )

        body = s.shapes.add_textbox(
            PPTInches(.8),
            PPTInches(1.2),
            PPTInches(11.8),
            PPTInches(5.8),
        )

        tf = body.text_frame

        tf.clear()
        tf.word_wrap = True

        for i, item in enumerate(bullets):

            p = (
                tf.paragraphs[0]
                if i == 0
                else tf.add_paragraph()
            )

            p.text = str(item)
            p.alignment = PP_ALIGN.RIGHT
            p.font.name = "Arial"
            p.font.size = PPTPt(16)

    slide(
        "المساعد الذكي للأستاذ | APC",
        [
            f"التخصص: {label(specialite)}",
            f"المقياس: {form.get('module') or 'غير محدد'}",
            f"الحجم الساعي: {form['total_hours']} ساعة",
            f"عدد الكفاءات المحددة: {len(competences)}",
        ],
    )

    for fiche in fiches:

        slide(
            f"الكفاءة: {fiche['competence']['nom']}",
            [
                f"الرمز: {fiche['competence']['code']}",
                fiche["objectif_intermediaire"],
                *[
                    f"{p['titre_ar']} — {p['duree_min']} دقيقة"
                    for p in fiche["phases"]
                ],
            ],
        )

        slide(
            "المحتوى والموارد",
            [
                f"{x['element']}: {x['detail']}"
                for x in fiche["contenu_cours"]
            ]
            or [
                "يستكمل المحتوى من المرجع المعتمد."
            ],
        )

    out = io.BytesIO()

    prs.save(out)

    return out.getvalue()


# ============================================================
# واجهة التطبيق
# ============================================================

def render_header():

    st.markdown(
        """
        <div class="hero">
            <h1>🎓 المساعد الذكي للأستاذ</h1>
            <p>
                هندسة التكوين وإعداد الوثائق وفق المقاربة بالكفاءات APC
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar():

    with st.sidebar:

        logo = (
            next(
                (
                    p
                    for p in PHOTOS_DIR.glob("*")
                    if p.is_file()
                    and "itp1" in p.stem.casefold()
                ),
                None,
            )
            if PHOTOS_DIR.exists()
            else None
        )

        if logo:

            st.image(
                str(logo),
                use_container_width=True,
            )

        st.markdown(
            "## المرجع المحلي RNFC"
        )

        st.caption(
            f"مجلد البيانات: `{DATA_DIR}`"
        )

        connector = RNFCConnector()

        sheets = connector.get_sheet_names()

        sheet = (
            st.selectbox(
                "ورقة Excel",
                sheets,
            )
            if sheets
            else None
        )

        if st.button(
            "تحميل بيانات RNFC",
            use_container_width=True,
        ):

            try:

                payload = (
                    connector.load_data(sheet_name=sheet)
                    if sheet
                    else connector.load_data()
                )

                st.session_state["rnfc_payload"] = payload

                st.session_state["rnfc_source"] = payload.get(
                    "source",
                    "",
                )

                st.success(
                    f"تم تحميل "
                    f"{payload.get('stats', {}).get('specialites', 0)} تخصص."
                )

                st.rerun()

            except RNFCConnectorError as exc:

                st.error(str(exc))

            except Exception as exc:

                st.error(
                    f"خطأ غير متوقع أثناء التحميل: {exc}"
                )

        payload = st.session_state.get(
            "rnfc_payload"
        )

        if payload:

            st.metric(
                "التخصصات",
                payload.get("stats", {}).get("specialites", 0),
            )

        render_teacher_workspace()


# ============================================================
# الصفحة الأولى: اختيار التخصص
# ============================================================

def page_selection(payload):

    st.header(
        "1. اختيار التخصص"
    )

    if not payload or not payload.get("specialites"):

        st.info(
            "ضع ملف RNFC داخل مجلد data بجانب التطبيق، "
            "ثم اضغط تحميل بيانات RNFC."
        )

        return

    specs = payload["specialites"]

    sectors = unique_by_id(
        [
            x.get("secteur", {})
            for x in specs
        ]
    )

    sector = (
        st.selectbox(
            "القطاع المهني",
            sectors,
            format_func=option_label,
            key="sector_select",
        )
        if sectors
        else None
    )

    subset = [
        x
        for x in specs
        if not sector
        or x.get("secteur", {}).get("id") == sector.get("id")
    ]

    domains = unique_by_id(
        [
            x.get("domaine", {})
            for x in subset
        ]
    )

    domain = (
        st.selectbox(
            "الشعبة / المجال",
            domains,
            format_func=option_label,
            key="domain_select",
        )
        if domains
        else None
    )

    subset = [
        x
        for x in subset
        if not domain
        or x.get("domaine", {}).get("id") == domain.get("id")
    ]

    spec = (
        st.selectbox(
            "التخصص",
            subset,
            format_func=option_label,
            key="specialite_select",
        )
        if subset
        else None
    )

    if spec:

        st.session_state["selected_specialite"] = spec

        st.success(
            f"التخصص المحدد: {label(spec)}"
        )


# ============================================================
# الصفحة الثانية: المعلومات التنظيمية
# ============================================================

def page_information():

    st.header(
        "2. المعلومات التنظيمية"
    )

    saved = st.session_state.get(
        "apc_form",
        {},
    )

    modes = [
        "حضوري",
        "تمهين",
        "عن بعد",
        "مختلط",
    ]

    languages = [
        "العربية",
        "العربية مع المصطلح الفرنسي",
    ]

    with st.form("apc_info_form"):

        c1, c2 = st.columns(2)

        institution = c1.text_input(
            "المؤسسة التكوينية",
            value=saved.get("institution", ""),
        )

        niveau = c2.text_input(
            "مستوى التكوين",
            value=saved.get("niveau", ""),
        )

        mode = c1.selectbox(
            "نمط التكوين",
            modes,
            index=(
                modes.index(saved.get("mode"))
                if saved.get("mode") in modes
                else 0
            ),
        )

        module = c2.text_input(
            "اسم المقياس",
            value=saved.get("module", ""),
        )

        total_hours = c1.number_input(
            "الحجم الساعي للمقياس",
            min_value=1,
            max_value=2000,
            value=int(saved.get("total_hours", 60)),
        )

        lesson_minutes = c2.number_input(
            "مدة الحصة / بطاقة التعلم بالدقائق",
            min_value=15,
            max_value=480,
            value=int(saved.get("lesson_minutes", 120)),
        )

        reference = c1.text_area(
            "مرجع البرنامج الرسمي أو ملاحظات التوثيق",
            value=saved.get("reference", ""),
        )

        language = c2.selectbox(
            "لغة الوثائق",
            languages,
            index=(
                languages.index(saved.get("language"))
                if saved.get("language") in languages
                else 0
            ),
        )

        submitted = st.form_submit_button(
            "حفظ المعلومات",
            use_container_width=True,
        )

    if submitted:

        st.session_state["apc_form"] = {
            "institution": institution,
            "niveau": niveau,
            "mode": mode,
            "module": module,
            "total_hours": int(total_hours),
            "lesson_minutes": int(lesson_minutes),
            "reference": reference,
            "language": language,
        }

        st.success(
            "تم حفظ المعلومات التنظيمية."
        )


# ============================================================
# التحقق من البيانات المحددة
# ============================================================

def selected_data():

    spec = st.session_state.get(
        "selected_specialite"
    )

    form = st.session_state.get(
        "apc_form"
    )

    if not spec:

        st.info(
            "اختر التخصص أولاً."
        )

        return None

    if not form:

        st.info(
            "أكمل المعلومات التنظيمية أولاً."
        )

        return None

    comps = spec.get(
        "competences",
        [],
    )

    if not comps:

        st.warning(
            "لا توجد عناصر تأهيلية مستخرجة من modQ "
            "لهذا التخصص. لن يتم إنشاء كفاءة افتراضية."
        )

        return None

    return spec, form, comps


# ============================================================
# الصفحة الثالثة: الكفاءات وبطاقات التعلم
# ============================================================

def page_competences():

    st.header(
        "3. الكفاءات وبطاقات التعلم"
    )

    data = selected_data()

    if not data:
        return

    spec, form, comps = data

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "الرمز": c.get("code"),
                    "العنصر التأهيلي": c.get("label_ar") or c.get("label"),
                    "المقابل الفرنسي": c.get("label_fr", ""),
                    "المصدر": c.get("source_status", "بيانات المرجع"),
                }
                for c in comps
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    complementary = spec.get(
        "ressources_complementaires",
        [],
    )

    if complementary:

        with st.expander(
            "الوحدات / المواد التكميلية الواردة في RNFC (modc)"
        ):

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "العنصر بالعربية": x.get("label_ar") or x.get("label"),
                            "المقابل الفرنسي": x.get("label_fr", ""),
                        }
                        for x in complementary
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

    cqp = spec.get(
        "competences_professionnelles_cqp",
        [],
    )

    if cqp:

        with st.expander(
            "قائمة CQP الواردة في RNFC (listcqp)"
        ):

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "العنصر بالعربية": x.get("label_ar") or x.get("label"),
                            "المقابل الفرنسي": x.get("label_fr", ""),
                        }
                        for x in cqp
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

    ids = [
        c["id"]
        for c in comps
    ]

    selected = st.multiselect(
        "حدد العناصر التي تريد إعداد بطاقاتها",
        ids,
        default=[ids[0]],
        format_func=lambda cid: next(
            (
                f"{c.get('code', '')} — {c.get('label', '')}"
                for c in comps
                if c["id"] == cid
            ),
            cid,
        ),
        key="competence_select",
    )

    active = [
        c
        for c in comps
        if c["id"] in selected
    ]

    if active:

        engine = APCEngine(
            form["lesson_minutes"]
        )

        fiches = [
            engine.generer_fiche(c)
            for c in active
        ]

        st.session_state.update(
            {
                "selected_competences": active,
                "generated_fiches": fiches,
            }
        )

        for fiche in fiches:

            with st.expander(
                f"{fiche['competence']['code']} — "
                f"{fiche['competence']['nom']}",
                expanded=True,
            ):

                st.write(
                    fiche["objectif_intermediaire"]
                )

                st.dataframe(
                    pd.DataFrame(fiche["plan_cours"]),
                    use_container_width=True,
                    hide_index=True,
                )

                for note in fiche.get("quality_notes", []):

                    st.warning(note)


# ============================================================
# الصفحة الرابعة: المصفوفة واللوجيغرام
# ============================================================

def page_logigramme():

    st.header(
        "4. مصفوفة الكفاءات واللوجيغرام"
    )

    data = selected_data()

    if not data:
        return

    _, _, comps = data

    mode = st.selectbox(
        "طريقة التنظيم",
        ["APC_strict", "traditionnel"],
        format_func=lambda x: LogigrammeGenerator.MODES[x]["label"],
        key="logigramme_mode",
    )

    generator = LogigrammeGenerator()

    try:

        matrix = generator.generer_matrice(
            comps,
            mode,
        )

        process = generator.generer_processus(
            comps,
            mode,
        )

        st.dataframe(
            matrix,
            use_container_width=True,
            hide_index=True,
        )

        if process["cycles"]:

            st.error(
                f"علاقات دائرية مكتشفة: {process['cycles']}"
            )

        if process["unknown_prerequisites"]:

            st.warning(
                "متطلبات قبلية غير معروفة: "
                f"{process['unknown_prerequisites']}"
            )

        if process["blocked_nodes"]:

            st.warning(
                f"عناصر متعذرة الترتيب بسبب دورة: "
                f"{process['blocked_nodes']}"
            )

        if process["is_valid_dag"]:

            if process.get("has_documented_dependencies"):

                st.success(
                    "العلاقات القبلية المعروفة لا تحتوي "
                    "على دورات أو مراجع مجهولة."
                )

            else:

                st.info(
                    "لا توجد علاقات قبلية موثقة في بيانات العناصر المحددة؛ "
                    "لذلك لا يُفترض ترتيب بيداغوجي أو مجموعات متسلسلة."
                )

        st.session_state["matrix_df"] = matrix
        st.session_state["process"] = process
        st.session_state["selected_mode"] = mode

    except Exception as exc:

        st.error(
            f"تعذر إنشاء المصفوفة: {exc}"
        )


# ============================================================
# الصفحة الخامسة: الحقيبة البيداغوجية والتصدير
# ============================================================

def page_package():

    st.header(
        "5. الحقيبة البيداغوجية والتصدير"
    )

    data = selected_data()

    if not data:
        return

    spec, form, _ = data

    comps = st.session_state.get(
        "selected_competences",
        [],
    )

    if not comps:

        st.info(
            "انتقل إلى صفحة الكفاءات وحدد العناصر المطلوب إعدادها."
        )

        return

    engine = APCEngine(
        form["lesson_minutes"]
    )

    fiches = [
        engine.generer_fiche(c)
        for c in comps
    ]

    generator = LogigrammeGenerator()

    mode = st.session_state.get(
        "selected_mode",
        "APC_strict",
    )

    try:

        matrix = generator.generer_matrice(
            comps,
            mode,
        )

        dossier = generator.generer_dossier_ouverture(
            spec,
            comps,
            mode,
        )

    except Exception as exc:

        st.error(
            f"تعذر إعداد ملف التنظيم: {exc}"
        )

        return

    process = dossier["controle_coherence"]

    quality = {
        "عدد العناصر المختارة": str(len(comps)),
        "وجود علاقات دائرية": (
            "نعم"
            if process["cycles"]
            else "لا وفق البيانات المتاحة"
        ),
        "متطلبات قبلية مجهولة": str(
            len(process["unknown_prerequisites"])
        ),
        "عناصر متعذرة الترتيب": str(
            len(process["blocked_nodes"])
        ),
        "مدد بطاقات التعلم": (
            f"{form['lesson_minutes']} دقيقة لكل بطاقة؛ "
            "توزيع المقياس الكلي يحتاج إلى رزنامة معتمدة"
        ),
        "حالة الاعتماد": (
            "مسودة للمراجعة؛ لا تعتبر اعتماداً رسمياً تلقائياً"
        ),
    }

    st.markdown(
        """
        <div class="note">
            الحقيبة الحالية تعتمد العناصر المستخرجة من المرجع.
            أي موارد أو معايير غير متوفرة موسومة كمقترحات
            ولا تُعرض على أنها نص رسمي.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader(
        "ملخص فحص الجودة"
    )

    st.table(
        pd.DataFrame(
            [
                {
                    "الفحص": k,
                    "النتيجة": v,
                }
                for k, v in quality.items()
            ]
        )
    )

    try:

        word = build_word_document(
            spec,
            comps,
            fiches,
            dossier,
            matrix,
            form,
            quality,
        )

        ppt = build_ppt(
            spec,
            comps,
            fiches,
            form,
        )

        c1, c2 = st.columns(2)

        c1.download_button(
            "تحميل الحقيبة Word",
            word,
            "SmartTeacherAssistant_APC.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

        c2.download_button(
            "تحميل العرض PowerPoint",
            ppt,
            "SmartTeacherAssistant_APC.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )

        client = st.session_state.get(
            "cloud_client"
        )

        if client:

            st.divider()

            st.subheader(
                "حفظ الحقيبة في حسابك السحابي"
            )

            project_title = st.text_input(
                "اسم الحقيبة",
                value=f"{label(spec)} — {form.get('module') or 'حقيبة APC'}",
            )

            if st.button(
                "حفظ الحقيبة لاسترجاعها من أجهزتي",
                use_container_width=True,
            ):

                try:

                    snapshot = {
                        "specialite": spec,
                        "form": form,
                        "competences": comps,
                        "mode": mode,
                    }

                    save_teacher_project(
                        client,
                        project_title,
                        snapshot,
                    )

                    st.success(
                        "تم حفظ الحقيبة في حسابك. يمكنك استرجاعها "
                        "من أي جهاز بعد تسجيل الدخول."
                    )

                except Exception as exc:

                    st.error(
                        f"تعذر حفظ الحقيبة: {exc}"
                    )

    except Exception as exc:

        st.error(
            f"حدث خطأ أثناء إنشاء الوثائق: {exc}"
        )


# ============================================================
# تشغيل التطبيق
# ============================================================

def main():

    if not cloud_access_gate():
        return

    render_header()

    render_sidebar()

    if (
        st.session_state.pop("show_admin_panel", False)
        and is_admin(st.session_state.get("cloud_user_id", ""))
    ):

        _render_admin_panel()

        if st.button(
            "العودة إلى التطبيق"
        ):

            st.rerun()

        return

    payload = st.session_state.get(
        "rnfc_payload"
    )

    tabs = st.tabs(
        [
            "1. التخصص",
            "2. المعلومات",
            "3. الكفاءات",
            "4. المصفوفة",
            "5. الحقيبة والتصدير",
        ]
    )

    with tabs[0]:
        page_selection(payload)

    with tabs[1]:
        page_information()

    with tabs[2]:
        page_competences()

    with tabs[3]:
        page_logigramme()

    with tabs[4]:
        page_package()


if __name__ == "__main__":
    main()
