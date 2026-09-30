"""Shell-support subpackage: logic extracted from ``streamlit_app.py``.

These modules hold the (largely Streamlit-independent) helpers the app shell wires
together, so the logic is importable and unit-testable on its own. The shell keeps
only the thin ``st.session_state`` plumbing and the module-level script body.
"""
