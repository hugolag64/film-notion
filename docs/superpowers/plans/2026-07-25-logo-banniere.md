# Logo dans la bannière Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher le logo de la racine dans le coin supérieur gauche de la bannière Backstage.

**Architecture:** `main.py` exposera la racine du projet en lecture seule sous une URL statique dédiée. `frontend/ui.py` utilisera cette URL dans l'élément image du bandeau, à la place du libellé texte actuel. Les styles d'image resteront locaux à l'élément afin de conserver la hauteur de la barre.

**Tech Stack:** Python, NiceGUI, FastAPI, pytest.

## Global Constraints

- Utiliser le fichier existant `Logo.png` sans le déplacer ni le modifier.
- Conserver les liens de navigation et leur comportement.
- Limiter visuellement le logo à environ 42 px de haut en conservant ses proportions.

---

### Task 1: Exposer et afficher le logo de la bannière

**Files:**
- Modify: `main.py:24-34`
- Modify: `frontend/ui.py:77-78`
- Modify: `tests/test_theme.py:1-27`

**Interfaces:**
- Consumes: fichier racine `Logo.png`.
- Produces: URL HTTP `/static/Logo.png` consommée par `ui.image`.

- [ ] **Step 1: Write the failing test**

Ajouter dans `tests/test_theme.py` : `from pathlib import Path`, puis :

```python
def test_root_logo_is_available():
    assert (Path(__file__).resolve().parents[1] / "Logo.png").is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_theme.py::test_root_logo_is_available -v`

Expected: FAIL tant que le fichier logo n'est pas présent à la racine.

- [ ] **Step 3: Write minimal implementation**

Dans `main.py`, monter le répertoire projet sous `/static` avec `PROJECT_DIR = os.path.dirname(__file__)` puis `app.mount("/static", StaticFiles(directory=PROJECT_DIR), name="static")`. Dans `frontend/ui.py`, remplacer le libellé de marque par `ui.image("/static/Logo.png").style("height:42px; width:auto;")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_theme.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add main.py frontend/ui.py tests/test_theme.py` puis `git commit -m "feat: add logo to top banner"`.
