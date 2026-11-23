# -*- coding: utf-8 -*-
"""Authentication, trial, licensing and teacher-project helpers for Smart Teacher Assistant."""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

Client = Any

def _create_client(url: str, key: str):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise CloudConfigurationError("مكتبة supabase غير مثبتة. نفذ تثبيت requirements.txt.") from exc
    return create_client(url, key)


class CloudConfigurationError(RuntimeError):
    pass


class CloudAccessError(RuntimeError):
    pass


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def cloud_configured() -> bool:
    return bool(_env("SUPABASE_URL") and _env("SUPABASE_ANON_KEY"))


def create_public_client() -> Client:
    url, key = _env("SUPABASE_URL"), _env("SUPABASE_ANON_KEY")
    if not url or not key:
        raise CloudConfigurationError(
            "إعدادات Supabase غير مكتملة. يلزم ضبط SUPABASE_URL وSUPABASE_ANON_KEY في متغيرات البيئة."
        )
    return _create_client(url, key)


def create_admin_client() -> Client:
    url, key = _env("SUPABASE_URL"), _env("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise CloudConfigurationError("لوحة المصمم تحتاج إلى SUPABASE_URL وSUPABASE_SERVICE_ROLE_KEY.")
    return _create_client(url, key)


def attach_user_token(client: Client, access_token: str) -> Client:
    if not access_token:
        raise CloudAccessError("انتهت جلسة الدخول. يرجى تسجيل الدخول مجدداً.")
    client.postgrest.auth(access_token)
    return client


def sha256_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def make_session_id() -> str:
    return str(uuid.uuid4())


def register_session(client: Client, session_id: str) -> Dict[str, Any]:
    response = client.rpc("register_teacher_session", {"p_session_id": session_id}).execute()
    data = response.data
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise CloudAccessError("تعذر التحقق من جلسة الحساب. تحقق من تطبيق مخطط قاعدة البيانات.")
    return data


def start_trial(client: Client) -> None:
    client.rpc("start_trial_if_needed").execute()


def get_access_status(client: Client) -> Dict[str, Any]:
    response = client.rpc("get_my_access_status").execute()
    data = response.data
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise CloudAccessError("تعذر قراءة حالة التجربة أو الترخيص.")
    return data


def redeem_license(client: Client, code: str) -> Dict[str, Any]:
    response = client.rpc("redeem_teacher_license", {"p_code_hash": sha256_code(code)}).execute()
    data = response.data
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise CloudAccessError("لم يتمكن الخادم من تأكيد الترخيص.")
    return data


def save_teacher_project(client: Client, title: str, payload: Dict[str, Any], project_id: Optional[str] = None):
    row = {"title": title.strip(), "payload": payload}
    if project_id:
        response = client.table("teacher_projects").update(row).eq("id", project_id).execute()
    else:
        response = client.table("teacher_projects").insert(row).execute()
    return response.data


def list_teacher_projects(client: Client):
    return client.table("teacher_projects").select("id,title,created_at,updated_at").order("updated_at", desc=True).execute().data or []


def load_teacher_project(client: Client, project_id: str):
    rows = client.table("teacher_projects").select("id,title,payload,created_at,updated_at").eq("id", project_id).limit(1).execute().data or []
    return rows[0] if rows else None


def is_admin(user_id: str) -> bool:
    try:
        admin = create_admin_client()
        rows = admin.table("app_admins").select("user_id").eq("user_id", user_id).limit(1).execute().data or []
        return bool(rows)
    except Exception:
        return False


def issue_license_code(admin: Client, user_id: str, duration_days: int, max_sessions: int, code_valid_days: int = 30) -> str:
    code = secrets.token_urlsafe(18).replace("-", "").replace("_", "").upper()[:24]
    admin.table("license_codes").insert({
        "code_hash": sha256_code(code),
        "assigned_user_id": user_id,
        "duration_days": int(duration_days),
        "max_sessions": int(max_sessions),
        "code_expires_at": (datetime.now(timezone.utc) + timedelta(days=int(code_valid_days))).isoformat(),
        "status": "available",
    }).execute()
    return "-".join(code[i:i+6] for i in range(0, len(code), 6))


def normalize_license_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().upper()
