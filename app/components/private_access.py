"""Private recordings/exports never enter Streamlit's public media storage."""

from datetime import datetime, timezone
import hashlib
import secrets

import streamlit as st

from backend import production


def begin_session(user):
    revision = user.get("_auth_revision", 0)  # Fresh registration begins at revision zero.
    production.verify_session_revision(user["id"], revision)
    st.session_state.user_id = user["id"]
    st.session_state.auth_revision = revision
    st.session_state.media_session_key = secrets.token_urlsafe(32)


def _session(user):
    if st.session_state.get("user_id") != user["id"]:
        raise PermissionError("Sign in before opening private data.")
    revision = st.session_state.get("auth_revision")
    production.verify_session_revision(user["id"], revision)
    if "media_session_key" not in st.session_state:
        st.session_state.media_session_key = secrets.token_urlsafe(32)
    return {"session_key": st.session_state.media_session_key, "expected_revision": revision}


def _fresh(grant):
    if not isinstance(grant, dict) or not grant.get("expires_at"):
        return False
    expires = datetime.fromisoformat(grant["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return (expires - datetime.now(timezone.utc)).total_seconds() > 15


def private_player(user, assessment, media):
    kwargs = _session(user)
    key = "private_player_" + media["id"]
    grant = st.session_state.get(key)
    if not _fresh(grant):
        grant = production.create_media_grant(user["id"], assessment["id"], media["id"], **kwargs)
        st.session_state[key] = grant
    if media["mime_type"].startswith("video/"):
        st.video(grant["url"])
    elif media["mime_type"].startswith("audio/"):
        st.audio(grant["url"])
    st.caption("Recording access expires after three minutes. Reload this page to renew it.")


def private_download(label, data, *, user, assessment_id, file_name, mime, key):
    """Issue exports only on explicit request, with current permission/revision."""
    grant_key = "private_download_" + key
    content = data.encode("utf-8") if isinstance(data, str) else data
    stamp = hashlib.sha256(content).hexdigest()
    grant = st.session_state.get(grant_key)
    if _fresh(grant) and grant.get("content_stamp") == stamp:
        # Recheck access before displaying a still-live link. Gateway also checks
        # independently, including a link copied before consent withdrawal.
        _session(user)
        st.link_button(label, grant["url"], width="stretch")
        st.caption("Private download link expires in three minutes. Keep downloaded health information secure.")
    else:
        if st.button(label, key=key, width="stretch"):
            grant = production.create_artifact_grant(user["id"], assessment_id, data, file_name, mime,
                                                     **_session(user))
            grant["content_stamp"] = stamp
            st.session_state[grant_key] = grant
            st.rerun()
        st.caption("Select once to prepare a private download, then open its temporary link.")
