TOKENS = {
    "--bg": "#faf6ef",
    "--surface": "#ffffff",
    "--border": "#ece4d6",
    "--text": "#2b2420",
    "--text-muted": "#8a8578",
    "--accent": "#7a2331",
    "--accent-gold": "#c9a35c",
    "--font-display": "Georgia,'Times New Roman',serif",
    "--font-body": "Arial,Helvetica,sans-serif",
    "--radius": "10px",
}


def build_theme_css() -> str:
    variables = "\n".join(f"  {name}: {value};" for name, value in TOKENS.items())
    return f"""<style>
:root {{
{variables}
}}
body {{ background-color: var(--bg); font-family: var(--font-body); color: var(--text); }}
.bs-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 2px 10px rgba(43, 36, 32, 0.05);
  transition: border-color 0.15s ease;
}}
.bs-card:hover {{ border-color: var(--accent); }}
.bs-title {{ font-family: var(--font-display); color: var(--text); font-weight: 700; }}
.q-btn.bs-accent-btn {{
  background: var(--accent) !important;
  color: var(--bg) !important;
  border-radius: 999px !important;
  font-family: var(--font-body);
}}
.q-btn.bs-outline-btn {{
  border: 1px solid var(--accent) !important;
  color: var(--accent) !important;
  border-radius: 999px !important;
  background: transparent !important;
  font-family: var(--font-body);
}}
.q-badge.bs-badge {{ background: var(--accent) !important; color: var(--bg) !important; }}
.bs-poster-placeholder {{
  background: linear-gradient(135deg, var(--border), var(--accent-gold));
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
}}
.bs-topbar {{ background: var(--text); color: var(--bg); }}
.bs-navlink {{ color: var(--bg) !important; opacity: 0.75; font-size: 0.85rem; }}
.bs-navlink.active {{ opacity: 1; border-bottom: 2px solid var(--accent-gold); }}
</style>
"""


def apply_theme() -> None:
    from nicegui import ui
    ui.add_head_html(build_theme_css())
