"""Single role-aware entry point; services enforce every data access as well."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from backend.db import init_db
from backend import services
from app import views
from app.components.design import brand_wordmark
from app.components.data_privacy import data_privacy_page, data_requests_page
from app.components.validation_review import validation_page
from app.components.clinic_pilot import clinic_pilot_page
from backend.production import verify_session_revision
from app.components.patient_navigation import navigation_label

st.set_page_config(page_title="ParkinSense-PK", page_icon=":material/accessibility_new:", layout="wide")


@st.cache_resource
def initialize():
    init_db()
    return True


try:
    initialize()
except Exception:
    st.title("ParkinSense-PK")
    st.error("The database is unavailable. Start the local PostgreSQL service using the README setup steps.")
    st.stop()

views.style()


def render(page):
    try:
        page.run()
    except (ValueError, PermissionError, LookupError) as exc:
        st.error(str(exc))
    except SQLAlchemyError:
        st.error("The database request could not be completed. Check the database connection and try again.")


actor = None
if st.session_state.get("user_id"):
    try:
        actor = services.get_user(st.session_state.user_id)
        verify_session_revision(actor["id"], st.session_state.get("auth_revision"))
        if not actor.get("active"):
            views.clear_session()
            st.rerun()
    except (ValueError, LookupError, PermissionError):
        views.clear_session()
        st.rerun()
    except SQLAlchemyError:
        st.error("The database is unavailable. Reconnect it before continuing.")
        st.stop()

def nav_title(label):
    return navigation_label(label, actor)


if actor is None:
    render(st.navigation([st.Page(views.auth_page, title=nav_title("Welcome"), default=True)]))
else:
    st.session_state.update(logged_in=True, role=actor["role"], active_patient_id=actor.get("patient_id"))
    with st.sidebar:
        brand_wordmark(compact=True)
        st.caption(f"{actor['full_name']} · {actor['role'].title()}")
        if st.button(nav_title("Log out"), width="stretch"):
            views.clear_session()
            st.rerun()
    role = actor["role"]
    if role == "patient":
        pages = {
            nav_title("My care"): [
                st.Page(views.patient_home, title=nav_title("Home"), default=True),
                st.Page(views.my_care_page, title=nav_title("My Care")),
                st.Page(views.assessment_hub, title=nav_title("Start Assessment")),
            ],
            nav_title("Movement"): [
                st.Page(views.motion_page, title=nav_title("3D Movement Studio")),
                st.Page(views.gait_page, title=nav_title("Walking / Gait")),
                st.Page(views.hand_page, title=nav_title("Hand / Finger")),
                st.Page(views.transfer_page, title=nav_title("Sit-to-Stand")),
                st.Page(views.reach_page, title=nav_title("Reach / Grasp")),
            ],
            nav_title("Voice and daily life"): [
                st.Page(views.voice_page, title=nav_title("Voice / Speech")),
                st.Page(views.adl_page, title=nav_title("ADL Questionnaire")),
            ],
            nav_title("My history"): [
                st.Page(views.results_page, title=nav_title("My Results")),
                st.Page(views.progress_page, title=nav_title("Progress")),
                st.Page(views.reports_page, title=nav_title("Reports")),
                st.Page(views.profile_page, title=nav_title("Profile")),
                st.Page(data_privacy_page, title=nav_title("Data & privacy")),
            ],
        }
    elif role == "clinician":
        pages = {"Care team": [
            st.Page(views.clinician_page, title=nav_title("Dashboard"), default=True),
            st.Page(views.care_plan_page, title=nav_title("Patient follow-up")),
            st.Page(clinic_pilot_page, title=nav_title("Clinic pilot")),
            st.Page(validation_page, title=nav_title("Measurement validation")),
            st.Page(views.motion_page, title=nav_title("3D Movement Studio")),
            st.Page(views.progress_page, title=nav_title("Trends")),
            st.Page(views.reports_page, title=nav_title("Reports")),
            st.Page(views.profile_page, title=nav_title("Profile")),
        ]}
    elif role == "admin":
        pages = {"Administration": [st.Page(views.admin_page, title=nav_title("Admin"), default=True),
                                    st.Page(data_requests_page, title=nav_title("Data requests"))]}
    else:
        views.clear_session()
        st.rerun()
    render(st.navigation(pages, expanded=True))
